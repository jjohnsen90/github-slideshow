"""Synthetic timecard data.

Everything in this module is generated. There are no real employees, no real
client accounts and no real punch records here, and nothing in this repository
reads from a production system. That is deliberate: timecard data is exactly the
sort of personal information that should never live in source control.

Generation is deterministic — the seed is derived from (employee id, date) — so
a given selection renders identically on every rerun and screenshots stay
stable.
"""

from __future__ import annotations

import random
import zlib
from datetime import date as Date
from datetime import datetime, time, timedelta

import pandas as pd

# --------------------------------------------------------------------------
# Reference dimensions
# --------------------------------------------------------------------------

FACILITIES = [
    {"code": "MEM01", "name": "Memphis DC 1"},
    {"code": "NSH02", "name": "Nashville DC 2"},
    {"code": "RIV03", "name": "Riverside DC 3"},
    {"code": "STA04", "name": "Statesville DC 4"},
]

DEPARTMENTS = ["Inbound", "Outbound", "Inventory Control", "Value-Added Services"]

SHIFTS = {
    "1st — 06:00 start": time(6, 0),
    "2nd — 14:30 start": time(14, 30),
    "3rd — 22:30 start": time(22, 30),
}

# Hue is assigned by account and the categorical scale is capped at three, so
# the demo universe holds three. A fourth would fold into a neutral "Other"
# rather than inventing a fourth hue — see theme.assign_slots.
ACCOUNTS = ["Northwind Foods", "Cascade Outdoor", "Lumen Home"]

# Activity is the secondary channel (pattern fill), cycled *within* an account,
# so it only ever has to disambiguate segments that already share a hue.
ACTIVITIES_BY_DEPARTMENT = {
    "Inbound": ["Receiving", "Putaway", "Unloading"],
    "Outbound": ["Picking", "Packing", "Loading"],
    "Inventory Control": ["Cycle Count", "Replenishment", "Audit"],
    "Value-Added Services": ["Kitting", "Labeling", "Repack"],
}

_FIRST = [
    "Alvina", "Bettis", "Corwin", "Delphia", "Everly", "Fenwick", "Greer",
    "Harlan", "Ivory", "Jessamy", "Kestrel", "Lorne", "Marlow", "Nyla",
    "Oberon", "Pryor", "Quillon", "Rosalind", "Sorrel", "Thaddeus", "Ulla",
    "Verity", "Winsome", "Yarrow",
]
_LAST = [
    "Ashcombe", "Braddock", "Colquitt", "Dunmore", "Ellsworth", "Fairweather",
    "Grimsby", "Hollowell", "Inglewood", "Jarrow", "Kesteven", "Lindquist",
    "Merriweather", "Northcott", "Ockham", "Pemberly", "Quarrier", "Ravensworth",
    "Stillwell", "Thorncroft", "Underhill", "Vanterpool", "Westbrook", "Yardley",
]

PAY_WORKED = "Worked"
PAY_BREAK = "Paid break"
PAY_LUNCH = "Unpaid lunch"

COVER_OK = "RF activity recorded"
COVER_GAP = "Paid, no RF scan"
COVER_UNPAID = "Unpaid lunch"
COVER_OFFCLOCK = "RF scan while off the clock"


def _seed(*parts) -> random.Random:
    key = "|".join(str(p) for p in parts).encode()
    return random.Random(zlib.crc32(key))


# --------------------------------------------------------------------------
# Roster
# --------------------------------------------------------------------------


def roster() -> pd.DataFrame:
    """The full synthetic roster across every facility.

    Stable across reruns — this is the hierarchy the facility / department /
    shift / employee filters drill through.
    """
    rows = []
    for facility in FACILITIES:
        rng = _seed("roster", facility["code"])
        for department in DEPARTMENTS:
            for n in range(rng.randint(3, 5)):
                first = rng.choice(_FIRST)
                last = rng.choice(_LAST)
                shift = rng.choice(list(SHIFTS))
                emp_no = 100000 + rng.randint(0, 899999)
                rows.append(
                    {
                        "employee_id": f"{facility['code']}-{emp_no}",
                        "employee": f"{last}, {first}",
                        "facility": facility["name"],
                        "facility_code": facility["code"],
                        "department": department,
                        "shift": shift,
                        "role": rng.choice(
                            ["Associate I", "Associate II", "Lead", "Trainer"]
                        ),
                    }
                )
    df = pd.DataFrame(rows).drop_duplicates(subset="employee_id")
    return df.sort_values(["facility", "department", "employee"]).reset_index(drop=True)


