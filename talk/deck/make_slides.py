"""Build the portable presentation (preview.html) from the HTML slides, preserving their design.

The editable sources are project/slides/*.html and project/deck.json; this command never rewrites them.
preview.html embeds fonts, images, D3 and the dashboard's charts.js, so it runs offline. On top of the slides
it adds, in the presentation only (the .pptx is built from the slide sources and is not affected):

  motion     titles settle, numbers count up, blocks cascade, pictures wipe in; off under reduced motion
  charts     the dashboard's own D3 charts replace five chart pictures (hover for values); the pictures stay
             as the fallback and in print
  presenter  S speaker notes with timers in a second window, O overview, F full screen, B blank screen;
             sources link to their DOIs, findings link to the same view of the public dashboard

Refresh the chart data from a dashboard build (writes assets/live_charts.json):
  python talk/deck/make_slides.py --dashboard-data data/runs/<run>/data/benchmarks/dashboard/site/dashboard_data.json
"""
from __future__ import annotations
import argparse
import base64
import csv
import html as htmllib
import json
import mimetypes
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
SLIDES = ROOT / 'project/slides'
LIVE_JSON = ROOT / 'assets/live_charts.json'
BLOBS = {
 '1fb20c959926284dd1854d9c6102e55e':'matrix',
 '132f503925f35b32dc8876a44ed61ac2':'trend_oa',
 '96fde507943b392dd08bf6db6c11315d':'trend_data',
 '9f18b9e4a7d4ea6ca13fc229c654623f':'trend_code',
 '67939026af6f2060dc9d39d3844cc83b':'trend_preprint',
 '837a5f4520811da05dfc2266dcdc66ae':'trend_reg',
 '902bac47b083c3a58b90bccb23a37e71':'oa_status',
 '7283090421ebd52d983830d9f2327368':'das_year',
 '3cbd9b26c3fb379a188b53906e212ea5':'das_disc',
 '82578c9fd21556d92fd12ae68fbf6f25':'eq_route',
 'c2d75a6018dc709db7762c9a8bacf42f':'eq_ft',
 '4af052f78d2110e6a65d8d016cdbe00e':'cm_inst',
}
# picture on the slide -> live chart that replaces it in the presentation
LIVE_FOR = {
 '/_blob/132f503925f35b32dc8876a44ed61ac2': 'oa_trend',
 '../../../outputs/figures/dashboard/trend_oa_slide.png': 'oa_trend',
 '/_blob/902bac47b083c3a58b90bccb23a37e71': 'oa_status',
 '/_blob/7283090421ebd52d983830d9f2327368': 'das_year',
 '../../../outputs/figures/dashboard/oa_status_slide.png': 'oa_status',
 '../../../outputs/figures/dashboard/das_year_slide.png': 'das_year',
 '/_blob/c2d75a6018dc709db7762c9a8bacf42f': 'eq_ft',
 '../../../outputs/figures/dashboard/cm_inst_merged.png': 'cm_inst',
}
DASHBOARD = 'https://friseeb.github.io/stroke_open_science_outputs/'
# finding slide -> the same view in the public dashboard
EXPLORE = {
 'method': 'view=s1',
 'oa-trend': 'view=s2&metric=oa&trendLayout=overlay',
 'oa-type': 'view=s2&oaGrouping=status&oaMode=bars',
 'flat': 'view=s2&metric=data',
 'das': 'view=s3&dasGrouping=five&dasMode=bars',
 'equity': 'view=s4',
 'commitment': 'view=s5&cmEntity=institutions&cmTop=15&cmMode=dots',
}
# words in a slide's source line -> where they point (only text outside tags is linked)
SOURCES = {
 'Liew 2022': 'https://doi.org/10.1038/s41597-022-01401-7',
 'Open Science Collaboration 2015': 'https://doi.org/10.1126/science.aac4716',
 'Button 2013': 'https://doi.org/10.1038/nrn3475',
 'Sena 2010': 'https://doi.org/10.1371/journal.pbio.1000344',
 'Baker 2016': 'https://doi.org/10.1038/533452a',
 'Hardwicke 2024': 'https://doi.org/10.1177/25152459241283477',
 'NINDS 1995': 'https://doi.org/10.1056/NEJM199512143332401',
 'Dachs 2008': 'https://doi.org/10.1371/journal.pmed.0050113',
 'Ingall 2004': 'https://doi.org/10.1161/01.STR.0000140891.70547.56',
 'Nissen 2007': 'https://doi.org/10.1056/NEJMoa072761',
 'van den Heuvel 2026': 'https://doi.org/10.1038/s41593-025-02196-7',
 'UK MHRA 2015': 'https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/448997/Final_conclusions_and_recommendations.pdf',
 'NINDS archive, 15 Oct 2026': 'https://www.ninds.nih.gov/current-research/research-funded-ninds/clinical-research/archived-clinical-research-datasets',
 'Davis, BMJ 2008': 'https://doi.org/10.1136/bmj.a568',
 'this benchmark, 2015–2023': DASHBOARD,
 'MT-GLASS, Circulation 2023': 'https://pubmed.ncbi.nlm.nih.gov/36883458/',
 'NICE 2024': 'https://www.nice.org.uk/guidance/htg708',
 'de la Rosa, Nat Commun 2025': 'https://doi.org/10.1038/s41467-025-62373-x',
 'Chalmers and Glasziou, Lancet 2009': 'https://doi.org/10.1016/S0140-6736(09)60329-9',
 'Taherifard, BMJ 2026': 'https://doi.org/10.1136/bmj-2026-100460',
 'Milham, Nat Commun 2018': 'https://doi.org/10.1038/s41467-018-04976-1',
 'Williams, J Polit Econ 2013': 'https://doi.org/10.1086/669706',
 'friseeb.github.io/stroke_open_science_outputs': DASHBOARD,
 'Rauh 2020': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7049215/',
 'Heckerman 2025': 'https://doi.org/10.7554/eLife.81051',
 'Scutt 2020': 'https://pubmed.ncbi.nlm.nih.gov/32912955/',
 'Gabelica 2022': 'https://www.jclinepi.com/article/S0895-4356(22)00141-X/abstract',
 'Bergeat 2022': 'https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2792858',
 'Rowhani-Farid 2020': 'https://pubmed.ncbi.nlm.nih.gov/32269804/',
 'Rice 2020': 'https://pubmed.ncbi.nlm.nih.gov/32586791/',
 'Scheel 2021': 'https://doi.org/10.1177/25152459211007467',
 'COS list 2026': 'https://www.cos.io/initiatives/registered-reports',
}


