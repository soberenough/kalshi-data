"""Is the evening long-breakout an edge or just gold's uptrend? Compare with BUY at 18:00 every evening (same stop 40, same exit, same costs),
split into two halves of the 2-year sample, and a paired comparison on the nights the breakout triggered."""
import json, importlib.util, statistics as st
spec=importlib.util.spec_from_file_location("g","research/gold_evening_break.py")
src=open("research/gold_evening_break.py").read().split("out={}")[0]; g={}; exec(src,g)
B=g["bars"]("60m","730d"); tday=g["tday"]
def baseline(B,stop=40,end_h=9,cost=0.5):
    days={}
    for b in B: days.setdefault(tday(b[0]),[]).append(b)
    keys=sorted(days); res={}
    for k,nk in zip(keys,keys[1:]):
        ev=[b for b in days[nk] if b[0].hour>=18]+[b for b in days[nk] if b[0].hour<end_h]
        if not ev or ev[0][0].hour<18: continue
        e=ev[0][1]
        for b in ev:
            if b[3]<=e-stop: res[k]=-stop-cost; break
        else: res[k]=ev[-1][4]-e-cost
    return res
out={}
for end_h in (2,9):
    br=dict(g["run"](B,"long",40,None,end_h)); base=baseline(B,40,end_h)
    ks=sorted(base); half=ks[len(ks)//2]
    def S(d,sub=None):
        v=[x for k,x in d.items() if (sub is None or sub(k))]
        return {"n":len(v),"total_$":round(10*sum(v)),"avg_pt":round(st.mean(v),2) if v else 0}
    paired=[br[k]-base[k] for k in br if k in base]
    m=st.mean(paired); se=st.stdev(paired)/len(paired)**0.5
    out[f"exit {end_h:02d}:00"]={
      "breakout_all":S(br),"baseline_all":S(base),
      "breakout_1st_half":S(br,lambda k:k<half),"baseline_1st_half":S(base,lambda k:k<half),
      "breakout_2nd_half":S(br,lambda k:k>=half),"baseline_2nd_half":S(base,lambda k:k>=half),
      "baseline_on_breakout_nights":S({k:base[k] for k in br if k in base}),
      "paired_breakout_minus_baseline_pt":{"mean":round(m,2),"t":round(m/se,2),"n":len(paired)},
      "split_date":str(half)}
json.dump(out,open("research/gold_baseline.json","w"),indent=1); print(json.dumps(out,indent=1))
