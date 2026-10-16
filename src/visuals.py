'''
shelf_visuals.py
 
Create simple figures that show the results of the spatial analysis:
 
This file reads the csv files produced by shelf_spatial.py and makes
four figures that help answer the questions
 
1. Does the food shelf network sufficiently reach LILA areas?
2. Does the food shelf network fill the retail gap, or does it repeat
   the same pattern as the retail market?
 
This is done by producing png figures that show:
    1. Map of Gi* coldspots with LILA tracts outlined
    2. Scatter plot of retail access vs food shelf access
    3. Map of bivariate Local Moran's I clusters
    4. Bar chart of the 2x2 quadrat shares for LILA vs all tracts
 
Each figure is made by one function that can be called from main.py.
Run the functions in shelf_spatial.py first so the csv files exist.
 
Required packages:
    pip install geopandas matplotlib pandas
'''
import os
import numpy as np
from scipy.stats import spearmanr
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch

LILA_COLS = ["LILATracts_1And10", "LILATracts_halfAnd10", "LILATracts_1And20"]

from spatial_analysis import (
    SHAPE_PATH, SHAPE_ID_COL, SCORE_COL, RETAIL_COL, SUMMARY_PATH,
    OUT_GISTAR, OUT_SPEARMAN, OUT_MORAN, OUT_QUADRAT, OUT_QUADRAT_SUMMARY,
)


OUT_REGIONAL = "data/processed/regional_breakdown.csv"

REGION_COUNTIES = {
    "Twin Cities Metro": ["003","019","037","053","123","139","163"],
    "Northwest": ["069","089","107","113","119","125","135","007","029","057","077","087"],
    "Northeast": ["001","017","031","061","071","075","137"],
    "Central": ["021","035","097","153","159","009","141","145","171",
                "025","059","065","095","115"],
    "West Central": ["005","027","041","051","111","121","149","155","167"],
    "Southwest": ["011","023","067","073","085","093","129","151","173",
                  "033","063","081","083","101","105","117","127","133"],
    "South Central": ["013","015","043","079","091","103","143","161","165"],
    "Southeast": ["039","045","047","049","055","099","109","131","147","157","169"],
}
COUNTY_TO_REGION = {c: r for r, cs in REGION_COUNTIES.items() for c in cs}



FIG_DIR = "visualizations"
DPI = 200

GISTAR_COLORS = {
    "Coldspot": "#2166ac",
    "Hotspot": "#b2182b",
    "Not significant": "#e0e0e0",
}
MORAN_COLORS = {
    "HH": "#b2182b",
    "LL": "#2166ac",
    "LH": "#92c5de",
    "HL": "#f4a582",
    "Not significant": "#e0e0e0",
}
QUADRAT_COLORS = {
    "Low retail / Low shelf": "#c6dbef",
    "Low retail / High shelf": "#6baed6",
    "High retail / Low shelf": "#3182bd",
    "High retail / High shelf": "#08519c",
}


#---- Helper Functions ----#
def load_shapes():
    shapes = gpd.read_file(SHAPE_PATH)
    shapes = shapes.rename(columns={SHAPE_ID_COL: "GEO_ID"})
    shapes["GEO_ID"] = shapes["GEO_ID"].astype(str)

    # drop water-only tracts (Lake Superior, Red Lake, Lake of the Woods, etc.)
    shapes = shapes[~shapes["GEO_ID"].str.endswith("990000")]
    return shapes[["GEO_ID", "geometry"]]


def draw_cluster_map(ax, shapes, results, class_col, colors, title):
    '''
    Draws a map of all tracts colored by class_col with white edges.
    '''
    gdf = shapes.merge(results, on="GEO_ID", how="left")
    gdf.plot(ax=ax, color="#f5f5f5", edgecolor="white", linewidth=0.1)

    for label, color in colors.items():
        subset = gdf[gdf[class_col] == label]
        if len(subset) > 0:
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.1)

    handles = [Patch(facecolor=c, label=l) for l, c in colors.items()]
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=True)
    ax.set_title(title, fontsize=12)
    ax.set_axis_off()