def asset(src):
 if src.startswith('/_blob/'):
  path=ROOT.parent/'outputs/figures/dashboard'/f'{BLOBS[src.rsplit("/",1)[1]]}.png'
 else:
  path=(SLIDES/src).resolve()
 mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
 return f'data:{mime};base64,'+base64.b64encode(path.read_bytes()).decode()


def outside_tags(html, fn):
 """Apply fn to the text between tags only, never to tag attributes."""
 return re.sub(r'>([^<]+)<', lambda m: '>' + fn(m.group(1)) + '<', html)


def link_sources(section):
 body, sep, aside = section.partition('<aside>')
 urls = {htmllib.escape(label, quote=False): url for label, url in SOURCES.items()}
 pattern = re.compile('|'.join(re.escape(k) for k in sorted(urls, key=len, reverse=True)))
 # one pass over the original text, so a link's own URL is never linked again
 fn = lambda text: pattern.sub(lambda m: f'<a class="src" href="{urls[m.group(0)]}" target="_blank" rel="noopener">{m.group(0)}</a>', text)
 return outside_tags(body, fn) + sep + aside


def live_charts(section):
 def swap(m):
  tag = m.group(0)
  src = re.search(r'src="([^"]+)"', tag).group(1)
  key = LIVE_FOR.get(src)
  if not key:
   return tag
  size = re.search(r'width:(\d+)px;height:(\d+)px', tag)
  w, h = size.groups() if size else ('1664', '560')
  return f'<div class="live-chart" data-chart="{key}" style="width:{w}px;height:{h}px">{tag}</div>'
 return re.sub(r'<img [^>]*>', swap, section)


