# /// script
# dependencies = ["pandas"]
# ///
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
df = pd.read_csv("soilgrids_sites.csv")
short = {s: s.split(" (")[0] for s in df.site.unique()}
df["site"] = df.site.map(short)
print("NULL share by site:"); print(df.groupby("site").value.apply(lambda s: s.isna().mean()).round(2))
print("\nNULL share by prop (non-urban):"); print(df[df.site!="Hannover centre"].groupby("prop").value.apply(lambda s: s.isna().mean()).round(2))
print("\nTopsoil 0-5cm mean:")
print(df[(df.depth=="0-5cm")&(df.stat=="mean")].pivot(index="site", columns="prop", values="value").round(2))
print("\nocs 0-30cm:"); print(df[df.prop=="ocs"].pivot_table(index="site", columns=["depth","stat"], values="value"))
print("\nClay/sand/silt sum check (0-5cm mean):")
t = df[(df.depth=="0-5cm")&(df.stat=="mean")&df.prop.isin(["clay","sand","silt"])].groupby("site").value.sum(); print(t)
print("\nDepth profiles (mean) for soc, clay, phh2o, bdod:")
for p in ["soc","clay","phh2o","bdod"]:
    print(p); print(df[(df.prop==p)&(df.stat=="mean")&(df.depth!="0-30cm")].pivot(index="site", columns="depth", values="value")[["0-5cm","5-15cm","15-30cm","30-60cm","60-100cm","100-200cm"]].round(1))
print("\nUncertainty band 0-5cm (Q05 / median / Q95) and ratio:")
for p in ["soc","clay","phh2o"]:
    x = df[(df.prop==p)&(df.depth=="0-5cm")].pivot(index="site", columns="stat", values="value")
    print(p); print(x[["Q0.05","Q0.5","mean","Q0.95","uncertainty"]].round(2))