def draw_lila_cluster_map(ax, shapes, results, class_col, colors, title, lila_col):
    '''
    LILA-focused map: non-LILA tracts are light grey, tracts with unknown LILA
    status (no USDA match) are pale yellow, non-significant LILA tracts are a
    darker grey, and significant LILA tracts use their category colors.
    '''
    gdf = shapes.merge(results, on="GEO_ID", how="left")

    # 1. Base layer: all tracts light grey
    gdf.plot(ax=ax, color="#f0f0f0", edgecolor="white", linewidth=0.1)

    # 2. Tracts with no USDA match: LILA status unknown
    unknown = gdf[gdf["in_usda"].eq(False)]
    if len(unknown) > 0:
        unknown.plot(ax=ax, color="#fdf0c8", edgecolor="white", linewidth=0.1)

    # 3. LILA tracts that are not significant: darker grey
    lila_nonsig = gdf[(gdf[lila_col] == True) & (gdf[class_col] == "Not significant")]
    if len(lila_nonsig) > 0:
        lila_nonsig.plot(ax=ax, color="#cccccc", edgecolor="white", linewidth=0.1)

    # 4. Significant LILA tracts: category colors
    for label, color in colors.items():
        if label == "Not significant":
            continue
        subset = gdf[(gdf[lila_col] == True) & (gdf[class_col] == label)]
        if len(subset) > 0:
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.1)

    # Legend
    handles = [Patch(facecolor=c, label=l) for l, c in colors.items() if l != "Not significant"]
    handles.append(Patch(facecolor="#cccccc", label="LILA (Not significant)"))
    handles.append(Patch(facecolor="#f0f0f0", label="Non-LILA / Other"))
    handles.append(Patch(facecolor="#fdf0c8", label="LILA status unknown"))

    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=True)
    ax.set_title(title, fontsize=12)
    ax.set_axis_off()


#---- Master Visual Generation Function ----#
def generate_all_visuals():
    '''
    Generates all figures for each LILA definition.
    Call this from main.py.
    '''
    os.makedirs(FIG_DIR, exist_ok=True)
    shapes = load_shapes()
    
    # 1. Run map-based figures for each LILA definition
    for lila_col in LILA_COLS:
        plot_coldspot_map(shapes, lila_col)
        plot_retail_vs_shelf(lila_col)
        plot_moran_map(shapes, lila_col)
    
    plot_tract_access_map(shapes)
    plot_retail_access_map(shapes)
    build_regional_table()
    # 2. Run summary bar chart (combines all LILA definitions)
    plot_quadrat_bars()
    print(f"All figures saved to {FIG_DIR}/")


#---- 1. Gi* Coldspot Maps ----#
def plot_coldspot_map(shapes, lila_col):
    results = pd.read_csv(OUT_GISTAR, dtype={"GEO_ID": str})
    results = results[results["group"] == "all"]

    # Map A: All tracts (identical for every LILA definition, so save it once)
    if lila_col == LILA_COLS[0]:
        fig, ax = plt.subplots(figsize=(8, 9))
        draw_cluster_map(ax, shapes, results, "gi_class", GISTAR_COLORS,
                         "Food shelf access hot/cold spots (All tracts)")
        fig.savefig(os.path.join(FIG_DIR, "gistar_map_all.png"),
                    dpi=DPI, bbox_inches="tight")
        plt.close(fig)

    # Map B: LILA-focused map
    fig, ax = plt.subplots(figsize=(8, 9))
    draw_lila_cluster_map(ax, shapes, results, "gi_class", GISTAR_COLORS,
                          f"Food shelf access hot/cold spots ({lila_col} focus)", lila_col)
    fig.savefig(os.path.join(FIG_DIR, f"gistar_map_{lila_col}_lila.png"),
                dpi=DPI, bbox_inches="tight")
    plt.close(fig)


#---- 2. Retail vs Food Shelf Scatter ----#
def plot_retail_vs_shelf(lila_col):
    df = pd.read_csv(OUT_QUADRAT, dtype={"GEO_ID": str})
    spearman = pd.read_csv(OUT_SPEARMAN)
    rho = spearman.loc[spearman["group"] == "all", "spearman_rho"].iloc[0]

    # percentile ranks across ALL tracts (matches the quadrat cutoffs)
    df["retail_rank"] = df[RETAIL_COL].rank(pct=True)
    df["shelf_rank"] = df[SCORE_COL].rank(pct=True)

    # tracts with no USDA match have unknown LILA status: leave them out
    n_unknown = int((~df["in_usda"]).sum())
    df = df[df["in_usda"]].copy()
    df[lila_col] = df[lila_col].astype(bool)

    fig, ax = plt.subplots(figsize=(7, 6))
    non_lila = df[~df[lila_col]]
    lila = df[df[lila_col]]
    ax.scatter(non_lila["retail_rank"], non_lila["shelf_rank"],
               s=12, color="#bdbdbd", alpha=0.6, label="Non-LILA")
    ax.scatter(lila["retail_rank"], lila["shelf_rank"],
               s=18, color="#d95f02", alpha=0.8, label=f"LILA ({lila_col})")

    ax.axvline(0.5, color="black", linestyle="--", linewidth=0.8)
    ax.axhline(0.5, color="black", linestyle="--", linewidth=0.8)

    ax.set_xlabel("Retail access (percentile rank)")
    ax.set_ylabel("Food shelf access, E2SFCA (percentile rank)")
    ax.set_title(f"Retail vs food shelf access (rho = {rho:.2f}, all tracts)\n"
                 f"{n_unknown} tracts with unknown LILA status not shown", fontsize=10)
    ax.text(0.02, 0.02, "Double gap", fontsize=9, weight="bold")
    ax.text(0.02, 0.96, "Shelves fill gap", fontsize=9, weight="bold")
    ax.text(0.98, 0.02, "Shelves miss retail", fontsize=9, weight="bold", ha="right")
    ax.text(0.98, 0.96, "Well served", fontsize=9, weight="bold", ha="right")
    ax.legend(loc="center left", fontsize=8)

    path = os.path.join(FIG_DIR, f"retail_vs_shelf_{lila_col}.png")
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