def explore_link(sid, section):
 if sid not in EXPLORE:
  return section
 a = f'<a class="explore" href="{DASHBOARD}#{EXPLORE[sid]}" target="_blank" rel="noopener">Explore in the dashboard ↗</a>'
 return section.replace('<aside>', a + '\n<aside>', 1)


# ---------------------------------------------------------------------------------------------- chart data
OA_COLORS = {'diamond': '#5598e7', 'gold': '#eda100', 'hybrid': '#c04d8c', 'green': '#1baf7a', 'bronze': '#9a5a1f'}
NEUTRAL = '#b4b4ae'
DISC_COLORS = {'stroke': '#d7263d', 'neurology': '#2a78d6', 'neuroscience': '#1baf7a', 'cardiology': '#eda100'}
RAMP5 = ['#0d366b', '#1c5cab', '#2a78d6', '#5598e7', '#86b6ef']
RAMP4 = ['#0d366b', '#1c5cab', '#5598e7', '#86b6ef']
DAS_FIVE = [
 ('deposit', 'Deposited or public source', ['repository', 'public_source'], False),
 ('controlled', 'Controlled or restricted', ['controlled_or_restricted'], False),
 ('on_request', 'On request', ['on_request'], False),
 ('in_article', 'In article or supplement', ['in_article'], False),
 ('na', 'Not available or unclear', ['not_available_or_na', 'other_or_unclear'], False),
 ('none', 'No statement', ['no_statement'], True),
]
SIG = [('das_stmt', 'Statement', ['das_stmt']), ('das_deposit', 'Deposit', ['das_repository', 'das_public_source']),
       ('das_on_request', 'On request', ['das_on_request']), ('ft_github', 'GitHub', ['ft_github']), ('ft_reg', 'Registration', ['ft_reg'])]
MIN_N = 10   # the dashboard's MIN_N_RATE


