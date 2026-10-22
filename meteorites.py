"""Load, clean and summarise NASA's Meteorite Landings dataset.

The dataset is published by NASA on data.nasa.gov and comes from The
Meteoritical Society's Meteoritical Bulletin Database. One row = one known
meteorite (45,716 rows).

Everything else in this repo (the notebook, the static figures, the
interactive map and the numbers in the README) is built from the functions
in this module, so the cleaning rules live in exactly one place.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_CSV = ROOT / "data" / "Meteorite_Landings.csv"

SOURCE_PAGE = "https://data.nasa.gov/dataset/meteorite-landings"
SOURCE_CSV = "https://data.nasa.gov/docs/legacy/meteorite_landings/Meteorite_Landings.csv"

# Years outside this window are data-entry errors (e.g. one record says 2101).
# 860 keeps Nogata (Japan), the oldest witnessed fall in the database; the
# catalogue snapshot was compiled in 2013.
MIN_YEAR, MAX_YEAR = 800, 2016

ANTARCTICA_LAT = -60.0  # everything south of 60 S is Antarctica


def download(dest: Path = RAW_CSV, url: str = SOURCE_CSV) -> Path:
    """Download the raw CSV from data.nasa.gov."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "meteorites-landing"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


def load_raw(path: Path = RAW_CSV) -> pd.DataFrame:
    """Read the CSV exactly as NASA publishes it, with tidy column names."""
    df = pd.read_csv(path)
    return df.rename(columns={"mass (g)": "mass", "mass": "mass"})


# --- classification -------------------------------------------------------
# The database uses ~460 fine-grained class codes ("L6", "CM2", "Iron, IIIAB",
# "Eucrite-mmict", ...). For filtering and summaries they are folded into a
# handful of broad, standard groups.

GROUPS = [
    "Ordinary chondrite",
    "Carbonaceous chondrite",
    "Other chondrite",
    "Achondrite",
    "Lunar / Martian",
    "Iron",
    "Stony-iron",
    "Unclassified",
]

_ORDINARY = re.compile(r"^(H|L|LL|H/L|L/LL|OC)(?![a-z])")
_CARBONACEOUS = re.compile(r"^C(I|M|V|O|K|R|H|B)?(a|b)?([\d\-/.~ ]|$)")
_ENSTATITE = re.compile(r"^E(H|L)?[\d\-]|^E(H|L)?$")
_OTHER_CHONDRITE = re.compile(r"^(R|K)[\d\-]|^(R|K)$|^Chondrite")
_ACHONDRITE = re.compile(
    r"^(Eucrite|Howardite|Diogenite|Ureilite|Aubrite|Angrite|Acapulcoite|"
    r"Lodranite|Winonaite|Brachinite|Achondrite|Enst achon)"
)


def class_group(recclass: str) -> str:
    c = str(recclass).strip()
    if c.startswith(("Lunar", "Martian")):
        return "Lunar / Martian"
    if c.startswith("Iron"):
        return "Iron"
    if c.startswith(("Pallasite", "Mesosiderite")):
        return "Stony-iron"
    if _ACHONDRITE.match(c):
        return "Achondrite"
    if _ORDINARY.match(c):
        return "Ordinary chondrite"
    if _ENSTATITE.match(c) or _OTHER_CHONDRITE.match(c):
        return "Other chondrite"
    if _CARBONACEOUS.match(c):
        return "Carbonaceous chondrite"
    return "Unclassified"


