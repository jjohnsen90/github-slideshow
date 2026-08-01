"""Design tokens, palette assignment and page chrome.

The categorical slots below are a validated set: run
``node validate_palette.js "<hex,...>" --mode light|dark`` from the dataviz
reference and both modes clear the lightness band, chroma floor, adjacent-pair
CVD separation and the normal-vision floor. Light mode raises the expected
sub-3:1 contrast warning on the aqua / yellow / magenta slots, which is why
every segment carries a direct label and the app always ships a table view.

Do not reorder the slots. The ordering *is* the colour-blind safety mechanism —
adjacent pairs were the thing that got validated.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

LIGHT = {
    "surface": "#fcfcfb",
    "plane": "#f9f9f7",
    "text_primary": "#0b0b0b",
    "text_secondary": "#52514e",
    "text_muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "border": "rgba(11,11,11,0.10)",
    "series": [
        "#2a78d6",  # blue
        "#eb6834",  # orange
        "#1baf7a",  # aqua
        "#eda100",  # yellow
        "#e87ba4",  # magenta
        "#008300",  # green
        "#4a3aa7",  # violet
        "#e34948",  # red
    ],
    # Non-productive / structural time. Deliberately outside the categorical
    # ramp so unpaid time can never be mistaken for an account.
    "neutral_strong": "#898781",
    "neutral": "#c3c2b7",
    "neutral_soft": "#e1e0d9",
}

DARK = {
    "surface": "#1a1a19",
    "plane": "#0d0d0d",
    "text_primary": "#ffffff",
    "text_secondary": "#c3c2b7",
    "text_muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "border": "rgba(255,255,255,0.10)",
    "series": [
        "#3987e5",
        "#d95926",
        "#199e70",
        "#c98500",
        "#d55181",
        "#008300",
        "#9085e9",
        "#e66767",
    ],
    "neutral_strong": "#a3a199",
    # Separated enough to tell paid break from unpaid lunch on the dark
    # surface — the ramp's own steps collapse into the background here.
    "neutral": "#6e6d66",
    "neutral_soft": "#4a4943",
}

# Status palette is fixed and never themed. Reserved — never reused as a series.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

FONT_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

OTHER_LABEL = "Other"


def tokens(dark_mode: bool) -> dict:
    return DARK if dark_mode else LIGHT


# --------------------------------------------------------------------------
# Colour assignment
# --------------------------------------------------------------------------


def assign_slots(keys: list[str], dark_mode: bool) -> dict[str, str]:
    """Map a stable, filter-invariant key universe onto the categorical slots.

    ``keys`` must be the *whole* universe of possible keys, not the keys present
    in the current filter selection. Colour follows the entity: changing the
    facility or the employee must never repaint the categories that survive.

    Beyond eight keys the tail folds into a single neutral "Other" rather than
    generating a ninth hue.
    """
    t = tokens(dark_mode)
    ordered = sorted(set(keys))
    mapping: dict[str, str] = {}
    for i, key in enumerate(ordered):
        mapping[key] = t["series"][i] if i < len(t["series"]) else t["neutral_strong"]
    mapping[OTHER_LABEL] = t["neutral_strong"]
    return mapping


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def label_ink(fill_hex: str) -> str:
    """Pick white or near-black for a label set *inside* a coloured fill.

    The one place text is allowed to sit on a data colour — so it has to clear
    contrast against that fill rather than against the surface.
    """
    return "#ffffff" if relative_luminance(fill_hex) < 0.42 else "#0b0b0b"


# --------------------------------------------------------------------------
# Page chrome
# --------------------------------------------------------------------------


def page_css(dark_mode: bool) -> str:
    t = tokens(dark_mode)
    return f"""
