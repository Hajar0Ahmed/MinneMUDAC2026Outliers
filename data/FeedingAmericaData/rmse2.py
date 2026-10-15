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
df = df[df["_Month"] != 0]
df = df.dropna(subset=metrics, how="all")
df = df.drop_duplicates(subset=["_id_site", "Date"] + metrics)
allzero = (df[metrics].fillna(0) == 0).all(axis=1)
shared = df.duplicated(subset=["_id_site", "Date"], keep=False)
df = df[~(allzero & shared)]

cm = df.groupby(["County", "Date"])[metrics].sum(min_count=1).reset_index()
months = pd.date_range(cm["Date"].min(), cm["Date"].max(), freq="MS")

rows = []
for m in metrics:
    V = cm.pivot(index="County", columns="Date", values=m).reindex(columns=months).fillna(0).values
    for i in range(15, len(months)):
        actual = V[:, i]
        a2 = V[:, i-2:i].mean(axis=1)
        a3 = V[:, i-3:i].mean(axis=1)
        a6 = V[:, i-6:i].mean(axis=1)

        # seasonal factor: how this calendar month compared with the 3 months before it, in past years
        ratios = []
        k = i - 12
        while k >= 3:
            base = V[:, k-3:k].sum()
            if base > 0:
                ratios.append(V[:, k].sum() / base)
            k -= 12
        f = np.mean(ratios) if ratios else 1.0

        preds = {
            "A_3month (current)": a3,
            "B_blend 2+3+6": (a2 + a3 + a6) / 3,
            "C_3month x seasonal": a3 * f,
            "D_blend x seasonal": (a2 + a3 + a6) / 3 * f,
        }
        for name, p in preds.items():
            rows.append((m, name, months[i], np.sqrt(np.mean((p - actual) ** 2))))

r = pd.DataFrame(rows, columns=["metric", "method", "month", "rmse"])
print("\nMEDIAN RMSE, all months (lower = better)")
print(r.pivot_table(index="method", columns="metric", values="rmse", aggfunc="median").round(0))
print("\nAVERAGE RMSE, August only")
print(r[r["month"].dt.month == 8].pivot_table(index="method", columns="metric", values="rmse", aggfunc="mean").round(0))