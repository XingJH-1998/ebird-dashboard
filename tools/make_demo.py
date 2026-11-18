#!/usr/bin/env python3
"""生成一份合成的 eBird 导出数据,供在线演示使用。

数据完全由随机数生成,不包含任何真实观鸟记录:
地点是虚构的(名字/坐标/清单全部编的),物种名来自公开的 auk 分类表。

用法:
    python3 tools/make_demo.py                       # 输出到 demo/MyEBirdData.csv
    python3 tools/make_demo.py -o /tmp/demo.csv      # 换个输出路径
    python3 tools/make_demo.py --seed 7 --checklists 200
"""
import argparse, datetime as dt, random
import pandas as pd

TAX = 'demo/taxonomy.csv'

# 虚构的观测点:名称、Location ID、省份代码、经纬度、年份范围、清单数、纳入的科
SPOTS = [
    dict(name='滴水湖湿地 (Dishui Lake Wetland)', loc='L9000011', prov='CN-31', years=(2021, 2026), n=150,
         lat=30.9002, lon=121.9407, months=[1, 3, 3, 4, 4, 5, 9, 10, 10, 11, 11, 12],
         fams=['Anatidae', 'Ardeidae', 'Rallidae', 'Scolopacidae', 'Charadriidae', 'Laridae',
               'Alcedinidae', 'Hirundinidae', 'Motacillidae', 'Podicipedidae', 'Phalacrocoracidae']),
    dict(name='白云山 (Baiyun Mountain)', loc='L9000027', prov='CN-44', years=(2021, 2026), n=140,
         lat=23.1804, lon=113.2981, months=[1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 12],
         fams=['Paridae', 'Turdidae', 'Muscicapidae', 'Phylloscopidae', 'Timaliidae', 'Leiothrichidae',
               'Picidae', 'Corvidae', 'Columbidae', 'Pycnonotidae', 'Zosteropidae', 'Sittidae',
               'Aegithalidae', 'Certhiidae', 'Paradoxornithidae']),
    dict(name='盐城滩涂 (Yancheng Mudflat)', loc='L9000043', prov='CN-32', years=(2022, 2026), n=110,
         lat=33.3512, lon=120.5546, months=[3, 4, 4, 5, 8, 9, 9, 10, 10, 11, 11, 12],
         fams=['Scolopacidae', 'Charadriidae', 'Laridae', 'Ardeidae', 'Anatidae', 'Hirundinidae',
               'Motacillidae', 'Rallidae', 'Threskiornithidae', 'Ciconiidae']),
    dict(name='高黎贡山 (Gaoligong Mountain)', loc='L9000058', prov='CN-53', years=(2023, 2026), n=80,
         lat=25.3001, lon=98.8009, months=[1, 2, 3, 3, 4, 4, 5, 10, 11, 11, 12, 12],
         fams=['Timaliidae', 'Leiothrichidae', 'Phylloscopidae', 'Muscicapidae', 'Fringillidae',
               'Turdidae', 'Picidae', 'Paridae', 'Accipitridae', 'Emberizidae', 'Laniidae',
               'Cuculidae', 'Strigidae', 'Apodidae']),
    dict(name='钏路湿原 (Kushiro Marsh)', loc='L9000074', prov='JP-01', years=(2023, 2026), n=45,
         lat=43.0517, lon=144.4022, months=[2, 4, 5, 6, 7, 9, 10, 1, 12, 11, 5, 6],
         fams=['Anatidae', 'Laridae', 'Ardeidae', 'Scolopacidae', 'Corvidae', 'Paridae',
               'Alcedinidae', 'Accipitridae']),
    dict(name='岗卡章 (Kaeng Krachan)', loc='L9000088', prov='TH-76', years=(2024, 2026), n=40,
         lat=12.8503, lon=99.3511, months=[1, 2, 3, 4, 11, 12, 12, 2, 3, 4, 5, 10],
         fams=['Leiothrichidae', 'Picidae', 'Alcedinidae', 'Accipitridae', 'Columbidae',
               'Muscicapidae', 'Meropidae', 'Upupidae', 'Estrildidae', 'Cuculidae']),
]
PROTOCOLS = ['eBird - Traveling Count', 'eBird - Stationary Count', 'eBird - Casual Observation']
COLS = ['Submission ID', 'Common Name', 'Scientific Name', 'Taxonomic Order', 'Count',
        'State/Province', 'County', 'Location ID', 'Location', 'Latitude', 'Longitude',
        'Date', 'Time', 'Protocol', 'Duration (Min)', 'All Obs Reported',
        'Distance Traveled (km)', 'Area Covered (ha)', 'Number of Observers',
        'Breeding Code', 'Observation Details', 'Checklist Comments', 'ML Catalog Numbers']
