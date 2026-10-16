'''
preprocess.py
 
Prepare data for geospatial analysis:
 
This file performs data preprocessing by cleaning and merging four data sources.
 
Data Sources:
1. Organizations.xlsx : A data set containing foodshelf locations
1. org_FSStats.xlsx : A data set containing foodshelf inventory details
2. Census bureau data: A series of data sets that provide income and 
demographic information across each census tract
3. USDA data: The Food Access Reasearch atlas data set classifies tracts as
low income low access (LILA)
4. Grocery Gap Atlas: A data set that contains the grocery store access scores
across each census 
 
'''
 
import pandas as pd
import numpy as np
import geopandas as gpd
import urllib.request
import functools
import pgeocode
from census import Census
import os
from pathlib import Path
import us 
 
 
CENSUS_API_KEY = '4ff816c06406e44741d590bd7c46957a7890ea22'   # move to an env var / regenerate
 
TARGET_YEAR = 2024          # year the analysis is anchored to
MIN_COUNTY_SITES = 3        # min reporting shelves for a county median to be used
MEASURES = ["IndividualsReg", "HouseholdsReg", "PoundsReg"]
 
 
def get_data():
    '''
    Combine and clean census data and USDA LILA data
    '''
    #---- READ MAP THE MEAL GAP DATA ----#
    mmg = pd.read_excel("data/FeedingAmericaData/MMG2026_2024_Data_To_Share.xlsx",
                    sheet_name="County")
    
    mmg = mmg[(mmg["State"] == "MN") & (mmg["Year"] == 2024)].copy()
    
    mmg["county_fips"] = (pd.to_numeric(mmg["FIPS"], errors="coerce")
                            .astype("Int64").astype("string").str.zfill(5))
    
    mmg = mmg[["county_fips", "Overall Food Insecurity Rate"]].rename(
        columns={"Overall Food Insecurity Rate": "county_fi_rate"})
 
       
    #---- USE CENSUS API TO PULL POPULATION DATA ----#
    c = Census(CENSUS_API_KEY)
    
    census_data = c.acs5.state_county_tract(
    fields=['GEO_ID',
            'B01003_001E', #Population
            'B25002_002E', #Occupied Housing Units
            'B02001_002E', #White
            'B02001_003E', #Black
            'B02001_004E', #Native
            'B02001_005E', #Asian
            'B02001_006E', #pacific islander
            'B02001_007E', #other race
            'B02001_008E', # multiracial
            'B03001_003E', #Hispanic
            'B05001_006E', #not U.s citizen
            'B19013_001E', #Median Income
            'B17001_001E', #pop for whihc poverty determined
            'B17001_001M', #moe for poverty
            'B17001_002E', #people below poverty line
            'B17001_002M', #moe for below poverty line
            'B25044_003E', #does not own vehicle (owns)
            'B25044_010E', #does not own vehicle (rents)
            'B25044_001E', #vehicles available
            'B22010_002E', #households that recieved SNAP
            'B22010_001E', #SNAP total
            ],
    state_fips='27',
    county_fips='*',
    tract='*',  # asterisk means "all tracts"
    year=2023
    )
    
    #convert json to df
    census_data = pd.DataFrame(census_data)
    
    ## Create calculation columns
    
    census_data["GEO_ID"] = census_data["state"] + census_data["county"] + census_data["tract"]
    census_data["county_fips"] = census_data["state"] + census_data["county"]
    
    est_cols = [c_ for c_ in census_data.columns if c_.startswith("B")]
    census_data[est_cols] = census_data[est_cols].apply(pd.to_numeric, errors="coerce")
    census_data[est_cols] = census_data[est_cols].mask(census_data[est_cols] < -1e8)
    
    
    #calculate poverty rate
    census_data["poverty_rate"] = 100 * safe_div(census_data["B17001_002E"], census_data["B17001_001E"])
    
    census_data["snap"] = 100 * safe_div(census_data["B22010_002E"], census_data["B22010_001E"])
    
    census_data["no_vehicle"] = safe_div(census_data["B25044_003E"] + census_data["B25044_010E"],
                                         census_data["B25044_001E"])
    
    census_data["other/multirace"] = census_data["B02001_007E"] + census_data["B02001_008E"]
    
    #rename columns
    census_data.rename(columns={"B01003_001E": "population",
                                "B25002_002E": "housing_units",
                                "B02001_002E":"white",
                                "B02001_003E":"black",
                                "B02001_004E":"native",
                                "B02001_005E":"asian",
                                "B02001_006E":"pacific_islander",
                                "B03001_003E":"hispanic",
                                "B05001_006E":"not_citizen",
                                "B19013_001E":"median_income",
                                "B17001_002M":"moe_poverty"}, inplace=True)
    
    
    #add longitude and latidue of centroid for each census tract
    url = "https://www2.census.gov/geo/docs/reference/cenpop2020/tract/CenPop2020_Mean_TR27.txt"
    cen = pd.read_csv(url, dtype=str, encoding="utf-8-sig")
    cen["GEO_ID"] = cen["STATEFP"] + cen["COUNTYFP"] + cen["TRACTCE"]
    cen = cen.rename(columns={"LATITUDE": "cen_lat", "LONGITUDE": "cen_lon"})
    
   
    census_data = census_data.merge(cen[["GEO_ID", "cen_lat", "cen_lon"]],
                                    on="GEO_ID", how="left", validate="one_to_one")
    
    print("Tracts with no centroid:", census_data["cen_lat"].isna().sum())
    
    
    # ---- impute tract-level inputs ----
    census_data = impute_by_county(
        census_data, ["median_income", "poverty_rate", "snap", "no_vehicle"])
 
 
    # ---- tract food insecurity: scale county rate by relative tract need ----
    census_data = census_data.merge(mmg, on="county_fips", how="left", validate="many_to_one")
    census_data["need_index"] = (census_data["poverty_rate"] + census_data["snap"]) / 2
    w = census_data["population"].fillna(0)
    county_need = ((census_data["need_index"] * w).groupby(census_data["county_fips"]).transform("sum")
                   / w.groupby(census_data["county_fips"]).transform("sum").replace(0, np.nan))
    census_data["food_insecure"] = (census_data["county_fi_rate"]
                                    * census_data["need_index"] / county_need).clip(0, 1)
    census_data["food_insecure"] = census_data["food_insecure"].fillna(census_data["county_fi_rate"])
    
    
    
    #select relevant columns
    census_data = census_data.loc[:,['GEO_ID','population','median_income',
                                     'poverty_rate','moe_poverty','food_insecure',
                                     'no_vehicle','snap',
                                     'white', 'black', 'native', 'asian',
                                     'pacific_islander','other/multirace','hispanic','not_citizen',
                                     "cen_lat","cen_lon"]]
 
    #write to a csv
    census_data.to_csv("data/processed/census_data.csv",index=False)
    
    
    #---- READ USDA LRAM and SRAM DATA ----#
    usda_data= pd.read_csv("data/USDA/LRAM.csv", low_memory=False)
    
    usda_data = usda_data[usda_data['State']== "Minnesota"].copy()
    usda_data["GEO_ID"] = clean_geoid(usda_data["CensusTract"])
    
    usda_data.rename(columns={ "PovertyRate":"usda_poverty_rate",
                              "MedianFamilyIncome":"usda_median_income",
                              "TractHUNV":"usda_no_vehicle",
                              "TractSNAP":"usda_snap",
                              "TractLOWI":"low_income_pop",
                              },inplace=True)
    usda_data = usda_data.drop(columns=["CensusTract", "Pop2010", "OHU2010",
                                        "GroupQuartersFlag","NUMGQTRS","PCTGQTRS",
                                        "TractWhite","TractBlack","TractAsian","TractNHOPI",
                                        "TractAIAN","TractOMultir", "TractHispanic"])
    
    #explicit match flag (a NaN in a USDA column can also be a real missing value)
    usda_data["in_usda"] = True
    
    #write to a csv
    usda_data.to_csv("data/processed/usda_data.csv",index=False)
    
    
    #---- READ GROCERY ATLAS DATA ----#
    atlas_data = pd.read_csv("data/GroceryAtlasData/access_score.csv", low_memory=False)
 
    atlas_data["GEO_ID"] = clean_geoid(atlas_data["GEOID"])
    atlas_data = atlas_data[atlas_data["GEO_ID"].str.startswith("27", na=False)]
 
    atlas_data = atlas_data.loc[:,['GEO_ID', 'gravity_2023','gravity_2023_state_percentile',
                                   'gravity_2023_county_percentile',"hhi_2023",
                                   'hhi_2023_state_percentile','hhi_2023_county_percentile',
                                   'segregation_ICE_Black_Alone_White_Alone',
                                   'segregation_2023_state_percentile',
                                   'segregation_2023_county_percentile']] 
    
    atlas_data = atlas_data.drop_duplicates()
    assert atlas_data["GEO_ID"].is_unique, "Atlas has conflicting rows per tract"
 
    #write to csv
    atlas_data.to_csv("data/processed/atlas_data.csv",index=False)
    
    #--- Merge Results together across all data sets on GEO_ID
    combined = (census_data
            .merge(usda_data, on="GEO_ID", how="left", validate="one_to_one")
            .merge(atlas_data, on="GEO_ID", how="left", validate="one_to_one"))
    
    combined["in_usda"] = combined["in_usda"].fillna(False).astype(bool)
    
    print("Not in USDA :", (~combined["in_usda"]).sum())
    print("Not in Atlas:", combined["gravity_2023"].isna().sum())
    
    combined.to_csv("data/processed/combined_data.csv",index=False)
    
    #--- Merge in organization data 
    final_data = clean_org_data(combined)   
    
    final_data.to_csv("data/processed/final_data.csv",index=False)
    
    return(final_data)
    
    
    
    
    
 
