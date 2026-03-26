#!/usr/bin/env python3
"""
WHG Social Housing Environmental Analysis — v3 (with charts)
No resampling/interpolation — raw data only.
Charts via Chart.js CDN. No "fail" language.
"""

import os
import csv
import math
import json
from datetime import datetime, timedelta
from collections import defaultdict

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WHG_data", "weather_data")
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")

MOULD_RH_HIGH = 70
MOULD_RH_CRIT = 80
DEW_POINT_MARGIN = 3
OVERHEAT_CIBSE = 26
OVERHEAT_SEVERE = 28
UNDERHEAT_WHO = 18
UNDERHEAT_SEVERE = 16
UNDERHEAT_CRIT = 12
CO2_GOOD = 800
CO2_ACTION = 1000
CO2_POOR = 1500
OCCUPANCY_THRESH = 15
F_RSI_CRITICAL = 0.75


def sf(v):
    try: return float(v)
    except: return None

def e_sat(T):
    if T is None: return None
    return 610.94 * math.exp((17.625 * T) / (T + 243.04))

def dew_point(T, RH):
    if T is None or RH is None or RH <= 0: return None
    g = math.log(RH / 100.0) + (17.625 * T) / (243.04 + T)
    return (243.04 * g) / (17.625 - g)

def vp(T, RH):
    es = e_sat(T)
    if es is None or RH is None: return None
    return es * (RH / 100.0)

def parse_ts(s):
    s = s.strip()
    if '+' in s: s = s[:s.index('+')]
    elif s.endswith('Z'): s = s[:-1]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

def load_csv(filepath):
    rows = []
    with open(filepath, 'r') as f:
        for r in csv.DictReader(f):
            vt = r.get('vtime', '').strip()
            if not vt: continue
            try: ts = parse_ts(vt)
            except: continue
            rows.append({
                'time': ts,
                'avgT': sf(r.get('avgT')), 'avgH': sf(r.get('avgH')),
                'avgLux': sf(r.get('avgLux')), 'avgRe': sf(r.get('avgRe')),
                'avgCO2': sf(r.get('avgCO2')), 'avgUV': sf(r.get('avgUV')),
                'avgrdr': sf(r.get('avgrdr')),
                'weather_temperature': sf(r.get('weather_temperature')),
                'weather_humidity': sf(r.get('weather_humidity')),
                'weather_wind_speed': sf(r.get('weather_wind_speed')),
                'weather_cloud_cover': sf(r.get('weather_cloud_cover')),
                'weather_precipitation': sf(r.get('weather_precipitation')),
            })
    rows.sort(key=lambda x: x['time'])
    return rows


def daily_aggregates(rows):
    """Compute daily min/mean/max for charting."""
    by_day = defaultdict(lambda: defaultdict(list))
    for r in rows:
        d = r['time'].strftime('%Y-%m-%d')
        for k in ['avgT', 'avgH', 'avgCO2', 'weather_temperature']:
            if r[k] is not None:
                by_day[d][k].append(r[k])
    # Also compute daily VPX
    vpx_day = defaultdict(list)
    for r in rows:
        if all(r[k] is not None for k in ['avgT', 'avgH', 'weather_temperature', 'weather_humidity']):
            vi = vp(r['avgT'], r['avgH'])
            vo = vp(r['weather_temperature'], r['weather_humidity'])
            if vi is not None and vo is not None:
                vpx_day[r['time'].strftime('%Y-%m-%d')].append(vi - vo)

    days = sorted(by_day.keys())
    result = {'dates': days}
    for field in ['avgT', 'avgH', 'avgCO2', 'weather_temperature']:
        result[f'{field}_mean'] = [round(sum(by_day[d][field])/len(by_day[d][field]), 1) if by_day[d][field] else None for d in days]
        result[f'{field}_min'] = [round(min(by_day[d][field]), 1) if by_day[d][field] else None for d in days]
        result[f'{field}_max'] = [round(max(by_day[d][field]), 1) if by_day[d][field] else None for d in days]
    result['vpx_mean'] = [round(sum(vpx_day[d])/len(vpx_day[d]), 1) if vpx_day.get(d) else None for d in days]
    return result


def compute_metrics(rows):
    if not rows: return None
    temps = [r['avgT'] for r in rows if r['avgT'] is not None]
    humids = [r['avgH'] for r in rows if r['avgH'] is not None]
    co2s = [r['avgCO2'] for r in rows if r['avgCO2'] is not None]
    re_vals = [r['avgRe'] for r in rows if r['avgRe'] is not None]
    total = len(rows)
    if not temps or not humids: return None

    first_ts = rows[0]['time']
    last_ts = rows[-1]['time']
    days_span = max((last_ts - first_ts).total_seconds() / 86400, 1)

    mean_temp = sum(temps)/len(temps)
    std_temp = (sum((t-mean_temp)**2 for t in temps)/len(temps))**0.5
    mean_rh = sum(humids)/len(humids)

    pct_rh_70 = sum(1 for h in humids if h > MOULD_RH_HIGH)/len(humids)*100
    pct_rh_80 = sum(1 for h in humids if h > MOULD_RH_CRIT)/len(humids)*100
    dew_close = sum(1 for r in rows if r['avgT'] is not None and r['avgH'] is not None and dew_point(r['avgT'],r['avgH']) is not None and (r['avgT']-dew_point(r['avgT'],r['avgH']))<DEW_POINT_MARGIN)
    pct_dew_close = dew_close/total*100
    mould_score = min(100, pct_rh_70*0.5 + pct_rh_80*1.5 + pct_dew_close*0.3)

    vpx_vals = []
    for r in rows:
        if all(r[k] is not None for k in ['avgT','avgH','weather_temperature','weather_humidity']):
            vi, vo = vp(r['avgT'],r['avgH']), vp(r['weather_temperature'],r['weather_humidity'])
            if vi is not None and vo is not None: vpx_vals.append(vi-vo)
    mean_vpx = sum(vpx_vals)/len(vpx_vals) if vpx_vals else None
    pct_vpx_300 = sum(1 for v in vpx_vals if v>300)/len(vpx_vals)*100 if vpx_vals else 0
    pct_vpx_600 = sum(1 for v in vpx_vals if v>600)/len(vpx_vals)*100 if vpx_vals else 0

    cri_vals = []
    cri_crit = 0
    for r in rows:
        if all(r[k] is not None for k in ['avgT','avgH','weather_temperature']):
            dp = dew_point(r['avgT'], r['avgH'])
            ts = F_RSI_CRITICAL*(r['avgT']-r['weather_temperature'])+r['weather_temperature']
            if dp is not None:
                c = ts - dp
                cri_vals.append(c)
                if c < 1: cri_crit += 1
    mean_cri = sum(cri_vals)/len(cri_vals) if cri_vals else None
    min_cri = min(cri_vals) if cri_vals else None
    pct_cri_critical = cri_crit/len(cri_vals)*100 if cri_vals else 0

    ehr_vals = []
    for r in rows:
        if all(r[k] is not None for k in ['avgT','avgH','weather_temperature','weather_humidity']):
            wo = vp(r['weather_temperature'], r['weather_humidity'])
            ei = e_sat(r['avgT'])
            if wo and ei: ehr_vals.append(r['avgH'] - (wo/ei)*100)
    mean_ehr = sum(ehr_vals)/len(ehr_vals) if ehr_vals else None

    pct_over_25 = sum(1 for t in temps if t>25)/len(temps)*100
    pct_over_26 = sum(1 for t in temps if t>OVERHEAT_CIBSE)/len(temps)*100
    pct_over_28 = sum(1 for t in temps if t>OVERHEAT_SEVERE)/len(temps)*100

    # Adaptive comfort
    daily_out = defaultdict(list)
    for r in rows:
        if r['weather_temperature'] is not None:
            daily_out[r['time'].date()].append(r['weather_temperature'])
    daily_means = {d: sum(v)/len(v) for d,v in daily_out.items()}
    sd = sorted(daily_means.keys())
    rm_map = {}
    trm = None
    for i, d in enumerate(sd):
        trm = daily_means[d] if i==0 else 0.8*trm + 0.2*daily_means[sd[i-1]]
        rm_map[d] = trm
    ad_ex = ad_tot = 0
    for r in rows:
        if r['avgT'] is not None:
            rm = rm_map.get(r['time'].date())
            if rm is not None:
                ad_tot += 1
                if r['avgT'] > 0.33*rm + 21.8 + 2: ad_ex += 1
    pct_adaptive = ad_ex/ad_tot*100 if ad_tot else 0

    solar_pairs = [(r['avgLux'],r['avgT']) for r in rows if r['avgLux'] is not None and r['avgT'] is not None and 8<=r['time'].hour<=18]
    solar_corr = None
    if len(solar_pairs)>20:
        lx,ty = [p[0] for p in solar_pairs],[p[1] for p in solar_pairs]
        mx,my = sum(lx)/len(lx), sum(ty)/len(ty)
        num = sum((x-mx)*(y-my) for x,y in zip(lx,ty))
        dx = sum((x-mx)**2 for x in lx)**0.5
        dy = sum((y-my)**2 for y in ty)**0.5
        if dx>0 and dy>0: solar_corr = round(num/(dx*dy),3)

    pct_under_18 = sum(1 for t in temps if t<UNDERHEAT_WHO)/len(temps)*100
    pct_under_16 = sum(1 for t in temps if t<UNDERHEAT_SEVERE)/len(temps)*100
    pct_under_12 = sum(1 for t in temps if t<UNDERHEAT_CRIT)/len(temps)*100

    fuel_poverty = False
    w7 = 2016
    if len(rows) > w7:
        for i in range(0, len(rows)-w7, 288):
            ch = [r['avgT'] for r in rows[i:i+w7] if r['avgT'] is not None]
            if ch and max(ch) < UNDERHEAT_WHO:
                fuel_poverty = True; break

    hdd = sum(max(0, 15.5-r['weather_temperature'])/288 for r in rows if r['weather_temperature'] is not None)

    mean_co2 = sum(co2s)/len(co2s) if co2s else None
    max_co2 = max(co2s) if co2s else None
    pct_co2_1000 = sum(1 for c in co2s if c>CO2_ACTION)/len(co2s)*100 if co2s else 0
    pct_co2_1500 = sum(1 for c in co2s if c>CO2_POOR)/len(co2s)*100 if co2s else 0

    win_ev = 0
    for i in range(1, len(rows)):
        r0,r1 = rows[i-1], rows[i]
        if all(v is not None for v in [r0['avgT'],r1['avgT'],r0['avgCO2'],r1['avgCO2'],r1['avgRe'],r1['weather_temperature']]):
            if r1['avgT']-r0['avgT']<-0.5 and r1['avgCO2']-r0['avgCO2']<-50 and r1['avgRe']>OCCUPANCY_THRESH and r1['weather_temperature']<r1['avgT']:
                win_ev += 1
    win_ev_day = round(win_ev/max(days_span,1), 2)

    pct_occ = sum(1 for v in re_vals if v>OCCUPANCY_THRESH)/len(re_vals)*100 if re_vals else None

    deltas = [r['avgT']-r['weather_temperature'] for r in rows if r['avgT'] is not None and r['weather_temperature'] is not None]
    mean_delta = sum(deltas)/len(deltas) if deltas else None

    out_temps = [r['weather_temperature'] for r in rows if r['weather_temperature'] is not None]
    if out_temps:
        mo = sum(out_temps)/len(out_temps)
        so = (sum((t-mo)**2 for t in out_temps)/len(out_temps))**0.5
        tri = round(std_temp/so, 3) if so>0 else None
    else: tri = None

    dates_seen = set(r['time'].date() for r in rows)
    npe_vals = []
    for day in sorted(dates_seen):
        ev = [r for r in rows if r['time'].date()==day and r['time'].hour==22 and r['avgT'] is not None]
        nd = day+timedelta(days=1)
        mo = [r for r in rows if r['time'].date()==nd and r['time'].hour==6 and r['avgT'] is not None]
        no = [r['weather_temperature'] for r in rows if ((r['time'].date()==day and r['time'].hour>=22) or (r['time'].date()==nd and r['time'].hour<6)) and r['weather_temperature'] is not None]
        if ev and mo and no:
            te,tm2,to2 = ev[0]['avgT'], mo[0]['avgT'], sum(no)/len(no)
            if te-to2>1: npe_vals.append((te-tm2)/(te-to2))
    mean_npe = sum(npe_vals)/len(npe_vals) if npe_vals else None

    wind_pairs = []
    for i in range(1,len(rows)):
        r0,r1 = rows[i-1],rows[i]
        if r1['avgRe'] is not None and r1['avgRe']<OCCUPANCY_THRESH and all(v is not None for v in [r0['avgT'],r1['avgT'],r1['weather_wind_speed']]):
            wind_pairs.append((r1['weather_wind_speed'], (r1['avgT']-r0['avgT'])*12))
    wind_corr = None
    if len(wind_pairs)>20:
        wx,wy = [p[0] for p in wind_pairs],[p[1] for p in wind_pairs]
        mwx,mwy = sum(wx)/len(wx), sum(wy)/len(wy)
        num = sum((x-mwx)*(y-mwy) for x,y in zip(wx,wy))
        dwx = sum((x-mwx)**2 for x in wx)**0.5
        dwy = sum((y-mwy)**2 for y in wy)**0.5
        if dwx>0 and dwy>0: wind_corr = round(num/(dwx*dwy),3)

    tc = [abs(rows[i]['avgT']-rows[i-1]['avgT']) for i in range(1,len(rows)) if rows[i]['avgT'] is not None and rows[i-1]['avgT'] is not None]
    mtv = sum(tc)/len(tc) if tc else 0

    # ── Occupied vs Unoccupied split (using avgrdr) ──
    occ_rows = [r for r in rows if r.get('avgrdr') is not None and r['avgrdr'] > 0.3]
    unocc_rows = [r for r in rows if r.get('avgrdr') is not None and r['avgrdr'] <= 0.3]

    def occ_stats(subset):
        ts = [r['avgT'] for r in subset if r['avgT'] is not None]
        hs = [r['avgH'] for r in subset if r['avgH'] is not None]
        cs = [r['avgCO2'] for r in subset if r['avgCO2'] is not None]
        vpxs = []
        for r in subset:
            if all(r[k] is not None for k in ['avgT','avgH','weather_temperature','weather_humidity']):
                vi2, vo2 = vp(r['avgT'],r['avgH']), vp(r['weather_temperature'],r['weather_humidity'])
                if vi2 is not None and vo2 is not None: vpxs.append(vi2-vo2)
        return {
            'count': len(subset),
            'mean_temp': round(sum(ts)/len(ts),1) if ts else None,
            'min_temp': round(min(ts),1) if ts else None,
            'max_temp': round(max(ts),1) if ts else None,
            'mean_rh': round(sum(hs)/len(hs),1) if hs else None,
            'max_rh': round(max(hs),1) if hs else None,
            'pct_rh_70': round(sum(1 for h in hs if h>MOULD_RH_HIGH)/len(hs)*100,1) if hs else 0,
            'pct_rh_80': round(sum(1 for h in hs if h>MOULD_RH_CRIT)/len(hs)*100,1) if hs else 0,
            'mean_co2': round(sum(cs)/len(cs),0) if cs else None,
            'max_co2': round(max(cs),0) if cs else None,
            'pct_co2_1000': round(sum(1 for c in cs if c>CO2_ACTION)/len(cs)*100,1) if cs else 0,
            'pct_co2_1500': round(sum(1 for c in cs if c>CO2_POOR)/len(cs)*100,1) if cs else 0,
            'mean_vpx': round(sum(vpxs)/len(vpxs),1) if vpxs else None,
            'pct_under_18': round(sum(1 for t in ts if t<UNDERHEAT_WHO)/len(ts)*100,1) if ts else 0,
            'pct_over_26': round(sum(1 for t in ts if t>OVERHEAT_CIBSE)/len(ts)*100,1) if ts else 0,
        }

    occ_metrics = occ_stats(occ_rows)
    unocc_metrics = occ_stats(unocc_rows)

    # Ratings (no "fail")
    def mr(s):
        if s>=40: return "Critical"
        if s>=20: return "High"
        if s>=10: return "Medium"
        return "Low"
    def ohr(p):
        if p>3: return "Exceeds Limit"
        if p>1: return "Warning"
        return "Pass"
    def uhr(p):
        if p>20: return "Critical"
        if p>10: return "High"
        if p>5: return "Medium"
        return "Low"
    def vr(m):
        if m is None: return "No data"
        if m>CO2_POOR: return "Inadequate"
        if m>CO2_ACTION: return "Poor"
        if m>CO2_GOOD: return "Acceptable"
        return "Good"
    def vpxr(v):
        if v is None: return "No data"
        if v>600: return "Very High"
        if v>300: return "High"
        if v>200: return "Elevated"
        return "Normal"
    def crir(c):
        if c is None: return "No data"
        if c<1: return "Critical"
        if c<3: return "High"
        if c<5: return "Moderate"
        return "Low"
    def fr(t):
        if t is None: return "No data"
        if t>0.7: return "Lightweight"
        if t>0.3: return "Moderate"
        return "Heavy"

    return {
        'first_ts': first_ts.strftime('%Y-%m-%d'), 'last_ts': last_ts.strftime('%Y-%m-%d'),
        'days_span': round(days_span,1), 'data_points': total,
        'mean_temp': round(mean_temp,1), 'min_temp': round(min(temps),1), 'max_temp': round(max(temps),1),
        'std_temp': round(std_temp,2), 'mean_temp_variability': round(mtv,3),
        'mean_rh': round(mean_rh,1), 'max_rh': round(max(humids),1),
        'pct_rh_70': round(pct_rh_70,1), 'pct_rh_80': round(pct_rh_80,1),
        'pct_dew_close': round(pct_dew_close,1),
        'mould_score': round(mould_score,1), 'mould_rating': mr(mould_score),
        'mean_vpx': round(mean_vpx,1) if mean_vpx is not None else None,
        'pct_vpx_300': round(pct_vpx_300,1), 'pct_vpx_600': round(pct_vpx_600,1),
        'vpx_rating': vpxr(mean_vpx),
        'mean_cri': round(mean_cri,1) if mean_cri is not None else None,
        'min_cri': round(min_cri,1) if min_cri is not None else None,
        'pct_cri_critical': round(pct_cri_critical,1), 'cri_rating': crir(mean_cri),
        'mean_ehr': round(mean_ehr,1) if mean_ehr is not None else None,
        'pct_over_25': round(pct_over_25,1), 'pct_over_26': round(pct_over_26,1),
        'pct_over_28': round(pct_over_28,1), 'pct_adaptive_exceed': round(pct_adaptive,1),
        'overheat_rating': ohr(pct_over_26), 'solar_corr': solar_corr,
        'pct_under_18': round(pct_under_18,1), 'pct_under_16': round(pct_under_16,1),
        'pct_under_12': round(pct_under_12,1),
        'fuel_poverty_flag': fuel_poverty, 'underheat_rating': uhr(pct_under_18),
        'hdd_total': round(hdd,1),
        'mean_co2': round(mean_co2,0) if mean_co2 is not None else None,
        'max_co2': round(max_co2,0) if max_co2 is not None else None,
        'pct_co2_above_1000': round(pct_co2_1000,1), 'pct_co2_above_1500': round(pct_co2_1500,1),
        'ventilation_rating': vr(mean_co2), 'window_events_per_day': win_ev_day,
        'pct_occupied': round(pct_occ,1) if pct_occ is not None else None,
        'mean_indoor_outdoor_delta': round(mean_delta,1) if mean_delta is not None else None,
        'thermal_responsiveness': tri, 'fabric_rating': fr(tri),
        'mean_npe': round(mean_npe,3) if mean_npe is not None else None,
        'wind_infiltration_corr': wind_corr,
        'occ': occ_metrics,
        'unocc': unocc_metrics,
        '_cluster_features': [
            mean_temp, std_temp, mean_rh, pct_rh_70, pct_over_26, pct_under_18,
            mean_co2 or 0, mean_delta or 0, mtv, pct_occ or 0,
            mean_vpx or 0, mean_cri or 0, mean_ehr or 0, tri or 0,
        ]
    }


