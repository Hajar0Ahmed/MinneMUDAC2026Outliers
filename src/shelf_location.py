'''
shelf_location.py

This file consists of functions necessary to estimate coordinates for each food shelf.
This is done by conducting a montecarlo simulation that selects candidate locations
through numerous draws. These draws are conducted based on constraints to mitigate
for the assumption that a food shelf is equally likely to appear in every location.

This is done for applying constraints based on:
1. Zip code
2. Census Tract
3. City

The procedure is as follows:
1. Build the area the food shelf must be in 
(the overlap of its zip code, city and census tract)
2. Find every building in that area using OpenStreetMap
3. Pick one building at random, many times over. 

Only viable building coordinates are considered as candidate locations to prevent
coordinates from landing on bodies of water or empty plots of land.
'''


import numpy as np
import pandas as pd
import geopandas as gpd
import osmnx as ox
import time
import urllib.request
import zlib 
from pathlib import Path
from shapely.ops import unary_union

#---- Global variables----#
ox.settings.cache_folder = "data/osm_cache"   # saved downloads, so reruns skip them
ox.settings.requests_timeout = 180  
CRS = "EPSG:32615"          # projected CRS that measures in meters
MIN_AREA = 1_000            # ignore overlap areas smaller than this (square meters)
N_DRAWS = 200               # number of draws per food shelf
SEED = 42                   # keeps the random draws the same every run
OUTPUT_PATH = Path("data/processed/shelf_location_draws.csv")


# building types that are unlikely to be a food shelf
NON_TARGET = {"house", "detached", "semidetached_house", "residential",
              "apartments", "garage", "garages", "shed", "carport",
              "static_caravan", "hut", "cabin"}

#global variables to load in building data
PBF_PATH = Path("data/Spatial/minnesota-latest.osm.pbf")
PBF_URL = "https://download.geofabrik.de/north-america/us/minnesota-latest.osm.pbf"
BUILDINGS_PATH = Path("data/Spatial/mn_buildings.gpkg")
_all_buildings = None    


def get_locations():
    '''
    Load the food shelf data, run the monte carlo simulation and save the
    draws as a csv.
    '''

    #---- Load datan----#
    orgdata = pd.read_csv("data/processed/org_data.csv",
                      dtype={"GEO_ID": str, "Zip": str, "_id_site": str})
    orgdata["_id_site"] = orgdata["_id_site"].str.strip().str.replace(r"\.0$", "", regex=True)
    orgdata["Zip"] = orgdata["Zip"].str.extract(r"(\d{5})", expand=False) 
    
    n_all = len(orgdata)
    orgdata = orgdata[orgdata["capacity"].notna() & (orgdata["capacity"] > 0)]
    print(f"Placing {len(orgdata)} of {n_all} shelves (rest have no usable capacity)")

    #---- Load Boundary Maps ----#
    tracts, zips, places = load_boundaries(orgdata)

    #---- Run Simulation ----#
    draws = estimate_food_shelf_locations(orgdata, tracts, zips, places,
                                          n_draws=N_DRAWS, seed=SEED)

    #---- Save Draws ----#
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cols = ["_id_site", "draw", "lon", "lat", "constraint_used", "n_buildings"]
    draws[cols].to_csv(OUTPUT_PATH, index=False)



