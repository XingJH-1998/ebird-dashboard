#!/usr/bin/env python3
"""eBird 个人数据可视化仪表盘生成器 / Personal eBird data dashboard generator.

用法 / Usage:
    python3 ebird_dashboard.py MyEBirdData.csv                 # 输出到 ./dashboard/
    python3 ebird_dashboard.py MyEBirdData.csv -o out --taxonomy tax.csv

输出 / Outputs (均写入 -o 目录):
    dashboard.html        单文件网页(数据内嵌),直接用浏览器打开
    data.json             网页用到的全部统计结果,便于二次开发
    coverage.json         目/科覆盖率(仅在找到 auk 分类时生成)
    family_coverage.csv   目/科覆盖率表格,可直接用 Excel 打开

MyEBirdData.csv: eBird -> My eBird -> Download My Data 得到的文件。
依赖 / Requires: Python 3.8+, pandas.
目/科覆盖率 (可选 / optional): 需要 auk 的 ebird_taxonomy。
  - 传入 --taxonomy tax.csv(在 R 里运行 write.csv(auk::ebird_taxonomy,"tax.csv",row.names=FALSE)),或
  - 本机装有 R 和 auk 时自动导出;都没有则跳过该部分。
输出的 dashboard.html 是单文件,可直接分享;网页中的图表库/底图从 CDN 加载,需要联网。
注意: 输出包含你的位置坐标和清单日期,分享前请确认你愿意公开这些信息。
"""
import argparse, json, os, subprocess, sys, tempfile
import pandas as pd

CN = {'11':'北京','12':'天津','13':'河北','14':'山西','15':'内蒙古','21':'辽宁','22':'吉林','23':'黑龙江','31':'上海','32':'江苏','33':'浙江','34':'安徽','35':'福建','36':'江西','37':'山东','41':'河南','42':'湖北','43':'湖南','44':'广东','45':'广西','46':'海南','50':'重庆','51':'四川','52':'贵州','53':'云南','54':'西藏','61':'陕西','62':'甘肃','63':'青海','64':'宁夏','65':'新疆','71':'台湾','91':'香港','92':'澳门'}
CC = {'CN':'中国','HK':'中国香港','MO':'中国澳门','TW':'中国台湾','GB':'英国','US':'美国','CA':'加拿大','AU':'澳大利亚','NZ':'新西兰','JP':'日本','KR':'韩国','MY':'马来西亚','ID':'印度尼西亚','SG':'新加坡','TH':'泰国','VN':'越南','KH':'柬埔寨','LA':'老挝','MM':'缅甸','PH':'菲律宾','IN':'印度','LK':'斯里兰卡','BD':'孟加拉国','NP':'尼泊尔','BT':'不丹','MN':'蒙古','RU':'俄罗斯','DE':'德国','FR':'法国','ES':'西班牙','IT':'意大利','NL':'荷兰','NO':'挪威','SE':'瑞典','FI':'芬兰','CH':'瑞士','KE':'肯尼亚','TZ':'坦桑尼亚','ZA':'南非','BR':'巴西','MX':'墨西哥','CR':'哥斯达黎加','EC':'厄瓜多尔','PE':'秘鲁','CO':'哥伦比亚','AR':'阿根廷','CL':'智利'}


GENUS_FAMILY = {'Melophus': 'Emberizidae', 'Schoeniclus': 'Emberizidae'}


def species_mask(d):
    """True 表示可计入"种"的记录:去掉 sp./斜杠种/杂交种/家养型,保留亚种组并合并到种。"""
    cn, sc = d['Common Name'], d['Scientific Name']
    binom = sc.str.split().str[:2].str.join(' ')
    bad = (cn.str.contains(r' sp\.| x |hybrid|Domestic') | sc.str.contains(r' x | sp\.|\(')
           | (cn.str.contains('/') & ~cn.str.endswith(')')) | binom.str.contains('/')
           | (binom == 'Columba livia'))  # 家鸽/岩鸽 eBird 不计
    return ~bad, binom