# K-Means
def norm(data):
    if not data: return data,[],[]
    n=len(data[0])
    mi=[min(r[i] for r in data) for i in range(n)]
    ma=[max(r[i] for r in data) for i in range(n)]
    rng=[ma[i]-mi[i] if ma[i]!=mi[i] else 1 for i in range(n)]
    return [[(r[i]-mi[i])/rng[i] for i in range(n)] for r in data],mi,rng

def euc(a,b): return sum((x-y)**2 for x,y in zip(a,b))**0.5

def km(data,k=4,mi=100):
    import random; random.seed(42)
    if len(data)<=k: return list(range(len(data))),data[:]
    c=random.sample(data,k); lb=[0]*len(data)
    for _ in range(mi):
        nl=[min(range(k),key=lambda j:euc(p,c[j])) for p in data]
        if nl==lb: break
        lb=nl
        for j in range(k):
            ms=[data[i] for i in range(len(data)) if lb[i]==j]
            if ms: c[j]=[sum(m[f] for m in ms)/len(ms) for f in range(len(data[0]))]
    return lb,c

def sil(data,lb):
    n=len(data)
    if n<3: return 0
    sc=[]
    for i in range(n):
        same=[j for j in range(n) if lb[j]==lb[i] and j!=i]
        if not same: sc.append(0); continue
        a=sum(euc(data[i],data[j]) for j in same)/len(same)
        b=float('inf')
        for cc in set(lb)-{lb[i]}:
            ot=[j for j in range(n) if lb[j]==cc]
            if ot: b=min(b,sum(euc(data[i],data[j]) for j in ot)/len(ot))
        sc.append((b-a)/max(a,b) if max(a,b)>0 and b!=float('inf') else 0)
    return sum(sc)/len(sc)

def best_k(data,mx=6):
    bk,bs,bl=2,-1,None
    for k in range(2,min(mx+1,len(data))):
        lb,_=km(data,k); s=sil(data,lb)
        if s>bs: bk,bs,bl=k,s,lb
    return bk,bl,bs

def desc_cluster(members):
    if not members: return "Empty"
    av=lambda k: sum(m[k] for m in members)/len(members)
    t=[]; am=av('mould_score'); au=av('pct_under_18'); ao=av('pct_over_26'); ar=av('mean_rh')
    avpx = av('mean_vpx') if all(m.get('mean_vpx') is not None for m in members) else None
    t.append("High mould risk" if am>30 else "Moderate mould risk" if am>15 else "Low mould risk")
    t.append("significant under-heating" if au>15 else "overheating tendency" if ao>3 else "adequate temperature")
    if ar>65: t.append("high humidity")
    elif ar<45: t.append("dry")
    if avpx is not None:
        if avpx>300: t.append("high VPX")
        elif avpx<100: t.append("low VPX")
    return ", ".join(t).capitalize()


# ── HTML ──
def rc(r):
    return {'Low':'#22c55e','Pass':'#22c55e','Good':'#22c55e','Normal':'#22c55e','Heavy':'#22c55e',
            'Medium':'#f59e0b','Acceptable':'#f59e0b','Warning':'#f59e0b','Moderate':'#f59e0b','Elevated':'#f59e0b',
            'High':'#ef4444','Poor':'#ef4444','Exceeds Limit':'#ef4444','Lightweight':'#ef4444',
            'Very High':'#991b1b','Critical':'#991b1b','Inadequate':'#991b1b','No data':'#9ca3af'}.get(r,'#9ca3af')

def rb(r):
    return {'Low':'#f0fdf4','Pass':'#f0fdf4','Good':'#f0fdf4','Normal':'#f0fdf4','Heavy':'#f0fdf4',
            'Medium':'#fffbeb','Acceptable':'#fffbeb','Warning':'#fffbeb','Moderate':'#fffbeb','Elevated':'#fffbeb',
            'High':'#fef2f2','Poor':'#fef2f2','Exceeds Limit':'#fef2f2','Lightweight':'#fef2f2',
            'Very High':'#fef2f2','Critical':'#fef2f2','Inadequate':'#fef2f2','No data':'#f9fafb'}.get(r,'#f9fafb')

def bdg(t,c,b): return f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;color:{c};background:{b}">{t}</span>'
def mc(v,u=''): return f'<td style="color:#9ca3af">—</td>' if v is None else f'<td>{v}{u}</td>'
def mini(cnt,lab,c,b): return f'<span class="mini-badge" style="color:{c};background:{b}">{cnt} {lab}</span>'

def gen_html(props, cl_labels, cl_descs, bk, ss):
    # Count risks
    counts = {}
    for key in ['mould_rating','cri_rating','vpx_rating','overheat_rating','underheat_rating','ventilation_rating','fabric_rating']:
        counts[key] = defaultdict(int)
    fp_count = 0
    for p in props:
        rm = p.get('rm')
        if rm:
            for key in counts: counts[key][rm[key]] += 1
            if rm['fuel_poverty_flag']: fp_count += 1

    tp = len(props)
    now = datetime.now().strftime('%d %B %Y')

    # Build chart data JSON
    chart_data = {}
    for p in props:
        chart_data[p['id']] = {
            'corridor': p.get('corridor_daily'),
            'room': p.get('room_daily'),
        }

    # Build portfolio-level bar chart data (sorted by mould score)
    sorted_props = sorted(props, key=lambda x: x['rm']['mould_score'], reverse=True)
    portfolio_labels = [p['id'][-6:] for p in sorted_props]
    portfolio_mould = [p['rm']['mould_score'] for p in sorted_props]
    portfolio_vpx = [p['rm']['mean_vpx'] or 0 for p in sorted_props]
    portfolio_under = [p['rm']['pct_under_18'] for p in sorted_props]
    portfolio_over = [p['rm']['pct_over_26'] for p in sorted_props]
    portfolio_co2 = [p['rm']['mean_co2'] or 0 for p in sorted_props]

    # Corridor vs Room comparison chart data
    comp_labels = []
    comp_temp_corr = []; comp_temp_room = []
    comp_rh_corr = []; comp_rh_room = []
    comp_mould_corr = []; comp_mould_room = []
    for p in props:
        cm = p.get('cm')
        rm = p.get('rm')
        if cm and rm:
            comp_labels.append(p['id'][-6:])
            comp_temp_corr.append(cm['mean_temp']); comp_temp_room.append(rm['mean_temp'])
            comp_rh_corr.append(cm['mean_rh']); comp_rh_room.append(rm['mean_rh'])
            comp_mould_corr.append(cm['mould_score']); comp_mould_room.append(rm['mould_score'])

    # Cluster radar data
    cluster_groups = defaultdict(list)
    for i, p in enumerate(props):
        cl = cl_labels[i] if i < len(cl_labels) else 0
        cluster_groups[cl].append(p['rm'])

    radar_data = {}
    for cl_id, members in cluster_groups.items():
        av = lambda k: round(sum(m[k] for m in members)/len(members), 1)
        radar_data[cl_id] = {
            'mean_temp': av('mean_temp'), 'mean_rh': av('mean_rh'),
            'mould_score': av('mould_score'), 'pct_under_18': av('pct_under_18'),
            'pct_over_26': av('pct_over_26'),
            'mean_co2': round(sum((m['mean_co2'] or 0) for m in members)/len(members), 0),
            'mean_vpx': round(sum((m['mean_vpx'] or 0) for m in members)/len(members), 1),
        }

    # ── Donut chart data for summary
    donut_data = {}
    for key, label_map in [
        ('mould_rating', {'Critical':'Critical','High':'High','Medium':'Medium','Low':'Low'}),
        ('overheat_rating', {'Exceeds Limit':'Exceeds Limit','Warning':'Warning','Pass':'Pass'}),
        ('underheat_rating', {'Critical':'Critical','High':'High','Medium':'Medium','Low':'Low'}),
        ('ventilation_rating', {'Inadequate':'Inadequate','Poor':'Poor','Acceptable':'Acceptable','Good':'Good'}),
    ]:
        donut_data[key] = {l: counts[key].get(l,0) for l in label_map}

    sc = '</scr' + 'ipt>'
    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>WHG Environmental Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js">{sc}
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.1.0/dist/chartjs-plugin-annotation.min.js">{sc}
<link href="https://fonts.googleapis.com/css?family=Inter:400,500,600,700,800" rel="stylesheet">
<style>
:root{{
  --bg:#f7f9fc;--card:#ffffff;--border:#e9eaf3;--text:#0b0e2c;--ts:#6f7182;
  --accent:#028cff;--accent-hover:#004cff;--al:#eaf4ff;
  --green:#13a570;--green-light:#e4faed;--green-dark:#05c168;
  --red:#dc2b2b;--red-light:#ffeff0;
  --orange:#d5691b;--orange-light:#fff3e4;--orange-300:#ff9e2c;
  --blue:#086cd9;--blue-light:#eaf4ff;
  --purple:#9240fb;--purple-light:#f6f1ff;
  --shadow-1:#195dc212;--shadow-2:#0b162c0d;
  --n100:white;--n200:#f7f9fc;--n300:#e9eaf3;--n400:#cacbd7;--n500:#989aad;--n600:#6f7182;--n700:#303350;--n800:#0b0e2c;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:Inter,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;-webkit-font-smoothing:antialiased}}
.hdr{{background:linear-gradient(135deg,#0b0e2c 0%,#1045cc 50%,#028cff 100%);color:#fff;padding:32px 40px}}
.hdr h1{{font-size:28px;font-weight:800;margin-bottom:4px;letter-spacing:-.5px}}.hdr p{{opacity:.85;font-size:14px;font-weight:400}}
.ctr{{max-width:1440px;margin:0 auto;padding:24px}}
.tabs{{display:flex;gap:4px;margin-bottom:24px;overflow-x:auto;padding-bottom:2px}}
.tab{{padding:9px 18px;cursor:pointer;font-size:12.6px;font-weight:500;color:var(--n800);background:var(--n100);
  border:1px solid var(--n300);border-radius:5px;white-space:nowrap;transition:all .3s ease}}
.tab:hover{{background:var(--n200);border-color:var(--n400)}}.tab.active{{background:var(--accent);color:white;border-color:var(--accent)}}
.tc{{display:none}}.tc.active{{display:block}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:28px}}
.tile{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px 24px;
  box-shadow:0 1px 3px var(--shadow-2);transition:all .2s ease}}
.tile:hover{{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.1);border-color:var(--n400)}}
.tile .lb{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--n600);margin-bottom:8px;font-weight:600}}
.tile .vl{{font-size:32px;font-weight:700;line-height:1;color:var(--n800)}}.tile .sb{{font-size:11px;color:var(--n600);margin-top:6px}}
.tile-row{{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}}
.mini-badge{{display:inline-flex;align-items:center;gap:3px;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid transparent}}
.tw{{overflow-x:auto;border-radius:12px;border:1px solid var(--border);background:var(--card);
  box-shadow:0 1px 3px var(--shadow-2);margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead{{background:var(--n200)}}
th{{padding:12px 14px;text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;
  letter-spacing:.5px;color:var(--n600);border-bottom:1px solid var(--border);white-space:nowrap}}
td{{padding:10px 14px;border-bottom:1px solid var(--n300)}}
tr:hover{{background:var(--n200)}}tr:last-child td{{border-bottom:none}}
.pl{{color:var(--accent);text-decoration:none;font-weight:600}}.pl:hover{{color:var(--accent-hover);text-decoration:underline}}
.pd{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;
  margin-bottom:20px;box-shadow:0 1px 3px var(--shadow-2)}}
.pd h3{{font-size:18px;margin-bottom:16px;font-weight:700;letter-spacing:-.25px}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:16px}}
.mb{{padding:14px 18px;border-radius:12px;border:1px solid var(--border);background:var(--n200);transition:all .2s ease}}
.mb:hover{{transform:translateY(-1px);box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.mb .ml{{font-size:11px;text-transform:uppercase;color:var(--n600);font-weight:600;letter-spacing:.5px}}
.mb .mv{{font-size:20px;font-weight:700;margin-top:4px;color:var(--n800)}}.mb .ms{{font-size:11px;color:var(--n500)}}
.cc{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;
  margin-bottom:14px;box-shadow:0 1px 3px var(--shadow-2)}}
.cc h4{{margin-bottom:8px;font-weight:700;letter-spacing:-.25px}}
.ib{{background:var(--blue-light);border:1px solid #8fc3ff;border-radius:12px;padding:16px 20px;
  margin-bottom:20px;font-size:13px;color:var(--blue)}}
.ib strong{{font-weight:700}}
.bl{{display:inline-flex;align-items:center;gap:4px;color:var(--accent);font-size:13px;
  text-decoration:none;margin-bottom:14px;font-weight:500}}
.bl:hover{{color:var(--accent-hover);text-decoration:underline}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.chart-box{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;
  box-shadow:0 1px 3px var(--shadow-2)}}
.chart-box h4{{font-size:12px;font-weight:600;color:var(--n600);margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px}}
.chart-box canvas{{width:100%!important;max-height:280px}}
.donut-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.donut-box{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;
  text-align:center;box-shadow:0 1px 3px var(--shadow-2)}}
