# MinneMUDAC2026Outliers
## Q6 — Food Need and Food-Shelf Utilization

### Data sources and vintages

Q6 combines the competition data with several external public datasets. Dataset vintages are stated explicitly because geographic definitions and socioeconomic measures can change over time.

| Source | Vintage used | Purpose in Q6 |
|---|---|---|
| MinneMUDAC competition food-shelf activity data | 2022–2025 for the main historical analysis; 2024 for the primary county comparison | Household visits, individuals served, pounds distributed, reporting county, food bank, and site-level activity |
| MinneMUDAC organization/site data | Competition-provided file | Site information used to investigate physical location and reporting-county differences |
| U.S. Census Bureau, American Community Survey 5-year county estimates | 2022–2024 | County population, poverty rate, SNAP household rate, median household income, households without vehicles, and related socioeconomic measures |
| Feeding America, Map the Meal Gap | MMG 2025 file for 2022–2023 estimates; MMG 2026 file for 2024 estimates | County food-insecurity estimates used to construct the independent need benchmark |
| USDA Economic Research Service, Rural-Urban Continuum Codes | 2023 RUCC | County rurality and metro/nonmetro classification |
| U.S. Census Bureau County Adjacency File | 2024 | Neighbor-county pooling analysis used to test whether residents may obtain food assistance across county borders |
| U.S. Census Bureau Centers of Population | 2020 block-group mean centers | Population-weighted demand locations for the geographic-access analysis |
| U.S. Census Bureau TIGERweb | 2020 Census blocks | Physical site coordinates and county-location checks used in the spatial and reporting-boundary sensitivity analyses |

The primary Q6 comparison uses **2024** because it is the latest year for which the activity data, ACS county characteristics, and Feeding America food-insecurity estimates can be aligned directly. The 2025 persistence result uses actual 2025 food-shelf activity with the latest available 2024 population and food-insecurity benchmark and is therefore treated as a sensitivity check rather than a true 2025 need estimate.