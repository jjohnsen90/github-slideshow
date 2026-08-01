"""Employee timecard — Dayforce vs Synapse RF labour reconciliation.

Runs as a Streamlit in Snowflake app. Data is synthetic (see demo_data.py);
no production system is queried and no real employee records are present.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import charts
import demo_data as dd
from theme import STATUS, page_css, tokens

st.set_page_config(
    page_title="Employee timecard",
    page_icon="🕐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "responsive": True,
}

ALL = "All"


# --------------------------------------------------------------------------
# Version-tolerant wrappers — Streamlit in Snowflake pins its own version, and
# the full-width keyword was renamed part-way through the 1.4x line.
# --------------------------------------------------------------------------


def full_width(fn, obj, **kwargs):
    try:
        return fn(obj, width="stretch", **kwargs)
    except Exception:
        return fn(obj, use_container_width=True, **kwargs)


def platform_dark() -> bool:
    """Whether the host — Streamlit's theme menu, or Snowflake's — is in dark.

    Following the platform keeps chart surfaces and widget chrome in agreement
    without styling Streamlit's own widgets, whose markup differs between the
    version here and the one Streamlit in Snowflake pins. Older hosts have no
    such API; those default to light, which is the validated default anyway.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


@st.cache_data(show_spinner=False)
def load_roster() -> pd.DataFrame:
    return dd.roster()


@st.cache_data(show_spinner=False)
def load_timecard(employee_id: str, day: date):
    people = load_roster()
    employee = people[people["employee_id"] == employee_id].iloc[0]
    punches, rf, cover = dd.timecard(employee, day)
    return employee, punches, rf, cover


# --------------------------------------------------------------------------
# Derived measures
# --------------------------------------------------------------------------


def measures(punches: pd.DataFrame, rf: pd.DataFrame, cover: pd.DataFrame) -> dict:
    worked = punches[punches["pay_type"] == dd.PAY_WORKED]["minutes"].sum()
    paid_break = punches[punches["pay_type"] == dd.PAY_BREAK]["minutes"].sum()
    unpaid = punches[punches["pay_type"] == dd.PAY_LUNCH]["minutes"].sum()

    covered = cover[cover["state"] == dd.COVER_OK]["minutes"].sum()
    gap = cover[cover["state"] == dd.COVER_GAP]["minutes"].sum()
    offclock = cover[cover["state"] == dd.COVER_OFFCLOCK]["minutes"].sum()

    on_clock_rf = rf[rf["pay_type"] == dd.PAY_WORKED]
    mismatch = on_clock_rf[~on_clock_rf["matched"]]["minutes"].sum()

    return {
        "paid_minutes": worked + paid_break,
        "worked_minutes": worked,
        "break_minutes": paid_break,
        "unpaid_minutes": unpaid,
        "covered_minutes": covered,
        "gap_minutes": gap,
        "offclock_minutes": offclock,
        "mismatch_minutes": mismatch,
        "coverage_pct": (covered / worked * 100) if worked else 0.0,
        "units": int(rf["units"].sum()) if not rf.empty else 0,
        "accounts": punches["account"].dropna().nunique(),
        "rf_segments": len(rf),
        "clock_in": punches["start"].min(),
        "clock_out": punches["end"].max(),
    }


def hours(minutes: float) -> str:
    return f"{minutes / 60:.2f}"