<style>
  .stApp {{
      background: {t["plane"]};
      color: {t["text_primary"]};
      font-family: {FONT_STACK};
  }}
  /* Clears the Streamlit toolbar, which floats over the top-right corner and
     otherwise clips the labels of the right-hand filters. */
  .block-container {{ padding-top: 3.6rem; padding-bottom: 3rem; max-width: 1500px; }}

  .tc-title {{
      font-size: 1.55rem; font-weight: 650; letter-spacing: -0.015em;
      color: {t["text_primary"]}; margin: 0 0 .15rem 0;
  }}
  .tc-sub {{ font-size: .875rem; color: {t["text_secondary"]}; margin: 0 0 1.1rem 0; }}

  .tc-card {{
      background: {t["surface"]};
      border: 1px solid {t["border"]};
      border-radius: 14px;
      padding: 1.05rem 1.2rem 1.15rem 1.2rem;
      margin-bottom: 1rem;
  }}
  .tc-card-title {{
      font-size: .78rem; font-weight: 620; text-transform: uppercase;
      letter-spacing: .07em; color: {t["text_muted"]}; margin: 0 0 .1rem 0;
  }}
  .tc-card-note {{ font-size: .82rem; color: {t["text_secondary"]}; margin: 0 0 .85rem 0; }}

  /* Hero figure — exactly one per view. Proportional figures, not tabular. */
  .tc-hero-value {{
      font-size: 3.05rem; font-weight: 640; line-height: 1;
      letter-spacing: -0.03em; color: {t["text_primary"]};
  }}
  .tc-hero-unit {{ font-size: 1.15rem; font-weight: 500; color: {t["text_secondary"]}; }}

  .tc-tile-label {{
      font-size: .76rem; font-weight: 600; text-transform: uppercase;
      letter-spacing: .06em; color: {t["text_muted"]}; margin-bottom: .3rem;
  }}
  .tc-tile-value {{
      font-size: 1.6rem; font-weight: 620; line-height: 1.1;
      letter-spacing: -0.02em; color: {t["text_primary"]};
  }}
  .tc-tile-delta {{ font-size: .8rem; font-weight: 550; margin-top: .2rem; }}

  /* Meter — fill carries severity, track is a lighter step of the same ramp. */
  .tc-meter-track {{
      height: 9px; border-radius: 999px; background: {t["neutral_soft"]};
      overflow: hidden; margin-top: .55rem;
  }}
  .tc-meter-fill {{ height: 100%; border-radius: 999px; }}

  .tc-flag {{
      display: flex; gap: .6rem; align-items: flex-start;
      padding: .6rem .75rem; border-radius: 9px; margin-bottom: .45rem;
      background: {t["plane"]}; border: 1px solid {t["border"]};
      font-size: .855rem; color: {t["text_primary"]};
  }}
  .tc-flag-icon {{ font-size: .95rem; line-height: 1.35; flex: 0 0 auto; }}
  .tc-flag-time {{
      color: {t["text_muted"]}; font-variant-numeric: tabular-nums;
      font-size: .8rem; white-space: nowrap;
  }}

  .tc-demo-banner {{
      display: inline-flex; align-items: center; gap: .45rem;
      background: {t["surface"]}; border: 1px solid {t["border"]};
      border-left: 3px solid {STATUS["warning"]};
      border-radius: 8px; padding: .45rem .7rem; margin-bottom: 1.1rem;
      font-size: .82rem; color: {t["text_secondary"]};
  }}

  div[data-testid="stMetricValue"] {{ color: {t["text_primary"]}; }}
  label, .stRadio label, .stSelectbox label {{ color: {t["text_secondary"]} !important; }}

  /* Widget chrome only needs overriding when the reader has used the in-app
     toggle to diverge from Streamlit's own theme; when the two agree,
     Streamlit has already styled these correctly. Both markups are targeted on
     purpose — Streamlit moved widgets from BaseWeb to React Aria mid-1.5x, and
     Streamlit in Snowflake pins its own version, so which one is live depends
     on the host. Emotion class hashes are never targeted: they change between
     releases. Anything that misses degrades to Streamlit's default styling. */
  div[data-baseweb="select"] > div,
  div[data-baseweb="input"],
  div[data-baseweb="base-input"],
  div[data-testid="stSelectbox"] div[role="group"],
  div[data-testid="stDateInput"] div[role="group"] {{
      background-color: {t["surface"]} !important;
      border-color: {t["border"]} !important;
      color: {t["text_primary"]} !important;
  }}
  div[data-testid="stSelectbox"] svg, div[data-baseweb="select"] svg {{
      fill: {t["text_secondary"]} !important;
  }}
  div[data-baseweb="select"] div,
  div[data-baseweb="base-input"] input,
  div[data-testid="stSelectbox"] input,
  div[data-testid="stDateInput"] input {{
      color: {t["text_primary"]} !important;
      -webkit-text-fill-color: {t["text_primary"]} !important;
  }}
  div[data-baseweb="popover"] ul, div[data-baseweb="menu"],
  .react-aria-Popover, .react-aria-ListBox {{
      background-color: {t["surface"]} !important;
  }}
  div[data-baseweb="popover"] li, .react-aria-ListBoxItem {{
      color: {t["text_primary"]} !important;
  }}

  .stTabs [data-baseweb="tab-list"] {{ border-bottom-color: {t["border"]}; }}
  .stTabs [data-baseweb="tab"] {{ color: {t["text_secondary"]}; }}
  .stTabs [aria-selected="true"] {{ color: {t["text_primary"]}; }}
  .stDownloadButton button {{
      background: {t["surface"]}; color: {t["text_primary"]};
      border: 1px solid {t["border"]};
  }}
</style>
"""


def plotly_layout(dark_mode: bool) -> dict:
    t = tokens(dark_mode)
    return dict(
        paper_bgcolor=t["surface"],
        plot_bgcolor=t["surface"],
        font=dict(family=FONT_STACK, size=12, color=t["text_secondary"]),
        hoverlabel=dict(
            bgcolor=t["surface"],
            bordercolor=t["border"],
            font=dict(family=FONT_STACK, size=12, color=t["text_primary"]),
            align="left",
        ),
    )
