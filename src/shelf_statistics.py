'''
shelf_statistics.py

Calculate statistics to compare E2SFCA score and LILA tracts:

This file consists of functions that calculate  various values that
seek to answer the question

1. Does the food shelf network sufficiently reach LILA areas?

This is done by producing a csv that contains:
    1. Median for LILA and non-LILA
    2. Cliffs Delta for LILA and non-LILA
    3. Quartiles for LILA and non-LILA
    
'''

import numpy as np
import pandas as pd


SUMMARY_PATH = "data/processed/tract_e2sfca_scores.csv"
TRACT_PATH = "data/processed/final_data.csv"
OUTPUT_PATH = "data/processed/shelf_statistics.csv"

LILA_COLS = ["LILATracts_1And10", "LILATracts_halfAnd10", "LILATracts_1And20"]
SCORE_COL = "e2sfca_mean"


def get_statistics():
    """
    Computes medians, Cliff's Delta, and bottom quartile shares 
    across USDA LILA definitions and saves results to CSV.
    """
    # 1. Load data
    summary = pd.read_csv(SUMMARY_PATH, dtype={"GEO_ID": str})
    tracts = pd.read_csv(TRACT_PATH, dtype={"GEO_ID": str})
    
    df = tracts.merge(summary, on="GEO_ID", how="inner")
<<<<<<< HEAD
    df = df[(df["population"] > 0) & df["in_usda"]].copy()
=======
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
    q25_threshold = df[SCORE_COL].quantile(0.25)
    
    results = []
    
    print("=" * 70)
    print(" LILA SENSITIVITY STATISTICS REPORT")
    print("=" * 70)
    print(f"Total Tracts: {len(df)} | Q25 Threshold: {q25_threshold:.4f}\n")
    
    for col in LILA_COLS:
        if col not in df.columns:
            print(f"Warning: '{col}' missing. Skipping.")
            continue
            
<<<<<<< HEAD
        df[col] = df[col].eq(1)
=======
        df[col] = df[col].astype(bool)
>>>>>>> 1d12938602ec54d6e6c3074c8d56820a2a622a49
        lila_group = df[df[col]][SCORE_COL].dropna()
        non_lila_group = df[~df[col]][SCORE_COL].dropna()
        
        med_lila = lila_group.median()
        med_non_lila = non_lila_group.median()
        c_delta = calculate_cliff_delta(lila_group.values, non_lila_group.values)
        
        share_lila_q1 = (lila_group <= q25_threshold).mean() * 100
        share_non_lila_q1 = (non_lila_group <= q25_threshold).mean() * 100
        
        print(f"Definition: {col}")
        print(f"  - Median Access (LILA / Non-LILA): {med_lila:.4f} / {med_non_lila:.4f}")
        print(f"  - Cliff's Delta: {c_delta:.4f}")
        print(f"  - Bottom Quartile Share (LILA / Non-LILA): {share_lila_q1:.1f}% / {share_non_lila_q1:.1f}%")
        print("-" * 70)
        
        results.append({
            "definition": col,
            "median_lila": med_lila,
            "median_non_lila": med_non_lila,
            "cliff_delta": c_delta,
            "share_lila_q1_pct": share_lila_q1,
            "share_non_lila_q1_pct": share_non_lila_q1
        })
        
    results_df = pd.DataFrame(results)
    results_df.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved statistics summary to {OUTPUT_PATH}")
    
    return results_df


def calculate_cliff_delta(x, y):
    nx, ny = len(x), len(y)
    if nx == 0 or ny == 0:
        return np.nan
    greater = np.sum(x[:, None] > y[None, :])
    less = np.sum(x[:, None] < y[None, :])
    return (greater - less) / (nx * ny)