#---- 3. Bivariate Moran Maps ----#
def plot_moran_map(shapes, lila_col):
    results = pd.read_csv(OUT_MORAN, dtype={"GEO_ID": str})

    # Map A: All tracts (save once)
    if lila_col == LILA_COLS[0]:
        fig, ax = plt.subplots(figsize=(8, 9))
        draw_cluster_map(ax, shapes, results, "moran_cluster", MORAN_COLORS,
                         "Bivariate Local Moran's I (All tracts)")
        fig.savefig(os.path.join(FIG_DIR, "moran_map_all.png"),
                    dpi=DPI, bbox_inches="tight")
        plt.close(fig)

    # Map B: LILA-focused map
    fig, ax = plt.subplots(figsize=(8, 9))
    draw_lila_cluster_map(ax, shapes, results, "moran_cluster", MORAN_COLORS,
                          f"Bivariate Local Moran's I ({lila_col})", lila_col)
    fig.savefig(os.path.join(FIG_DIR, f"moran_map_{lila_col}_lila.png"),
                dpi=DPI, bbox_inches="tight")
    plt.close(fig)


#---- 4. Quadrat Bar Chart ----#
def plot_quadrat_bars():
    summary = pd.read_csv(OUT_QUADRAT_SUMMARY)
    summary = summary.set_index("subset")

    quadrat_names = list(QUADRAT_COLORS.keys())
    pct_cols = [f"pct_{q}" for q in quadrat_names]
    
    pct = summary[pct_cols]
    pct.columns = quadrat_names  

    fig, ax = plt.subplots(figsize=(10, 5))
    
    pct.plot(kind="bar", ax=ax, width=0.8, color=QUADRAT_COLORS)

    ax.axhline(25, color="black", linestyle="--", linewidth=0.8)
    ax.set_ylabel("Share of tracts (%)")
    ax.set_xlabel("")
    ax.set_title("Where do LILA tracts fall on retail and food shelf access?")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right", fontsize=8)
    ax.legend(title="Tract Group / Quadrant", fontsize=8)

    path = os.path.join(FIG_DIR, "quadrat_bars.png")
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    

def plot_tract_access_map(shapes):
    '''
    Tract-level continuous access map using an index relative to the mean score.
    '''
    df = pd.read_csv(SUMMARY_PATH, dtype={"GEO_ID": str})
    gdf = shapes.merge(df, on="GEO_ID", how="left")

    # Normalize scores relative to the study-area mean
    mean_score = gdf[SCORE_COL].mean()
    gdf["access_index"] = gdf[SCORE_COL] / mean_score if mean_score > 0 else 0.0

    fig, ax = plt.subplots(figsize=(8, 9))

    # Diverging colormap centered on 1.0 (the statewide average)
    norm = mcolors.TwoSlopeNorm(
        vmin=0.0,
        vcenter=1.0,
        vmax=max(1.5, gdf["access_index"].quantile(0.99))
    )

    gdf.plot(
        ax=ax,
        column="access_index",
        cmap="RdYlBu_r",
        norm=norm,
        edgecolor="white",
        linewidth=0.02,
        legend=True,
        legend_kwds={
            "label": "E2SFCA access index (1.0 = average)",
            "orientation": "vertical",
            "shrink": 0.55,
            "pad": 0.02
        }
    )

    fig.suptitle("Food-Shelf Geographic Access in Minnesota, 2024",
                 fontsize=13, fontweight="bold", y=0.92)
    ax.set_title("Geographic Site Access (Tract-Level)", fontsize=11, loc="center", pad=10)
    ax.set_axis_off()

    path = os.path.join(FIG_DIR, "tract_geographic_access_map.png")
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved normalized tract geographic access map to {path}")


