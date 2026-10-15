import pandas as pd
import numpy as np

df = pd.read_excel(r"C:\Users\nafib\OneDrive\Desktop\Challenge Minnemudac\org_FSStats.xlsx")
df["Date"] = pd.to_datetime(df["DateForSearch"])
df["County"] = df["County"].replace({
    "Saint Louis": "St. Louis",
    "Hennepin-Minneapolis": "Hennepin", "Hennepin-Suburbs": "Hennepin",
    "Ramsey-Saint Paul": "Ramsey", "Ramsey-Suburbs": "Ramsey",
})
metrics = ["HouseholdsReg", "PoundsReg", "ChildrenReg", "SeniorsReg", "AdultsReg"]

# Cleaning rules (write these down for the judges)
df = df[df["_Month"] != 0]                                    # second copy of Dec 2022
df = df.dropna(subset=metrics, how="all")                     # fully blank rows
df = df.drop_duplicates(subset=["_id_site", "Date"] + metrics)  # exact copies
allzero = (df[metrics].fillna(0) == 0).all(axis=1)
shared = df.duplicated(subset=["_id_site", "Date"], keep=False)
df = df[~(allzero & shared)]                                  # zero placeholder next to a real row

# One row per county per month; rows for the same site-month are added
cm = df.groupby(["County", "Date"])[metrics].sum(min_count=1)
cm["n_sites"] = df.groupby(["County", "Date"])["_id_site"].nunique()
cm = cm.reset_index()

# Checks
print(cm["County"].nunique(), "counties,", cm["Date"].nunique(), "months (expect 86 and 55)")
months = cm.groupby("County").size()
print(months[months < 55])

cm["Year"], cm["Month"] = cm["Date"].dt.year, cm["Date"].dt.month
aug = cm[cm["Month"] == 8].pivot(index="County", columns="Year", values="HouseholdsReg")
print(aug.loc[["Hennepin", "Waseca", "Kanabec"]])

cm.to_csv("data/county_month.csv", index=False)

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
metrics = ["HouseholdsReg", "PoundsReg", "ChildrenReg", "SeniorsReg", "AdultsReg"]
min_excess = {"HouseholdsReg": 50, "PoundsReg": 5000, "ChildrenReg": 30, "SeniorsReg": 20, "AdultsReg": 50}

cm = pd.read_csv("data/county_month.csv", parse_dates=["Date"])
cm = cm.sort_values(["County", "Date"]).reset_index(drop=True)

# Negative values are corrections, so treat them as missing
for m in metrics:
    cm.loc[cm[m] < 0, m] = np.nan

# Flag county-months far above the county's own nearby months
flag = pd.Series(False, index=cm.index)
for m in metrics:
    med = cm.groupby("County")[m].transform(
        lambda s: s.rolling(7, center=True, min_periods=3).median())
    flag |= (cm[m] > 3 * med) & ((cm[m] - med) > min_excess[m])
print(flag.sum(), "county-months flagged")
print(cm.loc[flag, ["County", "Date"] + metrics].to_string())

# Blank out flagged rows (all five metrics), then fill gaps by interpolation
cm.loc[flag, metrics] = np.nan
all_months = pd.date_range("2022-01-01", "2026-07-01", freq="MS")
P = {}
for m in metrics:
    t = cm.pivot(index="County", columns="Date", values=m).reindex(columns=all_months)
    P[m] = t.interpolate(axis=1, limit_direction="both")

# Statewide households by year and month (look for the 2022 shift and Jul vs Aug)
tot = P["HouseholdsReg"].sum()
print(tot.groupby([tot.index.year, tot.index.month]).sum().unstack().round(0))

# Is July 2026 itself trustworthy? Compare it to Feb-Jun 2026
h = P["HouseholdsReg"]
base = h.loc[:, pd.Timestamp(2026, 2, 1):pd.Timestamp(2026, 6, 1)].median(axis=1)
chk = (h[pd.Timestamp(2026, 7, 1)] / base).replace([np.inf, -np.inf], np.nan).sort_values()
print("July 2026 vs Feb-Jun median (lowest and highest):")
print(pd.concat([chk.head(6), chk.tail(6)]).round(2))

# Backtest on Aug 2024 and Aug 2025
def forecast_aug(Pm, y):
    T = pd.Timestamp
    jul = Pm[T(y, 7, 1)]
    growth = (Pm[[T(y, k, 1) for k in (5, 6, 7)]].sum(axis=1)
              / Pm[[T(y - 1, k, 1) for k in (5, 6, 7)]].sum(axis=1))
    c = Pm[T(y - 1, 8, 1)] * growth
    return {"A repeat July": jul, "C last Aug x growth": c, "D average of A and C": (jul + c) / 2}

rows = []
for m in metrics:
    for y in (2024, 2025):
        actual = P[m][pd.Timestamp(y, 8, 1)]
        for name, pred in forecast_aug(P[m], y).items():
            pred = pred.replace([np.inf, -np.inf], np.nan)
            ok = pred.notna() & actual.notna() & (actual > 0)
            rows.append({"metric": m, "year": y, "method": name,
                         "median_county_err": ((pred[ok] - actual[ok]).abs() / actual[ok]).median() * 100,
                         "statewide_err": (pred[ok].sum() / actual[ok].sum() - 1) * 100})
res = pd.DataFrame(rows)
print(res.pivot_table(index=["metric", "method"], columns="year",
                      values=["median_county_err", "statewide_err"]).round(1))