def clean_org_data(combined_data):
    '''
    Build the shelf table (org_data.csv) and add shelf_count to the tract table.
 
    Shelves kept: active, not a farmers market, not a meal program, and either
    flagged as a distribution site or present in the stats file. Parent
    "Agency" records (isDistributionSite == 0, no stats) are administrative
    umbrellas for the real sites, so they are not shelves.
    '''
    orgdata = pd.read_excel("data/ChallengeData/Organization.xlsx",
                        dtype={"block_geoid": str})
    orgstats = pd.read_excel("data/ChallengeData/org_FSStats.xlsx")
 
    #--- Clean ids (keeps real decimal ids like 13462.1, strips only ".0") ---#
    orgdata["_id_site"] = clean_site_id(orgdata["__ID"])
    orgstats["_id_site"] = clean_site_id(orgstats["_id_site"])
    orgstats = orgstats.dropna(subset=["_id_site"])
    
    stats_ids = set(orgstats["_id_site"])
    
    # --- Clean Org Data ---#
    orgdata["GEO_ID"] = clean_geoid(orgdata["block_geoid"])
    
    #pick only active food shelves: drop farmers markets and meal programs.
    is_meal = orgdata["AgencyType"].astype("string").str.contains("meal", case=False, na=False)
    is_dist = (orgdata["isDistributionSite"] == 1) | orgdata["_id_site"].isin(stats_ids)
    
    orgdata = orgdata[(orgdata["isActive"] == 1) &
                      (orgdata["AgencyType"] != "Farmers Market") &
                      ~is_meal &
                      is_dist].copy()
    
    #Update Zip code and City based on Mail Zip and City if NA
    orgdata = fill_zip_and_city(orgdata)
    
    #Filter for data sets without geographic information
    orgdata = orgdata[orgdata["GEO_ID"].notna() |
                    orgdata["Zip"].notna()]
    
    #IF GEO_ID is NA and Zipcode exists calculate estimate of census tract by Zip centroid
    imputed_orgdata = get_missing_tracts_from_zip(orgdata)
    
    #--- Capacity calculation ---# 
    capacity = build_capacity(orgstats, TARGET_YEAR)
    
    #keep shelves with no stats so they can be flagged / imputed
    org_data = imputed_orgdata.merge(capacity, on="_id_site", how="left", validate="one_to_one")
    org_data = impute_missing_capacity(org_data, stats_ids)
    
    print("\nShelf capacity sources:")
    print(org_data["capacity_source"].value_counts(dropna=False))
    
    # Select Relevant columns of data
    org_data = org_data.loc[:, ["GEO_ID",
                                "City",
                                "Zip",
                                "County",
                                "AgencyType",
                                "_id_site",
                                "capacity",
                                "capacity_source",
                                "capacity_year",
                                "is_zip_centroid"]]
    
    #Write org_data as a csv
    org_data.to_csv("data/processed/org_data.csv",index=False)
    
    #Aggregate by GEO_ID to add this column to census data
    #shelf_count: number of food shelves with a usable capacity in a census tract
    shelf_count = (org_data.dropna(subset=["GEO_ID", "capacity"])
                        .groupby("GEO_ID").size()
                        .reset_index(name="shelf_count"))
 
    combined_data["GEO_ID"] = clean_geoid(combined_data["GEO_ID"])
 
    merged_df = pd.merge(combined_data, shelf_count, on="GEO_ID", how="left")
    merged_df["shelf_count"] = merged_df["shelf_count"].fillna(0).astype(int)
    
    return(merged_df)
    
    
    
