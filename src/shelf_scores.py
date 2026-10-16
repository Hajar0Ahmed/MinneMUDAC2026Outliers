'''
shelf_scores.py
 
Capacity-weighted E2SFCA scores for tracts, using Monte Carlo draws of
food shelf locations.
 
Steps:
1. Load the food shelf table, the draws CSV, and the tract table
2. Attach each shelf's capacity to its draws
3. Project the draws and tract centroids to meters (EPSG:32615)
4. For ONE draw: get the distance weight between every tract and shelf
5. E2SFCA step 1: for each shelf, supply / weighted demand in its catchment
6. E2SFCA step 2: for each tract, add up the ratios of shelves it can reach
7. Repeat for every draw
8. Save the tract scores to a CSV
'''
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial.distance import cdist

#---- settings ----#

SHELF_PATH = "data/processed/org_data.csv"
DRAWS_PATH = "data/processed/shelf_location_draws.csv"
TRACT_PATH = "data/processed/final_data.csv"

RUN = "primary"   # "primary" | "reported_only" | "equal_supply"
RUNS = {
    "primary":       {"sources": None, "equal": False},
    "reported_only": {"sources": ["reported", "reported_other_year"], "equal": False},
    "equal_supply":  {"sources": None, "equal": True},
}
SUFFIX = "" if RUN == "primary" else f"_{RUN}"

OUT_DIR = "data/processed"
SUMMARY_PATH = f"{OUT_DIR}/tract_e2sfca_scores.csv"
MATRIX_PATH = f"{OUT_DIR}/e2sfca_draws.npy"          # (n_draws, n_tracts)
INDEX_PATH = f"{OUT_DIR}/e2sfca_tract_index.csv"       # column order of the matrix
DRAW_IDS_PATH = f"{OUT_DIR}/e2sfca_draw_ids.csv"       # row order of the matrix

CAPACITY_COL = "capacity"
POP_COL = "population"
RATE_COL = "food_insecure"  

# Distance decay bands in miles: (from_miles, to_miles, weight)
BANDS_MILES = [(0,5,1.0),
               (5,10,.75),
               (10,20,.5),
               (20,30,.25)]

METERS_PER_MILE = 1609.344
PROJECTED_CRS = "EPSG:32615"


def get_scores():
    draws, tracts = load_inputs()
    matrix, draw_ids = run_e2sfca(draws, tracts)

    # Full per-draw matrix + interpretive orderings
    np.save(MATRIX_PATH, matrix.astype(np.float32))
    tracts[["GEO_ID", POP_COL]].to_csv(INDEX_PATH, index=False)
    pd.DataFrame({"draw": draw_ids}).to_csv(DRAW_IDS_PATH, index=False)

    # Summary across draws
    summary = pd.DataFrame({
        "GEO_ID": tracts["GEO_ID"].values,
        "e2sfca_mean": matrix.mean(axis=0),
        "e2sfca_median": np.median(matrix, axis=0),
        "e2sfca_std": matrix.std(axis=0),
        "e2sfca_p05": np.percentile(matrix, 5, axis=0),
        "e2sfca_p95": np.percentile(matrix, 95, axis=0),
        "share_draws_zero": (matrix == 0).mean(axis=0),
        "n_draws": matrix.shape[0],
    })
    summary.to_csv(SUMMARY_PATH, index=False)

    print(f"Saved matrix {matrix.shape} to {MATRIX_PATH}")
    print(f"Saved summary for {len(summary)} tracts to {SUMMARY_PATH}")


#---- loading data ----#

