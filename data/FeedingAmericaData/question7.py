import pandas as pd

# ------------------------- SETTINGS -------------------------
folder = r"C:\Users\nafib\OneDrive\Desktop\Challenge Minnemudac"
TEAM_ID = ""        # type your team ID here when you receive it
WINDOW = 3          # months averaged: 3 = May, June, July 2026
# ------------------------------------------------------------

metrics = ["HouseholdsReg", "PoundsReg", "ChildrenReg", "SeniorsReg", "AdultsReg"]
sub_cols = ["HouseholdReg_Predicted", "PoundsReg_Predicted", "ChildrenReg_Predicted",
            "SeniorsReg_Predicted", "AdultsReg_Predicted"]

# 1. Load the food shelf data and the submission template
df = pd.read_excel(folder + r"\org_FSStats.xlsx")
template = pd.read_csv(folder + r"\Graduate_Predictions_Submit.csv", encoding="utf-8-sig")
template = template.dropna(subset=["County"]).copy()      # drop the empty rows at the bottom

# 2. Fix dates and county names
df["Date"] = pd.to_datetime(df["DateForSearch"])
df["County"] = df["County"].replace({
    "Saint Louis": "St. Louis",
    "Hennepin-Minneapolis": "Hennepin", "Hennepin-Suburbs": "Hennepin",
    "Ramsey-Saint Paul": "Ramsey", "Ramsey-Suburbs": "Ramsey",
})

# 3. Remove bad rows
df = df[df["_Month"] != 0]                                      # repeated December 2022 rows
df = df.dropna(subset=metrics, how="all")                       # completely blank rows
df = df.drop_duplicates(subset=["_id_site", "Date"] + metrics)  # exact copies
allzero = (df[metrics].fillna(0) == 0).all(axis=1)
shared = df.duplicated(subset=["_id_site", "Date"], keep=False)
df = df[~(allzero & shared)]                                    # zero rows next to a real row

# 4. Add up all rows by county and month
cm = df.groupby(["County", "Date"])[metrics].sum(min_count=1).reset_index()

# 5. Predict August 2026 = average of the last WINDOW months (ending July 2026)
recent = pd.date_range(end="2026-07-01", periods=WINDOW, freq="MS")
pred = cm[cm["Date"].isin(recent)].groupby("County")[metrics].mean().clip(lower=0)
pred.columns = sub_cols
pred["key"] = pred.index.str.lower().str.strip()

# 6. Fill the template (county names matched ignoring capital letters)
template["key"] = template["County"].str.lower().str.strip()
out = template[["RowID", "County", "key"]].merge(pred, on="key", how="left")
out["RowID"] = out["RowID"].astype(int)

# Counties with no rows in the data (Wilkin): no activity recorded, so predict 0
missing = out[sub_cols].isna().any(axis=1)
out[sub_cols] = out[sub_cols].fillna(0)
out[sub_cols] = out[sub_cols].round(0).astype("Int64")

out["YourTeamID"] = TEAM_ID
out = out[["RowID", "County"] + sub_cols + ["YourTeamID"]]

# 7. Safety checks
problems = []
if cm["Date"].max() != pd.Timestamp("2026-07-01"):
    problems.append("Latest month in the data is not July 2026: " + str(cm["Date"].max().date()))
if len(out) != 87:
    problems.append("Expected 87 rows, got " + str(len(out)))
if out[sub_cols].isna().any().any():
    problems.append("There are blank prediction cells")
if (out[sub_cols] < 0).any().any():
    problems.append("There are negative predictions")
if TEAM_ID == "":
    problems.append("TEAM_ID is empty")
unmatched = sorted(set(pred["key"]) - set(template["key"]))
if unmatched:
    problems.append("Counties in the data that are not in the template: " + str(unmatched))

print("Months used:", [d.strftime("%Y-%m") for d in recent])
print("Counties predicted as 0 (no data):", out.loc[missing, "County"].tolist())
print("Ten biggest counties by households:")
print(out.nlargest(10, "HouseholdReg_Predicted")[["County"] + sub_cols].to_string(index=False))
print("PROBLEMS:" if problems else "ALL CHECKS PASSED")
for p in problems:
    print(" -", p)

# 8. Save
out.to_csv(folder + r"\Graduate_Predictions_Submit_FILLED.csv", index=False, encoding="utf-8-sig")
print("Saved Graduate_Predictions_Submit_FILLED.csv with", len(out), "rows")