def build_live_data(dashboard_json: Path) -> dict:
 """The five slide charts, aggregated exactly as the dashboard's app.js does (all papers, default year range)."""
 d = json.loads(dashboard_json.read_text())
 K = {k: i for i, k in enumerate(d['count_keys'])}
 y0, y1 = d['default_year_range']
 years = [y for y in d['years'] if y0 <= y <= y1]
 partial = []  # no 'incomplete' band on slides: 2025 counts are complete and the footers say its OA status is still settling
 discs = {x['key']: x for x in d['disciplines']}

 def by_year(disc):
  acc = {}
  for r in disc['cells']:
   if r[0] in years:
    a = acc.setdefault(r[0], [0] * len(K))
    for j, v in enumerate(r[len(d['cell_keys']):]):
     a[j] += v
  return acc

 def total(acc, keys):
  return sum(acc[K[k]] for k in keys)

 # 1. published open access (gold, diamond or hybrid) by year, four disciplines
 series = []
 for key in ('stroke', 'neurology', 'neuroscience', 'cardiology'):
  if key not in discs:
   continue
  acc = by_year(discs[key])
  vals, ns = [], []
  for y in years:
   a = acc.get(y)
   n = a[K['n']] if a else 0
   lic = sum(a[K[k]] for k in ('oa_diamond', 'oa_gold', 'oa_hybrid')) if a else 0  # published open: fixed at publication
   vals.append(round(lic / n, 5) if a and n >= MIN_N else None)
   ns.append(n)
  series.append({'key': key, 'label': discs[key]['label'], 'color': DISC_COLORS[key], 'emphasis': key == 'stroke', 'values': vals, 'ns': ns})
 oa_trend = {'kind': 'lineChart', 'key': [{'label': s['label'], 'color': s['color']} for s in series],
             'opts': {'series': series, 'xs': years, 'fmt': 'pct', 'yMin': 0.2, 'partial': partial, 'markers': d.get('policy_events', []), 'layout': 'overlay'}}

 stroke = by_year(discs['stroke'])

 def stacked(classes, denom_keys):
  denoms = [total(stroke[y], denom_keys) if y in stroke else 0 for y in years]
  counts, shares = {}, {}
  for c in classes:
   counts[c['key']] = [total(stroke[y], c['sum']) if y in stroke else 0 for y in years]
   shares[c['key']] = [round(counts[c['key']][i] / denoms[i], 5) if denoms[i] >= MIN_N else None for i in range(len(years))]
  out = [{k: c[k] for k in ('key', 'label', 'neutral', 'color')} for c in classes]
  return {'kind': 'stacked', 'key': [{'label': c['label'], 'color': c['color'], 'kind': 'rect'} for c in classes],
          'opts': {'classes': out, 'xs': years, 'shares': shares, 'counts': counts, 'denoms': denoms, 'mode': 'bars', 'partial': partial, 'markers': []}}

 # 2. open-access status by year, stroke
 statuses = d['oa_status_order']
 oa_classes = [{'key': s, 'label': s[0].upper() + s[1:], 'neutral': s == 'closed', 'color': NEUTRAL if s == 'closed' else OA_COLORS[s], 'sum': ['oa_' + s]} for s in statuses]
 oa_status = stacked(oa_classes, ['oa_' + s for s in statuses])

 # 3. data-availability statements by year, stroke (five classes + no statement)
 ramp = iter(RAMP5)
 das_classes = [{'key': k, 'label': lab, 'neutral': neu, 'color': NEUTRAL if neu else next(ramp), 'sum': ['das_' + c for c in cats]} for k, lab, cats, neu in DAS_FIVE]
 das_year = stacked(das_classes, ['das_audited'])

 # 4. full-text indicators by first-author income group, stroke (all years in range)
 s = discs['stroke']
 groups = s.get('income_groups') or []
 inc = {}
 for r in s.get('income_cells') or []:
  if r[0] in years:
   a = inc.setdefault(r[len(d['income_keys']) - 1], [0] * len(K))
   for j, v in enumerate(r[len(d['income_keys']):]):
    a[j] += v
 pts = []
 for gi, g in enumerate(d['income_order']):
  if g not in groups:
   continue
  a = inc.get(groups.index(g))
  if a and a[K['das_audited']] >= MIN_N:
   pts.append((g, d['income_labels'].get(g, g), RAMP4[gi], a))
 rows = [{'key': key, 'label': label, 'points': [{'key': g, 'label': lab, 'color': col, 'value': round(total(a, num) / a[K['das_audited']], 5), 'n': a[K['das_audited']]} for g, lab, col, a in pts]} for key, label, num in SIG]
 eq_ft = {'kind': 'dotPlot', 'key': [{'label': lab, 'color': col} for _, lab, col, _ in pts], 'opts': {'rows': rows, 'fmt': 'pct', 'mode': 'dots'}}

 # 5. commitment index, institutions (the talk's merged table, as on the slide)
 table = REPO / 'talk/outputs/tables/stroke_commitment_institutions.csv'
 inst = list(csv.DictReader(table.open()))
 inst = sorted(sorted(inst, key=lambda x: int(x['n_audited']), reverse=True)[:60], key=lambda x: float(x['commitment_index']), reverse=True)[:15]
 cm_inst = {'kind': 'rankDots', 'key': [], 'textSize': 21,
            'opts': {'items': [{'key': x['institution'], 'label': x['institution'], 'value': round(float(x['commitment_index']), 3),
                                'rows': [{'value': x['n_audited'], 'label': 'audited articles'}]} for x in inst],
                     'fmt': 'x', 'reference': {'value': 1, 'label': 'Stroke average'}, 'color': '#d7263d', 'mode': 'dots', 'labelWidth': 460}}

 return {'source': str(dashboard_json.relative_to(REPO)) if dashboard_json.is_relative_to(REPO) else str(dashboard_json),
         'generated_at': d.get('generated_at'), 'run_date': d.get('run_date'),
         'charts': {'oa_trend': {**oa_trend, 'vw': 820}, 'oa_status': {**oa_status, 'vw': 560}, 'das_year': {**das_year, 'vw': 1000},
                    'eq_ft': {**eq_ft, 'vw': 550}, 'cm_inst': {**cm_inst, 'vw': 1380}}}