.donut-box h4{{font-size:11px;font-weight:600;color:var(--n600);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px}}
.donut-box canvas{{max-height:180px}}
h3{{font-weight:700;color:var(--n800);letter-spacing:-.25px}}
@media (max-width:900px){{.chart-row,.donut-row{{grid-template-columns:1fr}}.tiles{{grid-template-columns:1fr 1fr}}.hdr{{padding:20px}}.ctr{{padding:16px}}}}
</style></head><body>
<div class="hdr"><h1>WHG Environmental Monitoring Dashboard</h1>
<p>Social Housing Portfolio Analysis &mdash; {tp} Properties &mdash; Generated {now}</p></div>
<div class="ctr">
<div class="tabs">
<div class="tab active" onclick="showTab('summary')">Summary</div>
<div class="tab" onclick="showTab('mould')">Damp & Mould</div>
<div class="tab" onclick="showTab('moisture')">Moisture Analysis</div>
<div class="tab" onclick="showTab('overheat')">Overheating</div>
<div class="tab" onclick="showTab('underheat')">Under-heating</div>
<div class="tab" onclick="showTab('ventilation')">Ventilation</div>
<div class="tab" onclick="showTab('fabric')">Building Fabric</div>
<div class="tab" onclick="showTab('occupancy')">Occupancy Impact</div>
<div class="tab" onclick="showTab('comparison')">Corridor vs Room</div>
<div class="tab" onclick="showTab('riskdiff')">Risk Divergence</div>
<div class="tab" onclick="showTab('clusters')">Clustering</div>
<div class="tab" onclick="showTab('properties')">All Properties</div>
<div class="tab" onclick="showTab('methodology')">Methodology</div>
<div class="tab" onclick="showTab('info')">Info</div>
<div class="tab" onclick="showTab('glossary')">Glossary</div>
</div>

<!-- SUMMARY -->
<div id="tab-summary" class="tc active">
<div class="tiles">
<div class="tile"><div class="lb">Properties Monitored</div><div class="vl">{tp}</div><div class="sb">Corridor + room sensors each</div></div>
<div class="tile"><div class="lb">Damp & Mould Risk</div><div class="vl" style="color:{rc('Critical') if counts['mould_rating'].get('Critical',0) else rc('High') if counts['mould_rating'].get('High',0) else '#22c55e'}">{counts['mould_rating'].get('Critical',0)+counts['mould_rating'].get('High',0)}</div><div class="sb">High/Critical risk</div>
<div class="tile-row">{mini(counts['mould_rating'].get('Critical',0),'Critical','#991b1b','#fef2f2')}{mini(counts['mould_rating'].get('High',0),'High','#ef4444','#fef2f2')}{mini(counts['mould_rating'].get('Medium',0),'Medium','#f59e0b','#fffbeb')}{mini(counts['mould_rating'].get('Low',0),'Low','#22c55e','#f0fdf4')}</div></div>
<div class="tile"><div class="lb">Condensation Risk</div><div class="vl" style="color:{rc('Critical') if counts['cri_rating'].get('Critical',0) else '#22c55e'}">{counts['cri_rating'].get('Critical',0)+counts['cri_rating'].get('High',0)}</div><div class="sb">High/Critical CRI</div>
<div class="tile-row">{mini(counts['cri_rating'].get('Critical',0),'Critical','#991b1b','#fef2f2')}{mini(counts['cri_rating'].get('High',0),'High','#ef4444','#fef2f2')}{mini(counts['cri_rating'].get('Moderate',0),'Moderate','#f59e0b','#fffbeb')}{mini(counts['cri_rating'].get('Low',0),'Low','#22c55e','#f0fdf4')}</div></div>
<div class="tile"><div class="lb">Overheating</div><div class="vl" style="color:{rc('Exceeds Limit') if counts['overheat_rating'].get('Exceeds Limit',0) else '#22c55e'}">{counts['overheat_rating'].get('Exceeds Limit',0)}</div><div class="sb">Exceeding CIBSE limits</div>
<div class="tile-row">{mini(counts['overheat_rating'].get('Exceeds Limit',0),'Exceeds','#ef4444','#fef2f2')}{mini(counts['overheat_rating'].get('Warning',0),'Warning','#f59e0b','#fffbeb')}{mini(counts['overheat_rating'].get('Pass',0),'Pass','#22c55e','#f0fdf4')}</div></div>
<div class="tile"><div class="lb">Under-heating</div><div class="vl" style="color:{rc('Critical') if counts['underheat_rating'].get('Critical',0) else '#22c55e'}">{counts['underheat_rating'].get('Critical',0)+counts['underheat_rating'].get('High',0)}</div><div class="sb">High/Critical</div>
<div class="tile-row">{mini(counts['underheat_rating'].get('Critical',0),'Critical','#991b1b','#fef2f2')}{mini(counts['underheat_rating'].get('High',0),'High','#ef4444','#fef2f2')}{mini(counts['underheat_rating'].get('Medium',0),'Medium','#f59e0b','#fffbeb')}{mini(counts['underheat_rating'].get('Low',0),'Low','#22c55e','#f0fdf4')}</div></div>
<div class="tile"><div class="lb">Ventilation</div><div class="vl" style="color:{rc('Inadequate') if counts['ventilation_rating'].get('Inadequate',0) else '#22c55e'}">{counts['ventilation_rating'].get('Inadequate',0)+counts['ventilation_rating'].get('Poor',0)}</div><div class="sb">Poor/Inadequate</div>
<div class="tile-row">{mini(counts['ventilation_rating'].get('Inadequate',0),'Inadequate','#991b1b','#fef2f2')}{mini(counts['ventilation_rating'].get('Poor',0),'Poor','#ef4444','#fef2f2')}{mini(counts['ventilation_rating'].get('Acceptable',0),'Acceptable','#f59e0b','#fffbeb')}{mini(counts['ventilation_rating'].get('Good',0),'Good','#22c55e','#f0fdf4')}</div></div>
<div class="tile"><div class="lb">Fabric Performance</div><div class="vl" style="color:{rc('Lightweight') if counts['fabric_rating'].get('Lightweight',0) else '#22c55e'}">{counts['fabric_rating'].get('Lightweight',0)}</div><div class="sb">Lightweight (poor thermal mass)</div>
<div class="tile-row">{mini(counts['fabric_rating'].get('Lightweight',0),'Light','#ef4444','#fef2f2')}{mini(counts['fabric_rating'].get('Moderate',0),'Moderate','#f59e0b','#fffbeb')}{mini(counts['fabric_rating'].get('Heavy',0),'Heavy','#22c55e','#f0fdf4')}</div></div>
<div class="tile"><div class="lb">Fuel Poverty Indicator</div><div class="vl" style="color:{'#ef4444' if fp_count else '#22c55e'}">{fp_count}</div><div class="sb">Never reaching 18°C in 7-day window</div></div>
</div>

<!-- Summary donut charts -->
<div class="donut-row">
<div class="donut-box"><h4>Damp & Mould</h4><canvas id="donut-mould"></canvas></div>
<div class="donut-box"><h4>Overheating</h4><canvas id="donut-overheat"></canvas></div>
<div class="donut-box"><h4>Under-heating</h4><canvas id="donut-underheat"></canvas></div>
<div class="donut-box"><h4>Ventilation</h4><canvas id="donut-vent"></canvas></div>
</div>

<!-- Portfolio bar charts -->
<div class="chart-row">
<div class="chart-box"><h4>Mould Score by Property</h4><canvas id="bar-mould"></canvas></div>
<div class="chart-box"><h4>Mean VPX by Property (Pa)</h4><canvas id="bar-vpx"></canvas></div>
</div>
<div class="chart-row">
<div class="chart-box"><h4>% Time Under 18°C</h4><canvas id="bar-under"></canvas></div>
<div class="chart-box"><h4>% Time Over 26°C</h4><canvas id="bar-over"></canvas></div>
</div>

<div style="display:flex;align-items:center;gap:12px;margin:20px 0 12px">
<h3 style="font-size:16px">Risk Overview</h3>
<label style="font-size:12px;color:var(--n600);font-weight:500">Sort by:</label>
<select id="risk-sort" onchange="sortRiskTable()" style="padding:6px 12px;border:1px solid var(--n300);border-radius:6px;font-family:Inter,sans-serif;font-size:12px;color:var(--n800);background:var(--n100);cursor:pointer">
<option value="mould">Mould Risk</option>
<option value="condensation">Condensation Risk</option>
<option value="vpx">VPX</option>
<option value="overheat">Overheating</option>
<option value="underheat">Under-heating</option>
<option value="ventilation">Ventilation</option>
<option value="fabric">Fabric</option>
<option value="delta_temp">Corridor-Room &Delta;T</option>
<option value="delta_rh">Corridor-Room &Delta;RH</option>
<option value="delta_mould">Corridor-Room &Delta;Mould</option>
<option value="room_alert">Room Risk Alert</option>
</select>
</div>
<div class="tw"><table id="risk-table">
<thead><tr><th>Property</th><th>Mould</th><th>Condensation</th><th>VPX</th><th>Overheat</th><th>Under-heat</th><th>Ventilation</th><th>Fabric</th><th>Room Risk Alert</th><th>&Delta;T (R-C)</th><th>&Delta;RH (R-C)</th><th>&Delta;Mould (R-C)</th><th>Cluster</th></tr></thead><tbody>
'''
    # Build sort data JSON
    sort_data = []
    for i,p in enumerate(props):
        rm=p.get('rm'); cm=p.get('cm')
        if not rm: continue
        sid=p['id'][-6:]; cl=cl_labels[i] if i<len(cl_labels) else 0
        # Numeric sort values (higher = worse)
        risk_order = {'Critical':4,'Very High':4,'Inadequate':4,'High':3,'Exceeds Limit':3,'Poor':3,'Lightweight':3,
                      'Medium':2,'Moderate':2,'Warning':2,'Acceptable':2,'Elevated':2,
                      'Low':1,'Pass':1,'Good':1,'Normal':1,'Heavy':1,'No data':0}
        dt = round(rm['mean_temp'] - cm['mean_temp'], 1) if cm and cm.get('mean_temp') is not None else None
        drh = round(rm['mean_rh'] - cm['mean_rh'], 1) if cm and cm.get('mean_rh') is not None else None
        dm = round(rm['mould_score'] - cm['mould_score'], 1) if cm and cm.get('mould_score') is not None else None
        sort_data.append({
            'sid': sid, 'pid': p['id'], 'cl': cl+1,
            'mould': risk_order.get(rm['mould_rating'],0), 'mould_s': rm['mould_score'],
            'condensation': risk_order.get(rm['cri_rating'],0), 'cri_s': rm.get('mean_cri') or 99,
            'vpx': risk_order.get(rm['vpx_rating'],0), 'vpx_s': rm.get('mean_vpx') or 0,
            'overheat': risk_order.get(rm['overheat_rating'],0), 'oh_s': rm['pct_over_26'],
            'underheat': risk_order.get(rm['underheat_rating'],0), 'uh_s': rm['pct_under_18'],
            'ventilation': risk_order.get(rm['ventilation_rating'],0), 'vent_s': rm.get('mean_co2') or 0,
            'fabric': risk_order.get(rm['fabric_rating'],0), 'tri_s': rm.get('thermal_responsiveness') or 0,
            'delta_temp': abs(dt) if dt is not None else 0,
            'delta_rh': abs(drh) if drh is not None else 0,
            'delta_mould': abs(dm) if dm is not None else 0,
            'dt': dt, 'drh': drh, 'dm': dm,
            'room_alert': 0,
            'ratings': {k: rm[k] for k in ['mould_rating','cri_rating','vpx_rating','overheat_rating','underheat_rating','ventilation_rating','fabric_rating']},
        })
        # Compute room_alert count for sorting
        if cm:
            ra_count = 0
            for rk in ['mould_rating','cri_rating','vpx_rating','overheat_rating','underheat_rating','ventilation_rating']:
                r_room2 = risk_order.get(rm.get(rk,''),0)
                r_corr2 = risk_order.get(cm.get(rk,''),0)
                if r_room2 >= 3 and r_room2 > r_corr2: ra_count += 1
            sort_data[-1]['room_alert'] = ra_count

    # Build table rows with delta columns and highlighting
    for i,p in enumerate(props):
        rm=p.get('rm'); cm=p.get('cm')
        if not rm: continue
        sid=p['id'][-6:]; cl=cl_labels[i] if i<len(cl_labels) else 0
        dt = round(rm['mean_temp'] - cm['mean_temp'], 1) if cm and cm.get('mean_temp') is not None else None
        drh = round(rm['mean_rh'] - cm['mean_rh'], 1) if cm and cm.get('mean_rh') is not None else None
        dm = round(rm['mould_score'] - cm['mould_score'], 1) if cm and cm.get('mould_score') is not None else None

        def delta_td(val, warn, crit):
            if val is None: return '<td style="color:var(--n500)">—</td>'
            av = abs(val)
            if av >= crit: bg = 'var(--red-light)'; c = 'var(--red)'; icon = ' &#9888;'
            elif av >= warn: bg = 'var(--orange-light)'; c = 'var(--orange)'; icon = ''
            else: bg = ''; c = 'var(--green)'; icon = ''
            style = f'color:{c};font-weight:600'
            if bg: style += f';background:{bg}'
            return f'<td style="{style}">{val:+.1f}{icon}</td>'

        # Room Risk Alert: flag where room has higher risk than corridor
        alerts = []
        if cm:
            risk_order2 = {'Critical':4,'Very High':4,'Inadequate':4,'High':3,'Exceeds Limit':3,'Poor':3,'Lightweight':3,
                           'Medium':2,'Moderate':2,'Warning':2,'Acceptable':2,'Elevated':2,
                           'Low':1,'Pass':1,'Good':1,'Normal':1,'Heavy':1,'No data':0}
            for rk, lbl in [('mould_rating','Mould'),('cri_rating','CRI'),('vpx_rating','VPX'),
                            ('overheat_rating','Overheat'),('underheat_rating','Cold'),('ventilation_rating','CO2')]:
                r_room = risk_order2.get(rm.get(rk,''),0)
                r_corr = risk_order2.get(cm.get(rk,''),0)
                if r_room >= 3 and r_room > r_corr:
                    alerts.append(lbl)
        if alerts:
            alert_html = '<td style="background:var(--red-light)"><span style="color:var(--red);font-weight:700;font-size:11px">&#9888; ' + ', '.join(alerts) + '</span></td>'
        else:
            alert_html = '<td style="color:var(--green);font-size:11px">—</td>'

        html+=f'<tr data-idx="{i}"><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td>'
        for k in ['mould_rating','cri_rating','vpx_rating','overheat_rating','underheat_rating','ventilation_rating','fabric_rating']:
            r=rm[k]; html+=f'<td>{bdg(r,rc(r),rb(r))}</td>'
        html+=f'{alert_html}{delta_td(dt, 2, 4)}{delta_td(drh, 5, 10)}{delta_td(dm, 5, 15)}'
        html+=f'<td>{mini("","Cluster "+str(cl+1),"#1e40af","#eff6ff")}</td></tr>\n'
    html+='</tbody></table></div></div>\n'

    # ── Tab content for each category (tables same as before but with chart at top) ──

    # DAMP & MOULD
    html+='''<div id="tab-mould" class="tc">
