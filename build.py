"""Rebuild every generated artefact from data/Meteorite_Landings.csv.

    python build.py              # use the CSV in data/
    python build.py --download   # fetch the latest CSV from data.nasa.gov first

Outputs
    docs/data/meteorites.js     compact data for the interactive map (docs/index.html)
    docs/data/basemap.js        Natural Earth land + borders for the same map
    data/insights.json          every number quoted in the README
    assets/map.png              static world map
    assets/insights.png         infographic
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import cartopy.crs as ccrs  # noqa: E402
import cartopy.feature as cfeature  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import meteorites as M  # noqa: E402

DOCS_DATA = M.ROOT / "docs" / "data" / "meteorites.js"
BASEMAP = M.ROOT / "docs" / "data" / "basemap.js"
INSIGHTS_JSON = M.ROOT / "data" / "insights.json"
ASSETS = M.ROOT / "assets"

# Palette (validated for colour-vision deficiency): blue = found, orange = fell.
FOUND_DARK, FELL_DARK = "#3987e5", "#d95926"
FOUND, FELL, ANTARCTICA, OTHER = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
NO_COORDS = "#b9b8b2"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def marker_size(mass_g: np.ndarray) -> np.ndarray:
    """Area in pt^2, growing with log10(mass): 1 g -> ~1, 60 t -> ~60."""
    lm = np.log10(np.nan_to_num(mass_g, nan=1.0) + 1)
    return 0.6 + lm**2


# --- static map --------------------------------------------------------------


def draw_map(df, out):
    m = df[df["mappable"]]
    found, fell = m[m["fall"] == "Found"], m[m["fall"] == "Fell"]

    fig = plt.figure(figsize=(16, 10.2), dpi=150, facecolor="#0e1116")
    ax = fig.add_axes([0.01, 0.075, 0.98, 0.79], projection=ccrs.Robinson())
    ax.set_global()
    ax.set_facecolor("#0e1116")
    ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#1f242c", edgecolor="none")
    ax.add_feature(
        cfeature.COASTLINE.with_scale("110m"), edgecolor="#3a414c", linewidth=0.4
    )
    ax.spines["geo"].set_edgecolor("#2a2f37")

    pc = ccrs.PlateCarree()
    found = found.sort_values("mass", ascending=False)
    ax.scatter(found["reclong"], found["reclat"], s=marker_size(found["mass"].values),
               c=FOUND_DARK, alpha=0.55, linewidths=0, transform=pc, rasterized=True)
    ax.scatter(fell["reclong"], fell["reclat"], s=marker_size(fell["mass"].values),
               c=FELL_DARK, alpha=0.9, linewidths=0.3, edgecolors="#0e1116",
               transform=pc, rasterized=True)

    fig.text(0.03, 0.945, "Where 32,186 meteorites landed on Earth".replace(
        "32,186", f"{len(m):,}"), color="#f0efec", fontsize=24, weight="bold")
    fig.text(0.03, 0.905,
             f"Every located record in NASA's Meteorite Landings dataset · "
             f"{len(found):,} found, {len(fell):,} seen falling · dot size grows with mass",
             color="#c3c2b7", fontsize=13)

    handles = [
        Line2D([], [], marker="o", ls="", color=FOUND_DARK, ms=8, label=f"Found ({len(found):,})"),
        Line2D([], [], marker="o", ls="", color=FELL_DARK, ms=8, label=f"Seen falling ({len(fell):,})"),
    ]
    leg = fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.03, 0.02),
                     ncol=2, frameon=False, fontsize=12, labelcolor="#f0efec")
    for size_g, label in [(1e3, "1 kg"), (1e6, "1 t"), (6e7, "60 t")]:
        handles.append(Line2D([], [], marker="o", ls="", color="#8a8984",
                              ms=np.sqrt(marker_size(np.array([size_g]))[0]), label=label))
    fig.legend(handles=handles[2:], loc="lower left", bbox_to_anchor=(0.36, 0.02), ncol=3,
               frameon=False, fontsize=12, labelcolor="#c3c2b7", title=None)
    fig.add_artist(leg)
    fig.text(0.97, 0.03, "Data: NASA / The Meteoritical Society · github.com/crisdesivo/meteorites-landing",
             color="#8a8984", fontsize=10, ha="right")
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)


# --- infographic ---------------------------------------------------------------


def _bar_labels(ax, bars, fmt, color=INK_2, pad=3):
    for b in bars:
        w = b.get_width()
        ax.text(w, b.get_y() + b.get_height() / 2, " " + fmt(w), va="center",
                ha="left", fontsize=10, color=color)


def draw_infographic(df, ins, out):
    fig = plt.figure(figsize=(15, 15.5), dpi=120, facecolor=SURFACE)
    gs = fig.add_gridspec(3, 2, height_ratios=[0.3, 1.15, 1.25], hspace=0.42, wspace=0.42,
                          left=0.135, right=0.97, top=0.89, bottom=0.04)

    fig.text(0.135, 0.955, "45,716 meteorites in numbers".replace("45,716", f"{ins['records']:,}"),
             fontsize=26, weight="bold", color=INK)
    fig.text(0.135, 0.928, "Computed from NASA's Meteorite Landings dataset "
             "(The Meteoritical Society) by build.py in this repo", fontsize=13, color=INK_2)

    # Hero numbers
    hero = fig.add_subplot(gs[0, :])
    hero.axis("off")
    tiles = [
        (f"{ins['found'] / ins['records']:.1%}", "were found on the ground;\nonly "
         f"{ins['fell']:,} were seen falling"),
        (f"{ins['antarctica_share_of_mapped']:.0%}", "of the located meteorites\nlie south of 60°S (Antarctica)"),
        (f"{ins['post_1970_share']:.0%}", "of dated records are from\n1970 or later"),
        (f"{ins['groups'].loc['Iron', 'mass_share']:.0%}", "of the catalogued mass is iron,\n"
         f"from {ins['groups'].loc['Iron', 'count_share']:.1%} of the records"),
    ]
    for i, (big, small) in enumerate(tiles):
        x = i / len(tiles)
        hero.text(x, 0.55, big, fontsize=34, weight="bold", color=INK, transform=hero.transAxes)
        hero.text(x, 0.45, small, fontsize=12, color=INK_2, transform=hero.transAxes, va="top")

    # Finds per decade
    bd = ins["by_decade"]
    no_coords = (
        df[(df["year"] >= 1800) & (df["fall"] == "Found") & ~df["mappable"]]
        .groupby("decade").size().reindex(bd.index, fill_value=0)
    )
    located_elsewhere = bd["Found elsewhere or unlocated"] - no_coords
    bd = bd[bd.index >= 1900]
    no_coords, located_elsewhere = no_coords[bd.index], located_elsewhere[bd.index]
    ax = fig.add_subplot(gs[1, 0])
    x = np.arange(len(bd))
    series = [
        ("Antarctica", bd["Found in Antarctica"].values, ANTARCTICA),
        ("Elsewhere", located_elsewhere.values, FOUND),
        ("No coordinates", no_coords.values, NO_COORDS),
    ]
    bottom = np.zeros(len(bd))
    for label, vals, color in series:
        ax.bar(x, vals, bottom=bottom, color=color, width=0.78, label=label,
               edgecolor=SURFACE, linewidth=1.2)
        bottom += vals
    ax.set_xticks(x[::2], [f"{d}s" for d in bd.index[::2]], rotation=0, fontsize=9)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Meteorites found per decade, by where", loc="left", fontsize=15,
                 weight="bold", color=INK, pad=28)
    ax.text(0, 1.03, "Before 1970: a few hundred per decade. Since: thousands",
            transform=ax.transAxes, fontsize=11, color=INK_2)
    ax.legend(frameon=False, loc="upper left", fontsize=10)

    # Witnessed falls per decade
    ax = fig.add_subplot(gs[1, 1])
    falls = bd["Witnessed fall"]
    ax.bar(x, falls.values, color=FELL, width=0.78, edgecolor=SURFACE, linewidth=1.2)
    ax.set_xticks(x[::2], [f"{d}s" for d in bd.index[::2]], fontsize=9)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Meteorites seen falling per decade", loc="left", fontsize=15,
                 weight="bold", color=INK, pad=28)
    ax.text(0, 1.03, f"Roughly flat: {falls[falls.index < 2010].min()}–{falls.max()} per decade "
            f"(the 2010s only cover {ins['year_max'] - 2009} years)",
            transform=ax.transAxes, fontsize=11, color=INK_2)

    # Share of records vs share of mass
    g = ins["groups"].iloc[::-1]
    ax = fig.add_subplot(gs[2, 0])
    y = np.arange(len(g))
    h = 0.38
    b1 = ax.barh(y + h / 2, g["count_share"] * 100, height=h, color=MUTED, label="Share of records")
    b2 = ax.barh(y - h / 2, g["mass_share"] * 100, height=h, color=OTHER, label="Share of total mass")
    _bar_labels(ax, b1, lambda v: f"{v:.1f}%")
    _bar_labels(ax, b2, lambda v: f"{v:.1f}%")
    ax.set_yticks(y, g.index)
    ax.set_xlim(0, 105)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_title("Many stones, few irons, but irons hold the mass", loc="left",
                 fontsize=15, weight="bold", color=INK, pad=28)
    ax.text(0, 1.03, f"{ins['classes']} official classes folded into {len(g)} groups",
            transform=ax.transAxes, fontsize=11, color=INK_2)
    ax.legend(frameon=False, loc="lower right", fontsize=10)

    # Heaviest
    hv = ins["heaviest"].iloc[::-1]
    ax = fig.add_subplot(gs[2, 1])
    colors = [FELL if f == "Fell" else FOUND for f in hv["fall"]]
    bars = ax.barh(np.arange(len(hv)), hv["mass"] / 1e6, color=colors, height=0.66)
    _bar_labels(ax, bars, lambda v: f"{v:,.0f} t" if v >= 10 else f"{v:,.1f} t")
    ax.set_yticks(np.arange(len(hv)),
                  [f"{n} ({int(yr)})" for n, yr in zip(hv["name"], hv["year"])])
    ax.set_xlim(0, hv["mass"].max() / 1e6 * 1.18)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_title("The 10 heaviest meteorites", loc="left", fontsize=15, weight="bold",
                 color=INK, pad=28)
    ax.text(0, 1.03, "All ten are irons · year = found or fell", transform=ax.transAxes,
            fontsize=11, color=INK_2)
    ax.legend(handles=[Line2D([], [], marker="s", ls="", color=FOUND, ms=9, label="Found"),
                       Line2D([], [], marker="s", ls="", color=FELL, ms=9, label="Seen falling")],
              frameon=False, loc="lower right", fontsize=10)

    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


# --- basemap for the interactive map ----------------------------------------------


def write_basemap(out, tolerance=0.02):
    """Natural Earth 1:50m land + country borders (public domain) as a JS file.

    Shipping the outlines with the page keeps the map fully static: no tile
    server, no API key, works from file:// and from GitHub Pages.
    """
    from cartopy.io import shapereader
    from shapely.geometry import mapping

    def features(category, name):
        path = shapereader.natural_earth("50m", category, name)
        out_feats = []
        for geom in shapereader.Reader(path).geometries():
            g = geom.simplify(tolerance, preserve_topology=True)
            if g.is_empty:
                continue
            out_feats.append({"type": "Feature", "properties": {}, "geometry": mapping(g)})
        return {"type": "FeatureCollection", "features": out_feats}

    def rounded(obj):
        if isinstance(obj, float):
            return round(obj, 3)
        if isinstance(obj, (list, tuple)):
            return [rounded(v) for v in obj]
        if isinstance(obj, dict):
            return {k: rounded(v) for k, v in obj.items()}
        return obj

    data = {
        "land": rounded(features("physical", "land")),
        "borders": rounded(features("cultural", "admin_0_boundary_lines_land")),
    }
    out.write_text(
        "// Natural Earth 1:50m land and borders (public domain), simplified by build.py.\n"
        "window.BASEMAP = " + json.dumps(data, separators=(",", ":")) + ";\n"
    )


# --- JSON outputs ----------------------------------------------------------------


def write_insights(ins, out):
    hv = ins["heaviest"]
    payload = {k: v for k, v in ins.items() if k not in ("heaviest", "groups", "by_decade")}
    payload["heaviest"] = [
        {"name": r.name, "id": int(r.id), "class": r.recclass, "mass_t": round(r.mass / 1e6, 2),
         "fall": r.fall, "year": None if np.isnan(r.year) else int(r.year)}
        for r in hv.itertuples()
    ]
    payload["groups"] = {
        g: {"count": int(r["count"]), "mass_kg": round(float(r["mass_kg"]), 1),
            "count_share": round(float(r["count_share"]), 4),
            "mass_share": round(float(r["mass_share"]), 4)}
        for g, r in ins["groups"].iterrows()
    }
    payload["by_decade"] = {
        int(d): {k: int(v) for k, v in row.items()} for d, row in ins["by_decade"].iterrows()
    }
    out.write_text(json.dumps(payload, indent=2, default=float) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="fetch the latest CSV from data.nasa.gov")
    args = ap.parse_args()

    if args.download or not M.RAW_CSV.exists():
        print(f"Downloading {M.SOURCE_CSV}")
        M.download()

    df = M.load()
    ins = M.insights(df)
    ASSETS.mkdir(exist_ok=True)
    DOCS_DATA.parent.mkdir(parents=True, exist_ok=True)

    DOCS_DATA.write_text(
        "// Generated by build.py from NASA's Meteorite Landings dataset. Do not edit.\n"
        "window.METEORITES = " + json.dumps(M.map_records(df), separators=(",", ":")) + ";\n"
    )
    write_basemap(BASEMAP)
    write_insights(ins, INSIGHTS_JSON)
    draw_map(df, ASSETS / "map.png")
    draw_infographic(df, ins, ASSETS / "insights.png")

    print(f"{ins['records']:,} records, {ins['mappable']:,} mapped")
    for p in (DOCS_DATA, BASEMAP, INSIGHTS_JSON, ASSETS / "map.png", ASSETS / "insights.png"):
        print(f"  wrote {p.relative_to(M.ROOT)} ({p.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