def build_data(d):
    d['Date'] = pd.to_datetime(d['Date'])
    ok, binom = species_mask(d)
    d['bin'] = binom
    d['country'] = d['State/Province'].str[:2]
    s = d[ok].copy(); s['sp'] = s['bin']
    nm = s.groupby('bin')['Common Name'].agg(lambda x: x.str.replace(r'\s*\(.*\)$', '', regex=True).mode().iat[0]).to_dict()
    cl = d.drop_duplicates('Submission ID').copy()
    cl['ym'] = cl.Date.dt.strftime('%Y-%m'); cl['y'] = cl.Date.dt.year; cl['m'] = cl.Date.dt.month
    R = {}
    R['kpi'] = dict(species=int(s.sp.nunique()), checklists=int(len(cl)), days=int(cl.Date.nunique()),
        locations=int(d['Location ID'].nunique()), countries=int(d.country.nunique()),
        hours=round(float(cl['Duration (Min)'].sum() / 60)),
        individuals=int(pd.to_numeric(s.Count, errors='coerce').sum()),
        first=str(d.Date.min().date()), last=str(d.Date.max().date()),
        provinces=int(d[d.country == 'CN']['State/Province'].nunique()))
    months = pd.period_range(d.Date.min(), d.Date.max(), freq='M').strftime('%Y-%m').tolist()
    mc = cl.groupby('ym').size().reindex(months, fill_value=0)
    first = s.sort_values('Date').drop_duplicates('sp')
    fm = first.assign(ym=first.Date.dt.strftime('%Y-%m')).groupby('ym').size().reindex(months, fill_value=0)
    R['monthly'] = dict(months=months, checklists=mc.tolist(), newsp=fm.tolist(), cum=fm.cumsum().tolist())
    y0 = int(cl.y.min())
    R['heat'] = [[int(m - 1), int(y - y0), int(c)] for (y, m), c in cl.groupby(['y', 'm']).size().items()]
    R['years'] = sorted(int(y) for y in cl.y.unique()); R['y0'] = y0
    ys = s.assign(y=s.Date.dt.year).groupby('y').sp.nunique()
    R['yearly'] = dict(years=[int(y) for y in ys.index], species=ys.tolist(),
        checklists=[int((cl.y == y).sum()) for y in ys.index], newsp=[int((first.Date.dt.year == y).sum()) for y in ys.index])
    f = s.groupby('sp')['Submission ID'].nunique().sort_values(ascending=False)
    R['topsp'] = [[nm[k], int(v)] for k, v in f.head(20).items()]
    R['daily'] = [[k, int(v)] for k, v in cl.groupby(cl.Date.dt.strftime('%Y-%m-%d')).size().items()]
    t = pd.to_datetime(cl['Time'], format='%I:%M %p', errors='coerce').dt.hour.dropna().astype(int)
    R['hour'] = [int((t == h).sum()) for h in range(24)]
    g = s.groupby('country').agg(sp=('sp', 'nunique')); g['cl'] = cl.groupby('country').size()
    g = g.sort_values('sp', ascending=False)
    R['country'] = [[CC.get(k, k), int(r.sp), int(r.cl)] for k, r in g.iterrows()]
    c = s[s.country == 'CN'].copy(); c['p'] = c['State/Province'].str[3:].map(CN)
    pg = c.groupby('p').sp.nunique()
    pc = cl[cl.country == 'CN'].assign(p=lambda x: x['State/Province'].str[3:].map(CN)).groupby('p').size()
    R['prov'] = sorted([[k, int(v), int(pc.get(k, 0))] for k, v in pg.items()], key=lambda x: -x[1])
    L = d.groupby(['Location ID', 'Location', 'Latitude', 'Longitude']).agg(cl=('Submission ID', 'nunique')).reset_index()
    L['sp'] = L['Location ID'].map(s.groupby('Location ID').sp.nunique()).fillna(0).astype(int)
    R['locs'] = [[r.Location, round(r.Latitude, 4), round(r.Longitude, 4), int(r.cl), int(r.sp)] for r in L.itertuples()]
    bd = s.groupby('Date').sp.nunique().sort_values(ascending=False).head(10)
    R['bestdays'] = [[str(k.date()), int(v), d[d.Date == k].Location.mode().iat[0]] for k, v in bd.items()]
    R['lifers'] = [[nm[r.sp], str(r.Date.date()), r.Location] for r in first.sort_values('Date', ascending=False).head(12).itertuples()]
    return R, s


def load_taxonomy(path):
    if path:
        return pd.read_csv(path)
    out = os.path.join(tempfile.mkdtemp(), 'tax.csv')
    try:
        subprocess.run(['Rscript', '-e', f'suppressMessages(library(auk));write.csv(ebird_taxonomy,"{out}",row.names=FALSE)'],
                       check=True, capture_output=True)
        return pd.read_csv(out)
    except Exception:
        return None