def _assignments(rng: random.Random, department: str) -> list[tuple[str, str]]:
    """The (account, activity) pairs one associate touches on one day.

    Capped so a shift stays legible: at most three accounts, and at most three
    activities inside any one account — the ceiling the pattern channel can
    carry without repeating a fill inside a hue.
    """
    pool = ACTIVITIES_BY_DEPARTMENT[department]
    accounts = rng.sample(ACCOUNTS, rng.choice([1, 2, 2, 3]))
    pairs: list[tuple[str, str]] = []
    for account in accounts:
        for activity in rng.sample(pool, rng.randint(1, min(3, len(pool)))):
            pairs.append((account, activity))
    rng.shuffle(pairs)
    return pairs


# --------------------------------------------------------------------------
# Dayforce punch detail
# --------------------------------------------------------------------------

# minutes, pay type — the shift skeleton before account/activity is layered on
_SHIFT_PLAN = [
    (135, PAY_WORKED),
    (15, PAY_BREAK),
    (120, PAY_WORKED),
    (30, PAY_LUNCH),
    (120, PAY_WORKED),
    (15, PAY_BREAK),
    (90, PAY_WORKED),
]


def dayforce_punches(employee: pd.Series, day: Date) -> pd.DataFrame:
    rng = _seed("dayforce", employee["employee_id"], day.isoformat())
    pairs = _assignments(rng, employee["department"])

    start_time = SHIFTS[employee["shift"]]
    cursor = datetime.combine(day, start_time) + timedelta(minutes=rng.randint(-7, 11))

    rows = []
    pair_idx = 0
    for minutes, pay_type in _SHIFT_PLAN:
        block_minutes = minutes + rng.randint(-8, 8) if pay_type == PAY_WORKED else minutes

        if pay_type != PAY_WORKED:
            rows.append(
                {
                    "start": cursor,
                    "end": cursor + timedelta(minutes=block_minutes),
                    "account": None,
                    "activity": pay_type,
                    "pay_type": pay_type,
                }
            )
            cursor += timedelta(minutes=block_minutes)
            continue

        # Split a worked block across one or two account/activity assignments.
        splits = 1 if block_minutes < 90 or rng.random() < 0.35 else 2
        remaining = block_minutes
        for s in range(splits):
            if s == splits - 1:
                seg = remaining
            else:
                seg = int(remaining * rng.uniform(0.38, 0.62))
            account, activity = pairs[pair_idx % len(pairs)]
            pair_idx += 1
            rows.append(
                {
                    "start": cursor,
                    "end": cursor + timedelta(minutes=seg),
                    "account": account,
                    "activity": activity,
                    "pay_type": PAY_WORKED,
                }
            )
            cursor += timedelta(minutes=seg)
            remaining -= seg

    df = pd.DataFrame(rows)
    df["minutes"] = (df["end"] - df["start"]).dt.total_seconds() / 60
    df["label"] = df["activity"]
    df["key"] = [
        f"{a} · {b}" if a else b for a, b in zip(df["account"], df["activity"])
    ]
    return df


# --------------------------------------------------------------------------
# Synapse RF gun labour activity
# --------------------------------------------------------------------------


def synapse_activity(employee: pd.Series, day: Date, punches: pd.DataFrame) -> pd.DataFrame:
    """RF-gun labour transactions, generated to *mostly* agree with Dayforce.

    The interesting part of the demo is where it disagrees: ramp-up gaps at the
    start of a block, dead time mid-block, an activity the associate is clocked
    into that differs from what Dayforce has them charged to, and the occasional
    scan during an unpaid lunch.
    """
    rng = _seed("synapse", employee["employee_id"], day.isoformat())
    pool = ACTIVITIES_BY_DEPARTMENT[employee["department"]]
    device = f"RF-{employee['facility_code']}-{rng.randint(1, 48):03d}"

    rows = []
    for _, punch in punches[punches["pay_type"] == PAY_WORKED].iterrows():
        cursor = punch["start"] + timedelta(minutes=rng.randint(0, 5))  # ramp-up
        block_end = punch["end"]

        while cursor < block_end:
            run = rng.randint(18, 52)
            seg_end = min(cursor + timedelta(minutes=run), block_end)
            if (seg_end - cursor).total_seconds() / 60 < 4:
                break

            # Usually charged to the same activity Dayforce has; sometimes not.
            if rng.random() < 0.84:
                activity = punch["activity"]
            else:
                activity = rng.choice([a for a in pool if a != punch["activity"]])

            minutes = (seg_end - cursor).total_seconds() / 60
            rows.append(
                {
                    "start": cursor,
                    "end": seg_end,
                    "account": punch["account"],
                    "activity": activity,
                    "units": int(minutes * rng.uniform(1.4, 6.2)),
                    "device": device,
                    "matched": activity == punch["activity"],
                    "pay_type": PAY_WORKED,
                }
            )
            cursor = seg_end + timedelta(minutes=rng.randint(1, 14))  # dead time

    # Occasional scan during unpaid lunch — the flag worth surfacing.
    lunches = punches[punches["pay_type"] == PAY_LUNCH]
    if len(lunches) and rng.random() < 0.3:
        lunch = lunches.iloc[0]
        offset = rng.randint(2, 10)
        start = lunch["start"] + timedelta(minutes=offset)
        end = min(start + timedelta(minutes=rng.randint(5, 14)), lunch["end"])
        account = punches.loc[punches["account"].notna(), "account"]
        rows.append(
            {
                "start": start,
                "end": end,
                "account": account.iloc[0] if len(account) else None,
                "activity": rng.choice(pool),
                "units": rng.randint(8, 60),
                "device": device,
                "matched": False,
                "pay_type": PAY_LUNCH,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "start", "end", "account", "activity", "units",
                "device", "matched", "pay_type", "minutes", "label", "key",
            ]
        )
    df = df.sort_values("start").reset_index(drop=True)
    df["minutes"] = (df["end"] - df["start"]).dt.total_seconds() / 60
    df["label"] = df["activity"]
    df["key"] = [
        f"{a} · {b}" if a else b for a, b in zip(df["account"], df["activity"])
    ]
    return df