NEVER_SEEN = 0.25   # 25% 的物种当作“还没见过”,让覆盖率不是 100%


def rand_date(rng, y0, y1):
    return dt.date(rng.randint(y0, y1), rng.randint(1, 12), rng.randint(1, 28))


def build(tax, rng):
    rows = []
    order = {s: i + 1 for i, s in enumerate(tax.scientific_name)}
    sub = 0
    for spot in SPOTS:
        pool = [dict(r) for r in tax[tax.family.isin(spot['fams'])].to_dict('records')]
        for sp in pool:
            sp['w'] = rng.uniform(.15, 1.0)          # 遇见概率权重
            sp['first'] = None if rng.random() < NEVER_SEEN else rand_date(rng, *spot['years'])
        dates = sorted(rand_date(rng, *spot['years']) for _ in range(spot['n']))
        for d in dates:
            sub += 1
            cand = [sp for sp in pool if sp['first'] and sp['first'] <= d]
            if not cand:
                continue
            k = min(len(cand), rng.randint(6, 26))
            picks = rng.choices(cand, weights=[sp['w'] for sp in cand], k=k)
            uniq, used = [], set()
            for sp in picks:
                if sp['scientific_name'] in used:
                    continue
                used.add(sp['scientific_name']); uniq.append(sp)
            hh = rng.choice([5, 6, 6, 7, 7, 7, 8, 8, 9, 10, 14, 15])
            proto = rng.choices(PROTOCOLS, weights=[.6, .3, .1])[0]
            dur = rng.choice([45, 60, 75, 90, 120, 150, 180, 240])
            dist = round(rng.uniform(.6, 7.5), 3) if 'Traveling' in proto else ''
            for sp in uniq:
                rows.append(['S%09d' % (700000000 + sub), sp['common_name'], sp['scientific_name'],
                             order.get(sp['scientific_name'], 0), rng.randint(1, 45),
                             spot['prov'], '', spot['loc'], spot['name'],
                             round(spot['lat'], 4), round(spot['lon'], 4), d.isoformat(),
                             dt.time(hh, rng.randint(0, 59)).strftime('%I:%M %p'), proto,
                             dur, 1, dist, '', rng.choice([1, 1, 1, 2, 3]), '', '', '', ''])
    return pd.DataFrame(rows, columns=COLS)


def main():
    ap = argparse.ArgumentParser(description='生成合成 eBird 演示数据')
    ap.add_argument('-o', '--out', default='demo/MyEBirdData.csv')
    ap.add_argument('--seed', type=int, default=20261118)
    ap.add_argument('--checklists', type=int, default=0, help='覆盖每个地点的清单数(0 = 用内置值)')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    tax = pd.read_csv(TAX)
    if a.checklists:
        for s in SPOTS:
            s['n'] = a.checklists
    df = build(tax, rng).sort_values(['Date', 'Submission ID'], kind='stable')
    df.to_csv(a.out, index=False)
    print(f'{len(df)} 行 / {df["Submission ID"].nunique()} 份清单 / {df["Scientific Name"].nunique()} 种 -> {a.out}')


if __name__ == '__main__':
    main()
