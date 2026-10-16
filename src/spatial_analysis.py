
'''
spatial_analysis.py

Conduct Spatial Analysis:

This file consists of functions required to answer the following questions:
1. Does the food shelf network sufficiently reach LILA areas?
2.Does the food shelf network fill the retail gap, or
does it repeat the same pattern as the retail market?


These questions are answered by
    1. Gi* hot/cold spots of E2SFCA, overlaid with LILA (all, urban, rural)
    2. Spearman correlation of E2SFCA and retail access (all, urban, rural)
    3. Bivariate Local Moran's I of retail access and E2SFCA
    4. 2x2 quadrat classification (low/high retail x low/high food shelf)
'''


import numpy as np
import pandas as pd
import geopandas as gpd
from libpysal import weights
from esda.getisord import G_Local
from esda.moran import Moran_Local_BV
from scipy.stats import spearmanr
 

SUMMARY_PATH = "data/processed/tract_e2sfca_scores.csv"
TRACT_PATH = "data/processed/final_data.csv"
SHAPE_PATH = "data/Spatial/tl_2023_27_tract.zip"   
SHAPE_ID_COL = "GEOID"                           

OUT_GISTAR = "data/processed/gistar_results.csv"
OUT_GISTAR_SUMMARY = "data/processed/gistar_lila_summary.csv"
OUT_SPEARMAN = "data/processed/spearman_results.csv"
OUT_MORAN = "data/processed/bivariate_moran_tracts.csv"
OUT_MORAN_SUMMARY = "data/processed/bivariate_moran_summary.csv"
OUT_QUADRAT = "data/processed/quadrat_tracts.csv"
OUT_QUADRAT_SUMMARY = "data/processed/quadrat_summary.csv"
 
LILA_COLS = ["LILATracts_1And10", "LILATracts_halfAnd10", "LILATracts_1And20"]
SCORE_COL = "e2sfca_mean"        # food shelf access score
RETAIL_COL = "gravity_2023"      # Grocery Gap Atlas retail access
URBAN_COL = "Urban"              # 1 = urban, 0 = rural
 
N_PERM = 999       # number of permutations for pseudo p-values
SEED = 42          # makes the permutations reproducible
ALPHA = 0.05       # significance level
SPLIT_Q = 0.5      # quantile used for low/high in the quadrat (median)
 
 

def load_data():
    '''
    Loads the tract boundaries and merges in the E2SFCA scores and
    the tract data. Drops tracts missing a score or retail value.
    Returns a GeoDataFrame.
    '''
    # 1. Load the tables and the tract boundaries
    summary = pd.read_csv(SUMMARY_PATH, dtype={"GEO_ID": str})
    tracts = pd.read_csv(TRACT_PATH, dtype={"GEO_ID": str})
    shapes = gpd.read_file(SHAPE_PATH)
    shapes[SHAPE_ID_COL] = shapes[SHAPE_ID_COL].astype(str)
    shapes = shapes.rename(columns={SHAPE_ID_COL: "GEO_ID"})
 
    # 2. Merge everything on GEO_ID (the retail score is already in final_data.csv)
    df = tracts.merge(summary, on="GEO_ID", how="inner")
    gdf = shapes[["GEO_ID", "geometry"]].merge(df, on="GEO_ID", how="inner")
 
    # 3. Make sure LILA columns are True/False
    for col in LILA_COLS:
        if col in gdf.columns:
<<<<<<< HEAD
            gdf[col] = gdf[col].eq(1)

    # Drop unpopulated tracts and tracts with no score or retail value
    gdf = gdf[gdf["population"] > 0]
    
=======
            gdf[col] = gdf[col].astype(bool)
 
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    # 4. Drop tracts with no score or no retail value
    gdf = gdf.dropna(subset=[SCORE_COL, RETAIL_COL]).reset_index(drop=True)
 
    return gdf
 
 
def split_by_urbanicity(gdf):
    '''
    Splits the data into all, urban and rural tracts.
    Returns a dictionary of {group name: GeoDataFrame}.
    '''
    # 1. Build one GeoDataFrame per group
    groups = {
        "all": gdf.copy(),
        "urban": gdf[gdf[URBAN_COL] == 1].reset_index(drop=True),
        "rural": gdf[gdf[URBAN_COL] == 0].reset_index(drop=True),
    }
 
    return groups
 
 