def plot_retail_access_map(shapes):
    '''
    Draws a tract-level continuous retail access map using the gravity_2023 score:
    - Blue = 0 / low retail access, Red = highest retail access.
    - Uses the RdYlBu_r (reversed) colormap.
    '''
    df = pd.read_csv(OUT_QUADRAT, dtype={"GEO_ID": str})
    gdf = shapes.merge(df, on="GEO_ID", how="left")

    fig, ax = plt.subplots(figsize=(8, 9))
    
    # Check if gravity_2023 exists in the dataset
    retail_col_name = "gravity_2023" if "gravity_2023" in gdf.columns else RETAIL_COL

    gdf.plot(
        ax=ax, 
        column=retail_col_name, 
        cmap="RdYlBu_r", 
        edgecolor="white", 
        linewidth=0.02, 
        legend=True,
        legend_kwds={
            "label": "Retail Access Score\n(Gravity 2023)",
            "orientation": "vertical",
            "shrink": 0.55,
            "pad": 0.02
        }
    )

    fig.suptitle("Grocery Retail Access in Minnesota, 2023", fontsize=13, fontweight="bold", y=0.92)
    ax.set_title("Retail Market Access (Tract-Level - Gravity)", fontsize=11, loc="center", pad=10)
    ax.set_axis_off()
    
    path = os.path.join(FIG_DIR, "tract_retail_access_map.png")
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved retail access map to {path}")
    
    

def build_regional_table(lila_col="LILATracts_1And10"):
    '''
    Region-level summary: shelf access, coldspot share, double-gap share,
    retail/shelf correlation, and LILA vs non-LILA shelf access.
    '''
    df = pd.read_csv(OUT_QUADRAT, dtype={"GEO_ID": str})
    gi = pd.read_csv(OUT_GISTAR, dtype={"GEO_ID": str})
    gi = gi.loc[gi["group"] == "all", ["GEO_ID", "gi_class"]]
    df = df.merge(gi, on="GEO_ID", how="left")

    df["region"] = df["GEO_ID"].str[-11:].str[2:5].map(COUNTY_TO_REGION)
    df = df.dropna(subset=["region", RETAIL_COL, SCORE_COL]).copy()

    # statewide median cutoffs (same as the quadrat analysis)
    r_cut, s_cut = df[RETAIL_COL].median(), df[SCORE_COL].median()
    low_r, low_s = df[RETAIL_COL] < r_cut, df[SCORE_COL] < s_cut
    df["double_gap"] = low_r & low_s
    df["shelf_fills_gap"] = low_r & ~low_s
    df["coldspot"] = df["gi_class"].eq("Coldspot")
    df["is_lila"] = df["in_usda"].eq(True) & df[lila_col].eq(True)
    df["is_nonlila"] = df["in_usda"].eq(True) & df[lila_col].eq(False)

    rows = []
    for region, g in df.groupby("region"):
        lila, non = g[g["is_lila"]], g[g["is_nonlila"]]
        rho = (spearmanr(g[RETAIL_COL], g[SCORE_COL])[0] if len(g) >= 15 else np.nan)
        rows.append({
            "region": region,
            "n_tracts": len(g),
            "median_shelf_access": g[SCORE_COL].median(),
            "median_retail_access": g[RETAIL_COL].median(),
            "pct_coldspot": 100 * g["coldspot"].mean(),
            "pct_double_gap": 100 * g["double_gap"].mean(),
            "pct_shelf_fills_gap": 100 * g["shelf_fills_gap"].mean(),
            "spearman_rho": rho,
            "n_lila": len(lila),
            "lila_median_shelf": lila[SCORE_COL].median() if len(lila) else np.nan,
            "nonlila_median_shelf": non[SCORE_COL].median() if len(non) else np.nan,
            "pct_lila_double_gap": (100 * lila["double_gap"].mean()
                                    if len(lila) else np.nan),
        })

    table = (pd.DataFrame(rows)
             .sort_values("median_shelf_access", ascending=False)
             .round(2))
    table.to_csv(OUT_REGIONAL, index=False)
    print(table.to_string(index=False))
    plot_regional_bars(table)
    return table


def plot_regional_bars(table):
    '''Slide-friendly chart: coldspot share and double-gap share by region.'''
    t = table.sort_values("pct_double_gap")
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(t))
    ax.barh(y + 0.2, t["pct_double_gap"], height=0.4,
            color="#c6dbef", label="Low retail & low shelf access (%)")
    ax.barh(y - 0.2, t["pct_coldspot"], height=0.4,
            color="#2166ac", label="Shelf-access coldspot (%)")
    ax.set_yticks(y)
    ax.set_yticklabels(t["region"])
    ax.set_xlabel("Share of tracts in region (%)")
    ax.set_title("Where shelf access falls short, by region")
    ax.legend(fontsize=8, loc="lower right")
    fig.savefig(os.path.join(FIG_DIR, "regional_breakdown.png"),
                dpi=DPI, bbox_inches="tight")
    plt.close(fig)