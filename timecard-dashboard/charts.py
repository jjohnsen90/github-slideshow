"""The timecard figure.

Three lanes on one shared time axis, so the reader compares by looking straight
down rather than by remembering:

    Dayforce     what the associate was paid for, and what it was charged to
    Synapse RF   what the RF gun says they were actually clocked into
    Coverage     the reconciliation of the two

Encoding: **hue carries the account, fill pattern carries the activity.** Two
channels rather than one composite key, for two reasons. Colour first: in a
timeline any two segments can end up touching, so the palette has to clear the
all-pairs colour-vision gate rather than the easier adjacent-pairs one, and
three is the largest subset of the categorical ramp that does — nowhere near
enough for every account × activity combination. Legibility second: split
channels mean the legend is two short keys instead of one long list of
composites, and a reader learns "orange = Lumen Home" and "hatched = Receiving"
once instead of memorising nine compound swatches.

Every segment wide enough to hold one also carries a direct text label, and
every value in here is in the table view.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import demo_data as dd
from theme import STATUS, assign_slots, label_ink, plotly_layout, tokens

LANE_DAYFORCE = "Dayforce"
LANE_SYNAPSE = "Synapse RF"
LANE_COVERAGE = "Coverage"

# Solid, then the 45° pair. Restricted to these three: horizontal and vertical
# fills read as gridlines or bars, and "x"/"+" muddy at this size. Three is
# also all that is needed — an associate works one department, and a department
# has three activities.
PATTERN_SHAPES = ["", "/", "\\"]

COVERAGE_COLORS = {
    dd.COVER_OK: STATUS["good"],
    dd.COVER_GAP: STATUS["warning"],
    dd.COVER_OFFCLOCK: STATUS["critical"],
}

# Status colour never carries meaning alone — each state ships with an icon.
COVERAGE_ICONS = {
    dd.COVER_OK: "✓",
    dd.COVER_GAP: "▲",
    dd.COVER_OFFCLOCK: "✕",
    dd.COVER_UNPAID: "—",
}

GROUP_ACCOUNT = "account"
GROUP_ACTIVITY = "activity"
GROUP_TIME = "timetype"
GROUP_COVERAGE = "coverage"

# Plotly's own text fitting shrinks a label until it fits, which on a short
# segment produces two-pixel type; `uniformtext` is all-or-nothing across the
# whole figure. So fit is measured here and a label that will not fit is simply
# not drawn — the tooltip and the table view still carry the value.
LABEL_FONT_PX = 10
CHAR_PX = 5.9
LABEL_PADDING_PX = 18
# Conservative assumption for the responsive plot area. Under-estimating it
# only ever drops a borderline label; over-estimating would let one overflow.
ASSUMED_PLOT_PX = 1120


def _tone(hex_color: str, dark_mode: bool) -> str:
    """Tone-on-tone pattern foreground — a step of the fill's own colour.

    Blends away from the surface: darker on light, lighter on dark, so the
    hatching stays visible in both modes without introducing a second hue.
    """
    h = hex_color.lstrip("#")
    rgb = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    if dark_mode:
        out = [int(c + (255 - c) * 0.46) for c in rgb]
    else:
        out = [int(c * 0.60) for c in rgb]
    return "#" + "".join(f"{c:02x}" for c in out)


def account_colors(dark_mode: bool) -> dict[str, str]:
    """Stable account → hue map, computed from the whole account universe.

    Built from ``dd.ACCOUNTS`` rather than from whatever is on screen, so
    changing facility or employee never repaints an account.
    """
    return assign_slots(dd.ACCOUNTS, dark_mode)


def pattern_map(frames: list[pd.DataFrame]) -> dict[str, str]:
    """Assign a pattern per activity, consistently across every account.

    Global rather than per-account on purpose: if "/" meant Receiving under one
    hue and Putaway under another, the pattern channel would carry no meaning
    the reader could learn.
    """
    activities: list[str] = []
    for frame in frames:
        if frame.empty or "activity" not in frame:
            continue
        for account, activity in zip(frame["account"], frame["activity"]):
            if account is None or pd.isna(account):
                continue  # pay types are neutral-filled, never patterned
            if activity not in activities:
                activities.append(activity)
    return {
        activity: PATTERN_SHAPES[i % len(PATTERN_SHAPES)]
        for i, activity in enumerate(sorted(activities))
    }


def _label_fits(text: str, minutes: float, span_minutes: float) -> bool:
    if not text or span_minutes <= 0:
        return False
    segment_px = (minutes / span_minutes) * ASSUMED_PLOT_PX
    return segment_px >= len(text) * CHAR_PX + LABEL_PADDING_PX


def _fmt(ts) -> str:
    return pd.Timestamp(ts).strftime("%-I:%M %p")


def _duration(minutes: float) -> str:
    total = int(round(minutes))
    h, m = divmod(total, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _segment_style(row, t: dict, colors: dict, patterns: dict, lane: str):
    """Fill colour, pattern shape and grouping key for one segment."""
    if lane == LANE_COVERAGE:
        state = row["state"]
        return COVERAGE_COLORS.get(state, t["neutral_soft"]), "", state

    account = row.get("account")
    if account is None or pd.isna(account):
        # Structural, non-account time. Deliberately outside the categorical
        # ramp so unpaid time can never be mistaken for a client account.
        pay_type = row.get("pay_type")
        fill = t["neutral_soft"] if pay_type == dd.PAY_LUNCH else t["neutral"]
        return fill, "", pay_type

    return (
        colors.get(account, t["neutral_strong"]),
        patterns.get(row["activity"], ""),
        f"{account} · {row['activity']}",
    )


def _build_lane(
    frame: pd.DataFrame,
    lane: str,
    t: dict,
    colors: dict,
    patterns: dict,
    span_minutes: float,
) -> list[dict]:
    """Group a lane's segments into one trace-worth of bars per style."""
    if frame.empty:
        return []

    buckets: dict[str, dict] = {}
    last_labelled: str | None = None

    for _, row in frame.iterrows():
        fill, shape, key = _segment_style(row, t, colors, patterns, lane)
        bucket = buckets.setdefault(
            key,
            {"key": key, "lane": lane, "fill": fill, "shape": shape,
             "base": [], "width": [], "text": [], "custom": []},
        )
        # ISO strings rather than Timestamps: the static-export path serialises
        # the figure with orjson, which does not know pandas types.
        bucket["base"].append(pd.Timestamp(row["start"]).isoformat())
        bucket["width"].append((row["end"] - row["start"]).total_seconds() * 1000)

        # Label selectively. The coverage strip carries none — its legend is
        # icon + label, and its detail lives in the exceptions list and the
        # table — and a run of identical neighbours is labelled once.
        text = ""
        if lane != LANE_COVERAGE:
            candidate = str(row.get("label") or "")
            if candidate != last_labelled:
                if _label_fits(candidate, row["minutes"], span_minutes):
                    text = candidate
                    last_labelled = candidate
                else:
                    last_labelled = None
        bucket["text"].append(text)

        detail = ""
        if lane == LANE_SYNAPSE:
            detail = f"<br>{int(row['units'])} units · {row['device']}"
            if not row["matched"]:
                detail += "<br>⚠ Activity differs from Dayforce"
            if row.get("pay_type") == dd.PAY_LUNCH:
                detail += "<br>✕ Scanned during unpaid lunch"
        elif lane == LANE_DAYFORCE:
            detail = f"<br>{row.get('pay_type', '')}"

        bucket["custom"].append(
            [_fmt(row["start"]), _fmt(row["end"]), _duration(row["minutes"]), key, detail]
        )

    return list(buckets.values())


