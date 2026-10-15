'''
preprocess.py

Prepare data for geospatial analysis:

This file consist of three functions which perform data preprocessing by
cleaning and merging four data sources.

Data Sources:
1. Organizations.xlsls : A data set containing foodshelf locations
1. org_FSStats.xlsls : A data set containing foodshelf inventory details
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


def get_data():
    '''
    Combine and clean census data and USDA LILA data
    '''
    #---- READ MAP THE MEAL GAP DATA ----#
    mealgap_data = pd.read_excel("data/FeedingAmericaData/MMG2026_2024_Data_To_Share.xlsx",sheet_name="County")
     
       
    #---- USE CENSUS API TO PULL POPULATION DATA ----#
    api_key = '4ff816c06406e44741d590bd7c46957a7890ea22'
    c = Census(api_key)
    
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
    tract='*'  # asterisk means "all tracts"
    )
    
    #convert json to df
    census_data = pd.DataFrame(census_data)
    
    ## Create calculation columns
    
    census_data['GEO_ID'] = census_data['GEO_ID'].astype(str).str[-11:]
    
    #calculate poverty rate
    census_data['poverty_rate']= 100* (census_data['B17001_002E'].astype(int)/
                                       census_data['B17001_001E'].astype(int).replace({ 0 : np.nan }))
    
    #calculate number of poeple without vehicles
    census_data['no_vehicle']=(census_data['B25044_003E'].astype(int)+
                                   census_data['B25044_010E'].astype(int))/census_data['B25044_001E'].astype(int).replace({ 0 : np.nan })
    
    #calculate percent of households that recieve SNAP
    census_data['snap']= 100* (census_data['B22010_002E'].astype(int)/
                                       census_data['B22010_001E'].astype(int).replace({ 0 : np.nan }))
    
    census_data['other/multirace']=census_data['B02001_007E'].astype(int) +census_data['B02001_008E'].astype(int)
    
    #caclculate food insecurity prt tract using map the meal gap
    census_data['food_insecure']= ((census_data['poverty_rate']+
                                    census_data['snap'])/2)* mealgap_data["Overall Food Insecurity Rate"]
    
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
    
   
    census_data = pd.merge(census_data,cen, on=["GEO_ID"])
    
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
    usda_data= pd.read_csv("data/USDA/LRAM.csv")
    
    usda_data = usda_data[usda_data['State']== "Minnesota"]
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
    
    #write to a csv
    usda_data.to_csv("data/processed/usda_data.csv",index=False)
    
    
    #---- READ GROCERY ATLAS DATA ----#
    atlas_data = pd.read_csv("data/GroceryAtlasData/access_score.csv")
    
    atlas_data["GEO_ID"] = clean_geoid(atlas_data["GEOID"])
    atlas_data = atlas_data[atlas_data["GEO_ID"].str.startswith("27", na=False)]
    
    atlas_data = atlas_data.loc[:,['GEO_ID', 'gravity_2023','gravity_2023_state_percentile',
                                   'gravity_2023_county_percentile',"hhi_2023",
                                   'hhi_2023_state_percentile','hhi_2023_county_percentile',
                                   'segregation_ICE_Black_Alone_White_Alone',
                                   'segregation_2023_state_percentile',
                                   'segregation_2023_county_percentile']] 
    
     
    #write to csv
    atlas_data.to_csv("data/processed/atlas_data.csv",index=False)
    
    #--- Merge Results together across all data sets on GEO_ID
    data_frames = [census_data,usda_data,atlas_data]
    
    combined_data = functools.reduce(lambda left,right: pd.merge(left,right,on="GEO_ID"),data_frames)
    
    combined_data.to_csv("data/processed/combined_data.csv",index=False)
    
    #--- Merge in organization data 
    final_data = clean_org_data(combined_data)   
    
    final_data.to_csv("data/processed/final_data.csv",index=False)
    
    return(final_data)
    
    
    
    
    

def clean_org_data(combined_data):
    '''
    
    '''
    orgdata = pd.read_excel("data/ChallengeData/Organization.xlsx",
                        dtype={"block_geoid": str})
    orgstats = pd.read_excel("data/ChallengeData/org_FSStats.xlsx")
    
    
    #--- Clean Org Stats ---#
    orgstats["_id_site"] = orgstats._id_site.astype(str)
    orgstats = orgstats[orgstats["_Year"]==2024]
    
    
    orgstats = orgstats.loc[:,["_id_site","HouseholdsReg",
                               "IndividualsReg","PoundsReg", "FoodBank"]]
    
    orgstats = orgstats.dropna(subset=['_id_site'])
    
    orgstats = orgstats.groupby("_id_site",as_index=False).mean(numeric_only=True)
    
    # --- Clean Org Data ---#
    orgdata["GEO_ID"] = clean_geoid(orgdata["block_geoid"])
    
    #pick only active food shelfs 
    orgdata = orgdata[ (orgdata["isActive"]==1 ) &
                      (orgdata["AgencyType"] !="Farmers Market")] 
    
    #Update Zip code and City based on Mail Zip and City if NA
    orgdata = fill_zip_and_city(orgdata)
    
    #Filter for data sets without geographic information
    orgdata = orgdata[orgdata["GEO_ID"].notna() |
                    orgdata["Zip"].notna()]
    
    # Robust string ID cleaning (avoids float-to-int casting errors and removes '.0')
    orgdata["_id_site"] = (
        orgdata["__ID"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .replace(["nan", "None", "<NA>"], np.nan)
    )
    
    orgstats["_id_site"] = (
        orgstats["_id_site"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .replace(["nan", "None", "<NA>"], np.nan)
    )
    
    #IF GEO_ID is NA and Zipcode exists calculate estimate of census tract by Zip centroid
    imputed_orgdata = get_missing_tracts_from_zip(orgdata)
    
    #Merge them together (Inner join to exclude NA IDs)
    org_data = pd.merge(orgstats, imputed_orgdata, on="_id_site", how="inner")
    
    # Select Relevant columns of data (using org_data, not orgdata)
    org_data = org_data.loc[:, ["GEO_ID",
                                "City",
                                "Zip",
                                "_id_site",
                                "HouseholdsReg",
                                "IndividualsReg",
                                "PoundsReg",
                                "is_zip_centroid"]]
    
    #Write org_data as a csv
    org_data.to_csv("data/processed/org_data.csv",index=False)
    
    #Aggregate by GEO_ID to add this column to census data
    #shelf_count: number of food shelves in a census tract
    shelf_count = (org_data.dropna(subset=["GEO_ID"])
                        .groupby("GEO_ID").size()
                        .reset_index(name="shelf_count"))

    combined_data["GEO_ID"] = clean_geoid(combined_data["GEO_ID"])

    merged_df = pd.merge(combined_data, shelf_count, on="GEO_ID", how="left")
    merged_df["shelf_count"] = merged_df["shelf_count"].fillna(0).astype(int)
    
    return(merged_df)
    
    
    
    
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