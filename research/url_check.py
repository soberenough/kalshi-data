import json, requests
U = ["https://www.waveapps.com/invoicing","https://www.zoho.com/invoice/","https://www.paypal.com/us/business/accept-payments/invoice",
"https://stripe.com/invoicing","https://contracts.freelancersunion.org/","https://www.irs.gov/businesses/small-businesses-self-employed/self-employed-individuals-tax-center",
"https://www.irs.gov/businesses/small-businesses-self-employed/estimated-taxes","https://www.sba.gov/","https://www.score.org/",
"https://www.ftc.gov/business-guidance/small-businesses","https://www.usa.gov/small-claims-court","https://invoice-generator.com/",
"https://www.canva.com/invoices/templates/","https://www.freelancersunion.org/","https://www.nolo.com/legal-encyclopedia/small-claims-court"]
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
out = {}
for u in U:
    try:
        r = requests.get(u, headers=H, timeout=25, allow_redirects=True)
        t = r.text; i = t.lower().find("<title"); title = t[i:i+160].split(">",1)[-1].split("<",1)[0].strip() if i >= 0 else ""
        out[u] = {"status": r.status_code, "final": r.url, "title": title}
    except Exception as e:
        out[u] = {"error": type(e).__name__}
open("research/url_check.json","w").write(json.dumps(out, indent=1))