def _marker(fill: str, shape: str, t: dict, dark_mode: bool) -> dict:
    return dict(
        color=fill,
        # A 2px line in the *surface* colour is the surface gap: it separates
        # touching segments without adding contrasting ink around the mark.
        line=dict(color=t["surface"], width=2),
        pattern=dict(
            shape=shape,
            # "replace" — Plotly's default — treats marker.color as the pattern
            # foreground and leaves the background white, which strips the
            # account hue out of every hatched segment. Overlay keeps the hue
            # as the fill and draws the hatch tone-on-tone over it.
            fillmode="overlay",
            fgcolor=_tone(fill, dark_mode),
            size=6,
            solidity=0.42,
        ),
    )


def _emit(fig: go.Figure, bucket: dict, t: dict, dark_mode: bool) -> None:
    """Draw one style's bars. Data traces never appear in the legend — the
    legend is built separately from the two encoding channels."""
    fig.add_trace(
        go.Bar(
            name=bucket["key"],
            y=[bucket["lane"]] * len(bucket["base"]),
            x=bucket["width"],
            base=bucket["base"],
            orientation="h",
            width=0.34,  # keeps the painted bar at ~22px — never fills the band
            marker=_marker(bucket["fill"], bucket["shape"], t, dark_mode),
            text=bucket["text"],
            textposition="inside",
            insidetextanchor="middle",
            # Fit was decided above; forbid Plotly from shrinking type to make
            # something fit that shouldn't be drawn at all.
            constraintext="none",
            textfont=dict(color=label_ink(bucket["fill"]), size=LABEL_FONT_PX),
            cliponaxis=False,
            customdata=bucket["custom"],
            hovertemplate=(
                "<b>%{customdata[2]}</b><br>"
                "%{customdata[0]} – %{customdata[1]}<br>"
                "%{customdata[3]}"
                "%{customdata[4]}<extra></extra>"
            ),
            showlegend=False,
        )
    )