<div class="ib"><strong>Damp & Mould:</strong> BS 5250 (RH &gt; 70%), ISO 13788 (RH &gt; 80%), dew point proximity (&lt; 3°C). Score = 0.5&times;%RH&gt;70 + 1.5&times;%RH&gt;80 + 0.3&times;%DewClose.</div>
<div class="chart-row"><div class="chart-box"><h4>Mould Score Distribution</h4><canvas id="hist-mould"></canvas></div>
<div class="chart-box"><h4>Mean RH vs Mould Score</h4><canvas id="scatter-mould"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th>Property</th><th>Risk</th><th>Score</th><th>Mean RH</th><th>% RH&gt;70</th><th>% RH&gt;80</th><th>% Dew Close</th><th>Mean Temp</th></tr></thead><tbody>
'''
    for p in sorted(props, key=lambda x: x['rm']['mould_score'], reverse=True):
        rm=p['rm']; sid=p['id'][-6:]
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td>{bdg(rm["mould_rating"],rc(rm["mould_rating"]),rb(rm["mould_rating"]))}</td><td><strong>{rm["mould_score"]}</strong></td>{mc(rm["mean_rh"],"%")}{mc(rm["pct_rh_70"],"%")}{mc(rm["pct_rh_80"],"%")}{mc(rm["pct_dew_close"],"%")}{mc(rm["mean_temp"],"°C")}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # MOISTURE
    html+='''<div id="tab-moisture" class="tc">
<div class="ib"><strong>Moisture Analysis:</strong> <strong>VPX</strong> = indoor - outdoor vapour pressure (BRE IP 1/06). <strong>CRI</strong> = estimated surface temp at thermal bridge vs dew point (ISO 13788). <strong>EHR</strong> = actual RH - expected RH.</div>
<div class="chart-row"><div class="chart-box"><h4>VPX vs CRI (Scatter)</h4><canvas id="scatter-moisture"></canvas></div>
<div class="chart-box"><h4>Excess Humidity Ratio Distribution</h4><canvas id="hist-ehr"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th>Property</th><th>VPX</th><th>Mean VPX</th><th>%&gt;300</th><th>%&gt;600</th><th>CRI</th><th>Mean CRI</th><th>Min CRI</th><th>%CRI&lt;1K</th><th>Mean EHR</th></tr></thead><tbody>
'''
    for p in sorted(props, key=lambda x: x['rm'].get('mean_vpx') or 0, reverse=True):
        rm=p['rm']; sid=p['id'][-6:]
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td>{bdg(rm["vpx_rating"],rc(rm["vpx_rating"]),rb(rm["vpx_rating"]))}</td>{mc(rm["mean_vpx"]," Pa")}{mc(rm["pct_vpx_300"],"%")}{mc(rm["pct_vpx_600"],"%")}<td>{bdg(rm["cri_rating"],rc(rm["cri_rating"]),rb(rm["cri_rating"]))}</td>{mc(rm["mean_cri"],"K")}{mc(rm["min_cri"],"K")}{mc(rm["pct_cri_critical"],"%")}{mc(rm["mean_ehr"],"%")}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # OVERHEATING
    html+='''<div id="tab-overheat" class="tc">
<div class="ib"><strong>Overheating:</strong> CIBSE TM59 threshold 26°C. Adaptive comfort via TM52 running mean. Solar correlation = Pearson r (lux vs temp, daytime).</div>
<div class="chart-row"><div class="chart-box"><h4>% Time Over 26°C</h4><canvas id="bar-oh-detail"></canvas></div>
<div class="chart-box"><h4>Adaptive Comfort Exceedance %</h4><canvas id="bar-adaptive"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th>Property</th><th>Rating</th><th>Mean T</th><th>Max T</th><th>%&gt;25°C</th><th>%&gt;26°C</th><th>%&gt;28°C</th><th>% Adaptive</th><th>Solar r</th></tr></thead><tbody>
'''
    for p in sorted(props, key=lambda x: x['rm']['pct_over_26'], reverse=True):
        rm=p['rm']; sid=p['id'][-6:]
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td>{bdg(rm["overheat_rating"],rc(rm["overheat_rating"]),rb(rm["overheat_rating"]))}</td>{mc(rm["mean_temp"],"°C")}{mc(rm["max_temp"],"°C")}{mc(rm["pct_over_25"],"%")}{mc(rm["pct_over_26"],"%")}{mc(rm["pct_over_28"],"%")}{mc(rm["pct_adaptive_exceed"],"%")}{mc(rm["solar_corr"])}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # UNDER-HEATING
    html+='''<div id="tab-underheat" class="tc">
<div class="ib"><strong>Under-heating:</strong> WHO 18°C minimum. Severe &lt;16°C, Critical &lt;12°C. Fuel Poverty = never reaching 18°C in 7-day window. HDD base 15.5°C.</div>
<div class="chart-row"><div class="chart-box"><h4>% Time Under 18°C</h4><canvas id="bar-uh-detail"></canvas></div>
<div class="chart-box"><h4>Min Temperature by Property</h4><canvas id="bar-min-temp"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th>Property</th><th>Rating</th><th>Mean T</th><th>Min T</th><th>%&lt;18°C</th><th>%&lt;16°C</th><th>%&lt;12°C</th><th>Fuel Poverty</th><th>HDD</th></tr></thead><tbody>
'''
    for p in sorted(props, key=lambda x: x['rm']['pct_under_18'], reverse=True):
        rm=p['rm']; sid=p['id'][-6:]
        fp='<span style="color:#ef4444;font-weight:700">Yes</span>' if rm['fuel_poverty_flag'] else 'No'
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td>{bdg(rm["underheat_rating"],rc(rm["underheat_rating"]),rb(rm["underheat_rating"]))}</td>{mc(rm["mean_temp"],"°C")}{mc(rm["min_temp"],"°C")}{mc(rm["pct_under_18"],"%")}{mc(rm["pct_under_16"],"%")}{mc(rm["pct_under_12"],"%")}<td>{fp}</td>{mc(rm["hdd_total"])}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # VENTILATION
    html+='''<div id="tab-ventilation" class="tc">
<div class="ib"><strong>Ventilation:</strong> CO2 proxy per Part F. Window events = simultaneous temp drop + CO2 drop + occupied + outdoor cooler.</div>
<div class="chart-row"><div class="chart-box"><h4>Mean CO2 by Property</h4><canvas id="bar-co2"></canvas></div>
<div class="chart-box"><h4>Window Events per Day</h4><canvas id="bar-window"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th>Property</th><th>Rating</th><th>Mean CO2</th><th>Max CO2</th><th>%&gt;1000</th><th>%&gt;1500</th><th>Win Events/Day</th><th>% Occupied</th></tr></thead><tbody>
'''
    for p in sorted(props, key=lambda x: x['rm'].get('mean_co2') or 0, reverse=True):
        rm=p['rm']; sid=p['id'][-6:]
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td>{bdg(rm["ventilation_rating"],rc(rm["ventilation_rating"]),rb(rm["ventilation_rating"]))}</td>{mc(rm["mean_co2"]," ppm")}{mc(rm["max_co2"]," ppm")}{mc(rm["pct_co2_above_1000"],"%")}{mc(rm["pct_co2_above_1500"],"%")}{mc(rm["window_events_per_day"])}{mc(rm["pct_occupied"],"%")}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # FABRIC
    html+='''<div id="tab-fabric" class="tc">
<div class="ib"><strong>Building Fabric:</strong> TRI = std(indoor)/std(outdoor). NPE = night cooling effectiveness. Wind-infiltration r = wind vs indoor cooling correlation.</div>
<div class="chart-row"><div class="chart-box"><h4>Thermal Responsiveness Index</h4><canvas id="bar-tri"></canvas></div>
<div class="chart-box"><h4>Night Purge Effectiveness</h4><canvas id="bar-npe"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th>Property</th><th>Fabric</th><th>TRI</th><th>NPE</th><th>Wind r</th><th>&Delta;T</th><th>HDD</th><th>Temp Var</th></tr></thead><tbody>
'''
    for p in sorted(props, key=lambda x: x['rm'].get('thermal_responsiveness') or 0, reverse=True):
        rm=p['rm']; sid=p['id'][-6:]
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td>{bdg(rm["fabric_rating"],rc(rm["fabric_rating"]),rb(rm["fabric_rating"]))}</td>{mc(rm["thermal_responsiveness"])}{mc(rm["mean_npe"])}{mc(rm["wind_infiltration_corr"])}{mc(rm["mean_indoor_outdoor_delta"],"°C")}{mc(rm["hdd_total"])}{mc(rm["mean_temp_variability"],"°C")}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # OCCUPANCY IMPACT
    # Build chart data for occupied vs unoccupied
    occ_chart_labels = [p['id'][-6:] for p in props]
    occ_temp_o = [p['rm']['occ']['mean_temp'] or 0 for p in props]
    occ_temp_u = [p['rm']['unocc']['mean_temp'] or 0 for p in props]
    occ_rh_o = [p['rm']['occ']['mean_rh'] or 0 for p in props]
    occ_rh_u = [p['rm']['unocc']['mean_rh'] or 0 for p in props]
    occ_co2_o = [p['rm']['occ']['mean_co2'] or 0 for p in props]
    occ_co2_u = [p['rm']['unocc']['mean_co2'] or 0 for p in props]
    occ_vpx_o = [p['rm']['occ']['mean_vpx'] or 0 for p in props]
    occ_vpx_u = [p['rm']['unocc']['mean_vpx'] or 0 for p in props]

    html+='''<div id="tab-occupancy" class="tc">
<div class="ib"><strong>Occupancy Impact Analysis:</strong> Compares environmental conditions during <strong>occupied</strong> (avgrdr &gt; 0.3) vs <strong>unoccupied</strong> (avgrdr &le; 0.3) periods. This demonstrates the critical importance of occupancy-aware monitoring — occupants generate heat, moisture, and CO2 that significantly alter the indoor environment. Properties where occupied conditions are much worse than unoccupied may indicate behavioural factors (drying clothes, poor ventilation habits) vs structural issues (which persist regardless of occupancy).</div>
<div class="chart-row"><div class="chart-box"><h4>Mean Temperature: Occupied vs Unoccupied</h4><canvas id="occ-temp"></canvas></div>
<div class="chart-box"><h4>Mean Humidity: Occupied vs Unoccupied</h4><canvas id="occ-rh"></canvas></div></div>
<div class="chart-row"><div class="chart-box"><h4>Mean CO2: Occupied vs Unoccupied</h4><canvas id="occ-co2"></canvas></div>
<div class="chart-box"><h4>Mean VPX: Occupied vs Unoccupied</h4><canvas id="occ-vpx"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th rowspan="2">Property</th><th rowspan="2">% Occupied</th>
<th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">Temperature °C</th>
<th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">Humidity %</th>
<th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">CO2 (ppm)</th>
<th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">VPX (Pa)</th>
<th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">% RH &gt; 70</th></tr>
<tr><th>Occ</th><th>Unocc</th><th>&Delta;</th><th>Occ</th><th>Unocc</th><th>&Delta;</th>
<th>Occ</th><th>Unocc</th><th>&Delta;</th><th>Occ</th><th>Unocc</th><th>&Delta;</th>
<th>Occ</th><th>Unocc</th><th>&Delta;</th></tr></thead><tbody>
'''
    for p in props:
        rm=p['rm']; o=rm['occ']; u=rm['unocc']; sid=p['id'][-6:]
        def odc(ov,uv,w=1.5,cr=3):
            if ov is None or uv is None: return '<td>—</td>'
            d=ov-uv; c='#ef4444' if abs(d)>cr else '#f59e0b' if abs(d)>w else '#22c55e'
            return f'<td style="color:{c};font-weight:600">{d:+.1f}</td>'
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td>{mc(rm["pct_occupied"],"%")}'
        html+=f'<td>{o["mean_temp"] or "—"}</td><td>{u["mean_temp"] or "—"}</td>{odc(o["mean_temp"],u["mean_temp"])}'
        html+=f'<td>{o["mean_rh"] or "—"}</td><td>{u["mean_rh"] or "—"}</td>{odc(o["mean_rh"],u["mean_rh"],3,8)}'
        html+=f'<td>{o["mean_co2"] or "—"}</td><td>{u["mean_co2"] or "—"}</td>{odc(o["mean_co2"],u["mean_co2"],100,300)}'
        html+=f'<td>{o["mean_vpx"] or "—"}</td><td>{u["mean_vpx"] or "—"}</td>{odc(o["mean_vpx"],u["mean_vpx"],50,150)}'
        html+=f'<td>{o["pct_rh_70"]}</td><td>{u["pct_rh_70"]}</td>{odc(o["pct_rh_70"],u["pct_rh_70"],3,10)}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # CORRIDOR VS ROOM
    html+='''<div id="tab-comparison" class="tc">
<div class="ib"><strong>Corridor vs Room:</strong> EyeSense (corridor) vs SENS (lived-in room). Large deltas indicate insulation issues or ventilation imbalances.</div>
<div class="chart-row"><div class="chart-box"><h4>Temperature: Corridor vs Room</h4><canvas id="comp-temp"></canvas></div>
<div class="chart-box"><h4>Humidity: Corridor vs Room</h4><canvas id="comp-rh"></canvas></div></div>
<div class="chart-row"><div class="chart-box"><h4>Mould Score: Corridor vs Room</h4><canvas id="comp-mould"></canvas></div>
<div class="chart-box"><h4>Temperature Delta (Room - Corridor)</h4><canvas id="comp-delta"></canvas></div></div>
<div class="tw"><table>
<thead><tr><th rowspan="2">Property</th><th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">Temperature °C</th><th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">Humidity %</th><th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">Mould Score</th><th colspan="3" style="text-align:center;border-bottom:1px solid var(--border)">VPX (Pa)</th></tr>
<tr><th>Corr</th><th>Room</th><th>&Delta;</th><th>Corr</th><th>Room</th><th>&Delta;</th><th>Corr</th><th>Room</th><th>&Delta;</th><th>Corr</th><th>Room</th><th>&Delta;</th></tr></thead><tbody>
'''
    for p in props:
        cm=p.get('cm'); rm=p.get('rm')
        if not cm or not rm: continue
        sid=p['id'][-6:]
        def dc(cv,rv,w=1.5,cr=3):
            if cv is None or rv is None: return '<td>—</td>'
            d=rv-cv; c='#ef4444' if abs(d)>cr else '#f59e0b' if abs(d)>w else '#22c55e'
            return f'<td style="color:{c};font-weight:600">{d:+.1f}</td>'
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td>'
        html+=f'<td>{cm["mean_temp"]}</td><td>{rm["mean_temp"]}</td>{dc(cm["mean_temp"],rm["mean_temp"])}'
        html+=f'<td>{cm["mean_rh"]}</td><td>{rm["mean_rh"]}</td>{dc(cm["mean_rh"],rm["mean_rh"],5,10)}'
        html+=f'<td>{cm["mould_score"]}</td><td>{rm["mould_score"]}</td>{dc(cm["mould_score"],rm["mould_score"],5,15)}'
        cv2=cm["mean_vpx"]; rv2=rm["mean_vpx"]
        html+=f'<td>{cv2 if cv2 is not None else "—"}</td><td>{rv2 if rv2 is not None else "—"}</td>{dc(cv2,rv2,50,150)}</tr>\n'
    html+='</tbody></table></div></div>\n'

    # RISK DIVERGENCE TAB
    risk_order_rd = {'Critical':4,'Very High':4,'Inadequate':4,'High':3,'Exceeds Limit':3,'Poor':3,'Lightweight':3,
                     'Medium':2,'Moderate':2,'Warning':2,'Acceptable':2,'Elevated':2,
                     'Low':1,'Pass':1,'Good':1,'Normal':1,'Heavy':1,'No data':0}
    risk_cats = [
        ('mould_rating', 'Damp & Mould', 'mould_score'),
        ('cri_rating', 'Condensation', 'mean_cri'),
        ('vpx_rating', 'Vapour Pressure', 'mean_vpx'),
        ('overheat_rating', 'Overheating', 'pct_over_26'),
        ('underheat_rating', 'Under-heating', 'pct_under_18'),
        ('ventilation_rating', 'Ventilation', 'mean_co2'),
    ]

    # Count flagged properties
    flagged_props = []
    for p in props:
        rm2=p.get('rm'); cm2=p.get('cm')
        if not rm2: continue
        flags = []
        for rk, lbl, sk in risk_cats:
            r_room = risk_order_rd.get(rm2.get(rk,''),0)
            r_corr = risk_order_rd.get(cm2.get(rk,''),0) if cm2 else 0
            worst = max(r_room, r_corr)
            if worst >= 3:
                source = []
                if r_room >= 3: source.append('Room')
                if r_corr >= 3: source.append('Corridor')
                divergent = r_room != r_corr and worst >= 3
                flags.append({'cat': lbl, 'rk': rk, 'sk': sk, 'room_lvl': r_room, 'corr_lvl': r_corr,
                              'room_rat': rm2.get(rk,'—'), 'corr_rat': cm2.get(rk,'—') if cm2 else '—',
                              'source': ' & '.join(source), 'divergent': divergent,
                              'room_val': rm2.get(sk), 'corr_val': cm2.get(sk) if cm2 else None})
        flagged_props.append({'id': p['id'], 'sid': p['id'][-6:], 'flags': flags, 'flag_count': len(flags)})

    total_flagged = sum(1 for fp in flagged_props if fp['flag_count'] > 0)
    room_only = sum(1 for fp in flagged_props if any(f['room_lvl'] >= 3 and f['corr_lvl'] < 3 for f in fp['flags']))
    corr_only = sum(1 for fp in flagged_props if any(f['corr_lvl'] >= 3 and f['room_lvl'] < 3 for f in fp['flags']))
    both_high = sum(1 for fp in flagged_props if any(f['room_lvl'] >= 3 and f['corr_lvl'] >= 3 for f in fp['flags']))

    html+=f'''<div id="tab-riskdiff" class="tc">