def clean_site_id(s):
    '''Site ids as strings. Only a trailing '.0' is stripped, because ids such
    as 13462.1 are real, distinct sites (casting to int would merge them).'''
    return (s.astype(str)
             .str.strip()
             .str.replace(r"\.0$", "", regex=True)
             .replace(["nan", "None", "<NA>"], np.nan))
 
 
def pos_mean(x):
    '''Mean of the positive months only. A 0 or blank month means 'not
    reported', not 'served nobody', so zeros must not drag the average down.'''
    x = x[x > 0]
    return x.mean() if len(x) else np.nan
 
 
def build_capacity(orgstats, target_year=TARGET_YEAR):
    '''
    One capacity value per site (typical monthly individuals served).
 
    Preference order, most to least trusted. Years are ranked by distance from
    target_year (ties go to the earlier year), and within a year the measures
    are tried in order, so a same-year households figure beats a stale
    individuals figure from another year.
        reported               IndividualsReg
        households_converted   HouseholdsReg  * median(Individuals / Households)
        pounds_converted       PoundsReg      * median(Individuals / Pounds)
    '''
    site_year = (orgstats.groupby(["_id_site", "_Year"])[MEASURES]
                         .agg(pos_mean)
                         .reset_index())
    
    # conversion ratios estimated from site-years that report both measures
    hh_ratio = (site_year["IndividualsReg"] / site_year["HouseholdsReg"]).median()
    lb_ratio = (site_year["IndividualsReg"] / site_year["PoundsReg"]).median()
    print(f"Capacity ratios: {hh_ratio:.2f} individuals per household, "
          f"{lb_ratio:.4f} individuals per pound")
    
    steps = [("IndividualsReg", "reported", 1.0),
             ("HouseholdsReg", "households_converted", hh_ratio),
             ("PoundsReg", "pounds_converted", lb_ratio)]
    
    candidates = []
    for order, (col, label, factor) in enumerate(steps):
        d = site_year[["_id_site", "_Year", col]].dropna()
        d = d.assign(capacity=d[col] * factor, source=label, order=order)
        candidates.append(d[["_id_site", "_Year", "capacity", "source", "order"]])
    
    cand = pd.concat(candidates, ignore_index=True)
    cand["year_gap"] = (cand["_Year"] - target_year).abs()
    
    best = (cand.sort_values(["_id_site", "year_gap", "_Year", "order"])
                .drop_duplicates("_id_site")
                .rename(columns={"_Year": "capacity_year"}))
    
    other_year = best["capacity_year"] != target_year
    best["capacity_source"] = np.where(other_year, best["source"] + "_other_year", best["source"])
    
    return best[["_id_site", "capacity", "capacity_source", "capacity_year"]]
 
 