def _legend_entry(
    fig: go.Figure, label: str, fill: str, shape: str, t: dict,
    dark_mode: bool, group: str, title: str | None,
) -> None:
    """A swatch-only trace. Plots nothing; exists so the legend can key the two
    encoding channels separately instead of listing every composite."""
    fig.add_trace(
        go.Bar(
            name=label,
            x=[None],
            y=[None],
            orientation="h",
            marker=_marker(fill, shape, t, dark_mode),
            hoverinfo="skip",
            showlegend=True,
            legendgroup=group,
            legendgrouptitle_text=title,
        )
    )


def _build_legend(
    fig: go.Figure,
    punches: pd.DataFrame,
    rf: pd.DataFrame,
    cover: pd.DataFrame,
    t: dict,
    colors: dict,
    patterns: dict,
    dark_mode: bool,
) -> int:
    """Add the legend keys and report the tallest group, so the caller can
    reserve exactly enough height for it rather than clipping the last row."""
    present_accounts = [a for a in dd.ACCOUNTS if a in set(punches["account"].dropna())
                        | set(rf["account"].dropna() if not rf.empty else [])]
    present_activities = [a for a in patterns if a in set(punches["activity"])
                          | set(rf["activity"] if not rf.empty else [])]
    pay_types = [p for p in (dd.PAY_BREAK, dd.PAY_LUNCH) if p in set(punches["pay_type"])]
    states = [s for s in (dd.COVER_OK, dd.COVER_GAP, dd.COVER_OFFCLOCK, dd.COVER_UNPAID)
              if s in set(cover["state"])]

    for i, account in enumerate(present_accounts):
        _legend_entry(fig, account, colors[account], "", t, dark_mode,
                      GROUP_ACCOUNT, "Account" if i == 0 else None)

    for i, activity in enumerate(sorted(present_activities)):
        # Neutral fill so the swatch reads as "this pattern", not "this hue".
        swatch = t["neutral"] if dark_mode else t["neutral_strong"]
        _legend_entry(fig, activity, swatch, patterns[activity], t,
                      dark_mode, GROUP_ACTIVITY, "Activity" if i == 0 else None)

    for i, pay_type in enumerate(pay_types):
        fill = t["neutral_soft"] if pay_type == dd.PAY_LUNCH else t["neutral"]
        _legend_entry(fig, pay_type, fill, "", t, dark_mode,
                      GROUP_TIME, "Non-account time" if i == 0 else None)

    for i, state in enumerate(states):
        _legend_entry(fig, f"{COVERAGE_ICONS[state]} {state}",
                      COVERAGE_COLORS.get(state, t["neutral_soft"]), "", t, dark_mode,
                      GROUP_COVERAGE, "Paid-time coverage" if i == 0 else None)

    return max(
        len(present_accounts), len(present_activities), len(pay_types), len(states)
    )