<div class="ib"><strong>Risk Divergence Analysis:</strong> Compares risk levels between corridor (EyeSense) and room (SENS) sensors.
A property is flagged if <strong>either</strong> location shows High/Critical risk for any category. This catches hidden risks —
a corridor might read Low risk while the lived-in room is at High risk for mould, or vice versa.
Properties where corridor and room disagree on risk level are marked as <strong>divergent</strong>, indicating localised issues rather than whole-house problems.</div>

<div class="tiles" style="margin-bottom:20px">
<div class="tile"><div class="lb">Total Flagged Properties</div><div class="vl" style="color:var(--red)">{total_flagged}</div><div class="sb">At least one High/Critical risk in either sensor</div></div>
<div class="tile"><div class="lb">Room-Only Risk</div><div class="vl" style="color:var(--orange-300)">{room_only}</div><div class="sb">Room at risk, corridor is not</div></div>
<div class="tile"><div class="lb">Corridor-Only Risk</div><div class="vl" style="color:var(--purple)">{corr_only}</div><div class="sb">Corridor at risk, room is not</div></div>
<div class="tile"><div class="lb">Both At Risk</div><div class="vl" style="color:var(--red)">{both_high}</div><div class="sb">Both sensors show High/Critical</div></div>
</div>

<div class="chart-row">
<div class="chart-box"><h4>Flagged Risk Categories by Property</h4><canvas id="bar-riskdiff"></canvas></div>
<div class="chart-box"><h4>Room vs Corridor Risk Source</h4><canvas id="donut-riskdiff"></canvas></div>
</div>

<h3 style="margin:16px 0 12px;font-size:16px">Flagged Properties (Worst First)</h3>
'''

    # Sorted by flag count descending
    for fp in sorted(flagged_props, key=lambda x: x['flag_count'], reverse=True):
        if fp['flag_count'] == 0:
            continue
        sid3 = fp['sid']
        html += f'''<div class="cc" style="border-left:4px solid var(--red)">
<h4><a class="pl" href="#" onclick="showTab('prop-{fp['id']}')" style="font-size:16px">{sid3}</a>
<span style="margin-left:8px;font-size:12px;color:var(--red);font-weight:600">{fp['flag_count']} risk{"s" if fp['flag_count']>1 else ""} flagged</span></h4>
<div class="tw" style="margin-top:10px;margin-bottom:0"><table>
<thead><tr><th>Risk Category</th><th>Corridor Rating</th><th>Room Rating</th><th>Divergent?</th><th>Where</th><th>Corridor Value</th><th>Room Value</th></tr></thead><tbody>
'''
        for f in fp['flags']:
            div_icon = '<span style="color:var(--orange-300);font-weight:700">&#9888; Yes</span>' if f['divergent'] else '<span style="color:var(--n500)">No</span>'
            # Color the ratings
            cr = f['corr_rat']; rr = f['room_rat']
            cr_html = bdg(cr, rc(cr), rb(cr))
            rr_html = bdg(rr, rc(rr), rb(rr))
            # Source label
            if f['room_lvl'] >= 3 and f['corr_lvl'] < 3:
                src_html = '<span style="color:var(--orange-300);font-weight:600">Room only</span>'
            elif f['corr_lvl'] >= 3 and f['room_lvl'] < 3:
                src_html = '<span style="color:var(--purple);font-weight:600">Corridor only</span>'
            else:
                src_html = '<span style="color:var(--red);font-weight:600">Both</span>'
            cv3 = f['corr_val']
            rv3 = f['room_val']
            cvs = f'{cv3:.1f}' if cv3 is not None else '—'
            rvs = f'{rv3:.1f}' if rv3 is not None else '—'
            html += f'<tr><td style="font-weight:600">{f["cat"]}</td><td>{cr_html}</td><td>{rr_html}</td><td>{div_icon}</td><td>{src_html}</td><td>{cvs}</td><td>{rvs}</td></tr>\n'
        html += '</tbody></table></div></div>\n'

    # Properties with no flags
    clean_count = sum(1 for fp in flagged_props if fp['flag_count'] == 0)
    if clean_count > 0:
        html += f'<div class="cc" style="border-left:4px solid var(--green)"><h4 style="color:var(--green)">{clean_count} properties with no High/Critical risks in either sensor</h4><div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">'
        for fp in flagged_props:
            if fp['flag_count'] == 0:
                html += f'<a class="pl" href="#" onclick="showTab(\'prop-{fp["id"]}\')" style="padding:4px 10px;background:var(--green-light);border-radius:8px;font-size:12px">{fp["sid"]}</a>'
        html += '</div></div>\n'

    html += '</div>\n'

    # Build chart data for risk divergence tab
    rd_chart_labels = [fp['sid'] for fp in sorted(flagged_props, key=lambda x: x['flag_count'], reverse=True) if fp['flag_count'] > 0]
    rd_chart_values = [fp['flag_count'] for fp in sorted(flagged_props, key=lambda x: x['flag_count'], reverse=True) if fp['flag_count'] > 0]
    # Count source types
    room_only_flags = sum(1 for fp in flagged_props for f in fp['flags'] if f['room_lvl']>=3 and f['corr_lvl']<3)
    corr_only_flags = sum(1 for fp in flagged_props for f in fp['flags'] if f['corr_lvl']>=3 and f['room_lvl']<3)
    both_flags = sum(1 for fp in flagged_props for f in fp['flags'] if f['room_lvl']>=3 and f['corr_lvl']>=3)

    # CLUSTERING
    html+=f'''<div id="tab-clusters" class="tc">
<div class="ib"><strong>Clustering:</strong> K-Means, 14 normalised features. k={bk}, Silhouette={ss:.3f}.</div>
<div class="chart-box" style="margin-bottom:20px"><h4>Cluster Profiles (Radar)</h4><canvas id="radar-clusters" style="max-height:350px"></canvas></div>
'''
    for cl_id in sorted(cluster_groups.keys()):
        ms=cluster_groups[cl_id]; desc=cl_descs.get(cl_id,'')
        html+=f'<div class="cc"><h4 style="color:var(--accent)">Cluster {cl_id+1} — {len(ms)} properties</h4><p style="font-size:13px;color:var(--ts);margin-bottom:8px">{desc}</p><div class="tw" style="margin-bottom:0"><table><thead><tr><th>Property</th><th>Mean T</th><th>Mean RH</th><th>Mould</th><th>VPX</th><th>CRI</th><th>%&lt;18°C</th><th>%&gt;26°C</th><th>CO2</th><th>TRI</th></tr></thead><tbody>'
        for mp in ms:
            sid2=[p['id'][-6:] for p in props if p['rm'] is mp][0] if any(p['rm'] is mp for p in props) else '?'
            pid2=[p['id'] for p in props if p['rm'] is mp][0] if any(p['rm'] is mp for p in props) else ''
            html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{pid2}\')">{sid2}</a></td>{mc(mp["mean_temp"],"°C")}{mc(mp["mean_rh"],"%")}<td><strong>{mp["mould_score"]}</strong></td>{mc(mp["mean_vpx"]," Pa")}{mc(mp["mean_cri"],"K")}{mc(mp["pct_under_18"],"%")}{mc(mp["pct_over_26"],"%")}{mc(mp["mean_co2"]," ppm")}{mc(mp["thermal_responsiveness"])}</tr>\n'
        html+='</tbody></table></div></div>\n'
    html+='</div>\n'

    # ALL PROPERTIES
    html+='''<div id="tab-properties" class="tc"><div class="tw"><table>
<thead><tr><th>Property</th><th>Date Range</th><th>Days</th><th>Mean T</th><th>Mean RH</th><th>CO2</th><th>Mould</th><th>VPX</th><th>CRI</th><th>Overheat</th><th>Under-heat</th><th>Ventilation</th><th>Fabric</th></tr></thead><tbody>
'''
    for p in props:
        rm=p['rm']; sid=p['id'][-6:]
        html+=f'<tr><td><a class="pl" href="#" onclick="showTab(\'prop-{p["id"]}\')">{sid}</a></td><td style="font-size:11px">{rm["first_ts"]} — {rm["last_ts"]}</td><td>{rm["days_span"]}</td>{mc(rm["mean_temp"],"°C")}{mc(rm["mean_rh"],"%")}{mc(rm["mean_co2"]," ppm")}'
        for k in ['mould_rating','vpx_rating','cri_rating','overheat_rating','underheat_rating','ventilation_rating','fabric_rating']:
            r=rm[k]; html+=f'<td>{bdg(r,rc(r),rb(r))}</td>'
        html+='</tr>\n'
    html+='</tbody></table></div></div>\n'

    # METHODOLOGY (same text, no "fail")
    html+='''<div id="tab-methodology" class="tc"><div class="pd">
<h3>Methodology & Standards</h3>
<h4 style="margin-top:16px;margin-bottom:8px">Data Processing</h4>
<ul style="margin-left:20px;font-size:13px;color:var(--ts)"><li>Raw sensor data used directly — no resampling or interpolation applied</li><li>Weather data smoothed with 168-minute SG filter per EyeSense spec</li><li>Files with &lt;2 weeks data excluded</li><li>Monitoring-only: avgTcs, avgC, avgP, avgE not used</li></ul>
<h4 style="margin-top:16px;margin-bottom:8px">Basic Metrics</h4>
<ul style="margin-left:20px;font-size:13px;color:var(--ts)"><li><strong>Damp/Mould (BS 5250, ISO 13788):</strong> RH&gt;70% sustained, RH&gt;80% germination, dew point &lt;3°C margin</li><li><strong>Overheating (CIBSE TM59):</strong> &gt;26°C for &gt;3% occupied hours exceeds limit; 28°C corridor threshold</li><li><strong>Under-heating (WHO/NICE):</strong> &lt;18°C health risk, &lt;16°C respiratory, &lt;12°C cardiovascular</li><li><strong>Ventilation (Part F):</strong> CO2 &gt;1500ppm inadequate, &gt;1000ppm poor</li><li><strong>Fuel Poverty (Switchee HFPI):</strong> Never reaching 18°C in 7-day rolling window</li></ul>
<h4 style="margin-top:16px;margin-bottom:8px">Combined-Variable Metrics</h4>
<ul style="margin-left:20px;font-size:13px;color:var(--ts)"><li><strong>VPX (BRE IP 1/06):</strong> e<sub>indoor</sub> - e<sub>outdoor</sub>. &gt;300Pa = excess moisture, &gt;600Pa = intervention needed</li><li><strong>CRI (ISO 13788):</strong> T<sub>surface</sub> - T<sub>dewpoint</sub>, f<sub>Rsi</sub>=0.75. CRI&lt;1K = condensation, &lt;3K = mould</li><li><strong>EHR:</strong> Actual RH - expected RH</li><li><strong>Adaptive Comfort (CIBSE TM52):</strong> T<sub>max</sub>=0.33&times;T<sub>rm</sub>+21.8+2</li><li><strong>TRI:</strong> &sigma;(indoor T)/&sigma;(outdoor T)</li><li><strong>NPE:</strong> Night purge effectiveness</li><li><strong>Window Opening:</strong> Simultaneous dT&lt;-0.5°C + dCO2&lt;-50ppm + occupied + outdoor cooler</li><li><strong>Wind-Infiltration:</strong> Wind speed vs cooling rate correlation</li><li><strong>HDD (CIBSE TM41):</strong> Base 15.5°C</li><li><strong>Solar Correlation:</strong> Pearson r (lux vs temp, 08-18h)</li></ul>
<h4 style="margin-top:16px;margin-bottom:8px">Standards</h4>
<ul style="margin-left:20px;font-size:13px;color:var(--ts)"><li>BS 5250:2021, BS EN ISO 13788, BRE IP 1/06</li><li>CIBSE TM52, TM59, Guide A, TM41</li><li>WHO Housing and Health Guidelines, NICE NG6</li><li>Building Regulations Part F, HHSRS, ASHRAE 160</li></ul>
</div></div>

<!-- INFO TAB -->
<div id="tab-info" class="tc">
<div class="pd">
<h3>Parameter Guide</h3>
<p style="font-size:13px;color:var(--ts);margin-bottom:20px">This guide explains every parameter, metric, and rating used in this dashboard, what it means for the property, and how it is calculated from the raw sensor data.</p>

<div style="display:grid;grid-template-columns:1fr;gap:16px">

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">Indoor Temperature (avgT)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">Air temperature measured inside the property in degrees Celsius. The EyeSense sensor in the corridor and the SENS sensor in the room each record this independently at 5-minute intervals. This is the primary variable for assessing overheating and under-heating.</p>
</div>

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">Indoor Relative Humidity (avgH)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">Percentage of moisture in the air relative to the maximum the air can hold at that temperature. High RH (&gt;70%) over extended periods creates conditions for mould growth. RH above 80% at surfaces is the germination threshold for most mould species. Comfortable range is 40-60%.</p>
</div>

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">CO2 Concentration (avgCO2)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">Carbon dioxide in parts per million. Outdoor baseline is ~420 ppm. Occupants exhale CO2, so rising levels indicate people are present and the space may not be adequately ventilated. Above 1000 ppm ventilation should be improved; above 1500 ppm is inadequate per Building Regulations Part F. CO2 is used as a proxy for ventilation effectiveness.</p>
</div>

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">Light Intensity (avgLux)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">Indoor light level in lux. Used as a proxy for solar gain — higher lux during daytime indicates more sunlight entering the property, which contributes to passive heating and potential overheating. The solar correlation metric (Pearson r between lux and temperature during 08:00-18:00) reveals how sensitive the property is to solar-driven temperature rises.</p>
</div>

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">Occupancy Energy (avgRe)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">Motion/occupancy energy from the PIR sensor. Values above 15 indicate the space is occupied. This is used to distinguish occupied from unoccupied periods for analysis — environmental conditions during occupation (higher CO2, humidity from breathing and activity) differ significantly from unoccupied periods.</p>
</div>

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">Occupancy Fraction (avgrdr)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">The fraction of the 5-minute sampling window during which occupancy was detected (0.0 to 1.0). Values above 0.3 are classified as occupied periods. This is used in the Occupancy Impact tab to split all environmental metrics into occupied vs unoccupied conditions, demonstrating how human presence affects the indoor environment.</p>
</div>