def build_weights(gdf):
    '''
    Builds row-standardized Queen contiguity weights. Tracts with no
    neighbors (islands) are dropped because local statistics need
    at least one neighbor.
    Returns the (possibly smaller) GeoDataFrame and the weights.
    '''
    # 1. Build weights
    w = weights.Queen.from_dataframe(gdf, use_index=False)
 
    # 2. Drop islands and rebuild if there are any
    if len(w.islands) > 0:
        print(f"  Dropping {len(w.islands)} island tract(s) with no neighbors")
        gdf = gdf.drop(index=w.islands).reset_index(drop=True)
        w = weights.Queen.from_dataframe(gdf, use_index=False)
 
    # 3. Row-standardize
    w.transform = "R"
 
    return gdf, w
 
 
#----  Gi* Hot and Cold Spots ----#
def run_gistar():
    '''
<<<<<<< HEAD
    Runs Getis-Ord Gi* ONCE on the E2SFCA score for all tracts, using the full
    statewide neighbor structure (so urban tracts keep their rural neighbors).
    P-values are two-sided and FDR-adjusted across all tracts. Results are then
    summarized for all, urban and rural tracts, and overlaid with each LILA
    definition. Saves tract results and a LILA summary.
    '''
    # 1. Load data and build weights once, for the whole state
    gdf = load_data()
    gdf, w = build_weights(gdf)

    print("=" * 70)
    print(" Gi* COLDSPOT ANALYSIS")
    print("=" * 70)
    print(f"{len(gdf)} tracts, one statewide weights matrix")

    # 2. Run Gi* (star=True includes the tract itself)
    y = gdf[SCORE_COL].astype(float).values
    g = G_Local(y, w, star=True, permutations=N_PERM, seed=SEED)

    gdf["gi_z"] = g.Zs
    gdf["gi_p_raw"] = g.p_sim                       # one-sided, unadjusted
    gdf["gi_p"] = fdr_bh(two_sided(g.p_sim))        # two-sided, FDR-adjusted

    # 3. Classify using the adjusted p-value
    gdf["gi_class"] = "Not significant"
    gdf.loc[(gdf["gi_p"] < ALPHA) & (gdf["gi_z"] < 0), "gi_class"] = "Coldspot"
    gdf.loc[(gdf["gi_p"] < ALPHA) & (gdf["gi_z"] > 0), "gi_class"] = "Hotspot"

    raw_cold = ((two_sided(gdf["gi_p_raw"]) < ALPHA) & (gdf["gi_z"] < 0)).sum()
    print(f"Coldspots: {(gdf['gi_class'] == 'Coldspot').sum()} after FDR "
          f"({raw_cold} with unadjusted two-sided p)")
    print(f"Hotspots:  {(gdf['gi_class'] == 'Hotspot').sum()} after FDR")

    # 4. Summarize by group AFTER the statistic is computed
    groups = {
        "all": gdf,
        "urban": gdf[gdf[URBAN_COL] == 1],
        "rural": gdf[gdf[URBAN_COL] == 0],
    }

    summary_rows = []
    for name, sub in groups.items():
        print(f"Group: {name} ({len(sub)} tracts) | "
              f"coldspots: {(sub['gi_class'] == 'Coldspot').sum()}")

        # LILA overlay, using only tracts with a known LILA status
        known = sub[sub["in_usda"]]
        for col in LILA_COLS:
            if col not in known.columns:
                print(f"Warning: '{col}' missing. Skipping.")
                continue

            lila = known[known[col]]
            non_lila = known[~known[col]]