# --------------------------------------------------------------------------
# Coverage — where the two systems agree and where they don't
# --------------------------------------------------------------------------


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    out = [list(i) for i in sorted(intervals)]
    merged = [out[0]]
    for start, end in out[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def _subtract(
    base: tuple[datetime, datetime], cuts: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    pieces = [base]
    for cut_start, cut_end in cuts:
        nxt = []
        for start, end in pieces:
            if cut_end <= start or cut_start >= end:
                nxt.append((start, end))
                continue
            if cut_start > start:
                nxt.append((start, cut_start))
            if cut_end < end:
                nxt.append((cut_end, end))
        pieces = nxt
    return [p for p in pieces if (p[1] - p[0]).total_seconds() > 30]


def coverage(
    punches: pd.DataFrame, rf: pd.DataFrame, tolerance_minutes: float = 2.0
) -> pd.DataFrame:
    """Reconcile the two lanes into a paid-time coverage strip.

    ``tolerance_minutes`` closes the ordinary dead time between one scan and the
    next — walking to the next aisle, waiting on a pallet. Without it the strip
    shatters into dozens of one-minute slivers that read as a problem when they
    are just how scan-to-scan latency looks.
    """
    pad = timedelta(minutes=tolerance_minutes / 2)
    raw = _merge([(r["start"], r["end"]) for _, r in rf.iterrows()])
    # The tolerance is a reading aid for worked time only. Off-the-clock scanning
    # is measured against the real transaction times — never widened.
    soft = _merge([(s - pad, e + pad) for s, e in raw])

    rows = []
    for _, punch in punches.iterrows():
        span = (punch["start"], punch["end"])

        if punch["pay_type"] == PAY_LUNCH:
            overlaps = [
                (max(span[0], s), min(span[1], e))
                for s, e in raw
                if s < span[1] and e > span[0]
            ]
            for s, e in overlaps:
                rows.append({"start": s, "end": e, "state": COVER_OFFCLOCK})
            for s, e in _subtract(span, overlaps):
                rows.append({"start": s, "end": e, "state": COVER_UNPAID})
            continue

        overlaps = [
            (max(span[0], s), min(span[1], e))
            for s, e in soft
            if s < span[1] and e > span[0]
        ]
        for s, e in overlaps:
            rows.append({"start": s, "end": e, "state": COVER_OK})
        for s, e in _subtract(span, overlaps):
            rows.append({"start": s, "end": e, "state": COVER_GAP})

    # Collapse neighbours that resolved to the same state, so the strip reads as
    # runs of a condition rather than as confetti.
    merged: list[dict] = []
    for row in sorted(rows, key=lambda r: r["start"]):
        if merged and merged[-1]["state"] == row["state"] and merged[-1]["end"] >= row["start"]:
            merged[-1]["end"] = max(merged[-1]["end"], row["end"])
        else:
            merged.append(dict(row))

    df = pd.DataFrame(merged)
    df["minutes"] = (df["end"] - df["start"]).dt.total_seconds() / 60
    df["label"] = df["state"]
    df["key"] = df["state"]
    return df.reset_index(drop=True)


def timecard(employee: pd.Series, day: Date):
    punches = dayforce_punches(employee, day)
    rf = synapse_activity(employee, day, punches)
    return punches, rf, coverage(punches, rf)