def hm(minutes: float) -> str:
    total = int(round(minutes))
    h, m = divmod(total, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def coverage_severity(pct: float) -> str:
    if pct >= 90:
        return STATUS["good"]
    if pct >= 78:
        return STATUS["warning"]
    return STATUS["critical"]


def exceptions(
    rf: pd.DataFrame, cover: pd.DataFrame, threshold: int = 12, limit: int = 6
) -> list[dict]:
    """The handful of things a supervisor would actually follow up on.

    Deliberately capped. An uncapped list of every scan gap is a wall nobody
    reads; the full record is one tab away in the coverage table.
    """
    out = []

    for _, row in cover[cover["state"] == dd.COVER_OFFCLOCK].iterrows():
        out.append(
            {
                "icon": "✕",
                "color": STATUS["critical"],
                "text": f"RF activity recorded during unpaid lunch — {hm(row['minutes'])}",
                "when": f"{row['start']:%-I:%M %p} – {row['end']:%-I:%M %p}",
                "sort": row["start"],
            }
        )

    gaps = cover[(cover["state"] == dd.COVER_GAP) & (cover["minutes"] >= threshold)]
    for _, row in gaps.sort_values("minutes", ascending=False).head(3).iterrows():
        out.append(
            {
                "icon": "▲",
                "color": STATUS["warning"],
                "text": f"Paid with no RF scan — {hm(row['minutes'])}",
                "when": f"{row['start']:%-I:%M %p} – {row['end']:%-I:%M %p}",
                "sort": row["start"],
            }
        )

    if not rf.empty:
        mismatched = rf[(~rf["matched"]) & (rf["pay_type"] == dd.PAY_WORKED)]
        for _, row in mismatched.sort_values("minutes", ascending=False).head(2).iterrows():
            out.append(
                {
                    "icon": "◆",
                    "color": STATUS["serious"],
                    "text": (
                        f"Clocked into {row['activity']} on the RF gun, "
                        f"charged elsewhere in Dayforce — {hm(row['minutes'])}"
                    ),
                    "when": f"{row['start']:%-I:%M %p} – {row['end']:%-I:%M %p}",
                    "sort": row["start"],
                }
            )

    return sorted(out, key=lambda r: r["sort"])[:limit]


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


def main() -> None:
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = platform_dark()

    people = load_roster()

    # --- filter row: one row, above everything it scopes -------------------
    f1, f2, f3, f4, f5, f6 = st.columns([1.5, 1.4, 1.2, 1.9, 1.1, 0.8])

    with f1:
        facility = st.selectbox("Facility", sorted(people["facility"].unique()))
    scoped = people[people["facility"] == facility]

    with f2:
        department = st.selectbox(
            "Department", [ALL] + sorted(scoped["department"].unique())
        )
    if department != ALL:
        scoped = scoped[scoped["department"] == department]

    with f3:
        shift = st.selectbox("Shift", [ALL] + sorted(scoped["shift"].unique()))
    if shift != ALL:
        scoped = scoped[scoped["shift"] == shift]

    with f4:
        if scoped.empty:
            st.selectbox("Employee", ["— no match —"], disabled=True)
            st.warning("No employees match that combination. Widen a filter.")
            return
        options = scoped["employee_id"].tolist()
        labels = dict(zip(scoped["employee_id"], scoped["employee"]))
        employee_id = st.selectbox(
            "Employee", options, format_func=lambda v: labels[v]
        )

    with f5:
        day = st.date_input("Date", value=date.today() - timedelta(days=1))

    with f6:
        st.session_state.dark_mode = st.toggle(
            "Dark",
            value=st.session_state.dark_mode,
            help=(
                "Follows the app theme by default. Toggle to override just the "
                "dashboard; both palettes are colour-vision validated."
            ),
        )

    dark = st.session_state.dark_mode
    t = tokens(dark)
    st.markdown(page_css(dark), unsafe_allow_html=True)

    employee, punches, rf, cover = load_timecard(employee_id, day)
    m = measures(punches, rf, cover)

    # --- header ------------------------------------------------------------
    st.markdown(
        f"<div class='tc-title'>{employee['employee']}</div>"
        f"<div class='tc-sub'>{employee['role']} · {employee['department']} · "
        f"{employee['shift']} · {employee['facility']} · "
        f"{day:%A, %B %-d, %Y} · ID {employee['employee_id']}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='tc-demo-banner'>⚠ Synthetic demo data — generated in-app. "
        "No real employee, punch or client records.</div>",
        unsafe_allow_html=True,
    )

    # --- figures: hero + tiles --------------------------------------------
    k1, k2, k3, k4 = st.columns([1.5, 1, 1, 1.4])

    with k1:
        st.markdown(
            "<div class='tc-card'>"
            "<div class='tc-tile-label'>Paid hours</div>"
            f"<div class='tc-hero-value'>{hours(m['paid_minutes'])}"
            "<span class='tc-hero-unit'> h</span></div>"
            f"<div class='tc-tile-delta' style='color:{t['text_secondary']}'>"
            f"{m['clock_in']:%-I:%M %p} – {m['clock_out']:%-I:%M %p} · "
            f"{hm(m['break_minutes'])} paid break · {hm(m['unpaid_minutes'])} unpaid"
            "</div></div>",
            unsafe_allow_html=True,
        )

    with k2:
        st.markdown(
            "<div class='tc-card'>"
            "<div class='tc-tile-label'>RF-scanned</div>"
            f"<div class='tc-tile-value'>{hours(m['covered_minutes'])} h</div>"
            f"<div class='tc-tile-delta' style='color:{t['text_secondary']}'>"
            f"{m['rf_segments']} transactions · {m['units']:,} units</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    with k3:
        gap_color = STATUS["warning"] if m["gap_minutes"] >= 30 else t["text_secondary"]
        st.markdown(
            "<div class='tc-card'>"
            "<div class='tc-tile-label'>Unaccounted</div>"
            f"<div class='tc-tile-value'>{hours(m['gap_minutes'])} h</div>"
            f"<div class='tc-tile-delta' style='color:{gap_color}'>"
            f"{'▲ ' if m['gap_minutes'] >= 30 else ''}"
            f"paid time with no RF scan</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    with k4:
        pct = m["coverage_pct"]
        fill = coverage_severity(pct)
        st.markdown(
            "<div class='tc-card'>"
            "<div class='tc-tile-label'>RF coverage of worked time</div>"
            f"<div class='tc-tile-value'>{pct:.0f}%</div>"
            f"<div class='tc-meter-track'><div class='tc-meter-fill' "
            f"style='width:{min(pct, 100):.1f}%;background:{fill}'></div></div>"
            f"<div class='tc-tile-delta' style='color:{t['text_secondary']}'>"
            f"{hm(m['covered_minutes'])} of {hm(m['worked_minutes'])} worked</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # --- the timecard itself ----------------------------------------------
    st.markdown(
        "<div class='tc-card-title'>Shift timeline</div>"
        "<div class='tc-card-note'>Hue is the client account; the fill pattern is the "
        "activity within that account. Hover any segment for the punch detail.</div>",
        unsafe_allow_html=True,
    )
    fig = charts.timecard_figure(punches, rf, cover, dark)
    full_width(st.plotly_chart, fig, config=PLOTLY_CONFIG)

    # --- exceptions + account mix -----------------------------------------
    c1, c2 = st.columns([1.25, 1])

    with c1:
        st.markdown("<div class='tc-card-title'>Exceptions</div>", unsafe_allow_html=True)
        flags = exceptions(rf, cover)
        if not flags:
            st.markdown(
                f"<div class='tc-flag'><span class='tc-flag-icon' "
                f"style='color:{STATUS['good']}'>✓</span>"
                "<span>Clean shift — RF activity accounts for all paid time.</span>"
                "</div>",
                unsafe_allow_html=True,
            )
        for flag in flags:
            st.markdown(
                f"<div class='tc-flag'>"
                f"<span class='tc-flag-icon' style='color:{flag['color']}'>{flag['icon']}</span>"
                f"<span style='flex:1'>{flag['text']}</span>"
                f"<span class='tc-flag-time'>{flag['when']}</span></div>",
                unsafe_allow_html=True,
            )

    with c2:
        st.markdown(
            "<div class='tc-card-title'>Worked time by account · activity</div>",
            unsafe_allow_html=True,
        )
        full_width(
            st.plotly_chart,
            charts.account_mix_figure(punches, dark),
            config=PLOTLY_CONFIG,
        )

        # Per-activity totals across both systems — the numbers the stacked bar
        # only encodes as width, spelled out so nothing depends on hovering.
        st.markdown(
            "<div class='tc-card-title' style='margin-top:.35rem'>By activity</div>",
            unsafe_allow_html=True,
        )
        worked = punches[punches["pay_type"] == dd.PAY_WORKED]
        paid_by_activity = worked.groupby("activity")["minutes"].sum()
        rf_by_activity = (
            rf.groupby("activity").agg(minutes=("minutes", "sum"), units=("units", "sum"))
            if not rf.empty
            else pd.DataFrame(columns=["minutes", "units"])
        )
        # Union, not just the Dayforce side: an activity the associate scanned
        # into but was never charged to is precisely the row worth seeing.
        activities = sorted(
            set(paid_by_activity.index) | set(rf_by_activity.index),
            key=lambda a: -(
                paid_by_activity.get(a, 0) + rf_by_activity["minutes"].get(a, 0)
            ),
        )
        for activity in activities:
            scanned = rf_by_activity["minutes"].get(activity, 0)
            units = int(rf_by_activity["units"].get(activity, 0))
            st.markdown(
                f"<div class='tc-flag'>"
                f"<span style='flex:1'>{activity}</span>"
                f"<span class='tc-flag-time'>{hours(paid_by_activity.get(activity, 0))} h paid · "
                f"{hours(scanned)} h scanned · {units:,} units</span></div>",
                unsafe_allow_html=True,
            )

    # --- table view: the relief for every value the charts only hover ------
    st.markdown("<div class='tc-card-title'>Detail</div>", unsafe_allow_html=True)
    tab_df, tab_rf, tab_cov = st.tabs(["Dayforce punches", "Synapse RF activity", "Coverage"])

    with tab_df:
        table = punches.assign(
            Start=punches["start"].dt.strftime("%-I:%M %p"),
            End=punches["end"].dt.strftime("%-I:%M %p"),
            Hours=(punches["minutes"] / 60).round(2),
        )[["Start", "End", "Hours", "account", "activity", "pay_type"]].rename(
            columns={"account": "Account", "activity": "Activity", "pay_type": "Pay type"}
        )
        full_width(st.dataframe, table, hide_index=True)

    with tab_rf:
        if rf.empty:
            st.info("No RF transactions recorded for this shift.")
        else:
            table = rf.assign(
                Start=rf["start"].dt.strftime("%-I:%M %p"),
                End=rf["end"].dt.strftime("%-I:%M %p"),
                Hours=(rf["minutes"] / 60).round(2),
                Matches=rf["matched"].map({True: "Yes", False: "No"}),
            )[
                ["Start", "End", "Hours", "account", "activity", "units", "device", "Matches"]
            ].rename(
                columns={
                    "account": "Account",
                    "activity": "Activity",
                    "units": "Units",
                    "device": "Device",
                    "Matches": "Matches Dayforce",
                }
            )
            full_width(st.dataframe, table, hide_index=True)

    with tab_cov:
        table = cover.assign(
            Start=cover["start"].dt.strftime("%-I:%M %p"),
            End=cover["end"].dt.strftime("%-I:%M %p"),
            Minutes=cover["minutes"].round(1),
        )[["Start", "End", "Minutes", "state"]].rename(columns={"state": "State"})
        full_width(st.dataframe, table, hide_index=True)

    export = pd.concat(
        [
            punches.assign(source="Dayforce"),
            rf.assign(source="Synapse RF"),
        ],
        ignore_index=True,
    )
    st.download_button(
        "Download this timecard (CSV)",
        export.to_csv(index=False).encode("utf-8"),
        file_name=f"timecard_{employee_id}_{day:%Y%m%d}.csv",
        mime="text/csv",
    )


main()