def build_coverage(s, t):
    sps = t[(t.category == 'species') & (t.extinct == False)].copy()
    bysci = sps.set_index('scientific_name')
    bycom = sps.drop_duplicates('common_name').set_index('common_name')
    gen = sps.assign(g=sps.scientific_name.str.split().str[0]).drop_duplicates('g').set_index('g')
    u = s.drop_duplicates('bin')[['bin', 'Common Name']].copy()
    u['cname'] = u['Common Name'].str.replace(r'\s*\(.*\)$', '', regex=True)
    rows, extra, unres = [], [], []
    for r in u.itertuples():  # 学名 -> 英文名 -> 同属推断(分类版本比 auk 新时)
        if r.bin in bysci.index: x = bysci.loc[r.bin]
        elif r.cname in bycom.index: x = bycom.loc[r.cname]
        elif r.bin.split()[0] in gen.index:
            x = gen.loc[r.bin.split()[0]]; extra.append(x.family)
        elif r.bin.split()[0] in GENUS_FAMILY:  # auk 2025 之后新拆分的属
            x = sps[sps.family == GENUS_FAMILY[r.bin.split()[0]]].iloc[0]; extra.append(x.family)
        else: unres.append(r.bin); continue
        rows.append((x['order'], x['family']))
    if unres: print(f'  未能归入 auk 分类的物种 {len(unres)} 个(已忽略): {unres[:5]}...')
    o = pd.DataFrame(rows, columns=['order', 'family'])
    tf = sps.groupby(['order', 'family', 'family_common']).size().rename('total').reset_index()
    tf['seen'] = tf.family.map(o.groupby('family').size()).fillna(0).astype(int)
    ex = pd.Series(extra, dtype=object).value_counts()
    tf['total'] += tf.family.map(ex).fillna(0).astype(int)  # 额外种同时计入分子分母
    to = tf.groupby('order').agg(total=('total', 'sum'), seen=('seen', 'sum'), fams=('family', 'nunique')).reset_index()
    to['famseen'] = to.order.map(tf[tf.seen > 0].groupby('order').size()).fillna(0).astype(int)
    to['pct'] = (to.seen / to.total * 100).round(1); tf['pct'] = (tf.seen / tf.total * 100).round(1)
    return dict(orders=to.sort_values('pct', ascending=False).to_dict('records'),
        families=tf.sort_values(['order', 'family']).to_dict('records'),
        sum=dict(o_seen=int((to.seen > 0).sum()), o_total=len(to), f_seen=int((tf.seen > 0).sum()), f_total=len(tf),
                 s_seen=int(tf.seen.sum()), s_total=int(tf.total.sum()))), tf