def impute_missing_capacity(org_data, stats_ids):
    '''
    Fill capacity ONLY for distribution sites that never appear in the stats
    file (unknown size), using the median of reporting shelves in the same
    county (>= MIN_COUNTY_SITES of them), else the statewide median.
 
    Sites that DO appear in the stats file but never report a positive
    individuals / households / pounds figure are left as "none": they report
    zeros, which is not the same as unknown, and are most likely not pantries.
    '''
    org_data = org_data.copy()
    
    never_reported = org_data["capacity"].isna() & ~org_data["_id_site"].isin(stats_ids)
    
    reporting = org_data[org_data["capacity"].notna()]
    state_median = reporting["capacity"].median()
    
    by_county = reporting.groupby("County")["capacity"].agg(["median", "size"])
    county_median = by_county.loc[by_county["size"] >= MIN_COUNTY_SITES, "median"]
    
    county_fill = org_data.loc[never_reported, "County"].map(county_median)
    org_data.loc[never_reported, "capacity"] = county_fill.fillna(state_median)
    org_data.loc[never_reported, "capacity_source"] = np.where(
        county_fill.notna(), "imputed_county_median", "imputed_state_median")
    
    org_data["capacity_source"] = org_data["capacity_source"].fillna("none")
    return org_data
    
    
    