def estimate_food_shelf_locations(orgdata, tracts, zips, places,
                                  n_draws=200, seed=42):
    '''
    Run the monte carlo simulation. For every food shelf, pick a random
    building inside its area n_draws times.

    Returns a table with one row per food shelf per draw.
    '''

    all_draws = []        # one small table for each food shelf
    building_cache = {}   # stores buildings so we don't download them twice
    unplaced = []  
    
    for _, row in orgdata.iterrows():

        #--- Step 1: find the area this food shelf must be in
        zone, constraints_used = get_zone(row, tracts, zips, places)

        # skip food shelves we cannot place
        if zone is None:
            unplaced.append(row["_id_site"])  
            continue

        #--- Step 2: find the buildings inside that area
        cache_key = (constraints_used, str(row["Zip"]), str(row["City"]), str(row["GEO_ID"]))
        if cache_key not in building_cache:
            building_cache[cache_key] = get_building_points(zone)
        buildings = building_cache[cache_key]

        #--- Step 3: draw random locations
        # each food shelf gets its own random generator, so its draws do not
        # change if other food shelves are added or removed
        rng = np.random.default_rng([seed, zlib.crc32(str(row["_id_site"]).encode())])

        if len(buildings) > 0:
            # pick a random building n_draws times
            picks = rng.integers(0, len(buildings), n_draws)
            points = buildings.iloc[picks].values
        else:
            # no buildings were found, so pick random spots in the area instead
            random_spots = gpd.GeoSeries([zone], crs=CRS).sample_points(n_draws, rng=rng).iloc[0]
            points = list(random_spots.geoms)

        #--- Step 4: store the draws for this food shelf
        shelf_draws = pd.DataFrame({
            "_id_site": row["_id_site"],
            "draw": np.arange(n_draws),
            "constraint_used": constraints_used,
            "n_buildings": len(buildings),
            "geometry": points,
        })
        all_draws.append(shelf_draws)

    #---- Combine all food shelf draws ----#
    draws = pd.concat(all_draws, ignore_index=True)
    draws = gpd.GeoDataFrame(draws, geometry="geometry", crs=CRS)
    
    print(draws.groupby("constraint_used")["_id_site"].nunique())
    # convert to longitude and latitude
    draws = draws.to_crs(4326)
    draws["lon"] = draws.geometry.x
    draws["lat"] = draws.geometry.y

    return draws


def load_boundaries(orgdata, data_dir=None):
    '''
    Download (if needed) and read the three boundary maps:
    1. tracts: Minnesota census tracts
    2. zips: zip code areas, only for zips in the food shelf data
    3. places: Minnesota cities and towns
    '''
    data_dir = Path(data_dir) if data_dir else Path("data/Spatial")
    data_dir.mkdir(parents=True, exist_ok=True)

    zcta_path   = data_dir / "tl_2023_us_zcta520.zip"
    tracts_path = data_dir / "tl_2023_27_tract.zip"
    place_path  = data_dir / "tl_2023_27_place.zip"

    #---- Download files ----#
    downloads = {
        zcta_path:   "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip",
        tracts_path: "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_27_tract.zip",
        place_path:  "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_27_place.zip",
    }
    for path, url in downloads.items():
        if not path.exists():
            print(f"Downloading {path.name}...")
            urllib.request.urlretrieve(url, path)

    #---- Read maps ----#
    tracts = gpd.read_file(tracts_path)
    places = gpd.read_file(place_path)

    # Only read data from Minnesota
    zips = gpd.read_file(zcta_path, bbox=tuple(tracts.total_bounds))

    # keep only the zips in food shelf data
    wanted_zips = set(orgdata["Zip"].astype(str).str.zfill(5))
    zips = zips[zips["ZCTA5CE20"].isin(wanted_zips)]

    # switch all maps to the same CRS (meters) so areas can be measured
    return tracts.to_crs(CRS), zips.to_crs(CRS), places.to_crs(CRS)


def get_zone(row, tracts, zips, places):
    '''
    Find the area a food shelf must be in by overlapping its zip code,
    city and census tract.

    If the overlap is empty or too small (boundaries do not always line up),
    we drop the least trusted pieces one at a time.

    Returns the area and a label of the pieces that were used.
    '''

    #---- Find Area for each piece of info ----#
    areas = {
        "zip":   get_polygon(zips,   "ZCTA5CE20", row["Zip"]),
        "city":  get_polygon(places, "NAME",       row["City"]),
        "tract": get_polygon(tracts, "GEOID",      row["GEO_ID"]),
    }

    #---- Handele zip_centroid columns seperately ----#
    if row["is_zip_centroid"] == 1:
        # the tract was only estimated from the zip centroid so we disregard tract
        options = [["zip", "city"], ["zip"]]
    else:
        options = [["zip", "city", "tract"], ["zip", "tract"], ["city", "tract"],
                   ["tract"], ["zip", "city"], ["zip"]]

    #---- Use the the first combination that gives us usable area ----#
    for option in options:

        # skip this combination if one of its pieces was not found
        if any(areas[name] is None for name in option):
            continue

         # overlap the pieces
        zone = areas[option[0]]
        for name in option[1:]:
            zone = zone.intersection(areas[name])

        # remove stray lines and points left over from the overlap
        zone = keep_polygons(zone)

        # skip this combination if no polygon is left
        if zone is None:
            continue

        # keep it only if it is big enough to be meaningful
        if zone.area > MIN_AREA:
            return zone, "+".join(option)

    return None, "none"