def load_inputs():
    '''
    Reads shelves, draws, and tracts. Validates capacities and missing values,
    then returns projected coordinates.
    '''
    shelves = pd.read_csv(SHELF_PATH, dtype={"GEO_ID": str, "_id_site": str})
    draws = pd.read_csv(DRAWS_PATH, dtype={"_id_site": str})
    tracts = pd.read_csv(TRACT_PATH, dtype={"GEO_ID": str})

    for df in (shelves, draws):
        df["_id_site"] = df["_id_site"].str.strip().str.replace(r"\.0$", "", regex=True)

    cfg = RUNS[RUN]
    n_before = len(shelves)
    shelves = shelves[shelves[CAPACITY_COL].notna() & (shelves[CAPACITY_COL] > 0)]
    if cfg["sources"]:
        shelves = shelves[shelves["capacity_source"].isin(cfg["sources"])]
    shelves = shelves[["_id_site", CAPACITY_COL]].drop_duplicates("_id_site")
    if cfg["equal"]:
        shelves[CAPACITY_COL] = 1.0
    print(f"[{RUN}] shelves used: {len(shelves)} of {n_before}")

    no_draws = set(shelves["_id_site"]) - set(draws["_id_site"])
    if no_draws:
        print(f"WARNING: {len(no_draws)} shelves have no location draws")

    draws = draws.merge(shelves, on="_id_site", how="inner", validate="many_to_one")
    per_draw = draws.groupby("draw").size()
    print(f"Shelves per draw: min {per_draw.min()}, max {per_draw.max()}")
    draws["x"], draws["y"] = project_xy(draws, "lon", "lat")

    # missing population defaults to zero demand
    tracts["GEO_ID"] = clean_geoid(tracts["GEO_ID"])
    tracts = tracts.dropna(subset=["cen_lat", "cen_lon"]).copy()
    tracts[POP_COL] = tracts[POP_COL].fillna(0)

    rate = tracts[RATE_COL].astype(float)
    if rate.max() > 1:                       
        rate = rate / 100

    # fall back to the population-weighted statewide mean if rate missing
    n_missing = int(rate.isna().sum())
    if n_missing:
        valid = rate.notna() & (tracts[POP_COL] > 0)
        fallback = np.average(rate[valid], weights=tracts.loc[valid, POP_COL])
        rate = rate.fillna(fallback)
        print(f"{n_missing} tracts missing {RATE_COL}; filled with {fallback:.3f}")

    tracts["demand"] = tracts[POP_COL] * (0.08 +  (0.34 * rate))
    
    assert tracts[["cen_lat", "cen_lon"]].notna().all().all(), "tracts missing centroids"
    
    tracts = tracts.reset_index(drop=True)
    tracts["x"], tracts["y"] = project_xy(tracts, "cen_lon", "cen_lat")

    n_zero = int((tracts[POP_COL] <= 0).sum())
    print(f"Tracts: {len(tracts)} ({n_zero} with zero population)")

    return draws, tracts


#---- E2SFCA calculation ----#

def run_e2sfca(draws, tracts):
    '''
    Runs E2SFCA for every Monte Carlo draw using vectorized distance matrices.
    Returns the full matrix (n_draws x n_tracts) plus draw IDs[cite: 1].
    '''
    tract_xy = tracts[["x", "y"]].to_numpy()
    tract_pop = tracts["demand"].to_numpy(dtype=float)

    scores, draw_ids = [], []
    for draw_id, one_draw in draws.groupby("draw", sort=True):
        shelf_xy = one_draw[["x", "y"]].to_numpy()
        shelf_cap = one_draw[CAPACITY_COL].to_numpy(dtype=float)
        scores.append(score_one_draw(tract_xy, tract_pop, shelf_xy, shelf_cap))
        draw_ids.append(draw_id)

    return np.vstack(scores), np.array(draw_ids)


def score_one_draw(tract_xy, tract_pop, shelf_xy, shelf_cap):
    '''
    E2SFCA Step 1 and Step 2 implementation for a single draw:
    - Step 1: Compute distance-decay weights and provider-to-population ratios.
    - Step 2: Sum discounted provider ratios at each demand tract[cite: 1].
    '''
    dist_m = cdist(tract_xy, shelf_xy)
    weights = get_weights(dist_m)

    # Step 1: Catchment population demand weighted by distance decay
    demand = (weights * tract_pop[:, None]).sum(axis=0)

    ratio = np.zeros_like(shelf_cap, dtype=float)
    has_demand = demand > 0
    ratio[has_demand] = shelf_cap[has_demand] / demand[has_demand]
    
    # sanity chceck cuz something broke
    scores = (weights * ratio[None, :]).sum(axis=1)
    assert np.isclose((scores * tract_pop).sum(), ratio[has_demand] @ demand[has_demand]), "supply not conserved"
    return scores



def get_weights(dist_m):
    '''Distance-decay weight matrix from BANDS_MILES; zero beyond the final threshold[cite: 1].'''
    weights = np.zeros_like(dist_m, dtype=float)
    for low, high, weight in BANDS_MILES:
        in_band = (dist_m >= low * METERS_PER_MILE) & (dist_m < high * METERS_PER_MILE)
        weights[in_band] = weight
    return weights



def clean_geoid(series):
    '''Keep the last 11 digits as a string, e.g. 1400000US27003050100 -> 27003050100.'''
    return series.astype(str).str.strip().str[-11:].str.zfill(11)


def project_xy(df, lon_col, lat_col):
    '''Returns projected x, y (meters) arrays for a table with lon/lat columns[cite: 1].'''
    pts = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
        crs="EPSG:4326",
    ).to_crs(PROJECTED_CRS)
    return pts.geometry.x.values, pts.geometry.y.values