<div class="mb" style="border-left:4px solid var(--accent)">
<div class="ml">Outdoor Weather Data</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">External weather conditions correlated by timestamp from a weather API: temperature (°C), humidity (%), wind speed (m/s), cloud cover (%), and precipitation (mm). These are essential for calculating combined metrics like VPX, CRI, and thermal responsiveness — they provide the outdoor baseline against which indoor conditions are compared.</p>
</div>

<h4 style="margin-top:24px;margin-bottom:12px;color:var(--accent)">Derived Metrics — Damp & Mould</h4>

<div class="mb" style="border-left:4px solid var(--red)">
<div class="ml">Mould Risk Score (0-100)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> 0.5 &times; (%time RH&gt;70%) + 1.5 &times; (%time RH&gt;80%) + 0.3 &times; (%time dew point within 3°C of air temp), capped at 100.<br>
<strong>Ratings:</strong> Low (&lt;10), Medium (10-20), High (20-40), Critical (&gt;40).<br>
<strong>Standards:</strong> BS 5250:2021 (sustained RH &gt; 70% indicates risk), BS EN ISO 13788 (surface RH &gt; 80% = mould germination).</p>
</div>

<div class="mb" style="border-left:4px solid var(--red)">
<div class="ml">Vapour Pressure Excess — VPX (Pa)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> VPX = e<sub>sat</sub>(T<sub>indoor</sub>) &times; RH<sub>indoor</sub>/100 - e<sub>sat</sub>(T<sub>outdoor</sub>) &times; RH<sub>outdoor</sub>/100, where e<sub>sat</sub>(T) = 610.94 &times; exp(17.625T / (T+243.04)).<br>
<strong>What it means:</strong> The difference between indoor and outdoor vapour pressure reveals excess moisture being generated inside. Normal (&lt;200 Pa), Elevated (200-300), High (&gt;300 — likely drying clothes, poor ventilation), Very High (&gt;600 — intervention needed).<br>
<strong>Standard:</strong> BRE Information Paper IP 1/06.</p>
</div>

<div class="mb" style="border-left:4px solid var(--red)">
<div class="ml">Condensation Risk Index — CRI (K)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> CRI = T<sub>surface</sub> - T<sub>dewpoint</sub>, where T<sub>surface</sub> = f<sub>Rsi</sub> &times; (T<sub>indoor</sub> - T<sub>outdoor</sub>) + T<sub>outdoor</sub>, using f<sub>Rsi</sub> = 0.75 (worst thermal bridge).<br>
<strong>What it means:</strong> Estimates how close the coldest surface in the property is to the dew point. CRI &gt; 5K = Low risk, 3-5K = Moderate, 1-3K = High (mould likely), &lt;1K = Critical (condensation occurring).<br>
<strong>Standard:</strong> BS EN ISO 13788.</p>
</div>

<div class="mb" style="border-left:4px solid var(--red)">
<div class="ml">Excess Humidity Ratio — EHR (%RH)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> EHR = Actual indoor RH - Expected indoor RH if outdoor air were heated to indoor temperature with no moisture added.<br>
<strong>What it means:</strong> Isolates moisture generated inside the property from background outdoor moisture. EHR &lt;5% = normal, 5-15% = moderate (normal occupancy), 15-25% = high (drying clothes, cooking), &gt;25% = very high (water ingress or severely poor ventilation).</p>
</div>

<h4 style="margin-top:24px;margin-bottom:12px;color:var(--orange-300)">Derived Metrics — Temperature</h4>

<div class="mb" style="border-left:4px solid var(--orange-300)">
<div class="ml">Overheating Rating (CIBSE TM59)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Criterion:</strong> Indoor temperature exceeding 26°C for more than 3% of occupied hours exceeds CIBSE limits. 28°C is the severe/corridor threshold.<br>
<strong>Ratings:</strong> Pass (&le;1%), Warning (1-3%), Exceeds Limit (&gt;3%).<br>
<strong>Standard:</strong> CIBSE TM59 Design methodology for the assessment of overheating risk in homes.</p>
</div>

<div class="mb" style="border-left:4px solid var(--orange-300)">
<div class="ml">Adaptive Comfort Exceedance (CIBSE TM52)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> Upper comfort limit = 0.33 &times; T<sub>running mean outdoor</sub> + 21.8 + 2°C (Category II). Running mean: T<sub>rm</sub> = 0.8 &times; T<sub>rm,yesterday</sub> + 0.2 &times; T<sub>outdoor,yesterday</sub>.<br>
<strong>What it means:</strong> People adapt to warmer weather, so the acceptable indoor temperature rises with outdoor temperature. This metric shows the % of time indoor temperatures exceed this adaptive threshold.</p>
</div>

<div class="mb" style="border-left:4px solid var(--blue)">
<div class="ml">Under-heating Rating (WHO)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Thresholds:</strong> Below 18°C = health risk for healthy adults. Below 16°C = respiratory risk. Below 12°C = cardiovascular stress and hypothermia risk. 20-21°C recommended for elderly/vulnerable.<br>
<strong>Ratings:</strong> Low (&le;5%), Medium (5-10%), High (10-20%), Critical (&gt;20% of time below 18°C).<br>
<strong>Standards:</strong> WHO Housing and Health Guidelines, NICE NG6.</p>
</div>

<div class="mb" style="border-left:4px solid var(--blue)">
<div class="ml">Fuel Poverty Indicator (Switchee HFPI)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Criterion:</strong> Property flagged if it never reaches 18°C during any 7-day rolling window.<br>
<strong>What it means:</strong> Indicates the resident may be unable to afford adequate heating, or the heating system is fundamentally inadequate. This is a strong indicator of fuel poverty and potential health risk.</p>
</div>

<div class="mb" style="border-left:4px solid var(--blue)">
<div class="ml">Heating Degree Days — HDD</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> HDD = &Sigma; max(0, 15.5 - T<sub>outdoor</sub>) / 288 per 5-min reading.<br>
<strong>What it means:</strong> Cumulative measure of how much heating is needed over the monitoring period. Base temperature 15.5°C (CIBSE TM41 UK standard). Higher HDD = colder period requiring more energy. Used to normalise energy usage comparisons between properties.</p>
</div>

<h4 style="margin-top:24px;margin-bottom:12px;color:var(--green)">Derived Metrics — Ventilation & Behaviour</h4>

<div class="mb" style="border-left:4px solid var(--green)">
<div class="ml">Ventilation Rating (Part F)</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Thresholds:</strong> Mean CO2 &lt;800 ppm = Good, 800-1000 = Acceptable, 1000-1500 = Poor, &gt;1500 = Inadequate.<br>
<strong>Standard:</strong> Building Regulations Approved Document Part F — average CO2 must not exceed 1500 ppm during occupied periods.</p>
</div>

<div class="mb" style="border-left:4px solid var(--green)">
<div class="ml">Window Opening Events</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Detection:</strong> A window opening is identified when all four conditions occur simultaneously within a 5-minute step: indoor temperature drops &gt;0.5°C, CO2 drops &gt;50 ppm, the space is occupied (avgRe &gt; 15), and outdoor temperature is cooler than indoor.<br>
<strong>What it means:</strong> Indicates active ventilation behaviour by residents. Properties with very few window events and high CO2 may need ventilation improvements or resident engagement.</p>
</div>

<h4 style="margin-top:24px;margin-bottom:12px;color:var(--purple)">Derived Metrics — Building Fabric</h4>

<div class="mb" style="border-left:4px solid var(--purple)">
<div class="ml">Thermal Responsiveness Index — TRI</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> TRI = &sigma;(indoor temperature) / &sigma;(outdoor temperature).<br>
<strong>What it means:</strong> How much the indoor temperature tracks outdoor temperature swings. TRI &lt;0.3 = heavy thermal mass (concrete, thick masonry — temperature well-buffered). TRI &gt;0.7 = lightweight construction (timber frame — temperature tracks outdoor changes closely). Lower TRI generally indicates better thermal performance.<br>
<strong>Ratings:</strong> Heavy (&lt;0.3), Moderate (0.3-0.7), Lightweight (&gt;0.7).</p>
</div>

<div class="mb" style="border-left:4px solid var(--purple)">
<div class="ml">Night Purge Effectiveness — NPE</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Formula:</strong> NPE = (T<sub>22:00</sub> - T<sub>06:00</sub>) / (T<sub>22:00</sub> - T<sub>outdoor,night mean</sub>).<br>
<strong>What it means:</strong> How effectively the building cools overnight by releasing stored heat. NPE &gt;0.8 = excellent (building cools nearly to outdoor temp), 0.5-0.8 = good, 0.2-0.5 = moderate (thermal mass retention), &lt;0.2 = poor (sealed building, high internal heat retained).</p>
</div>

<div class="mb" style="border-left:4px solid var(--purple)">
<div class="ml">Wind-Infiltration Correlation</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Method:</strong> Pearson correlation between wind speed and indoor cooling rate (°C/hour) during unoccupied periods.<br>
<strong>What it means:</strong> A strong negative correlation (e.g., r &lt; -0.3) indicates the building loses heat faster when it is windy — a signature of air leakage through the building fabric. Properties with high wind-infiltration correlation would benefit from draught-proofing or airtightness improvements.</p>
</div>

<div class="mb" style="border-left:4px solid var(--purple)">
<div class="ml">Solar-Temperature Correlation</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px"><strong>Method:</strong> Pearson correlation between indoor lux and indoor temperature during daytime hours (08:00-18:00).<br>
<strong>What it means:</strong> High positive correlation indicates the property is sensitive to solar gain — large glazing, south-facing, or low thermal mass. This is useful in summer to identify overheating risk from solar exposure.</p>
</div>

<h4 style="margin-top:24px;margin-bottom:12px;color:var(--n600)">Corridor vs Room Comparison</h4>

<div class="mb" style="border-left:4px solid var(--n500)">
<div class="ml">Delta (&Delta;) Values</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">The difference between the room sensor (lived-in space) and the corridor sensor (transitional space). Shown as Room minus Corridor.<br>
<strong>&Delta;T (Temperature):</strong> Large positive delta = room is warmer (may indicate localised heating or solar gain). Large negative = room is colder (possible insulation issue). Highlighted amber if &ge;2°C, red if &ge;4°C.<br>
<strong>&Delta;RH (Humidity):</strong> Higher room humidity suggests moisture generation from occupancy/activities. Highlighted amber if &ge;5%, red if &ge;10%.<br>
<strong>&Delta;Mould Score:</strong> Higher room mould score indicates the lived-in space has worse conditions than the corridor. Highlighted amber if &ge;5 points, red with warning icon if &ge;15 points.</p>
</div>

<h4 style="margin-top:24px;margin-bottom:12px;color:var(--n600)">Clustering</h4>

<div class="mb" style="border-left:4px solid var(--n500)">
<div class="ml">K-Means Clustering</div>
<p style="font-size:13px;color:var(--n700);margin-top:6px">Properties are grouped by similarity across 14 environmental features: mean temperature, temperature std, mean humidity, % high RH, % overheating, % under-heating, mean CO2, indoor-outdoor &Delta;T, temperature variability, occupancy %, mean VPX, mean CRI, mean EHR, and TRI. All features are min-max normalised. The optimal number of clusters (k) is selected by testing k=2 to 6 and choosing the highest Silhouette Score, which measures how well-separated the clusters are. Each cluster represents a group of properties with similar environmental behaviour patterns.</p>
</div>

</div>
</div>
</div>

<!-- GLOSSARY TAB -->
<div id="tab-glossary" class="tc">
<div class="pd">
<h3>Glossary of Acronyms & Abbreviations</h3>
<p style="font-size:13px;color:var(--ts);margin-bottom:20px">Quick reference for all acronyms, abbreviations, and technical terms used in this dashboard.</p>

<div class="tw"><table>
<thead><tr><th style="width:140px">Acronym</th><th style="width:240px">Stands For</th><th>Description</th></tr></thead>
<tbody>
<tr style="background:var(--n200)"><td colspan="3" style="font-weight:700;color:var(--n700);padding:10px 14px">Metrics</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">RH</td><td>Relative Humidity</td><td>Percentage of moisture in the air relative to the maximum it can hold at that temperature.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">VPX</td><td>Vapour Pressure Excess</td><td>Difference between indoor and outdoor vapour pressure (Pa). Reveals excess moisture being generated inside the property, such as from drying clothes, cooking, or bathing. Based on BRE IP 1/06.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">CRI</td><td>Condensation Risk Index</td><td>Temperature gap (K) between the estimated coldest wall surface and the dew point. A small CRI means the walls are close to the point where condensation forms. Based on BS EN ISO 13788.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">EHR</td><td>Excess Humidity Ratio</td><td>The amount of extra humidity indoors beyond what would be expected from simply heating outdoor air. Shows how much moisture is being added by activities inside the property.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">TRI</td><td>Thermal Responsiveness Index</td><td>Measures how much the indoor temperature follows outdoor temperature swings. A low TRI means the building has heavy thermal mass and stays stable. A high TRI means temperatures fluctuate with the weather.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">NPE</td><td>Night Purge Effectiveness</td><td>How effectively the building cools down overnight. A value near 1.0 means it cools well; near 0 means heat is trapped inside.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">HDD</td><td>Heating Degree Days</td><td>A cumulative measure of how cold the weather has been over the monitoring period. Higher HDD means more heating was needed. Based on CIBSE TM41 (15.5°C base).</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">HFPI</td><td>Housing Fuel Poverty Index</td><td>A property is flagged if the indoor temperature never reaches 18°C during any 7-day period. This is a strong indicator that the resident may be unable to afford adequate heating.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">&Delta;T</td><td>Delta Temperature</td><td>Difference in temperature between two locations — typically Room minus Corridor, or Indoor minus Outdoor. Measured in °C.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">&Delta;RH</td><td>Delta Relative Humidity</td><td>Difference in humidity between two sensor locations. Measured in percentage points.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">f<sub>Rsi</sub></td><td>Temperature Factor at Internal Surface</td><td>A ratio used to estimate the temperature of the coldest internal wall surface. A value of 0.75 represents the worst-case thermal bridge (BS EN ISO 13788).</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">ACH</td><td>Air Changes per Hour</td><td>The rate at which indoor air is replaced by fresh outdoor air. Higher ACH means more ventilation — or more draughts and air leakage.</td></tr>
<tr style="background:var(--n200)"><td colspan="3" style="font-weight:700;color:var(--n700);padding:10px 14px">Units</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">ppm</td><td>Parts Per Million</td><td>Unit for CO2 concentration. Outdoor air is ~420 ppm. Above 1000 ppm indoors suggests ventilation should be improved; above 1500 ppm is inadequate.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Pa</td><td>Pascal</td><td>Unit of pressure. Used for vapour pressure and VPX measurements in this dashboard.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">K</td><td>Kelvin</td><td>Unit of temperature difference (1K = 1°C difference). Used for CRI and other thermal metrics where we are measuring a gap rather than an absolute temperature.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">°C</td><td>Degrees Celsius</td><td>Unit of temperature used for all indoor, outdoor, and threshold measurements.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">%</td><td>Percentage</td><td>Used for relative humidity, time-above-threshold metrics, and occupancy fraction.</td></tr>
<tr style="background:var(--n200)"><td colspan="3" style="font-weight:700;color:var(--n700);padding:10px 14px">Standards & Organisations</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">CIBSE</td><td>Chartered Institution of Building Services Engineers</td><td>UK professional body that publishes widely used building performance standards and design guides.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">TM52</td><td>CIBSE Technical Memorandum 52</td><td>Method for assessing overheating risk using adaptive thermal comfort. The acceptable indoor temperature adjusts based on recent outdoor weather.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">TM59</td><td>CIBSE Technical Memorandum 59</td><td>Overheating assessment specifically for homes. Key criterion: indoor temperature should not exceed 26°C for more than 3% of occupied hours.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">BS 5250</td><td>British Standard 5250</td><td>Code of practice for managing moisture in buildings. States that room-average humidity should not exceed 70% for prolonged periods.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">BS EN ISO 13788</td><td>European/International Standard 13788</td><td>Defines how to assess condensation and mould growth risk on building surfaces. Mould germination occurs when surface humidity exceeds 80%.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">BRE</td><td>Building Research Establishment</td><td>UK building science research body. Their IP 1/06 paper defines the vapour pressure excess method used in this analysis.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">IP 1/06</td><td>BRE Information Paper 1/06</td><td>Defines the VPX method for identifying excess indoor moisture. Widely used by housing providers to diagnose damp and mould causes.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Part F</td><td>Building Regulations Part F</td><td>UK building regulation on ventilation. Requires that average indoor CO2 does not exceed 1500 ppm during occupied periods.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">WHO</td><td>World Health Organisation</td><td>Recommends a minimum indoor temperature of 18°C for healthy adults, and 20–21°C for elderly or vulnerable residents.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">NICE NG6</td><td>NICE Guideline 6</td><td>UK health guidance on reducing excess winter deaths and illness caused by cold homes.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">HHSRS</td><td>Housing Health and Safety Rating System</td><td>Risk-based assessment system under the Housing Act 2004. Covers 29 hazards including damp, mould, and excess cold. Category 1 hazards require mandatory action.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">ASHRAE</td><td>American Society of Heating, Refrigerating and Air-Conditioning Engineers</td><td>International standards body. Standard 160 provides criteria for assessing moisture and mould risk in buildings.</td></tr>
<tr style="background:var(--n200)"><td colspan="3" style="font-weight:700;color:var(--n700);padding:10px 14px">Dashboard Terms</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Corridor Sensor</td><td>—</td><td>The environmental sensor placed in the corridor or hallway of each property. Represents transitional space conditions.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Room Sensor</td><td>—</td><td>The environmental sensor placed in a lived-in room (typically a bedroom or living room). Represents conditions where residents spend most of their time.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Divergent</td><td>—</td><td>A property where the corridor and room sensors show different risk levels for the same category. Indicates a localised issue rather than a whole-house problem.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Cluster</td><td>—</td><td>A group of properties with similar environmental behaviour patterns, identified automatically using statistical analysis (K-Means clustering).</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">Silhouette Score</td><td>—</td><td>A measure of how well-separated the property clusters are. Ranges from -1 to 1; higher values mean the clusters are more distinct.</td></tr>
<tr><td style="font-weight:700;color:var(--accent)">PIR</td><td>Passive Infrared</td><td>Motion detection technology used by the sensors to determine whether a space is occupied.</td></tr>
</tbody>
</table></div>
</div>
</div>
'''

    # ── INDIVIDUAL PROPERTY TABS with charts ──
    for i,p in enumerate(props):
        pid=p['id']; sid=pid[-6:]
        cm=p.get('cm'); rm=p.get('rm')
        if not rm: continue
        cl=cl_labels[i] if i<len(cl_labels) else 0

        html+=f'''<div id="tab-prop-{pid}" class="tc">