def main():
    ap = argparse.ArgumentParser(description='Generate a dashboard from MyEBirdData.csv')
    ap.add_argument('csv'); ap.add_argument('-o', '--out', default='dashboard')
    ap.add_argument('--taxonomy', help='auk ebird_taxonomy 导出的 CSV (可选)')
    a = ap.parse_args()
    d = pd.read_csv(a.csv, low_memory=False)
    need = {'Submission ID', 'Common Name', 'Scientific Name', 'Count', 'State/Province', 'Location ID', 'Location', 'Latitude', 'Longitude', 'Date', 'Time', 'Duration (Min)'}
    if need - set(d.columns): sys.exit(f'CSV 缺少列: {sorted(need - set(d.columns))}。请使用 eBird 的 MyEBirdData.csv。')
    os.makedirs(a.out, exist_ok=True)
    print('统计数据...'); R, s = build_data(d)
    print('读取分类 (auk)...'); t = load_taxonomy(a.taxonomy); cov = None
    if t is None: print('  未找到 auk 分类,跳过目/科覆盖率 (可用 --taxonomy 指定)')
    else:
        cov, tf = build_coverage(s, t)
        tf.rename(columns={'order': '目', 'family': '科', 'family_common': '科英文名', 'total': '总种数', 'seen': '已记录', 'pct': '覆盖率%'}) \
          .sort_values('覆盖率%', ascending=False).to_csv(os.path.join(a.out, 'family_coverage.csv'), index=False)
    html = TEMPLATE.replace('__DATA__', json.dumps(R, ensure_ascii=False)).replace('__COV__', json.dumps(cov, ensure_ascii=False))
    p = os.path.join(a.out, 'dashboard.html')
    open(p, 'w', encoding='utf-8').write(html)
    json.dump(R, open(os.path.join(a.out, 'data.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    if cov:
        json.dump(cov, open(os.path.join(a.out, 'coverage.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    k = R['kpi']; print(f"完成: {k['species']} 种 / {k['checklists']} 份清单 -> {p}")


TEMPLATE = r'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>我的观鸟数据</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#1f2a24;--mut:#6b756f;--line:#e4e2da;--c1:#2f7d5b;--c2:#d98b2b;--c3:#3b6ea5}
@media(prefers-color-scheme:dark){:root{--bg:#141a17;--card:#1c2420;--ink:#e8ece9;--mut:#93a09a;--line:#2b352f;--c1:#5fc08f;--c2:#e8a850;--c3:#7aa8dc}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,"PingFang SC",sans-serif}
.w{max-width:1200px;margin:0 auto;padding:24px 16px 48px}h1{margin:0 0 4px;font-size:26px}.sub{color:var(--mut);margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:16px}
.k,.card{background:var(--card);border:1px solid var(--line);border-radius:12px}.k{padding:14px}.k b{display:block;font-size:26px;color:var(--c1)}.k span{color:var(--mut);font-size:12px}
.g{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.card{padding:16px}.full{grid-column:1/-1}
h2{font-size:15px;margin:0 0 2px}.d{color:var(--mut);font-size:12px;margin-bottom:8px}.ch{height:320px}#map{height:440px;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:13px}td{padding:5px 4px;border-bottom:1px solid var(--line)}td:last-child{text-align:right;color:var(--mut)}
#t_best td:nth-child(1),#t_best td:nth-child(3),#t_lif td:nth-child(1),#t_lif td:nth-child(3){white-space:nowrap}
.bar{height:8px;border-radius:4px;background:var(--line);min-width:90px}.bar i{display:block;height:100%;border-radius:4px;background:var(--c1)}
.tw{max-height:520px;overflow:auto}th{position:sticky;top:0;background:var(--card);text-align:left;font-size:12px;color:var(--mut);padding:6px 4px;cursor:pointer;border-bottom:1px solid var(--line)}
.tw td:last-child{text-align:left;color:var(--ink)}.tw td.n{text-align:right;color:var(--mut)}input,select{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:inherit;margin:0 6px 8px 0}
@media(max-width:800px){.g{grid-template-columns:1fr}}
</style></head><body><div class="w">
<h1>🐦 我的观鸟数据</h1><div class="sub" id="sub"></div>
<div class="kpis" id="kpis"></div>
<div class="g">
<div class="card full"><h2>累计鸟种增长曲线</h2><div class="d">柱:每月新增鸟种(lifer) · 线:累计鸟种数</div><div class="ch" id="c_cum"></div></div>
<div class="card full"><h2>观鸟日历</h2><div class="d">每天提交的清单数</div><div class="ch" id="c_cal" style="height:880px"></div></div>
<div class="card"><h2>每年观鸟概况</h2><div class="d">清单数与当年记录鸟种数</div><div class="ch" id="c_year"></div></div>
<div class="card"><h2>月份 × 年份</h2><div class="d">清单数热力图 — 什么季节出门最多</div><div class="ch" id="c_heat"></div></div>
<div class="card"><h2>出发时间</h2><div class="d">清单开始的小时分布</div><div class="ch" id="c_hour"></div></div>
<div class="card"><h2>各国家/地区鸟种数</h2><div class="d">柱:鸟种数 · 括号外为清单数</div><div class="ch" id="c_country"></div></div>
<div class="card" id="card_prov"><h2>中国各省鸟种数</h2><div class="d">共 <span id="np"></span> 个省级行政区</div><div class="ch" style="height:480px" id="c_prov"></div></div>
<div class="card"><h2>最常遇到的 20 种鸟</h2><div class="d">出现在多少份清单中</div><div class="ch" style="height:480px" id="c_top"></div></div>
<div class="card full" id="card_ord"><h2>目水平覆盖率(以 auk ebird_taxonomy 2025 为蓝本)</h2><div class="d" id="covsum"></div><div class="ch" id="c_ord" style="height:900px"></div></div>
<div class="card full" id="card_fam"><h2>科水平覆盖率</h2><div class="d">点击表头排序 · 种数为 auk 分类中未灭绝的物种</div>
<input id="fq" placeholder="搜索科 / 英文名"><select id="fo"><option value="">全部目</option></select><label><input type="checkbox" id="fz"> 只看未记录的科</label>
<div class="tw"><table id="t_fam"></table></div></div>
<div class="card full"><h2>观鸟地点地图</h2><div class="d">圆点大小 = 清单数,颜色 = 鸟种数(越深越多)· 右上角可切换底图;若底图加载失败会自动改为无底图</div><div id="map"></div></div>
<div class="card"><h2>单日鸟种数 Top 10</h2><table id="t_best"></table></div>
<div class="card"><h2>最近的新增鸟种</h2><table id="t_lif"></table></div>
</div></div>
<script>
const R=__DATA__;
const css=getComputedStyle(document.documentElement),v=n=>css.getPropertyValue(n).trim();
const ink=v('--ink'),mut=v('--mut'),line=v('--line'),c1=v('--c1'),c2=v('--c2'),c3=v('--c3');
const K=R.kpi;
document.getElementById('sub').textContent=`${K.first} 至 ${K.last} · 数据来自 eBird`;
[['鸟种',K.species],['清单',K.checklists],['观鸟天数',K.days],['地点',K.locations],['国家/地区',K.countries],['观鸟小时',K.hours.toLocaleString()],['记录个体数',K.individuals.toLocaleString()]]
 .forEach(([a,b])=>kpis.insertAdjacentHTML('beforeend',`<div class="k"><b>${b}</b><span>${a}</span></div>`));
np.textContent=K.provinces;
const base={textStyle:{color:ink},grid:{left:48,right:20,top:30,bottom:30},tooltip:{trigger:'axis'}};
const ax=(o={})=>({axisLine:{lineStyle:{color:line}},axisLabel:{color:mut},splitLine:{lineStyle:{color:line}},...o});
function ch(id,o){const c=echarts.init(document.getElementById(id));c.setOption({...base,...o});addEventListener('resize',()=>c.resize());return c}
const M=R.monthly;
ch('c_cum',{grid:{left:48,right:64,top:30,bottom:30},legend:{textStyle:{color:mut},top:0},xAxis:ax({type:'category',data:M.months}),yAxis:[ax({type:'value'}),ax({type:'value',splitLine:{show:false}})],
 dataZoom:[{type:'inside'}],series:[{name:'每月新增',type:'bar',data:M.newsp,itemStyle:{color:c2}},{name:'累计',type:'line',yAxisIndex:1,data:M.cum,showSymbol:false,lineStyle:{width:3,color:c1},areaStyle:{color:c1,opacity:.12}}]});
const days=R.daily.map(x=>x[0]).sort(),ys=[...new Set(days.map(d=>d.slice(0,4)))];
document.getElementById('c_cal').style.height=(ys.length*96+50)+'px';
ch('c_cal',{tooltip:{formatter:p=>p.value[0]+':'+p.value[1]+' 份清单'},visualMap:{min:0,max:6,show:false,inRange:{color:[v('--line'),c1]},orient:'horizontal'},
 calendar:ys.map((y,i)=>({range:y,top:20+i*96,height:80,left:60,right:20,cellSize:['auto',11],
  itemStyle:{color:'transparent',borderColor:line},splitLine:{show:false},yearLabel:{color:mut,position:'left'},monthLabel:{color:mut,nameMap:'cn'},dayLabel:{show:false}})),
 series:ys.map((y,i)=>({type:'heatmap',coordinateSystem:'calendar',calendarIndex:i,data:R.daily.filter(x=>x[0].startsWith(y))}))});
const Y=R.yearly;
ch('c_year',{legend:{textStyle:{color:mut},top:0},xAxis:ax({type:'category',data:Y.years}),yAxis:ax({type:'value'}),
 series:[{name:'清单数',type:'bar',data:Y.checklists,itemStyle:{color:c3}},{name:'鸟种数',type:'bar',data:Y.species,itemStyle:{color:c1}}]});
const yrs=[...Array(R.years.at(-1)-R.y0+1).keys()].map(i=>R.y0+i);
ch('c_heat',{grid:{left:50,right:20,top:10,bottom:65},tooltip:{formatter:p=>`${yrs[p.value[1]]}年${p.value[0]+1}月:${p.value[2]} 份`},
 xAxis:{type:'category',data:[...Array(12).keys()].map(i=>i+1+'月'),axisLabel:{color:mut},splitArea:{show:true}},yAxis:{type:'category',data:yrs,axisLabel:{color:mut}},
 visualMap:{min:0,max:Math.max(...R.heat.map(x=>x[2])),orient:'horizontal',left:'center',bottom:0,textStyle:{color:mut},inRange:{color:[v('--line'),c1]}},
 series:[{type:'heatmap',data:R.heat,label:{show:true,color:'#000',fontSize:10},itemStyle:{borderColor:v('--card'),borderWidth:2}}]});
ch('c_hour',{xAxis:ax({type:'category',data:[...Array(24).keys()].map(h=>h+':00'),axisLabel:{color:mut,interval:2}}),yAxis:ax({type:'value'}),series:[{type:'bar',data:R.hour,itemStyle:{color:c2}}]});
const C=R.country;
ch('c_country',{grid:{left:90,right:60,top:10,bottom:20},xAxis:ax({type:'value'}),yAxis:ax({type:'category',data:C.map(x=>`${x[0]} (${x[2]})`).reverse()}),
 tooltip:{trigger:'axis'},series:[{type:'bar',data:C.map(x=>x[1]).reverse(),itemStyle:{color:c1},label:{show:true,position:'right',color:mut}}]});
const P=R.prov;if(!P.length)card_prov.remove();else{
document.getElementById('c_prov').style.height=Math.min(620,Math.max(220,P.length*40+70))+'px';
ch('c_prov',{grid:{left:60,right:40,top:10,bottom:20},xAxis:ax({type:'value'}),yAxis:ax({type:'category',data:P.map(x=>x[0]).reverse(),axisLabel:{color:mut,interval:0,fontSize:11}}),
 series:[{type:'bar',data:P.map(x=>x[1]).reverse(),itemStyle:{color:c3},label:{show:true,position:'right',color:mut,fontSize:10}}]});}
const T=R.topsp;
ch('c_top',{grid:{left:170,right:40,top:10,bottom:20},xAxis:ax({type:'value'}),yAxis:ax({type:'category',data:T.map(x=>x[0]).reverse(),axisLabel:{color:mut,interval:0,fontSize:11}}),
 series:[{type:'bar',data:T.map(x=>x[1]).reverse(),itemStyle:{color:c2},label:{show:true,position:'right',color:mut,fontSize:10}}]});
const rows=(id,a,f)=>document.getElementById(id).innerHTML=a.map(f).join('');
rows('t_best',R.bestdays,r=>`<tr><td>${r[0]}</td><td>${r[2]}</td><td><b>${r[1]}</b> 种</td></tr>`);
rows('t_lif',R.lifers,r=>`<tr><td>${r[0]}</td><td>${r[2]}</td><td>${r[1]}</td></tr>`);
const CV=__COV__;
if(!CV){card_ord.remove();card_fam.remove()}else{
covsum.textContent=`目 ${CV.sum.o_seen}/${CV.sum.o_total} · 科 ${CV.sum.f_seen}/${CV.sum.f_total} · 种 ${CV.sum.s_seen}/${CV.sum.s_total}(${(CV.sum.s_seen/CV.sum.s_total*100).toFixed(1)}%)`;
const O=[...CV.orders].sort((a,b)=>a.total-b.total);
ch('c_ord',{grid:{left:140,right:90,top:30,bottom:20},legend:{top:0,textStyle:{color:mut}},
 tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:p=>{const o=O[p[0].dataIndex];return `<b>${o.order}</b><br>已记录 ${o.seen} / ${o.total} 种(${o.pct}%)<br>科 ${o.famseen} / ${o.fams}`}},
 xAxis:ax({type:'log',min:1,name:'种数(对数轴)'}),yAxis:ax({type:'category',data:O.map(o=>o.order),axisLabel:{color:mut,interval:0,fontSize:11}}),
 series:[{name:'已记录',type:'bar',data:O.map(o=>o.seen||null),itemStyle:{color:c1},label:{show:true,position:'insideRight',color:'#fff',fontSize:10,formatter:p=>p.value}},
  {name:'分类总数',type:'bar',data:O.map(o=>o.total),itemStyle:{color:line},barGap:'-100%',z:0,label:{show:true,position:'right',color:mut,fontSize:10,formatter:p=>{const o=O[p.dataIndex];return `${o.pct}%`}}}]});
const fo=document.getElementById('fo');[...new Set(CV.families.map(f=>f.order))].forEach(o=>fo.insertAdjacentHTML('beforeend',`<option>${o}</option>`));
let sk='pct',sd=-1;
function drawFam(){const q=fq.value.toLowerCase();let a=CV.families.filter(f=>(!fo.value||f.order==fo.value)&&(!fz.checked||f.seen==0)&&(f.family+f.family_common+f.order).toLowerCase().includes(q));
 a.sort((x,y)=>(typeof x[sk]=='string'?x[sk].localeCompare(y[sk]):x[sk]-y[sk])*sd);
 t_fam.innerHTML='<tr>'+[['order','目'],['family','科'],['family_common','英文名'],['seen','已记录'],['total','总种数'],['pct','覆盖率']].map(([k,n])=>`<th data-k="${k}">${n}${k==sk?(sd>0?' ▲':' ▼'):''}</th>`).join('')+'</tr>'+
 a.map(f=>`<tr><td>${f.order}</td><td>${f.family}</td><td>${f.family_common}</td><td class="n">${f.seen}</td><td class="n">${f.total}</td><td><div style="display:flex;gap:6px;align-items:center"><div class="bar"><i style="width:${f.pct}%"></i></div>${f.pct}%</div></td></tr>`).join('');
 t_fam.querySelectorAll('th').forEach(h=>h.onclick=()=>{sd=sk==h.dataset.k?-sd:-1;sk=h.dataset.k;drawFam()})}
[fq,fo,fz].forEach(e=>e.oninput=drawFam);drawFam();
}
// map
const cols=['#fde68a','#f4a62a','#d9642b','#9b2226'],mx=Math.max(...R.locs.map(l=>l[4]));
function scatterMap(note){
 const el=document.getElementById('map');el.innerHTML='';
 const c=echarts.init(el,null,{renderer:'canvas'});
 c.setOption({textStyle:{color:ink},title:{text:note,textStyle:{color:mut,fontSize:11,fontWeight:'normal'},left:8,top:4},
  grid:{left:45,right:20,top:30,bottom:30},tooltip:{formatter:p=>`<b>${p.value[3]}</b><br>${p.value[2]} 份清单 · ${p.value[4]} 种`},
  xAxis:ax({type:'value',min:-180,max:180,name:'经度'}),yAxis:ax({type:'value',min:-60,max:80,name:'纬度'}),
  dataZoom:[{type:'inside',xAxisIndex:0,filterMode:'none'},{type:'inside',yAxisIndex:0,filterMode:'none'}],
  series:[{type:'scatter',data:R.locs.map(l=>[l[2],l[1],l[3],l[0],l[4]]),symbolSize:d=>4+Math.sqrt(d[2])*1.8,
   itemStyle:{opacity:.75,color:p=>cols[Math.min(3,Math.floor(Math.sqrt(p.value[4]/mx)*4))]}}]});
 addEventListener('resize',()=>c.resize());
}
(function(){
 if(typeof L==='undefined'){scatterMap('地图库未能加载,已改用经纬度散点图(滚轮可缩放)');return}
 const map=L.map('map').setView([30,105],4);
 const gd=L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',{subdomains:'1234',attribution:'© 高德地图',maxZoom:18});
 const osm=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap',maxZoom:18});
 const blank=L.tileLayer('data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==');
 let err=0,cur=gd;gd.addTo(map);
 L.control.layers({'高德地图':gd,'OpenStreetMap':osm,'无底图':blank}).addTo(map);
 [gd,osm].forEach(l=>l.on('tileerror',()=>{if(++err===8&&map.hasLayer(l)){map.removeLayer(l);blank.addTo(map);document.getElementById('map').style.background='#e8ecea'}}));
 R.locs.forEach(l=>{const t=Math.sqrt(l[4]/mx);L.circleMarker([l[1],l[2]],{radius:3+Math.sqrt(l[3])*1.8,color:'#fff',weight:.6,fillColor:cols[Math.min(3,Math.floor(t*4))],fillOpacity:.8})
  .bindPopup(`<b>${l[0]}</b><br>${l[3]} 份清单 · ${l[4]} 种`).addTo(map)});
 map.fitBounds(R.locs.filter(l=>l[1]>20&&l[2]>70&&l[2]<135).map(l=>[l[1],l[2]]));
})();
</script></body></html>
'''

if __name__ == '__main__':
    main()