=======
    Runs Getis-Ord Gi* on the E2SFCA score for all, urban and rural
    tracts. Flags significant coldspots and hotspots and overlays them
    with each LILA definition. Saves tract results and a LILA summary.
    '''
    # 1. Load data and split into groups
    gdf = load_data()
    groups = split_by_urbanicity(gdf)
 
    tract_results = []
    summary_rows = []
 
    print("=" * 70)
    print(" Gi* COLDSPOT ANALYSIS")
    print("=" * 70)
 
    for name, sub in groups.items():
        print(f"Group: {name} ({len(sub)} tracts)")
 
        # 2. Build weights for this group
        sub, w = build_weights(sub)
 
        # 3. Run Gi* (star=True includes the tract itself)
        y = sub[SCORE_COL].astype(float).values
        g = G_Local(y, w, star=True, permutations=N_PERM, seed=SEED)
 
        sub["gi_z"] = g.Zs
        sub["gi_p"] = g.p_sim
 
        # 4. Classify as coldspot, hotspot or not significant
        sub["gi_class"] = "Not significant"
        sub.loc[(sub["gi_p"] < ALPHA) & (sub["gi_z"] < 0), "gi_class"] = "Coldspot"
        sub.loc[(sub["gi_p"] < ALPHA) & (sub["gi_z"] > 0), "gi_class"] = "Hotspot"
        sub["group"] = name
 
        # 5. Overlay with each LILA definition
        for col in LILA_COLS:
            if col not in sub.columns:
                print(f"Warning: '{col}' missing. Skipping.")
                continue
 
            lila = sub[sub[col]]
            non_lila = sub[~sub[col]]
 
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
            summary_rows.append({
                "group": name,
                "definition": col,
                "n_lila": len(lila),
                "n_non_lila": len(non_lila),
                "lila_coldspots": (lila["gi_class"] == "Coldspot").sum(),
                "pct_lila_coldspot": (lila["gi_class"] == "Coldspot").mean() * 100,
                "pct_non_lila_coldspot": (non_lila["gi_class"] == "Coldspot").mean() * 100,
                "pct_lila_hotspot": (lila["gi_class"] == "Hotspot").mean() * 100,
                "pct_non_lila_hotspot": (non_lila["gi_class"] == "Hotspot").mean() * 100,
            })
<<<<<<< HEAD

    # 5. Save results (group = "all" keeps shelf_visuals.py working unchanged)
    tract_out = gdf[["GEO_ID", SCORE_COL, "gi_z", "gi_p_raw", "gi_p", "gi_class",
                     "in_usda", URBAN_COL] +
                    [c for c in LILA_COLS if c in gdf.columns]].copy()
    tract_out.insert(1, "group", "all")
    tract_out.to_csv(OUT_GISTAR, index=False)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_GISTAR_SUMMARY, index=False)

=======
 
        n_cold = (sub["gi_class"] == "Coldspot").sum()
        print(f"  Coldspots: {n_cold}")
 
        tract_results.append(
            sub[["GEO_ID", "group", SCORE_COL, "gi_z", "gi_p", "gi_class"] +
                [c for c in LILA_COLS if c in sub.columns]]
        )
 
    # 6. Save results
    pd.concat(tract_results).to_csv(OUT_GISTAR, index=False)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_GISTAR_SUMMARY, index=False)
 
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    return summary_df
 
 
#---- Spearman Correlation ----#
def run_spearman():
    '''
    Calculates the Spearman correlation between the E2SFCA score and
    the retail access score for all, urban and rural tracts.
    Saves rho, p-value and number of tracts to csv.
    '''
    # 1. Load data and split into groups
    gdf = load_data()
    groups = split_by_urbanicity(gdf)
 
    results = []
 
    print("=" * 70)
    print(" SPEARMAN CORRELATION: FOOD SHELF vs RETAIL ACCESS")
    print("=" * 70)
 
    for name, sub in groups.items():
        # 2. Calculate the correlation
        rho, p_value = spearmanr(sub[SCORE_COL], sub[RETAIL_COL])
 
        print(f"Group: {name} | n = {len(sub)} | rho = {rho:.3f} | p = {p_value:.4f}")
 
        results.append({
            "group": name,
            "n_tracts": len(sub),
            "spearman_rho": rho,
            "p_value": p_value,
        })
 
    # 3. Save results
    results_df = pd.DataFrame(results)
    results_df.to_csv(OUT_SPEARMAN, index=False)
 
    return results_df
 
 
#----  Bivariate Local Moran's I ----#
def run_bivariate_moran():
    '''
    Runs Bivariate Local Moran's I with retail access at each tract
    and the E2SFCA score of its neighbors. Labels significant clusters
    as HH, LL, HL or LH (retail first, food shelf second) and
    overlays them with LILA. Saves tract results and a summary.
    '''
    # 1. Load data and build weights
    gdf = load_data()
    gdf, w = build_weights(gdf)
 
    print("=" * 70)
    print(" BIVARIATE LOCAL MORAN'S I (retail -> food shelf)")
    print("=" * 70)
 
    # 2. Run the bivariate statistic
    x = gdf[RETAIL_COL].astype(float).values
    y = gdf[SCORE_COL].astype(float).values
    moran = Moran_Local_BV(x, y, w, permutations=N_PERM, seed=SEED)
 
    gdf["moran_I"] = moran.Is
<<<<<<< HEAD
    gdf["moran_p_raw"] = moran.p_sim
    gdf["moran_p"] = fdr_bh(two_sided(moran.p_sim))
=======
    gdf["moran_p"] = moran.p_sim
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
 
    # 3. Convert the quadrant numbers (1-4) into labels
    quadrant_labels = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}
    gdf["moran_cluster"] = [quadrant_labels[q] for q in moran.q]
    gdf.loc[gdf["moran_p"] >= ALPHA, "moran_cluster"] = "Not significant"
 
    # 4. Count clusters overall and within each LILA definition
    summary_rows = []
    cluster_names = ["HH", "LH", "LL", "HL", "Not significant"]
 
    for col in ["all tracts"] + LILA_COLS:
        if col == "all tracts":
            sub = gdf
        elif col in gdf.columns:
<<<<<<< HEAD
            sub = gdf[gdf["in_usda"] & gdf[col]]
=======
            sub = gdf[gdf[col]]
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
        else:
            print(f"Warning: '{col}' missing. Skipping.")
            continue
 
        row = {"subset": col, "n_tracts": len(sub)}
        for c in cluster_names:
            row[f"pct_{c}"] = (sub["moran_cluster"] == c).mean() * 100
        summary_rows.append(row)
 
        print(f"{col}: " + ", ".join(
            f"{c}={(sub['moran_cluster'] == c).sum()}" for c in cluster_names))
 
    # 5. Save results
<<<<<<< HEAD
    keep = ["GEO_ID", RETAIL_COL, SCORE_COL, "moran_I", "moran_p", "moran_cluster", "in_usda"]
=======
    keep = ["GEO_ID", RETAIL_COL, SCORE_COL, "moran_I", "moran_p", "moran_cluster"]
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    gdf[keep + [c for c in LILA_COLS if c in gdf.columns]].to_csv(OUT_MORAN, index=False)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_MORAN_SUMMARY, index=False)
 
    return summary_df
 
 
#----  Quadrat Classification ----#
def run_quadrat():
    '''
    Classifies every tract into a 2x2 grid of low/high retail access
    and low/high food shelf access (split at the median). Counts how
    many tracts fall in each cell, overall and for each LILA definition.
    '''
    # 1. Load data
    gdf = load_data()
 
    # 2. Find the low/high cutoffs
    retail_cut = gdf[RETAIL_COL].quantile(SPLIT_Q)
    shelf_cut = gdf[SCORE_COL].quantile(SPLIT_Q)
 
    print("=" * 70)
    print(" 2x2 QUADRAT CLASSIFICATION")
    print("=" * 70)
    print(f"Retail cutoff: {retail_cut:.4f} | Food shelf cutoff: {shelf_cut:.4f}\n")
 
    # 3. Label each tract
    retail_high = gdf[RETAIL_COL] > retail_cut
    shelf_high = gdf[SCORE_COL] > shelf_cut
 
    gdf["quadrat"] = "Low retail / Low shelf"
    gdf.loc[~retail_high & shelf_high, "quadrat"] = "Low retail / High shelf"
    gdf.loc[retail_high & ~shelf_high, "quadrat"] = "High retail / Low shelf"
    gdf.loc[retail_high & shelf_high, "quadrat"] = "High retail / High shelf"
 
    # 4. Count tracts in each cell overall and for each LILA definition
    quadrat_names = ["Low retail / Low shelf", "Low retail / High shelf",
                     "High retail / Low shelf", "High retail / High shelf"]
    summary_rows = []
 
    for col in ["all tracts"] + LILA_COLS:
        if col == "all tracts":
            sub = gdf
        elif col in gdf.columns:
            sub = gdf[gdf[col]]
        else:
            print(f"Warning: '{col}' missing. Skipping.")
            continue
 
        row = {"subset": col, "n_tracts": len(sub)}
        for q in quadrat_names:
            row[f"n_{q}"] = (sub["quadrat"] == q).sum()
            row[f"pct_{q}"] = (sub["quadrat"] == q).mean() * 100
        summary_rows.append(row)
 
        print(f"{col}: " + ", ".join(
            f"{q}={(sub['quadrat'] == q).sum()}" for q in quadrat_names))
 
    # 5. Save results
<<<<<<< HEAD
    keep = ["GEO_ID", RETAIL_COL, SCORE_COL, "quadrat", "in_usda"]
=======
    keep = ["GEO_ID", RETAIL_COL, SCORE_COL, "quadrat"]
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    gdf[keep + [c for c in LILA_COLS if c in gdf.columns]].to_csv(OUT_QUADRAT, index=False)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_QUADRAT_SUMMARY, index=False)
 
    return summary_df
<<<<<<< HEAD
 


#--- Helper Functions to correct p-values ---#
 
def two_sided(p_sim):
    '''esda's pseudo p-values are one-sided; double them for a two-sided test.'''
    return np.minimum(np.asarray(p_sim, dtype=float) * 2, 1.0)


def fdr_bh(p):
    '''
    Benjamini-Hochberg false discovery rate adjustment.
    Returns adjusted p-values (q-values) in the original order.
    '''
    p = np.asarray(p, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]     # keep it monotone
    out = np.empty(n)
    out[order] = np.clip(adjusted, 0, 1)
    return out
=======
 
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
