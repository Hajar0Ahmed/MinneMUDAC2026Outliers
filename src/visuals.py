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
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch

LILA_COLS = ["LILATracts_1And10", "LILATracts_halfAnd10", "LILATracts_1And20"]

from spatial_analysis import (
<<<<<<< HEAD
    SHAPE_PATH, SHAPE_ID_COL, SCORE_COL, RETAIL_COL, SUMMARY_PATH,
=======
    SHAPE_PATH, SHAPE_ID_COL, SCORE_COL, RETAIL_COL,
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    OUT_GISTAR, OUT_SPEARMAN, OUT_MORAN, OUT_QUADRAT, OUT_QUADRAT_SUMMARY,
)


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
    '''
    Loads tract boundaries and renames ID column to GEO_ID.
    '''
    shapes = gpd.read_file(SHAPE_PATH)
    shapes = shapes.rename(columns={SHAPE_ID_COL: "GEO_ID"})
    shapes["GEO_ID"] = shapes["GEO_ID"].astype(str)
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
<<<<<<< HEAD
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
=======
    Draws a LILA-focused map: non-LILA tracts are light grey, non-significant 
    LILA tracts are a darker grey, and significant LILA tracts use their category colors.
    '''
    gdf = shapes.merge(results, on="GEO_ID", how="left")
    
    # 1. Base layer: All tracts light grey
    gdf.plot(ax=ax, color="#f0f0f0", edgecolor="white", linewidth=0.1)

    # 2. LILA non-significant tracts get a slightly darker grey
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    lila_nonsig = gdf[(gdf[lila_col] == True) & (gdf[class_col] == "Not significant")]
    if len(lila_nonsig) > 0:
        lila_nonsig.plot(ax=ax, color="#cccccc", edgecolor="white", linewidth=0.1)

<<<<<<< HEAD
    # 4. Significant LILA tracts: category colors
=======
    # 3. Significant LILA tracts get their specific category colors
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    for label, color in colors.items():
        if label == "Not significant":
            continue
        subset = gdf[(gdf[lila_col] == True) & (gdf[class_col] == label)]
        if len(subset) > 0:
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.1)

<<<<<<< HEAD
    # Legend
    handles = [Patch(facecolor=c, label=l) for l, c in colors.items() if l != "Not significant"]
    handles.append(Patch(facecolor="#cccccc", label="LILA (Not significant)"))
    handles.append(Patch(facecolor="#f0f0f0", label="Non-LILA / Other"))
    handles.append(Patch(facecolor="#fdf0c8", label="LILA status unknown"))

=======
    # Legend setup
    handles = [Patch(facecolor=c, label=l) for l, c in colors.items() if l != "Not significant"]
    handles.append(Patch(facecolor="#cccccc", label="LILA (Not significant)"))
    handles.append(Patch(facecolor="#f0f0f0", label="Non-LILA / Other"))
    
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
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
    # 2. Run summary bar chart (combines all LILA definitions)
    plot_quadrat_bars()
    print(f"All figures saved to {FIG_DIR}/")


#---- 1. Gi* Coldspot Maps ----#
def plot_coldspot_map(shapes, lila_col):
    results = pd.read_csv(OUT_GISTAR, dtype={"GEO_ID": str})
    results = results[results["group"] == "all"]

<<<<<<< HEAD
    # Map A: All tracts (identical for every LILA definition, so save it once)
    if lila_col == LILA_COLS[0]:
        fig, ax = plt.subplots(figsize=(8, 9))
        draw_cluster_map(ax, shapes, results, "gi_class", GISTAR_COLORS,
                         "Food shelf access hot/cold spots (All tracts)")
        fig.savefig(os.path.join(FIG_DIR, "gistar_map_all.png"),
                    dpi=DPI, bbox_inches="tight")
        plt.close(fig)
=======
    # Map A: All tracts
    fig, ax = plt.subplots(figsize=(8, 9))
    draw_cluster_map(ax, shapes, results, "gi_class", GISTAR_COLORS,
                     f"Food shelf access hot/cold spots (All tracts)")
    path_all = os.path.join(FIG_DIR, f"gistar_map_{lila_col}.png")
    fig.savefig(path_all, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49

    # Map B: LILA-focused map
    fig, ax = plt.subplots(figsize=(8, 9))
    draw_lila_cluster_map(ax, shapes, results, "gi_class", GISTAR_COLORS,
                          f"Food shelf access hot/cold spots ({lila_col} focus)", lila_col)
<<<<<<< HEAD
    fig.savefig(os.path.join(FIG_DIR, f"gistar_map_{lila_col}_lila.png"),
                dpi=DPI, bbox_inches="tight")
=======
    path_lila = os.path.join(FIG_DIR, f"gistar_map_{lila_col}_lila.png")
    fig.savefig(path_lila, dpi=DPI, bbox_inches="tight")
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    plt.close(fig)


#---- 2. Retail vs Food Shelf Scatter ----#
def plot_retail_vs_shelf(lila_col):
    df = pd.read_csv(OUT_QUADRAT, dtype={"GEO_ID": str})
    spearman = pd.read_csv(OUT_SPEARMAN)
    rho = spearman.loc[spearman["group"] == "all", "spearman_rho"].iloc[0]

<<<<<<< HEAD
    # percentile ranks across ALL tracts (matches the quadrat cutoffs)
    df["retail_rank"] = df[RETAIL_COL].rank(pct=True)
    df["shelf_rank"] = df[SCORE_COL].rank(pct=True)

    # tracts with no USDA match have unknown LILA status: leave them out
    n_unknown = int((~df["in_usda"]).sum())
    df = df[df["in_usda"]].copy()
=======
    df["retail_rank"] = df[RETAIL_COL].rank(pct=True)
    df["shelf_rank"] = df[SCORE_COL].rank(pct=True)
    
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    df[lila_col] = df[lila_col].astype(bool)

    fig, ax = plt.subplots(figsize=(7, 6))
    non_lila = df[~df[lila_col]]
    lila = df[df[lila_col]]
<<<<<<< HEAD

=======
    
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    ax.scatter(non_lila["retail_rank"], non_lila["shelf_rank"],
               s=12, color="#bdbdbd", alpha=0.6, label="Non-LILA")
    ax.scatter(lila["retail_rank"], lila["shelf_rank"],
               s=18, color="#d95f02", alpha=0.8, label=f"LILA ({lila_col})")

    ax.axvline(0.5, color="black", linestyle="--", linewidth=0.8)
    ax.axhline(0.5, color="black", linestyle="--", linewidth=0.8)

    ax.set_xlabel("Retail access (percentile rank)")
    ax.set_ylabel("Food shelf access, E2SFCA (percentile rank)")
<<<<<<< HEAD
    ax.set_title(f"Retail vs food shelf access (rho = {rho:.2f}, all tracts)\n"
                 f"{n_unknown} tracts with unknown LILA status not shown", fontsize=10)
=======
    ax.set_title(f"Retail vs food shelf access (rho = {rho:.2f})")
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
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

<<<<<<< HEAD
    # Map A: All tracts (save once)
    if lila_col == LILA_COLS[0]:
        fig, ax = plt.subplots(figsize=(8, 9))
        draw_cluster_map(ax, shapes, results, "moran_cluster", MORAN_COLORS,
                         "Bivariate Local Moran's I (All tracts)")
        fig.savefig(os.path.join(FIG_DIR, "moran_map_all.png"),
                    dpi=DPI, bbox_inches="tight")
        plt.close(fig)
=======
    # Map A: All tracts
    fig, ax = plt.subplots(figsize=(8, 9))
    draw_cluster_map(ax, shapes, results, "moran_cluster", MORAN_COLORS,
                     f"Bivariate Local Moran's I (All tracts)")
    path_all = os.path.join(FIG_DIR, f"moran_map_{lila_col}.png")
    fig.savefig(path_all, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49

    # Map B: LILA-focused map
    fig, ax = plt.subplots(figsize=(8, 9))
    draw_lila_cluster_map(ax, shapes, results, "moran_cluster", MORAN_COLORS,
<<<<<<< HEAD
                          f"Bivariate Local Moran's I ({lila_col})", lila_col)
    fig.savefig(os.path.join(FIG_DIR, f"moran_map_{lila_col}_lila.png"),
                dpi=DPI, bbox_inches="tight")
=======
                          f"Bivariate Local Moran's I ({lila_col} focus)", lila_col)
    path_lila = os.path.join(FIG_DIR, f"moran_map_{lila_col}_lila.png")
    fig.savefig(path_lila, dpi=DPI, bbox_inches="tight")
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
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
<<<<<<< HEAD
    Tract-level continuous access map using an index relative to the mean score.
    '''
    df = pd.read_csv(SUMMARY_PATH, dtype={"GEO_ID": str})
    gdf = shapes.merge(df, on="GEO_ID", how="left")

    # Normalize scores relative to the study-area mean
