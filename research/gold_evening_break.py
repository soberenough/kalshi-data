"""Backtest: evening-session short on a break of BOTH the day's RTH low and the overnight low (gold futures).
Rule (as proposed after the 2026-11-17 drop):
  For each trading day D: L = min(RTH low of D [09:30-16:00 ET], overnight low [D-1 18:00 .. D 09:30 ET]).
  Evening window: D 18:00 -> D+1 02:00 ET (configurable). First time price trades below L - 0.1, sell 1 at L - 0.1.
  Stop = entry + STOP pts. Target = entry - TGT pts (or none). Otherwise exit at window end (close of last bar).
  Same bar touches stop and target -> assume STOP (worst case). Costs: 0.5 pt per round trip (commission + 1 tick slip each way).
Controls: mirror LONG on break of max(RTH high, overnight high); and the same short rule during RTH next day is not tested.
Data: Yahoo Finance GC=F (full-size gold; MGC moves identically, $10/pt for MGC).
"""
import requests, json, datetime as dt
from zoneinfo import ZoneInfo
ET=ZoneInfo("America/New_York")
H={"User-Agent":"Mozilla/5.0"}
def bars(interval,rng):
    for host in ("query1","query2"):
        r=requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/GC=F",params={"interval":interval,"range":rng},headers=H,timeout=30)
        if r.ok: break
    j=r.json()["chart"]["result"][0]; q=j["indicators"]["quote"][0]; out=[]
    for i,t in enumerate(j["timestamp"]):
        o,h,l,c=q["open"][i],q["high"][i],q["low"][i],q["close"][i]
        if None in (o,h,l,c): continue
        out.append((dt.datetime.fromtimestamp(t,ET),o,h,l,c))
    return out
def tday(ts):  # trading day: bars from 18:00 belong to next calendar day
    d=ts.date()
    if ts.hour>=18: d=d+dt.timedelta(days=1)
    while d.weekday()>=5: d=d+dt.timedelta(days=1)
    return d
def run(B,side,stop,tgt,end_h,cost=0.5):
    days={}
    for b in B: days.setdefault(tday(b[0]),[]).append(b)
    keys=sorted(days); res=[]
    for k,nk in zip(keys,keys[1:]):
        D=days[k]
        rth=[b for b in D if (b[0].hour,b[0].minute)>=(9,30) and b[0].hour<16]
        on=[b for b in D if b[0].hour>=18 or (b[0].hour,b[0].minute)<(9,30)]
        if len(rth)<3 or len(on)<3: continue
        if side=="short": lvl=min(min(b[3] for b in rth),min(b[3] for b in on))-0.1
        else: lvl=max(max(b[2] for b in rth),max(b[2] for b in on))+0.1
        ev=[b for b in days[nk] if b[0].hour>=18 or b[0].hour<end_h]
        ev=[b for b in ev if b[0].hour>=18]+[b for b in ev if b[0].hour<end_h]
        pos=None
        for b in ev:
            _,o,h,l,c=b
            if pos is None:
                if side=="short" and l<=lvl: pos=min(lvl,o)
                elif side=="long" and h>=lvl: pos=max(lvl,o)
                else: continue
            if side=="short":
                if h>=pos+stop: res.append((k,-stop-cost)); break
                if tgt and l<=pos-tgt: res.append((k,tgt-cost)); break
            else:
                if l<=pos-stop: res.append((k,-stop-cost)); break
                if tgt and h>=pos+tgt: res.append((k,tgt-cost)); break
        else:
            if pos is not None: res.append((k,(pos-ev[-1][4] if side=="short" else ev[-1][4]-pos)-cost))
    return res
def stats(r):
    if not r: return {"n":0}
    p=[x for _,x in r]; w=[x for x in p if x>0]; eq=0; pk=0; dd=0
    for x in p: eq+=x; pk=max(pk,eq); dd=max(dd,pk-eq)
    return {"n":len(p),"win%":round(100*len(w)/len(p)),"avg_pt":round(sum(p)/len(p),2),"total_pt":round(sum(p),1),"total_$MGC":round(10*sum(p)),"maxDD_$MGC":round(10*dd),"first":str(r[0][0]),"last":str(r[-1][0])}
out={}
for iv,rng in (("15m","60d"),("60m","730d")):
    try: B=bars(iv,rng)
    except Exception as e: out[iv]={"error":str(e)}; continue
    out[iv]={"bars":len(B)}
    for side in ("short","long"):
        for stop,tgt in ((40,None),(40,100),(20,40),(15,30),(10,20)):
            for end_h in (2,9):
                out[iv][f"{side} stop{stop} tgt{tgt} until{end_h:02d}:00"]=stats(run(B,side,stop,tgt,end_h))
json.dump(out,open("research/gold_evening_break.json","w"),indent=1)
lines=["# Gold evening breakdown backtest","",__doc__,""]
for iv,d in out.items():
    lines.append(f"## {iv} bars ({d.get('bars','?')})"); lines.append("| variant | n | win% | avg pt | total $ (1 MGC) | max DD $ |"); lines.append("|---|---|---|---|---|---|")
    for k,v in d.items():
        if isinstance(v,dict) and v.get("n"): lines.append(f"| {k} | {v['n']} | {v['win%']} | {v['avg_pt']} | {v['total_$MGC']} | {v['maxDD_$MGC']} |")
open("research/gold_evening_break.md","w").write("\n".join(lines))
print("\n".join(lines))