def get_missing_tracts_from_zip(data, data_dir=None):
    data_dir = Path(data_dir) if data_dir else Path("data/Spatial")
    data_dir.mkdir(parents=True, exist_ok=True)
 
    df = data.copy()
 
    # keep existing 0/1 convention; NaN -> 0
    if "is_zip_centroid" not in df.columns:
        df["is_zip_centroid"] = 0
        
    df["is_zip_centroid"] = df["is_zip_centroid"].fillna(0).astype(int)
 
    missing_mask = df["GEO_ID"].isna()
    if not missing_mask.any():
        return df
 
    # Zip, falling back to the mailing zip
    zip5 = clean_zip(df["Zip"]).fillna(clean_zip(df["MailZip"]))
    needed_zips = zip5[missing_mask].dropna().unique()
    if len(needed_zips) == 0:
        print(f"{missing_mask.sum()} rows missing GEO_ID and no zip to impute from.")
        return df
 
    zcta_path = data_dir / "tl_2023_us_zcta520.zip"
    if not zcta_path.exists():
        print("Downloading national ZCTA file (one time)...")
        urllib.request.urlretrieve(
            "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip",
            zcta_path,
        )
 
    tracts_path = data_dir / "tl_2023_27_tract.zip"
    if not tracts_path.exists():
        urllib.request.urlretrieve(
            "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_27_tract.zip",
            tracts_path,
        )
 
    # Read only needed ZCTAs; fall back to full read if `where` isn't supported
    where = "ZCTA5CE20 IN (" + ",".join(f"'{z}'" for z in needed_zips) + ")"
    try:
        zcta_gdf = gpd.read_file(zcta_path, where=where)
    except Exception:
        zcta_gdf = gpd.read_file(zcta_path)
        zcta_gdf = zcta_gdf[zcta_gdf["ZCTA5CE20"].isin(needed_zips)]
 
    tracts_gdf = gpd.read_file(tracts_path)
 
    zcta_proj = zcta_gdf.to_crs(5070)
    tracts_proj = tracts_gdf.to_crs(5070)
 
    pts = gpd.GeoDataFrame(
        {"ZCTA5CE20": zcta_proj["ZCTA5CE20"].values},
        geometry=zcta_proj.geometry.representative_point().values,
        crs=5070,
    )
 
    joined = gpd.sjoin(pts, tracts_proj[["GEOID", "geometry"]],
                       how="left", predicate="within")
    zip_to_geoid = (
        joined.drop_duplicates("ZCTA5CE20")
              .dropna(subset=["GEOID"])
              .set_index("ZCTA5CE20")["GEOID"]
    )
 
    # Fill only missing rows, and flag only the ones actually filled
    filled = zip5[missing_mask].map(zip_to_geoid)
    df.loc[missing_mask, "GEO_ID"] = filled
    df.loc[filled.index[filled.notna()], "is_zip_centroid"] = 1
 
    print(f"Imputed {filled.notna().sum()} GEO_IDs; "
          f"{df['GEO_ID'].isna().sum()} still missing.")
    return df
 
 