def get_polygon(table, column, value):
    '''
    Find the rows of a map where column matches value and merge them into
    one area. Returns None if nothing matches.
    '''
    table_values = table[column].astype(str).str.lower().str.strip()
    matches = table[table_values == str(value).lower().strip()]

    if len(matches) == 0:
        return None

    return matches.geometry.union_all()


def get_building_points(zone):
    '''
    Find every building inside the zone using OpenStreetMap and return one
    point inside each building.
    '''

    #---- Find Buildings in the zone ----#
    zone_lonlat = gpd.GeoSeries([zone], crs=CRS).to_crs(4326).iloc[0]
    buildings = download_buildings(zone_lonlat)

    # keep only buildings drawn as areas, not single points or lines
    buildings = buildings[buildings.geom_type.isin(["Polygon", "MultiPolygon"])]

    #if no buildings found pick a random spot
    if buildings.empty:
        return gpd.GeoSeries([], crs=CRS)

    buildings = buildings.to_crs(CRS)

    #---- look for places that are not housing (churches, community centers, stores) ----#
    # if every building is housing, keep them all
    if "building" in buildings.columns:
        non_housing = buildings[~buildings["building"].isin(NON_TARGET)]
        if len(non_housing) > 0:
            buildings = non_housing

    points = buildings.geometry.representative_point()

    # keep only points inside the zone
    return points[points.within(zone)]




def download_buildings(zone_lonlat):
    '''
    Find the buildings that touch a zone using the Minnesota OpenStreetMap
    file saved on this computer.

    The first call reads every building in the state (slow, a few minutes)
    and saves them, so later calls and later runs are fast.
    '''

    global _all_buildings

    #---- Step 1: load all Minnesota buildings (only the first time) ----#
    if _all_buildings is None:

        if BUILDINGS_PATH.exists():
            # use the saved copy from an earlier run
            _all_buildings = gpd.read_file(BUILDINGS_PATH)
        else:
            #---- Download the OSM file if it is not on this computer ----#
            if not PBF_PATH.exists():
                print("Downloading Minnesota OSM file (one time, a few hundred MB)...")
                PBF_PATH.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(PBF_URL, PBF_PATH)

            # read the buildings from the OSM file and save them for next time
            print("Reading buildings from the OSM file (one time, a few minutes)...")
            buildings = gpd.read_file(PBF_PATH, layer="multipolygons",
                                      where="building IS NOT NULL", engine="pyogrio")
            buildings = buildings[["building", "amenity", "name", "geometry"]]
            buildings.to_file(BUILDINGS_PATH, driver="GPKG")
            _all_buildings = buildings

    #---- Step 2: find the buildings that touch this zone ----#
    # the spatial index finds nearby buildings quickly
    hits = _all_buildings.sindex.query(zone_lonlat, predicate="intersects")
    return _all_buildings.iloc[hits]

def keep_polygons(shape):
    '''
    Make sure an area is a Polygon or MultiPolygon.
    Overlapping boundaries can leave behind stray lines and points,
    so we throw those away and keep only the polygon pieces.

    Returns None if there is no polygon left.
    '''

    #---- FIX INVALID SHAPES ----#
    # buffer(0) repairs shapes that cross over themselves
    if not shape.is_valid:
        shape = shape.buffer(0)

    #---- ALREADY A POLYGON ----#
    if shape.geom_type in ("Polygon", "MultiPolygon"):
        return shape

    #---- MIXED SHAPES: KEEP ONLY THE POLYGON PARTS ----#
    if shape.geom_type == "GeometryCollection":
        polygons = [part for part in shape.geoms
                    if part.geom_type in ("Polygon", "MultiPolygon")]
        if polygons:
            return unary_union(polygons)

    # lines and points cannot be used as an area
    return None