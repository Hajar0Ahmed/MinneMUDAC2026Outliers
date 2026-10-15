import pandas as pd
import numpy as np

folder = r"C:\Users\nafib\OneDrive\Desktop\Challenge Minnemudac"
metrics = ["HouseholdsReg", "PoundsReg", "ChildrenReg", "SeniorsReg", "AdultsReg"]

df = pd.read_excel(folder + r"\org_FSStats.xlsx")
df["Date"] = pd.to_datetime(df["DateForSearch"])
df["County"] = df["County"].replace({
    "Saint Louis": "St. Louis",
    "Hennepin-Minneapolis": "Hennepin", "Hennepin-Suburbs": "Hennepin",
    "Ramsey-Saint Paul": "Ramsey", "Ramsey-Suburbs": "Ramsey",
})

# same cleaning as the submission script
df = df[df["_Month"] != 0]
df = df.dropna(subset=metrics, how="all")
df = df.drop_duplicates(subset=["_id_site", "Date"] + metrics)
allzero = (df[metrics].fillna(0) == 0).all(axis=1)
shared = df.duplicated(subset=["_id_site", "Date"], keep=False)
df = df[~(allzero & shared)]

cm = df.groupby(["County", "Date"])[metrics].sum(min_count=1).reset_index()
months = pd.date_range(cm["Date"].min(), cm["Date"].max(), freq="MS")

windows = [1, 2, 3, 4, 6, 12, "all"]
rows = []
for m in metrics:
    P = cm.pivot(index="County", columns="Date", values=m).reindex(columns=months).fillna(0)
    V = P.values
    for i in range(12, len(months)):          # predict each month using only earlier months
        actual = V[:, i]
        for w in windows:
            pred = V[:, :i].mean(axis=1) if w == "all" else V[:, i - w:i].mean(axis=1)
            rmse = np.sqrt(np.mean((pred - actual) ** 2))
            label = "all" if w == "all" else "%02d" % w
            rows.append((m, label, months[i], rmse))

r = pd.DataFrame(rows, columns=["metric", "window", "month", "rmse"])

print("\nMEDIAN RMSE over all months (lower = better)")
print(r.pivot_table(index="window", columns="metric", values="rmse", aggfunc="median").round(0))

print("\nAVERAGE RMSE, August months only")
print(r[r["month"].dt.month == 8].pivot_table(index="window", columns="metric", values="rmse", aggfunc="mean").round(0))