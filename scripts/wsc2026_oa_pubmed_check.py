# For a sample of DOIs: find the PubMed record, and whether PubMed flags it as free full text / in PMC.
import sys, json, time, csv, re, urllib.request, urllib.parse
E = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
def post(ep, data):
    body = urllib.parse.urlencode({**data, "tool": "stroke_open_science_oacheck"}).encode()
    for i in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(E + ep, data=body), timeout=60) as r:
                txt = r.read().decode("utf-8", "ignore")
            time.sleep(0.45)
            j = json.loads(txt)
            if ep == "esearch.fcgi" and "idlist" not in j.get("esearchresult", {}):
                raise ValueError(txt[:200])
            return j
        except Exception as e:
            print("retry", ep, str(e)[:120], file=sys.stderr); time.sleep(3 + 4 * i)
    raise RuntimeError("failed " + ep)
def search(term):
    return post("esearch.fcgi", {"db": "pubmed", "retmode": "json", "retmax": 1000, "term": term})["esearchresult"]["idlist"]
src, dst = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src)))
clean = lambda d: re.sub(r'["\\]', "", d.strip().lower())
res = {}
for b in range(0, len(rows), 50):
    batch = rows[b:b + 50]
    q = "(" + " OR ".join(f'"{clean(r["doi_norm"])}"[aid]' for r in batch) + ")"
    allp = search(q); free = set(search(q + " AND free full text[sb]")); pmc = set(search(q + " AND pubmed pmc[sb]"))
    pm2doi = {}
    if allp:
        summ = post("esummary.fcgi", {"db": "pubmed", "retmode": "json", "id": ",".join(allp)})["result"]
        for p in allp:
            rec = summ.get(p, {})
            ids = [a["value"].lower() for a in rec.get("articleids", []) if a.get("idtype") == "doi"]
            m = re.findall(r"doi:\s*(\S+)", rec.get("elocationid", "") or "")
            for d in ids + [x.lower() for x in m]:
                pm2doi.setdefault(d, p)
    for r in batch:
        d = clean(r["doi_norm"]); p = pm2doi.get(d)
        res[d] = {"pmid": p or "", "pubmed_free": (p in free) if p else "", "in_pmc": (p in pmc) if p else ""}
    print(b + len(batch), "done", sum(1 for v in res.values() if v["pmid"]), "found", flush=True)
with open(dst, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["pmid", "pubmed_free", "in_pmc"])
    w.writeheader()
    for r in rows:
        w.writerow({**r, **res[clean(r["doi_norm"])]})