# ---------------------------------------------------------------------------------------------- build
def main():
 ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
 ap.add_argument('--dashboard-data', type=Path, help='dashboard_data.json to refresh assets/live_charts.json from')
 ap.add_argument('--out', type=Path, default=ROOT/'preview.html', help='where to write the page (default: preview.html)')
 ap.add_argument('--link', action='append', default=[], metavar='LABEL=URL', help='a link for the reading view\'s top bar (repeatable)')
 ap.add_argument('--artifact', action='store_true', help='write the page body only (no doctype, html or viewport tags), for publishing as a claude.ai artifact')
 args = ap.parse_args()
 if args.dashboard_data:
  LIVE_JSON.write_text(json.dumps(build_live_data(args.dashboard_data.resolve()), separators=(',', ':')) + '\n')
  print('Wrote', LIVE_JSON.relative_to(REPO))
 live = json.loads(LIVE_JSON.read_text()) if LIVE_JSON.exists() else None

 deck=json.loads((ROOT/'project/deck.json').read_text())
 sections=[]; notes={}; titles={}
 for sid in deck['order']:
  html=(SLIDES/f'{sid}.html').read_text()
  match=re.search(r'<aside>(.*?)</aside>',html,re.S)
  notes[sid]=re.sub('<[^>]+>','',match.group(1)).strip() if match else ''
  t=re.search(r'<h[12][^>]*>(.*?)</h[12]>',html,re.S)
  titles[sid]=htmllib.unescape(re.sub(r'<[^>]+>',' ',t.group(1))).strip() if t else sid
  if live:
   html=live_charts(html)
  html=link_sources(explore_link(sid,html))
  html=re.sub(r'src="([^"]+)"',lambda m:'src="'+asset(m[1])+'"',html)
  sections.append(html)
 fontcss=''
 for family,file,weight in [('Instrument Sans','InstrumentSans-variable.ttf','400 700'),('Instrument Serif','InstrumentSerif-Regular.ttf','400')]:
  data=base64.b64encode((ROOT/'assets/fonts'/file).read_bytes()).decode()
  fontcss+=f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,{data});font-weight:{weight};font-display:block}}"
 title='Open science in stroke research'
 links=[{'label':l.split('=',1)[0],'href':l.split('=',1)[1]} for l in args.link]
 meta={'title':title,'order':deck['order'],'titles':titles,'notes':notes,'links':links}
 scripts=''
 if live:
  scripts+='<script>'+(ROOT/'assets/vendor/d3-7.9.0.min.js').read_text()+'</script>'
  scripts+='<script>'+(REPO/'dashboard/charts.js').read_text()+'</script>'
 scripts+='<script type="application/json" id="deck-meta">'+json.dumps(meta,ensure_ascii=False).replace('</','<\\/')+'</script>'
 scripts+='<script type="application/json" id="deck-live">'+(json.dumps(live,separators=(',',':')).replace('</','<\\/') if live else 'null')+'</script>'
 scripts+='<script>'+(ROOT/'present/deck.js').read_text()+'</script>'
 head=(f'<title>{title}</title><meta name="claude:viewport-fit-sides" content="cover">' if args.artifact else
       f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{title}</title>')
 html=(head+'<style>'+fontcss+(ROOT/'present/deck.css').read_text()+'</style>'
       +''.join(sections)+
       '<div id="progress"></div><nav id="deck-nav"><button id="prev" aria-label="Previous slide">Previous</button><span id="count"></span>'
       '<button id="next" aria-label="Next slide">Next</button><span class="keys">S notes · R read · O overview · F full screen · B blank</span></nav>'
       '<div id="blank" hidden></div>'+scripts+('' if args.artifact else '</html>'))
 args.out.write_text(html)
 (ROOT/'speaker_notes.json').write_text(json.dumps(notes,indent=2,ensure_ascii=False)+'\n')
 print(f'Built preview from {len(sections)} slides' + (' with live charts' if live else '') + '.')

if __name__=='__main__':main()
