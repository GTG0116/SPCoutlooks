"""
generate_png.py
Renders SPC outlook GeoJSON files as styled PNG maps matching
the look of official SPC products.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")  # headless

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER

# ── Color tables ──────────────────────────────────────────────────────────────

CATEGORICAL_COLORS = {
    "TSTM": ("#C1E9C1", "#4A8F4A"),
    "MRGL": ("#66A366", "#2E6B2E"),
    "SLGT": ("#FFE066", "#C8A800"),
    "ENH":  ("#FFA500", "#C06000"),
    "MDT":  ("#E8000D", "#8B0000"),
    "HIGH": ("#FF00FF", "#9900CC"),
}

CATEGORICAL_LABELS = {
    "TSTM": "Thunderstorm",
    "MRGL": "Marginal",
    "SLGT": "Slight",
    "ENH":  "Enhanced",
    "MDT":  "Moderate",
    "HIGH": "High",
}

CATEGORICAL_ORDER = ["TSTM", "MRGL", "SLGT", "ENH", "MDT", "HIGH"]

PROB_COLORS = {
    "0.02": ("#008B00", "#005500"),
    "0.05": ("#8B4513", "#5C2C0A"),
    "0.10": ("#FFD700", "#B89B00"),
    "0.15": ("#FF4500", "#C02000"),
    "0.30": ("#FF0000", "#8B0000"),
    "0.45": ("#FF00FF", "#9900CC"),
    "0.60": ("#800080", "#4B004B"),
    # Also accept integer-style labels
    "2":  ("#008B00", "#005500"),
    "5":  ("#8B4513", "#5C2C0A"),
    "10": ("#FFD700", "#B89B00"),
    "15": ("#FF4500", "#C02000"),
    "30": ("#FF0000", "#8B0000"),
    "45": ("#FF00FF", "#9900CC"),
    "60": ("#800080", "#4B004B"),
}

PROB_LABELS = {
    "0.02": "2%",  "0.05": "5%",  "0.10": "10%",
    "0.15": "15%", "0.30": "30%", "0.45": "45%", "0.60": "60%",
    "2":    "2%",  "5":    "5%",  "10":   "10%",
    "15":   "15%", "30":   "30%", "45":   "45%", "60":   "60%",
}

PROB_ORDER = ["0.02", "0.05", "0.10", "0.15", "0.30", "0.45", "0.60",
              "2",     "5",    "10",   "15",   "30",   "45",   "60"]

TYPE_TITLES = {
    "categorical":   "Categorical Outlook",
    "tornado":       "Tornado Probability",
    "wind":          "Wind Probability",
    "hail":          "Hail Probability",
    "probabilistic": "Probabilistic Outlook",
}

# ── Map setup helpers ─────────────────────────────────────────────────────────

PROJECTION = ccrs.LambertConformal(
    central_longitude=-96,
    central_latitude=37.5,
    standard_parallels=(33, 45),
)

LAND_COLOR    = "#F5F1E3"
OCEAN_COLOR   = "#A8D8EA"
LAKE_COLOR    = "#A8D8EA"
STATE_COLOR   = "#888888"
BORDER_COLOR  = "#444444"
COAST_COLOR   = "#444444"
BG_COLOR      = "#FFFFFF"
TITLE_COLOR   = "#1A1A1A"

# CONUS extent in PlateCarree
EXTENT = [-122, -63, 21, 50]


def _build_axes(figsize=(14, 8.5)):
    fig = plt.figure(figsize=figsize, facecolor=BG_COLOR, dpi=150)
    ax = fig.add_axes([0.01, 0.06, 0.78, 0.88], projection=PROJECTION)

    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.set_facecolor(OCEAN_COLOR)

    # Background features
    ax.add_feature(cfeature.OCEAN.with_scale("50m"),      facecolor=OCEAN_COLOR, zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"),       facecolor=LAND_COLOR,  zorder=1)
    ax.add_feature(cfeature.LAKES.with_scale("50m"),      facecolor=LAKE_COLOR,  zorder=2)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"),  edgecolor=COAST_COLOR, linewidth=0.6, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"),    edgecolor=BORDER_COLOR,linewidth=0.8, zorder=5)
    ax.add_feature(cfeature.STATES.with_scale("50m"),     edgecolor=STATE_COLOR, linewidth=0.4, zorder=5)

    return fig, ax


def _sort_features(features, color_table, order):
    """Sort GeoJSON features by risk level (lowest first so highest renders on top)."""
    label_rank = {lbl: i for i, lbl in enumerate(order)}

    def rank(f):
        label = (f.get("properties") or {}).get("LABEL", "")
        return label_rank.get(label, -1)

    return sorted(features, key=rank)


def _get_color(label, color_table):
    """Return (fill, edge) for a given risk label."""
    # Try exact match first, then normalise
    if label in color_table:
        return color_table[label]
    # Normalise probability labels like "10.00" → "0.10"
    try:
        val = float(label)
        if val > 1:
            val /= 100
        key = f"{val:.2f}"
        if key in color_table:
            return color_table[key]
    except (ValueError, TypeError):
        pass
    return ("#CCCCCC", "#888888")


def _add_geojson_layer(ax, geojson, color_table, order):
    """Add GeoJSON features as polygon patches on the axes."""
    from shapely.geometry import shape, MultiPolygon, Polygon, GeometryCollection
    import shapely

    features = geojson.get("features", [])
    if not features:
        return []

    features = _sort_features(features, color_table, order)
    used_labels = []

    for feat in features:
        props = feat.get("properties") or {}
        label = props.get("LABEL", "")
        is_sig = "SIG" in label.upper() or props.get("LABEL2", "").upper().startswith("SIG")

        fill, edge = _get_color(label, color_table)

        try:
            geom = shape(feat["geometry"])
        except Exception:
            continue

        # Flatten to list of simple polygons
        if isinstance(geom, (MultiPolygon, GeometryCollection)):
            polys = list(geom.geoms)
        elif isinstance(geom, Polygon):
            polys = [geom]
        else:
            polys = [geom]

        for poly in polys:
            if poly.is_empty:
                continue
            try:
                ax.add_geometries(
                    [poly],
                    crs=ccrs.PlateCarree(),
                    facecolor=fill,
                    edgecolor=edge,
                    linewidth=0.6,
                    alpha=0.75,
                    zorder=3,
                )
                if is_sig:
                    # Hatching for significant risk
                    ax.add_geometries(
                        [poly],
                        crs=ccrs.PlateCarree(),
                        facecolor="none",
                        edgecolor="#000000",
                        linewidth=0.0,
                        hatch="///",
                        alpha=0.5,
                        zorder=4,
                    )
            except Exception:
                pass

        if label not in used_labels and label in color_table:
            used_labels.append(label)

    return used_labels


def _add_legend(fig, used_labels, color_table, label_map, title):
    """Add a styled legend panel to the right of the map."""
    legend_ax = fig.add_axes([0.80, 0.10, 0.19, 0.80])
    legend_ax.set_axis_off()

    # Panel background
    legend_ax.add_patch(mpatches.FancyBboxPatch(
        (0, 0), 1, 1,
        boxstyle="round,pad=0.02",
        linewidth=1, edgecolor="#AAAAAA", facecolor="#F8F8F8",
        transform=legend_ax.transAxes, zorder=0,
    ))

    legend_ax.text(0.5, 0.96, title, ha="center", va="top",
                   fontsize=9, fontweight="bold", color=TITLE_COLOR,
                   transform=legend_ax.transAxes, wrap=True)

    patch_h = 0.068
    gap     = 0.015
    top     = 0.90
    pad_x   = 0.08

    # Determine which labels to show (in defined order)
    from itertools import chain
    all_ordered = list(dict.fromkeys(chain(
        [l for l in color_table if l in used_labels],
    )))
    # Use the canonical order lists
    ordered = [l for l in (CATEGORICAL_ORDER + PROB_ORDER) if l in used_labels]
    # dedupe preserving order
    seen = set()
    ordered_unique = []
    for l in ordered:
        if l not in seen:
            ordered_unique.append(l)
            seen.add(l)

    for i, label in enumerate(ordered_unique):
        fill, edge = color_table.get(label, ("#CCC", "#888"))
        y = top - i * (patch_h + gap)

        rect = mpatches.FancyBboxPatch(
            (pad_x, y - patch_h), 0.25, patch_h,
            boxstyle="round,pad=0.005",
            linewidth=0.8, edgecolor=edge, facecolor=fill,
            transform=legend_ax.transAxes, zorder=1,
        )
        legend_ax.add_patch(rect)

        display = label_map.get(label, label)
        legend_ax.text(pad_x + 0.30, y - patch_h / 2, display,
                       ha="left", va="center", fontsize=8,
                       transform=legend_ax.transAxes, color=TITLE_COLOR)

    # Sig hatch sample if any sig in source (always show note)
    sig_y = top - len(ordered_unique) * (patch_h + gap) - gap
    if sig_y > 0.05:
        sig_rect = mpatches.FancyBboxPatch(
            (pad_x, sig_y - patch_h), 0.25, patch_h,
            boxstyle="round,pad=0.005",
            linewidth=0.8, edgecolor="#333", facecolor="#FFFFFF",
            hatch="///",
            transform=legend_ax.transAxes, zorder=1,
        )
        legend_ax.add_patch(sig_rect)
        legend_ax.text(pad_x + 0.30, sig_y - patch_h / 2, "Significant",
                       ha="left", va="center", fontsize=7.5,
                       transform=legend_ax.transAxes, color=TITLE_COLOR)


def _add_title(fig, day, outlook_type, geojson):
    """Add title bar with day number, type, and issue time."""
    meta = geojson.get("_meta", {})
    fetched = meta.get("fetched_utc", "")[:16].replace("T", " ") + " UTC" if meta.get("fetched_utc") else ""

    day_label = f"Day {day}"
    type_label = TYPE_TITLES.get(outlook_type, outlook_type.title())

    fig.text(0.01, 0.975,
             f"SPC {day_label} {type_label}",
             ha="left", va="top",
             fontsize=14, fontweight="bold", color=TITLE_COLOR)

    if fetched:
        fig.text(0.01, 0.955,
                 f"Data retrieved: {fetched}",
                 ha="left", va="top",
                 fontsize=8, color="#555555")

    # SPC branding footer
    fig.text(0.5, 0.01,
             "Storm Prediction Center  •  www.spc.noaa.gov  •  Rendered by SPCOutlooks",
             ha="center", va="bottom",
             fontsize=7, color="#888888")


def render_map(day, outlook_type, geojson, output_path):
    """Render a single outlook type to a PNG file."""
    is_cat = outlook_type == "categorical"
    color_table = CATEGORICAL_COLORS if is_cat else PROB_COLORS
    order       = CATEGORICAL_ORDER   if is_cat else PROB_ORDER
    label_map   = CATEGORICAL_LABELS  if is_cat else PROB_LABELS
    legend_title = "Risk Category"    if is_cat else "Probability"

    fig, ax = _build_axes()

    if geojson and geojson.get("features"):
        used = _add_geojson_layer(ax, geojson, color_table, order)
    else:
        used = []
        ax.text(0.5, 0.5, "No outlook data available",
                ha="center", va="center", fontsize=14,
                color="#666666", transform=ax.transAxes)

    _add_legend(fig, used or list(color_table.keys())[:0], color_table, label_map, legend_title)
    _add_title(fig, day, outlook_type, geojson or {})

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=BG_COLOR, edgecolor="none")
    plt.close(fig)
    print(f"  PNG saved → {output_path}")


def generate_all(output_root="output"):
    """Walk output_root and generate PNGs for every available GeoJSON."""
    for day in range(1, 9):
        day_dir = os.path.join(output_root, f"day{day}")
        if not os.path.isdir(day_dir):
            continue

        for outlook_type in ("categorical", "tornado", "wind", "hail", "probabilistic"):
            geojson_path = os.path.join(day_dir, f"{outlook_type}.geojson")
            if not os.path.exists(geojson_path):
                continue

            png_path = os.path.join(day_dir, f"{outlook_type}.png")
            print(f"Rendering Day {day} {outlook_type} PNG …")

            with open(geojson_path) as f:
                geojson = json.load(f)

            try:
                render_map(day, outlook_type, geojson, png_path)
            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "output"
    generate_all(root)