=======
    Draws a tract-level continuous access map using a normalized index
    '''
    df = pd.read_csv(OUT_QUADRAT, dtype={"GEO_ID": str})
    gdf = shapes.merge(df, on="GEO_ID", how="left")
    
    # Normalize scores relative to the study area mean\
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    mean_score = gdf[SCORE_COL].mean()
    gdf["access_index"] = gdf[SCORE_COL] / mean_score if mean_score > 0 else 0.0

    fig, ax = plt.subplots(figsize=(8, 9))
<<<<<<< HEAD

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
=======
    
    # Anchor the divergent colormap around 1.0 using TwoSlopeNorm
    norm = mcolors.TwoSlopeNorm(
        vmin=0.0, 
        vcenter=0.75,
        vmax=max(1.5,gdf["access_index"].quantile(0.99))
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
            "label": "E2SFCA access index",
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
            "orientation": "vertical",
            "shrink": 0.55,
            "pad": 0.02
        }
    )

<<<<<<< HEAD
    fig.suptitle("Food-Shelf Geographic Access in Minnesota, 2024",
                 fontsize=13, fontweight="bold", y=0.92)
    ax.set_title("Geographic Site Access (Tract-Level)", fontsize=11, loc="center", pad=10)
    ax.set_axis_off()

=======
    # Match the thematic layout hierarchy from your reference image
    fig.suptitle("Food-Shelf Geographic Access in Minnesota, 2024", fontsize=13, fontweight="bold", y=0.92)
    ax.set_title("Geographic Site Access (Tract-Level)", fontsize=11, loc="center", pad=10)
    ax.set_axis_off()
    
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
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