# --- cleaning ---------------------------------------------------------------


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns and flag what can be placed on a map.

    Rules (same spirit as the original notebook):
    * coordinates must exist and must not be the (0, 0) placeholder;
    * longitude must be within [-180, 180] (the one exception is
      "Meridiani Planum", which was found on Mars by NASA's Opportunity rover);
    * 223 Yamato records with a zero latitude are treated as unlocated;
    * years outside [MIN_YEAR, MAX_YEAR] are treated as unknown, not dropped.
    """
    df = raw.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df.loc[(df["year"] < MIN_YEAR) | (df["year"] > MAX_YEAR), "year"] = np.nan
    df["group"] = df["recclass"].map(class_group)
    has_coords = df["reclat"].notna() & df["reclong"].notna()
    not_null_island = ~((df["reclat"] == 0) & (df["reclong"] == 0))
    on_earth = df["reclong"].between(-180, 180) & df["reclat"].between(-90, 90)
    # 223 "Yamato" finds (an Antarctic field at 71.5 S) carry latitude 0, which
    # would put them on the equator in Kenya. Treat them as unlocated.
    bad_yamato = (df["reclat"] == 0) & df["name"].str.startswith("Yamato")
    df["mappable"] = has_coords & not_null_island & on_earth & ~bad_yamato
    df["antarctica"] = df["mappable"] & (df["reclat"] < ANTARCTICA_LAT)
    df["decade"] = (df["year"] // 10 * 10).astype("Int64")
    return df


def load(path: Path = RAW_CSV) -> pd.DataFrame:
    """Raw CSV -> cleaned frame (all rows, with a `mappable` flag)."""
    return clean(load_raw(path))


# --- insights ---------------------------------------------------------------


def insights(df: pd.DataFrame) -> dict:
    """Headline numbers, all computed from the dataset."""
    found = df["fall"] == "Found"
    fell = df["fall"] == "Fell"
    m = df[df["mappable"]]

    heaviest = (
        df.dropna(subset=["mass"])
        .sort_values("mass", ascending=False)
        .head(10)[["name", "id", "recclass", "group", "mass", "fall", "year", "reclat", "reclong"]]
    )

    groups = (
        df.groupby("group")
        .agg(count=("id", "size"), mass_kg=("mass", lambda s: s.sum() / 1000))
        .reindex(GROUPS)
        .fillna(0)
    )
    groups["count_share"] = groups["count"] / groups["count"].sum()
    groups["mass_share"] = groups["mass_kg"] / groups["mass_kg"].sum()

    kind = pd.Series(
        np.select(
            [fell, df["antarctica"]],
            ["Witnessed fall", "Found in Antarctica"],
            "Found elsewhere or unlocated",
        ),
        index=df.index,
    )
    since_1800 = df["year"] >= 1800
    by_decade = (
        pd.crosstab(df.loc[since_1800, "decade"], kind[since_1800])
        .reindex(
            columns=["Found in Antarctica", "Found elsewhere or unlocated", "Witnessed fall"],
            fill_value=0,
        )
    )

    witnessed = df[fell & df["year"].notna()].sort_values("year")

    stacks = m.groupby(["reclat", "reclong"]).agg(n=("id", "size"), name=("name", "first"))
    stacks = stacks.sort_values("n", ascending=False)
    top_stack = stacks.iloc[0]

    return {
        "records": len(df),
        "mappable": int(df["mappable"].sum()),
        "no_coords": int((df["reclat"].isna() | df["reclong"].isna()).sum()),
        "null_island": int(((df["reclat"] == 0) & (df["reclong"] == 0)).sum()),
        "found": int(found.sum()),
        "fell": int(fell.sum()),
        "relict": int((df["nametype"] == "Relict").sum()),
        "excluded_bad_yamato": int(
            ((df["reclat"] == 0) & (df["reclong"] != 0) & df["name"].str.startswith("Yamato")).sum()
        ),
        "antarctica": int(m["antarctica"].sum()),
        "unique_locations": int(len(stacks)),
        "largest_stack": {
            "records": int(top_stack["n"]),
            "example": str(top_stack["name"]),
            "lat": float(stacks.index[0][0]),
            "lon": float(stacks.index[0][1]),
        },
        "antarctica_share_of_mapped": float(m["antarctica"].mean()),
        "unknown_year": int(df["year"].isna().sum()),
        "year_min": int(df["year"].min()),
        "year_max": int(df["year"].max()),
        "classes": int(df["recclass"].nunique()),
        "total_mass_t": float(df["mass"].sum() / 1e6),
        "median_mass_g_found": float(df.loc[found, "mass"].median()),
        "median_mass_g_fell": float(df.loc[fell, "mass"].median()),
        "post_1970_share": float((df["year"] >= 1970).sum() / df["year"].notna().sum()),
        "oldest_falls": witnessed.head(3)[["name", "year", "recclass"]].to_dict("records"),
        "heaviest": heaviest,
        "groups": groups,
        "by_decade": by_decade,
    }


def map_records(df: pd.DataFrame) -> dict:
    """Compact, column-oriented payload for the interactive map."""
    m = df[df["mappable"]].copy()
    # Draw order: big rocks first so small ones stay visible; falls on top.
    m = m.sort_values(["fall", "mass"], ascending=[False, False], na_position="first")
    classes = sorted(m["recclass"].astype(str).unique())
    cls_index = {c: i for i, c in enumerate(classes)}
    return {
        "source": SOURCE_PAGE,
        "groups": GROUPS,
        "classes": classes,
        "name": m["name"].tolist(),
        "id": m["id"].astype(int).tolist(),
        "lat": m["reclat"].round(4).tolist(),
        "lon": m["reclong"].round(4).tolist(),
        "mass": [None if pd.isna(v) else round(float(v), 2) for v in m["mass"]],
        "year": [None if pd.isna(v) else int(v) for v in m["year"]],
        "fell": (m["fall"] == "Fell").astype(int).tolist(),
        "cls": [cls_index[str(c)] for c in m["recclass"]],
        "group": [GROUPS.index(g) for g in m["group"]],
    }
