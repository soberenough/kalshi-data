# Count last full week's Hillsborough county permits by lead-worthy type (aggregates only; no addresses saved).
import io, re, zipfile, json, datetime as dt, requests, collections
from xml.etree import ElementTree as ET
URL="https://www.arcgis.com/sharing/rest/content/items/3fd625c127734f0cafed1cfa648e1612/data"
NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
z=zipfile.ZipFile(io.BytesIO(requests.get(URL,timeout=180).content))
sheet=[n for n in z.namelist() if n.startswith("xl/worksheets/sheet")][0]
rows=[]
for _,el in ET.iterparse(z.open(sheet)):
    if el.tag!=NS+"row": continue
    v={}
    for c in el.findall(NS+"c"):
        col=re.match(r"[A-Z]+",c.get("r")).group(); t="".join(x.text or "" for x in c.iter(NS+"t"))
        if not t:
            ve=c.find(NS+"v"); t=ve.text if ve is not None else ""
        v[col]=t
    rows.append(v); el.clear()
head={k:v.upper() for k,v in rows[0].items()}; ix={v:k for k,v in head.items()}
D,DESC,TYPE,VAL=ix["ISSUED DATE"],ix["DESCRIPTION"],ix["TYPE"],ix.get("VALUE")
CATS={"New home":r"NEW SINGLE FAMILY|NEW SFR|SINGLE FAMILY DWELLING|NEW RESIDENCE|NEW HOME|\bSFD\b|TOWNHOM",
 "Roof replacement":r"RE-?ROOF|ROOF REPLACE|REROOF|SHINGLE|TEAR ?OFF",
 "Solar":r"SOLAR|PHOTOVOLTAIC|\bPV\b",
 "HVAC change-out":r"\bHVAC\b|A/C|AC CHANGE|CHANGE ?OUT|AIR HANDLER|CONDENSER|HEAT PUMP",
 "Generator":r"GENERATOR",
 "Fence":r"\bFENCE",
 "Windows/doors":r"WINDOW|DOOR REPLACE|IMPACT",
 "Addition/remodel":r"ADDITION|REMODEL|RENOVAT|KITCHEN|BATH",
 "Pool (new)":r"\bPOOL\b"}
end=dt.date(2026,11,15); start=end-dt.timedelta(days=6)
out=collections.Counter(); types=collections.Counter(); vals=collections.defaultdict(list)
for r in rows[1:]:
    d=r.get(D,"")
    try: day=dt.datetime.strptime(d[:10],"%m/%d/%Y").date()
    except ValueError: continue
    if not(start<=day<=end): continue
    types[r.get(TYPE,"")]+=1
    s=r.get(DESC,"").upper()
    for k,p in CATS.items():
        if re.search(p,s):
            out[k]+=1
            try: vals[k].append(float(r.get(VAL) or 0))
            except ValueError: pass
            break
res={"week":f"{start}..{end}","all_permits":sum(types.values()),"by_category":out.most_common(),
     "median_value":{k:int(sorted(v)[len(v)//2]) for k,v in vals.items() if v},"by_county_type":types.most_common()}
open("research/permit_types.json","w").write(json.dumps(res,indent=1))