def fill_zip_and_city(df):
    """Fill Zip from MailZip, then fill City (MailCity -> own data -> zip lookup)."""
    df = df.copy()
 
    # fall back to MailZip when Zip is empty
    zip_orig = clean_zip(df["Zip"])
    mail_zip = clean_zip(df["MailZip"])
    df["Zip"] = zip_orig.fillna(mail_zip)
    used_mail = zip_orig.isna() & mail_zip.notna()
 
    #normalize blanks to missing    
    df["City"] = df["City"].astype("string").str.strip().replace("", pd.NA)
 
    # If the zip came from mailing address, use the mailing city
    mail_city = df["MailCity"].astype("string").str.strip()
    df.loc[used_mail, "City"] = df.loc[used_mail, "City"].fillna(mail_city[used_mail])
 
    #Use the most common city for that zip 
    known = df.dropna(subset=["Zip", "City"])
    zip_to_city = known.groupby("Zip")["City"].agg(lambda x: x.mode().iat[0])
    need = df["City"].isna() & df["Zip"].notna()
    df.loc[need, "City"] = df.loc[need, "Zip"].map(zip_to_city)
 
    # use zip code to fill remaining cities
    need = df["City"].isna() & df["Zip"].notna()
    if need.any():
        res = pgeocode.Nominatim("us").query_postal_code(df.loc[need, "Zip"].tolist())
        df.loc[need, "City"] = res["place_name"].values
 
    return df
 
def impute_by_county(df, cols, weight="population", group="county_fips"):
    """Fill NaNs with the county pop-weighted mean, then the statewide mean.
    Adds <col>_imputed flags."""
    df = df.copy()
    for col in cols:
        missing = df[col].isna()
        df[f"{col}_imputed"] = missing
 
        w = df[weight].where(df[col].notna(), 0).fillna(0)
        num = (df[col].fillna(0) * w).groupby(df[group]).transform("sum")
        den = w.groupby(df[group]).transform("sum").replace(0, np.nan)
        county_mean = num / den
 
        valid = df[col].notna() & (df[weight] > 0)
        state_mean = (np.average(df.loc[valid, col], weights=df.loc[valid, weight])
                      if valid.any() else df[col].mean())
 
        df[col] = df[col].fillna(county_mean).fillna(state_mean)
        print(f"{col}: imputed {missing.sum()} of {len(df)} tracts")
    return df
 
def clean_zip(s):
    """Normalize to a 5-digit string; handles floats, ZIP+4, NaN."""
    return s.astype(str).str.extract(r"(\d{5})", expand=False)
 
 
def clean_geoid(s, length=11):
    """Return tract IDs as clean strings; trims 15-digit block IDs to the
    11-digit tract and leaves anything invalid as missing."""
    out = (
        s.astype("string")
         .str.strip()
         .str.replace(r"\.0$", "", regex=True)
         .str[:length]
    )
    return out.where(out.str.len() == length)
 
def safe_div(a, b):
    return a / b.where(b > 0)
 