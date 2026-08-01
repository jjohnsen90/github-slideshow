# Employee timecard — Dayforce vs Synapse RF

A Streamlit in Snowflake app that puts an associate's paid time and their RF-gun
labour activity on one shared time axis, and reconciles the two.

**All data in this app is synthetic and generated in-process.** There are no real
employees, punch records or client accounts anywhere in this repository, and the
app does not query a production system. Wiring it to real data is a deliberate,
separate step — see [Connecting real data](#connecting-real-data).

---

## What it shows

Three lanes, one time axis:

| Lane | Reads |
|---|---|
| **Dayforce** | What the associate was paid for, and which account · activity it was charged to |
| **Synapse RF** | What the RF gun says they were actually clocked into |
| **Coverage** | The reconciliation — scanned, paid-but-unscanned, unpaid, scanned-while-off-the-clock |

Above the lanes: paid hours, RF-scanned hours, unaccounted hours, and RF coverage
of worked time. Below: the exceptions a supervisor would follow up on, worked time
by account · activity, and a table view of every underlying record.

Filters scope everything below them — facility → department → shift → employee →
date.

## Encoding

**Hue carries the account. Fill pattern carries the activity.**

Two channels rather than one composite `Account · Activity` colour, for two
reasons:

1. **Colour vision.** In a timeline any two segments can end up touching, so the
   palette has to clear the *all-pairs* separation gate, not the easier
   adjacent-pairs one. Three hues is the largest subset of the categorical ramp
   that does — nowhere near enough for every account × activity combination.
   Both the light and dark palettes were validated with a CVD checker before
   being adopted; the light set trips the expected sub-3:1 contrast warning on
   its lighter slots, which is why every segment carries a direct label and the
   app always ships a table view.
2. **Legibility.** The legend becomes two short keys instead of one long list of
   compound swatches. A reader learns "orange = Lumen Home" and "hatched =
   Receiving" once.

Beyond three accounts the palette folds the tail into a neutral "Other" rather
than inventing a fourth hue. Status colours (coverage states) are reserved, never
reused as a series, and always ship with an icon and a label so they never depend
on colour alone.

Other deliberate choices worth knowing before you change them:

- Account → hue is computed from the whole account universe, not from what is on
  screen, so changing the filter never repaints a surviving account.
- Direct-label fit is measured in Python, not left to Plotly. Plotly shrinks a
  label until it fits, which produces two-pixel type on short segments, and its
  `uniformtext` setting is all-or-nothing across a figure. A label that will not
  fit is simply not drawn; the tooltip and the table still carry the value.
- Marker pattern uses `fillmode="overlay"`. Plotly's default, `"replace"`, treats
  `marker.color` as the pattern *foreground* and leaves the background white,
  which strips the account hue out of every hatched segment.
- Coverage folds sub-3-minute scan gaps into covered time. Without that the strip
  shatters into one-minute slivers that read as a problem when they are just
  scan-to-scan latency. The tolerance applies to worked time only — off-the-clock
  scanning is measured against real transaction times.

## Layout

```
streamlit_app.py    entry point: filters, figures, exceptions, table view
charts.py           the Plotly timeline and the account-mix bar
demo_data.py        synthetic roster, punches, RF activity, coverage reconciliation
theme.py            palette, tokens, page CSS
environment.yml     Snowflake Anaconda dependencies
```

## Running locally

```bash
pip install streamlit pandas plotly
streamlit run streamlit_app.py
```

## Deploying to Streamlit in Snowflake

Via Snowsight — Projects → Streamlit → **+ Streamlit App**, then paste
`streamlit_app.py` and add `charts.py`, `demo_data.py` and `theme.py` as
additional files, and put the `environment.yml` contents in the Packages panel.

Via SQL, from a stage:

```sql
CREATE STAGE IF NOT EXISTS timecard_stage;
-- PUT streamlit_app.py, charts.py, demo_data.py, theme.py, environment.yml
--     onto @timecard_stage (SnowSQL, or the Snowsight stage UI)

CREATE OR REPLACE STREAMLIT timecard_dashboard
  ROOT_LOCATION = '@<db>.<schema>.timecard_stage'
  MAIN_FILE     = 'streamlit_app.py'
  QUERY_WAREHOUSE = <warehouse>;

GRANT USAGE ON STREAMLIT timecard_dashboard TO ROLE <role>;
```

All four `.py` files must sit at the stage root — the app imports them as
top-level modules.

### Environment notes

- The app uses no custom bidirectional Streamlit components; SiS does not support
  them.
- Full-width chart and dataframe calls are wrapped, because the keyword was
  renamed part-way through the 1.4x line and SiS pins its own Streamlit version.
- Theme follows the host (`st.context.theme`) where that API exists, with an
  in-app toggle as an override. On older hosts it defaults to light.
- `marker_cornerradius` is applied inside a `try` — older Plotly builds skip it
  harmlessly.

## Connecting real data

`demo_data.py` is the only module that produces data. Every other module consumes
plain DataFrames, so replacing it is a contained change. Swap these three
functions for queries against your own tables:

| Function | Must return, per row |
|---|---|
| `roster()` | `employee_id, employee, facility, facility_code, department, shift, role` |
| `dayforce_punches(employee, day)` | `start, end, minutes, account, activity, pay_type, label, key` |
| `synapse_activity(employee, day, punches)` | `start, end, minutes, account, activity, units, device, matched, pay_type, label, key` |

`coverage()` is pure interval arithmetic over those two frames and needs no
changes. In SiS, get a session with
`from snowflake.snowpark.context import get_active_session`.

Two things to settle before that happens, because they are governance questions
rather than engineering ones:

- **Access.** A timecard reconciliation view is performance-adjacent personal
  data. It should be scoped by Snowflake role so a supervisor sees their own
  facility, not the whole network.
- **Interpretation.** "Unaccounted time" is *paid time with no RF scan*. That is
  not idle time and it is not time theft — meetings, training, cleanup, equipment
  faults, jams and paper work all land in it legitimately. Treating the coverage
  percentage as a productivity score would be a misreading of what the number
  measures. It is useful for finding process gaps and mis-charged accounts; it is
  not a performance rating.