def timecard_figure(
    punches: pd.DataFrame,
    rf: pd.DataFrame,
    cover: pd.DataFrame,
    dark_mode: bool,
) -> go.Figure:
    t = tokens(dark_mode)
    colors = account_colors(dark_mode)
    patterns = pattern_map([punches, rf])

    starts = list(punches["start"]) + list(rf["start"])
    ends = list(punches["end"]) + list(rf["end"])
    pad = pd.Timedelta(minutes=14)
    lo, hi = pd.Timestamp(min(starts)) - pad, pd.Timestamp(max(ends)) + pad
    span_minutes = (hi - lo).total_seconds() / 60

    fig = go.Figure()
    for frame, lane in ((punches, LANE_DAYFORCE), (rf, LANE_SYNAPSE), (cover, LANE_COVERAGE)):
        for bucket in _build_lane(frame, lane, t, colors, patterns, span_minutes):
            _emit(fig, bucket, t, dark_mode)

    legend_rows = _build_legend(fig, punches, rf, cover, t, colors, patterns, dark_mode)

    plot_px = 172               # three lanes of ~57px
    legend_px = 34 + legend_rows * 25
    axis_px = 40

    fig.update_layout(
        barmode="overlay",
        bargap=0.0,
        height=plot_px + axis_px + legend_px + 16,
        margin=dict(l=104, r=26, t=10, b=axis_px + legend_px),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-(axis_px / plot_px) - 0.08,
            x=0,
            font=dict(size=11.5, color=t["text_secondary"]),
            itemsizing="constant",
            itemclick=False,
            itemdoubleclick=False,
            tracegroupgap=22,
        ),
        xaxis=dict(
            type="date",
            range=[lo.isoformat(), hi.isoformat()],
            showgrid=True,
            gridcolor=t["grid"],
            gridwidth=1,
            griddash="solid",
            linecolor=t["axis"],
            tickformat="%-I:%M %p",
            dtick=3600000,
            tickfont=dict(size=11, color=t["text_muted"]),
            ticks="outside",
            ticklen=4,
            tickcolor=t["axis"],
        ),
        yaxis=dict(
            categoryorder="array",
            categoryarray=[LANE_COVERAGE, LANE_SYNAPSE, LANE_DAYFORCE],
            showgrid=False,
            zeroline=False,
            linecolor="rgba(0,0,0,0)",
            tickfont=dict(size=12.5, color=t["text_primary"]),
        ),
        **plotly_layout(dark_mode),
    )

    # Rounded data-ends where the installed Plotly supports it; harmless to skip.
    try:
        fig.update_traces(marker_cornerradius=3)
    except (ValueError, TypeError):
        pass

    return fig


def account_mix_figure(punches: pd.DataFrame, dark_mode: bool) -> go.Figure:
    """Worked minutes by account · activity — the magnitude view.

    A single stacked bar answers "how was the day split" without making the
    reader integrate segment widths off the timeline by eye. Same two encoding
    channels, so it needs no legend of its own.
    """
    t = tokens(dark_mode)
    colors = account_colors(dark_mode)
    worked = punches[punches["pay_type"] == dd.PAY_WORKED]
    patterns = pattern_map([worked])

    grouped = (
        worked.groupby(["account", "activity"], as_index=False)["minutes"]
        .sum()
        .sort_values("minutes", ascending=False)
    )
    total = grouped["minutes"].sum()

    fig = go.Figure()
    for _, row in grouped.iterrows():
        fill = colors.get(row["account"], t["neutral_strong"])
        hours = row["minutes"] / 60
        label = f"{hours:.1f}h" if _label_fits(f"{hours:.1f}h", row["minutes"], total) else ""
        # x is in hours so the axis reads in the same unit as every other figure
        fig.add_trace(
            go.Bar(
                name=f"{row['account']} · {row['activity']}",
                y=["Worked"],
                x=[hours],
                orientation="h",
                width=0.3,
                marker=_marker(fill, patterns.get(row["activity"], ""), t, dark_mode),
                text=[label],
                textposition="inside",
                insidetextanchor="middle",
                constraintext="none",
                textfont=dict(color=label_ink(fill), size=LABEL_FONT_PX),
                hovertemplate=(
                    f"<b>{hours:.2f} h</b><br>{row['account']} · {row['activity']}"
                    "<extra></extra>"
                ),
                showlegend=False,
            )
        )

    fig.update_layout(
        barmode="stack",
        height=104,
        margin=dict(l=74, r=26, t=8, b=32),
        xaxis=dict(
            showgrid=True,
            gridcolor=t["grid"],
            zeroline=False,
            tickfont=dict(size=11, color=t["text_muted"]),
            ticksuffix="h",
        ),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color=t["text_primary"])),
        **plotly_layout(dark_mode),
    )
    try:
        fig.update_traces(marker_cornerradius=3)
    except (ValueError, TypeError):
        pass
    return fig