<a class="bl" href="#" onclick="showTab('summary')">&larr; Back to Summary</a>
<div class="pd">
<h3>Property {sid} {mini("","Cluster "+str(cl+1),"#1e40af","#eff6ff")}</h3>
<p style="font-size:13px;color:var(--ts);margin-bottom:16px">Sensor: {pid} &mdash; {rm['first_ts']} to {rm['last_ts']} ({rm['days_span']}d, {rm['data_points']} readings)</p>
<div class="mg">
<div class="mb" style="border-left:3px solid {rc(rm['mould_rating'])}"><div class="ml">Damp & Mould</div><div class="mv">{rm['mould_rating']}</div><div class="ms">Score: {rm['mould_score']}/100</div></div>
<div class="mb" style="border-left:3px solid {rc(rm['cri_rating'])}"><div class="ml">Condensation</div><div class="mv">{rm['cri_rating']}</div><div class="ms">CRI: {rm['mean_cri'] if rm['mean_cri'] else "—"}K</div></div>
<div class="mb" style="border-left:3px solid {rc(rm['vpx_rating'])}"><div class="ml">VPX</div><div class="mv">{rm['vpx_rating']}</div><div class="ms">{rm['mean_vpx'] if rm['mean_vpx'] else "—"} Pa</div></div>
<div class="mb" style="border-left:3px solid {rc(rm['overheat_rating'])}"><div class="ml">Overheating</div><div class="mv">{rm['overheat_rating']}</div><div class="ms">{rm['pct_over_26']}% &gt;26°C</div></div>
<div class="mb" style="border-left:3px solid {rc(rm['underheat_rating'])}"><div class="ml">Under-heating</div><div class="mv">{rm['underheat_rating']}</div><div class="ms">{rm['pct_under_18']}% &lt;18°C</div></div>
<div class="mb" style="border-left:3px solid {rc(rm['ventilation_rating'])}"><div class="ml">Ventilation</div><div class="mv">{rm['ventilation_rating']}</div><div class="ms">CO2: {rm['mean_co2'] if rm['mean_co2'] else "—"} ppm</div></div>
<div class="mb" style="border-left:3px solid {rc(rm['fabric_rating'])}"><div class="ml">Fabric</div><div class="mv">{rm['fabric_rating']}</div><div class="ms">TRI: {rm['thermal_responsiveness'] if rm['thermal_responsiveness'] else "—"}</div></div>
<div class="mb" style="border-left:3px solid {'#ef4444' if rm['fuel_poverty_flag'] else '#22c55e'}"><div class="ml">Fuel Poverty</div><div class="mv">{'Yes' if rm['fuel_poverty_flag'] else 'No'}</div><div class="ms">HDD: {rm['hdd_total']}</div></div>
</div>
<div class="chart-row"><div class="chart-box"><h4>Daily Temperature (Corridor vs Room vs Outdoor)</h4><canvas id="ts-temp-{pid}"></canvas></div>
<div class="chart-box"><h4>Daily Humidity (Corridor vs Room)</h4><canvas id="ts-rh-{pid}"></canvas></div></div>
<div class="chart-row"><div class="chart-box"><h4>Daily CO2 (Corridor vs Room)</h4><canvas id="ts-co2-{pid}"></canvas></div>
<div class="chart-box"><h4>Daily VPX (Corridor vs Room)</h4><canvas id="ts-vpx-{pid}"></canvas></div></div>
'''
        # Comparison table
        html+='<h4 style="margin-bottom:12px">Corridor vs Room</h4><div class="tw"><table><thead><tr><th>Metric</th><th>Corridor</th><th>Room</th><th>Delta</th></tr></thead><tbody>'
        def crow(label,ck,rk,unit='',fmt='.1f'):
            cv=cm[ck] if cm and cm.get(ck) is not None else None
            rv=rm[rk] if rm.get(rk) is not None else None
            cvs=f'{cv:{fmt}}{unit}' if cv is not None else '—'
            rvs=f'{rv:{fmt}}{unit}' if rv is not None else '—'
            ds=f'{rv-cv:+{fmt}}{unit}' if cv is not None and rv is not None else '—'
            return f'<tr><td style="font-weight:500">{label}</td><td>{cvs}</td><td>{rvs}</td><td style="font-weight:600">{ds}</td></tr>'
        if cm:
            html+=crow('Mean Temperature','mean_temp','mean_temp','°C')
            html+=crow('Min Temperature','min_temp','min_temp','°C')
            html+=crow('Max Temperature','max_temp','max_temp','°C')
            html+=crow('Mean Humidity','mean_rh','mean_rh','%')
            html+=crow('Mould Score','mould_score','mould_score','','.1f')
            html+=crow('% RH > 70%','pct_rh_70','pct_rh_70','%')
            html+=crow('Mean VPX','mean_vpx','mean_vpx',' Pa','.1f')
            html+=crow('Mean CRI','mean_cri','mean_cri','K','.1f')
            html+=crow('Mean EHR','mean_ehr','mean_ehr','%','.1f')
            html+=crow('% Over 26°C','pct_over_26','pct_over_26','%')
            html+=crow('% Under 18°C','pct_under_18','pct_under_18','%')
            html+=crow('Mean CO2','mean_co2','mean_co2',' ppm','.0f')
            html+=crow('Window Events/Day','window_events_per_day','window_events_per_day','')
            html+=crow('% Occupied','pct_occupied','pct_occupied','%')
            html+=crow('TRI','thermal_responsiveness','thermal_responsiveness','','.3f')
            html+=crow('NPE','mean_npe','mean_npe','','.3f')
            html+=crow('Wind r','wind_infiltration_corr','wind_infiltration_corr','','.3f')
            html+=crow('Indoor-Outdoor ΔT','mean_indoor_outdoor_delta','mean_indoor_outdoor_delta','°C')
        else: html+='<tr><td colspan="4" style="color:#9ca3af">Corridor data not available</td></tr>'
        html+='</tbody></table></div></div></div>\n'

    # ── JAVASCRIPT ──
    chart_json = json.dumps(chart_data, default=str)
    portfolio_json = json.dumps({'labels':portfolio_labels,'mould':portfolio_mould,'vpx':portfolio_vpx,'under':portfolio_under,'over':portfolio_over,'co2':portfolio_co2})
    comp_json = json.dumps({'labels':comp_labels,'temp_corr':comp_temp_corr,'temp_room':comp_temp_room,'rh_corr':comp_rh_corr,'rh_room':comp_rh_room,'mould_corr':comp_mould_corr,'mould_room':comp_mould_room})
    donut_json = json.dumps(donut_data)
    radar_json = json.dumps(radar_data, default=str)

    # Scatter data for mould tab
    scatter_mould = json.dumps([{'x':p['rm']['mean_rh'],'y':p['rm']['mould_score'],'label':p['id'][-6:]} for p in props])
    # Scatter data for moisture tab
    scatter_moisture = json.dumps([{'x':p['rm']['mean_vpx'] or 0,'y':p['rm']['mean_cri'] or 0,'label':p['id'][-6:]} for p in props])
    # Histogram data
    mould_scores = json.dumps([p['rm']['mould_score'] for p in props])
    ehr_values = json.dumps([p['rm']['mean_ehr'] or 0 for p in props])
    # Overheating detail
    oh_labels = json.dumps([p['id'][-6:] for p in sorted(props, key=lambda x: x['rm']['pct_over_26'], reverse=True)])
    oh_vals = json.dumps([p['rm']['pct_over_26'] for p in sorted(props, key=lambda x: x['rm']['pct_over_26'], reverse=True)])
    ad_vals = json.dumps([p['rm']['pct_adaptive_exceed'] for p in sorted(props, key=lambda x: x['rm']['pct_over_26'], reverse=True)])
    # Under-heat detail
    uh_labels = json.dumps([p['id'][-6:] for p in sorted(props, key=lambda x: x['rm']['pct_under_18'], reverse=True)])
    uh_vals = json.dumps([p['rm']['pct_under_18'] for p in sorted(props, key=lambda x: x['rm']['pct_under_18'], reverse=True)])
    mint_vals = json.dumps([p['rm']['min_temp'] for p in sorted(props, key=lambda x: x['rm']['pct_under_18'], reverse=True)])
    # Ventilation detail
    co2_labels = json.dumps([p['id'][-6:] for p in sorted(props, key=lambda x: x['rm'].get('mean_co2') or 0, reverse=True)])
    co2_vals = json.dumps([p['rm']['mean_co2'] or 0 for p in sorted(props, key=lambda x: x['rm'].get('mean_co2') or 0, reverse=True)])
    win_labels = json.dumps([p['id'][-6:] for p in sorted(props, key=lambda x: x['rm']['window_events_per_day'], reverse=True)])
    win_vals = json.dumps([p['rm']['window_events_per_day'] for p in sorted(props, key=lambda x: x['rm']['window_events_per_day'], reverse=True)])
    # Fabric
    tri_labels = json.dumps([p['id'][-6:] for p in sorted(props, key=lambda x: x['rm'].get('thermal_responsiveness') or 0, reverse=True)])
    tri_vals = json.dumps([p['rm']['thermal_responsiveness'] or 0 for p in sorted(props, key=lambda x: x['rm'].get('thermal_responsiveness') or 0, reverse=True)])
    npe_labels = json.dumps([p['id'][-6:] for p in sorted(props, key=lambda x: x['rm'].get('mean_npe') or 0, reverse=True)])
    npe_vals = json.dumps([p['rm']['mean_npe'] or 0 for p in sorted(props, key=lambda x: x['rm'].get('mean_npe') or 0, reverse=True)])
    # Comp delta
    comp_deltas = json.dumps([round(comp_temp_room[i]-comp_temp_corr[i],1) for i in range(len(comp_labels))])

    occ_chart_labels_j = json.dumps(occ_chart_labels)
    occ_temp_o_j = json.dumps(occ_temp_o)
    occ_temp_u_j = json.dumps(occ_temp_u)
    occ_rh_o_j = json.dumps(occ_rh_o)
    occ_rh_u_j = json.dumps(occ_rh_u)
    occ_co2_o_j = json.dumps(occ_co2_o)
    occ_co2_u_j = json.dumps(occ_co2_u)
    occ_vpx_o_j = json.dumps(occ_vpx_o)
    occ_vpx_u_j = json.dumps(occ_vpx_u)
    sort_data_j = json.dumps(sort_data)
    rd_labels_j = json.dumps(rd_chart_labels)
    rd_values_j = json.dumps(rd_chart_values)
    rd_sources_j = json.dumps([room_only_flags, corr_only_flags, both_flags])

    html += f'''
<script>
const CD={chart_json};
const PD={portfolio_json};
const CP={comp_json};
const DD={donut_json};
const RD={radar_json};
const SM={scatter_mould};
const SMO={scatter_moisture};
const MS={mould_scores};
const EHR={ehr_values};
const OHL={oh_labels}, OHV={oh_vals}, ADV={ad_vals};
const UHL={uh_labels}, UHV={uh_vals}, MTV={mint_vals};
const C2L={co2_labels}, C2V={co2_vals};
const WNL={win_labels}, WNV={win_vals};
const TRL={tri_labels}, TRV={tri_vals};
const NPL={npe_labels}, NPV={npe_vals};
const CDLT={comp_deltas};
const OCL={occ_chart_labels_j};
const OTO={occ_temp_o_j}, OTU={occ_temp_u_j};
const ORO={occ_rh_o_j}, ORU={occ_rh_u_j};
const OCO={occ_co2_o_j}, OCU={occ_co2_u_j};
const OVO={occ_vpx_o_j}, OVU={occ_vpx_u_j};
const SORT_DATA={sort_data_j};
const RDL={rd_labels_j}, RDV={rd_values_j}, RDS={rd_sources_j};

Chart.defaults.font.family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
Chart.defaults.font.size=11;
Chart.defaults.plugins.legend.labels.boxWidth=12;
Chart.defaults.animation.duration=0;

const riskColors={{'Critical':'#991b1b','High':'#ef4444','Medium':'#f59e0b','Low':'#22c55e',
'Exceeds Limit':'#ef4444','Warning':'#f59e0b','Pass':'#22c55e',
'Inadequate':'#991b1b','Poor':'#ef4444','Acceptable':'#f59e0b','Good':'#22c55e'}};

function showTab(id){{
    document.querySelectorAll('.tc').forEach(e=>e.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));
    var t=document.getElementById('tab-'+id); if(t) t.classList.add('active');
    document.querySelectorAll('.tab').forEach(e=>{{if(e.getAttribute('onclick')&&e.getAttribute('onclick').indexOf("'"+id+"'")>=0) e.classList.add('active');}});
    window.scrollTo({{top:0,behavior:'smooth'}});
    // Lazy init property charts
    if(id.startsWith('prop-')){{ var pid=id.replace('prop-',''); initPropCharts(pid); }}
}}

// Donuts
function mkDonut(id,data){{
    var labels=Object.keys(data), vals=Object.values(data);
    var colors=labels.map(l=>riskColors[l]||'#9ca3af');
    new Chart(document.getElementById(id),{{type:'doughnut',data:{{labels:labels,datasets:[{{data:vals,backgroundColor:colors,borderWidth:2,borderColor:'#fff'}}]}},options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{padding:8}}}}}}}}}});
}}
mkDonut('donut-mould',DD.mould_rating);
mkDonut('donut-overheat',DD.overheat_rating);
mkDonut('donut-underheat',DD.underheat_rating);
mkDonut('donut-vent',DD.ventilation_rating);

