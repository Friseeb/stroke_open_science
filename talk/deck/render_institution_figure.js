// Refresh the existing benchmark dot-plot design from current merged institution counts.
// Run from the repository root with puppeteer-core available on NODE_PATH.
const fs=require('fs');
const path=require('path');
const puppeteer=require('puppeteer-core');
(async()=>{
  const root=process.cwd();
  const {execFileSync}=require('child_process');
  const code=`import csv,json
r=list(csv.DictReader(open('talk/outputs/tables/stroke_commitment_institutions.csv')))
r=sorted(sorted(r,key=lambda x:int(x['n_audited']),reverse=True)[:60],key=lambda x:float(x['commitment_index']),reverse=True)[:15]
print(json.dumps([dict(key=x['institution'],label=x['institution'],value=float(x['commitment_index']),n=int(x['n_audited'])) for x in r]))`;
  const items=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c',code],{cwd:root,encoding:'utf8'}));
  const browser=await puppeteer.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--no-sandbox']});
  const page=await browser.newPage();
  await page.setViewport({width:1380,height:520,deviceScaleFactor:2});
  await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
  const font=fs.readFileSync(path.join(root,'talk/deck/assets/fonts/InstrumentSans-variable.ttf')).toString('base64');
  await page.setContent('<html><head><style>@font-face{font-family:Instrument Sans;src:url(data:font/ttf;base64,'+font+');font-weight:400 700}:root{--ink:#141414;--ink-2:#4a4a47;--ink-3:#85857f;--grid:#dcdcd8;--hair:#c6c6c1;--bg:#f1f1ef;--surface-2:#e9e9e6;--accent:#d7263d;--neutral-mark:#b4b4ae}body{margin:0;background:#f1f1ef}#chart{width:1380px}#chart text{font-size:18px}</style></head><body><div id="chart"></div></body></html>');
  await page.addScriptTag({url:'https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js'});
  await page.addScriptTag({path:path.join(root,'dashboard/charts.js')});
  await page.evaluate(()=>document.fonts.load('18px "Instrument Sans"'));
  await page.evaluate(()=>document.fonts.ready);
  await page.evaluate(items=>Charts.rankDots(document.querySelector('#chart'),{items,fmt:'x',reference:{value:1,label:'Stroke average'},color:'#d7263d',mode:'dots',labelWidth:460}),items);
  await new Promise(r=>setTimeout(r,100));
  const svg=await page.$('#chart svg');
  await svg.screenshot({path:path.join(root,'talk/outputs/figures/dashboard/cm_inst_merged.png')});
  fs.writeFileSync(path.join(root,'talk/outputs/figures/dashboard/cm_inst_merged.svg'),await page.$eval('#chart svg',n=>n.outerHTML));
  await browser.close();
})();
