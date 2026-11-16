import json, requests
B="https://api.elections.kalshi.com/trade-api/v2"
out={}
for s in ["KXAAAGASD","KXAAAGASW"]:
    r=requests.get(f"{B}/series/{s}",timeout=30).json(); out[s+"_series"]=r
    m=requests.get(f"{B}/markets",params={"series_ticker":s,"status":"settled","limit":6},timeout=30).json()
    out[s+"_settled"]=[{k:x.get(k) for k in ("ticker","event_ticker","title","subtitle","yes_sub_title","strike_type","floor_strike","cap_strike","open_time","close_time","expiration_value","result","volume","rules_primary")} for x in m.get("markets",[])]
    n=0; cur=None
    while True:
        p={"series_ticker":s,"status":"settled","limit":1000}
        if cur: p["cursor"]=cur
        j=requests.get(f"{B}/markets",params=p,timeout=60).json(); n+=len(j.get("markets",[])); cur=j.get("cursor")
        if not cur or n>20000: break
    out[s+"_settled_count"]=n
try:
    t=requests.get("https://stooq.com/q/d/l/?s=rb.f&i=d",timeout=30).text; out["stooq_head"]=t[:300]; out["stooq_lines"]=t.count("\n")
except Exception as e: out["stooq_err"]=str(e)
open("research/gas_explore.json","w").write(json.dumps(out,indent=1)[:60000])