// Portfolio bars
function mkBar(id,labels,data,color,label,annot){{
    var ds=[{{label:label,data:data,backgroundColor:color,borderRadius:3}}];
    var opts={{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{maxRotation:90,minRotation:45,font:{{size:9}}}}}},y:{{beginAtZero:true}}}}}};
    if(annot){{
        opts.plugins.annotation={{annotations:{{line1:{{type:'line',yMin:annot.v,yMax:annot.v,borderColor:annot.c||'#ef4444',borderWidth:1.5,borderDash:[4,4],label:{{display:true,content:annot.l,position:'start',font:{{size:10}}}}}}}}}};
    }}
    new Chart(document.getElementById(id),{{type:'bar',data:{{labels:labels,datasets:ds}},options:opts}});
}}
mkBar('bar-mould',PD.labels,PD.mould,'#ef4444','Mould Score',{{v:20,c:'#f59e0b',l:'High Risk (20)'}});
mkBar('bar-vpx',PD.labels,PD.vpx,'#8b5cf6','VPX (Pa)',{{v:300,c:'#ef4444',l:'Excess Moisture (300 Pa)'}});
mkBar('bar-under',PD.labels,PD.under,'#3b82f6','% Under 18°C',{{v:10,c:'#ef4444',l:'High Risk (10%)'}});
mkBar('bar-over',PD.labels,PD.over,'#f97316','% Over 26°C',{{v:3,c:'#ef4444',l:'CIBSE Limit (3%)'}});

// Mould scatter
new Chart(document.getElementById('scatter-mould'),{{type:'scatter',data:{{datasets:[{{data:SM,backgroundColor:'#ef4444',pointRadius:5}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:function(c){{return c.raw.label+': RH '+c.raw.x+'%, Score '+c.raw.y}}}}}}}},scales:{{x:{{title:{{display:true,text:'Mean RH (%)'}}}},y:{{title:{{display:true,text:'Mould Score'}}}}}}}}}});

// Mould histogram
function mkHist(id,vals,color,xlabel){{
    var bins=[0,5,10,15,20,30,40,60,100]; var counts=new Array(bins.length-1).fill(0);
    vals.forEach(v=>{{for(var i=0;i<bins.length-1;i++){{if(v>=bins[i]&&v<bins[i+1]){{counts[i]++;break;}}}}}});
    var labels=bins.slice(0,-1).map((b,i)=>b+'-'+bins[i+1]);
    new Chart(document.getElementById(id),{{type:'bar',data:{{labels:labels,datasets:[{{data:counts,backgroundColor:color,borderRadius:3}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{title:{{display:true,text:xlabel}}}},y:{{title:{{display:true,text:'Count'}},beginAtZero:true}}}}}}}});
}}
mkHist('hist-mould',MS,'#ef4444','Mould Score Range');

// Moisture scatter
new Chart(document.getElementById('scatter-moisture'),{{type:'scatter',data:{{datasets:[{{data:SMO,backgroundColor:'#8b5cf6',pointRadius:5}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:function(c){{return c.raw.label+': VPX '+c.raw.x+'Pa, CRI '+c.raw.y+'K'}}}}}}}},scales:{{x:{{title:{{display:true,text:'Mean VPX (Pa)'}}}},y:{{title:{{display:true,text:'Mean CRI (K)'}}}}}}}}}});

// EHR histogram
(function(){{
    var vals=EHR; var mn=Math.min(...vals),mx=Math.max(...vals);
    var step=Math.max(1,Math.round((mx-mn)/8)); var bins=[];
    for(var b=Math.floor(mn);b<=mx+step;b+=step) bins.push(b);
    var counts=new Array(bins.length-1).fill(0);
    vals.forEach(v=>{{for(var i=0;i<bins.length-1;i++){{if(v>=bins[i]&&v<bins[i+1]){{counts[i]++;break;}}}}}});
    var labels=bins.slice(0,-1).map((b,i)=>b+'-'+bins[i+1]+'%');
    new Chart(document.getElementById('hist-ehr'),{{type:'bar',data:{{labels:labels,datasets:[{{data:counts,backgroundColor:'#06b6d4',borderRadius:3}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{y:{{beginAtZero:true}}}}}}}});
}})();

// Overheating detail bars
mkBar('bar-oh-detail',OHL,OHV,'#f97316','% > 26°C',{{v:3,c:'#ef4444',l:'CIBSE 3%'}});
mkBar('bar-adaptive',OHL,ADV,'#eab308','% Adaptive Exceed');

// Under-heat bars
mkBar('bar-uh-detail',UHL,UHV,'#3b82f6','% Under 18°C',{{v:10,c:'#ef4444',l:'High (10%)'}});
mkBar('bar-min-temp',UHL,MTV,'#06b6d4','Min Temp °C',{{v:18,c:'#f59e0b',l:'WHO 18°C'}});

// Ventilation bars
mkBar('bar-co2',C2L,C2V,'#8b5cf6','Mean CO2',{{v:1000,c:'#f59e0b',l:'Action (1000 ppm)'}});
mkBar('bar-window',WNL,WNV,'#10b981','Events/Day');

// Fabric bars
mkBar('bar-tri',TRL,TRV,'#f59e0b','TRI',{{v:0.7,c:'#ef4444',l:'Lightweight (0.7)'}});
mkBar('bar-npe',NPL,NPV,'#06b6d4','NPE');

// Comparison grouped bars
function mkGrouped(id,labels,d1,d2,l1,l2,c1,c2){{
    new Chart(document.getElementById(id),{{type:'bar',data:{{labels:labels,datasets:[{{label:l1,data:d1,backgroundColor:c1,borderRadius:3}},{{label:l2,data:d2,backgroundColor:c2,borderRadius:3}}]}},options:{{responsive:true,scales:{{x:{{ticks:{{maxRotation:90,minRotation:45,font:{{size:9}}}}}}}}}}}});
}}
// Risk divergence charts
if(RDL.length>0) mkBar('bar-riskdiff',RDL,RDV,'var(--red)','Risks Flagged');
new Chart(document.getElementById('donut-riskdiff'),{{type:'doughnut',data:{{labels:['Room Only','Corridor Only','Both'],datasets:[{{data:RDS,backgroundColor:['#ff9e2c','#9240fb','#dc2b2b'],borderWidth:2,borderColor:'#fff'}}]}},options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{padding:8}}}}}}}}}});

// Occupancy impact charts
mkGrouped('occ-temp',OCL,OTO,OTU,'Occupied','Unoccupied','#f97316','#94a3b8');
mkGrouped('occ-rh',OCL,ORO,ORU,'Occupied','Unoccupied','#8b5cf6','#94a3b8');
mkGrouped('occ-co2',OCL,OCO,OCU,'Occupied','Unoccupied','#ef4444','#94a3b8');
mkGrouped('occ-vpx',OCL,OVO,OVU,'Occupied','Unoccupied','#06b6d4','#94a3b8');

mkGrouped('comp-temp',CP.labels,CP.temp_corr,CP.temp_room,'Corridor','Room','#94a3b8','#3b82f6');
mkGrouped('comp-rh',CP.labels,CP.rh_corr,CP.rh_room,'Corridor','Room','#94a3b8','#8b5cf6');
mkGrouped('comp-mould',CP.labels,CP.mould_corr,CP.mould_room,'Corridor','Room','#94a3b8','#ef4444');
// Delta bar
new Chart(document.getElementById('comp-delta'),{{type:'bar',data:{{labels:CP.labels,datasets:[{{label:'Room - Corridor °C',data:CDLT,backgroundColor:CDLT.map(v=>v>0?'#ef4444':'#3b82f6'),borderRadius:3}}]}},options:{{responsive:true,scales:{{x:{{ticks:{{maxRotation:90,minRotation:45,font:{{size:9}}}}}},y:{{beginAtZero:false}}}}}}}});

// Cluster radar
(function(){{
    var labels=['Mean Temp','Mean RH','Mould Score','% Under 18','% Over 26','Mean CO2','Mean VPX'];
    var colors=['#3b82f6','#ef4444','#22c55e','#f59e0b','#8b5cf6','#06b6d4'];
    var maxVals=[35,100,100,100,100,2000,800];
    var datasets=[];
    Object.keys(RD).forEach(function(k,i){{
        var d=RD[k]; var vals=[d.mean_temp,d.mean_rh,d.mould_score,d.pct_under_18,d.pct_over_26,d.mean_co2,d.mean_vpx];
        var normed=vals.map((v,j)=>Math.min(100,(v/maxVals[j])*100));
        datasets.push({{label:'Cluster '+(parseInt(k)+1),data:normed,borderColor:colors[i%6],backgroundColor:colors[i%6]+'20',pointRadius:3}});
    }});
    new Chart(document.getElementById('radar-clusters'),{{type:'radar',data:{{labels:labels,datasets:datasets}},options:{{responsive:true,scales:{{r:{{min:0,max:100,ticks:{{stepSize:25}}}}}}}}}});
}})();

// Property time-series charts (lazy)
// Risk table sorting
function sortRiskTable(){{
    var key=document.getElementById('risk-sort').value;
    var tb=document.getElementById('risk-table').querySelector('tbody');
    var rows=Array.from(tb.querySelectorAll('tr'));
    // Build sort keys: for risk ratings use rating order + secondary score; for deltas use absolute value
    var sortKeys={{}};
    SORT_DATA.forEach(function(d,i){{
        var v=0;
        if(key==='mould') v=d.mould*1000+d.mould_s;
        else if(key==='condensation') v=d.condensation*1000+(100-d.cri_s);
        else if(key==='vpx') v=d.vpx*1000+d.vpx_s;
        else if(key==='overheat') v=d.overheat*1000+d.oh_s;
        else if(key==='underheat') v=d.underheat*1000+d.uh_s;
        else if(key==='ventilation') v=d.ventilation*1000+d.vent_s;
        else if(key==='fabric') v=d.fabric*1000+d.tri_s;
        else if(key==='delta_temp') v=d.delta_temp;
        else if(key==='delta_rh') v=d.delta_rh;
        else if(key==='delta_mould') v=d.delta_mould;
        else if(key==='room_alert') v=d.room_alert;
        sortKeys[i]=v;
    }});
    rows.sort(function(a,b){{
        var ai=parseInt(a.getAttribute('data-idx'));
        var bi=parseInt(b.getAttribute('data-idx'));
        return (sortKeys[bi]||0)-(sortKeys[ai]||0);
    }});
    rows.forEach(function(r){{ tb.appendChild(r); }});
}}
// Initial sort by mould
sortRiskTable();

var propChartsInit={{}};
function initPropCharts(pid){{
    if(propChartsInit[pid]) return;
    propChartsInit[pid]=true;
    var d=CD[pid]; if(!d) return;
    var room=d.room, corr=d.corridor;
    if(!room) return;
    var dates=room.dates;
    // Temperature
    var datasets=[{{label:'Room Mean',data:room.avgT_mean,borderColor:'#3b82f6',backgroundColor:'#3b82f620',fill:false,pointRadius:0,borderWidth:1.5}},
        {{label:'Room Range',data:room.avgT_max.map((v,i)=>v!=null&&room.avgT_min[i]!=null?v-room.avgT_min[i]:null),borderColor:'transparent',backgroundColor:'#3b82f615',fill:true,pointRadius:0}}];
    if(corr) datasets.push({{label:'Corridor Mean',data:corr.avgT_mean,borderColor:'#94a3b8',fill:false,pointRadius:0,borderWidth:1.5}});
    datasets.push({{label:'Outdoor',data:room.weather_temperature_mean,borderColor:'#22c55e',fill:false,pointRadius:0,borderWidth:1,borderDash:[3,3]}});
    mkTS('ts-temp-'+pid,dates,datasets,[{{v:26,c:'#ef4444',l:'26°C'}},{{v:18,c:'#3b82f6',l:'18°C'}}]);
    // Humidity
    var hds=[{{label:'Room',data:room.avgH_mean,borderColor:'#8b5cf6',fill:false,pointRadius:0,borderWidth:1.5}}];
    if(corr) hds.push({{label:'Corridor',data:corr.avgH_mean,borderColor:'#94a3b8',fill:false,pointRadius:0,borderWidth:1.5}});
    mkTS('ts-rh-'+pid,dates,hds,[{{v:70,c:'#f59e0b',l:'70%'}},{{v:80,c:'#ef4444',l:'80%'}}]);
    // CO2
    var cds=[{{label:'Room',data:room.avgCO2_mean,borderColor:'#f59e0b',fill:false,pointRadius:0,borderWidth:1.5}}];
    if(corr) cds.push({{label:'Corridor',data:corr.avgCO2_mean,borderColor:'#94a3b8',fill:false,pointRadius:0,borderWidth:1.5}});
    mkTS('ts-co2-'+pid,dates,cds,[{{v:1000,c:'#f59e0b',l:'1000'}},{{v:1500,c:'#ef4444',l:'1500'}}]);
    // VPX
    var vds=[{{label:'Room',data:room.vpx_mean,borderColor:'#8b5cf6',fill:false,pointRadius:0,borderWidth:1.5}}];
    if(corr) vds.push({{label:'Corridor',data:corr.vpx_mean,borderColor:'#94a3b8',fill:false,pointRadius:0,borderWidth:1.5}});
    mkTS('ts-vpx-'+pid,dates,vds,[{{v:300,c:'#f59e0b',l:'300 Pa'}},{{v:600,c:'#ef4444',l:'600 Pa'}}]);
}}

function mkTS(id,dates,datasets,annots){{
    var el=document.getElementById(id); if(!el) return;
    var opts={{responsive:true,interaction:{{mode:'index',intersect:false}},scales:{{x:{{type:'category',ticks:{{maxTicksLimit:12,maxRotation:45,font:{{size:9}}}}}},y:{{}}}},plugins:{{legend:{{labels:{{boxWidth:10,padding:6}}}}}}}};
    if(annots&&annots.length){{
        opts.plugins.annotation={{annotations:{{}}}};
        annots.forEach(function(a,i){{
            opts.plugins.annotation.annotations['l'+i]={{type:'line',yMin:a.v,yMax:a.v,borderColor:a.c,borderWidth:1,borderDash:[4,4],label:{{display:true,content:a.l,position:'start',font:{{size:9}}}}}};
        }});
    }}
    new Chart(el,{{type:'line',data:{{labels:dates,datasets:datasets}},options:opts}});
}}
</script>
</div></body></html>'''
    return html


def main():
    print("Loading sensor data (raw, no resampling)...")
    props = []
    for folder in sorted(os.listdir(BASE)):
        fp = os.path.join(BASE, folder)
        if not os.path.isdir(fp): continue
        files = [f for f in os.listdir(fp) if f.endswith('.csv')]
        ey = [f for f in files if f.startswith('EYESENSE_')]
        sn = [f for f in files if f.startswith('SENS_')]
        if not ey or not sn: continue
        print(f"  {folder}...")
        corr_raw = load_csv(os.path.join(fp, ey[0]))
        room_raw = load_csv(os.path.join(fp, sn[0]))
        cm = compute_metrics(corr_raw)
        rm = compute_metrics(room_raw)
        if rm:
            props.append({
                'id': folder,
                'cm': cm, 'rm': rm,
                'corridor_daily': daily_aggregates(corr_raw),
                'room_daily': daily_aggregates(room_raw),
            })
    print(f"\n{len(props)} properties loaded.")

    print("Clustering...")
    feats = [p['rm']['_cluster_features'] for p in props]
    nd, _, _ = norm(feats)
    bkv, labels, ssv = best_k(nd, mx=6)
    print(f"  k={bkv}, Silhouette={ssv:.3f}")

    cg = defaultdict(list)
    for i, p in enumerate(props): cg[labels[i]].append(p['rm'])
    cd = {cl: desc_cluster(m) for cl, m in cg.items()}

    print("Generating dashboard with charts...")
    html = gen_html(props, labels, cd, bkv, ssv)
    with open(OUTPUT, 'w') as f: f.write(html)
    print(f"\nDashboard: {OUTPUT}")


if __name__ == '__main__':
    main()
