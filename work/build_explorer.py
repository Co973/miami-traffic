import json, math, hashlib, sys, csv, re
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict, Counter

INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'C:\Users\ragha\Downloads\Timeline.json')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('outputs/miami-explorer')
OUT.mkdir(parents=True, exist_ok=True)
SIGNALS = Path(r'C:\Users\ragha\Downloads\TrafficSignals_gdb_7601094683208399504.csv')
STREET_NETWORK = Path(r'C:\Users\ragha\Downloads\StreetNetwork_gdb_4985840991390692744.csv')
MAJOR_ROADS = Path(r'C:\Users\ragha\Downloads\MajorRoads_gdb_8530929722969570122.csv')
TIGER_SHP = Path(r'C:\Users\ragha\Downloads\tl_2023_12086_edges\tl_2023_12086_edges.shp')
TIGER_DBF = Path(r'C:\Users\ragha\Downloads\tl_2023_12086_edges\tl_2023_12086_edges.dbf')
TMS = Path(r'C:\Users\ragha\Downloads\Traffic_TMSCOUNT_TDA_5925985072845764841.csv')
COUNT_STATIONS = Path(r'C:\Users\ragha\Downloads\MDCTrafficCountStation_gdb_969148723810286986.csv')

def epoch(s):
    return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()

NY = ZoneInfo('America/New_York')
def local_hour(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(NY).hour

def parse_latlng(v):
    if isinstance(v, str):
        a,b = v.split(',')[:2]
        return float(a.replace('°','')), float(b.replace('°',''))
    if isinstance(v, dict):
        return float(v.get('latitudeE7',0))/1e7, float(v.get('longitudeE7',0))/1e7
    raise ValueError('unknown coordinate')

def median(xs):
    if not xs: return None
    ys = sorted(xs); n=len(ys); m=n//2
    return ys[m] if n%2 else (ys[m-1]+ys[m])/2

def quantile(xs, q):
    if not xs: return None
    ys=sorted(xs); return ys[min(len(ys)-1, max(0, round((len(ys)-1)*q)))]

def distance_m(a, b):
    lat1,lon1=a; lat2,lon2=b
    return 111320*math.sqrt((lat1-lat2)**2+((lon1-lon2)*math.cos(math.radians((lat1+lat2)/2)))**2)

def read_dbf(path):
    import struct
    with path.open('rb') as f:
        h=f.read(32); n=struct.unpack('<I',h[4:8])[0]; hl=struct.unpack('<H',h[8:10])[0]; rl=struct.unpack('<H',h[10:12])[0]
        fields=[]
        for _ in range((hl-33)//32):
            b=f.read(32); fields.append((b[:11].split(b'\0',1)[0].decode('ascii','ignore'),b[16]))
        f.read(1); rows=[]
        for _ in range(n):
            rec=f.read(rl)
            if len(rec)<rl: break
            off=1; row={}
            for name,width in fields:
                row[name]=rec[off:off+width].decode('latin1','ignore').strip(); off+=width
            rows.append(row)
    return rows

def read_tiger_edges():
    import struct
    if not TIGER_SHP.exists() or not TIGER_DBF.exists(): return [], {'tiger_edges':0,'tiger_geometry':'missing'}
    attrs=read_dbf(TIGER_DBF); edges=[]
    with TIGER_SHP.open('rb') as f:
        f.read(100)
        while True:
            head=f.read(8)
            if len(head)<8: break
            _, words=struct.unpack('>2i',head); blob=f.read(words*2)
            if len(blob)<44: continue
            typ=struct.unpack('<i',blob[:4])[0]
            if typ!=3: continue
            xmin,ymin,xmax,ymax=struct.unpack('<4d',blob[4:36]); parts_n,points_n=struct.unpack('<2i',blob[36:44])
            parts=list(struct.unpack('<%di'%parts_n,blob[44:44+4*parts_n])) if parts_n else []
            po=44+4*parts_n+4*parts_n
            # The second 4*parts_n term above is intentionally retained for the
            # standard PolyLine layout's parts array alignment.
            po=44+4*parts_n
            points=[]
            for j in range(points_n):
                x,y=struct.unpack('<2d',blob[po+j*16:po+j*16+16]); points.append((y,x))
            idx=len(edges)
            a=attrs[idx] if idx<len(attrs) else {}
            if points: edges.append({'name':a.get('FULLNAME','').strip() or 'Unnamed road','mtfcc':a.get('MTFCC','').strip(),'points':points,'bbox':(ymin,xmin,ymax,xmax)})
    # Lightweight spatial index by degree cells; enough for endpoint matching.
    index=defaultdict(list); step=.02
    for i,e in enumerate(edges):
        y0,x0,y1,x1=e['bbox'];
        for gy in range(math.floor(y0/step),math.floor(y1/step)+1):
            for gx in range(math.floor(x0/step),math.floor(x1/step)+1): index[(gy,gx)].append(i)
    return {'edges':edges,'index':index,'step':step}, {'tiger_edges':len(edges),'tiger_geometry':'TIGER/Line 2023 Miami-Dade'}

def nearest_edge(lat, lon, tiger):
    if not tiger: return None
    step=tiger['step']; gy,gx=math.floor(lat/step),math.floor(lon/step); ids=[]
    for dy in (-1,0,1):
        for dx in (-1,0,1): ids.extend(tiger['index'].get((gy+dy,gx+dx),[]))
    best=None
    for i in set(ids):
        e=tiger['edges'][i]; y0,x0,y1,x1=e['bbox']
        if lat<y0-.01 or lat>y1+.01 or lon<x0-.01 or lon>x1+.01: continue
        pts=e['points']
        for a,b in zip(pts,pts[1:]):
            # Equirectangular projection is sufficient at Miami scale.
            k=math.cos(math.radians(lat)); ax=a[1]*k; ay=a[0]; bx=b[1]*k; by=b[0]; px=lon*k; py=lat
            dx=bx-ax; dy=by-ay; t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy or 1)))
            d=distance_m((lat,lon),(ay+t*dy,(ax+t*dx)/k))
            if best is None or d<best[0]: best=(d,e)
    if not best: return None
    return {'name':best[1]['name'],'mtfcc':best[1]['mtfcc'],'distance_m':round(best[0])}

def utm17_to_latlon(x, y):
    # NAD83 / UTM zone 17N; WGS84 constants are close enough for corridor
    # attribution at this scale and avoid adding a runtime GIS dependency.
    a=6378137.0; ecc=0.00669438002290; k0=.9996; e1=(1-math.sqrt(1-ecc))/(1+math.sqrt(1-ecc)); x-=500000; m=y/k0
    mu=m/(a*(1-ecc/4-3*ecc**2/64-5*ecc**3/256)); e1sq=e1*e1
    j1=3*e1/2-27*e1**3/32; j2=21*e1sq/16-55*e1**4/32; j3=151*e1**3/96; j4=1097*e1**4/512
    fp=mu+j1*math.sin(2*mu)+j2*math.sin(4*mu)+j3*math.sin(6*mu)+j4*math.sin(8*mu)
    c1=ecc/(1-ecc)*math.cos(fp)**2; t1=math.tan(fp)**2; n1=a/math.sqrt(1-ecc*math.sin(fp)**2); r1=a*(1-ecc)/(1-ecc*math.sin(fp)**2)**1.5; d=x/(n1*k0)
    lat=fp-(n1*math.tan(fp)/r1)*(d*d/2-(5+3*t1+10*c1-4*c1*c1-9*ecc/(1-ecc))*d**4/24)
    lon=(math.radians(-81)+(d-(1+2*t1+c1)*d**3/6)/math.cos(fp))
    return math.degrees(lat),math.degrees(lon)

def road_signature(s):
    s=(s or '').upper().replace('EXPWY','EXPRESSWAY').replace('EXPY','EXPRESSWAY').replace('HWAY','HIGHWAY').replace('HWY','HIGHWAY').replace('CSWY','CAUSEWAY').replace('AVE','AVENUE').replace('AV','AVENUE').replace('STREET','ST').replace('DRIVE','DR').replace('ROAD','RD')
    s=re.sub(r'(\d+)(ST|ND|RD|TH)\b',r'\1',s)
    s=re.sub(r'[^A-Z0-9]+',' ',s)
    tokens=set(s.split())
    if any(t.isdigit() for t in tokens):
        tokens -= {'ST','AVE','AVENUE','DR','RD','ROAD','BLVD','CT','LN','HWY','HIGHWAY','PKWY','PARKWAY','PL','TER','WAY'}
    return tokens

def load_tms():
    if not TMS.exists(): return {}, {'tms_rows':0,'tms_miami_rows':0,'tms_sites':0}
    groups=defaultdict(lambda:{'rows':0,'dates':[],'dirs':set(),'totals':[],'peaks':[],'hourly':defaultdict(list),'name':'','site':'','cosite':'','lat':None,'lon':None})
    total=miami=0
    with TMS.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            total+=1
            county=(r.get('COUNTY') or '').strip().lower()
            if not county.startswith('miami'): continue
            miami+=1; key=(r.get('COSITE','').strip(),r.get('DIR','').strip())
            g=groups[key]; g['rows']+=1; g['name']=(r.get('LOCALNAM') or '').strip(); g['site']=r.get('SITE','').strip(); g['cosite']=r.get('COSITE','').strip(); g['dirs'].add(r.get('DIR','').strip())
            try:g['dates'].append(datetime.strptime(r['BEGDATE'].strip(),'%m/%d/%Y %I:%M:%S %p').date().isoformat())
            except Exception:pass
            for fld, bucket in [('TOTVOL','totals'),('PEAKVOL','peaks')]:
                try:g[bucket].append(float(r.get(fld) or 0))
                except Exception:pass
            for h in range(1,25):
                try:g['hourly'][h].append(float(r.get(f'HR{h}') or 0))
                except Exception:pass
            try:g['lat'],g['lon']=utm17_to_latlon(float(r['x']),float(r['y']))
            except Exception:pass
    out=[]
    for g in groups.values():
        out.append({'name':g['name'],'signature':road_signature(g['name']),'site':g['site'],'cosite':g['cosite'],'direction':next(iter(g['dirs']),''),'rows':g['rows'],'date_start':min(g['dates']) if g['dates'] else None,'date_end':max(g['dates']) if g['dates'] else None,'days':len(set(g['dates'])),'median_total_volume':round(median(g['totals']),1) if g['totals'] else None,'median_peak_volume':round(median(g['peaks']),1) if g['peaks'] else None,'hourly_median':{str(h):round(median(v),1) for h,v in g['hourly'].items() if v},'lat':round(g['lat'],5) if g['lat'] else None,'lon':round(g['lon'],5) if g['lon'] else None})
    return out, {'tms_rows':total,'tms_miami_rows':miami,'tms_sites':len(out)}

def load_count_stations():
    """Load county AADT station points as context, never as peak directional volume."""
    if not COUNT_STATIONS.exists(): return [], {'count_station_rows':0,'count_station_aadt_rows':0}
    out=[]; total=0; with_aadt=0
    with COUNT_STATIONS.open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            total += 1
            try: lat=float(r.get('LAT') or 0); lon=float(r.get('LON') or 0)
            except Exception: continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180): continue
            aadt=None
            try:
                if (r.get('AADT2019') or '').strip():
                    aadt=float(r['AADT2019']); with_aadt += 1
            except Exception: pass
            out.append({'station':(r.get('MDSTA') or '').strip(), 'address':(r.get('ADDRESS') or '').strip(),
                        'lat':lat, 'lon':lon, 'aadt2019':aadt,
                        'signature':road_signature((r.get('ADDRESS') or '').strip())})
    return out, {'count_station_rows':total,'count_station_aadt_rows':with_aadt}

def load_gis_context():
    signals=[]
    if SIGNALS.exists():
        with SIGNALS.open(encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                try: signals.append({'lat':float(r['LAT']),'lon':float(r['LON']),'intersection':(r.get('Intersection') or '').strip(),'asset_type':(r.get('Asset Type') or '').strip()})
                except Exception: pass
    road_names=[]
    if MAJOR_ROADS.exists():
        with MAJOR_ROADS.open(encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                n=(r.get('SNAME') or '').strip()
                if n and n not in road_names: road_names.append(n)
    street_rows=0; speed_limits=[]
    if STREET_NETWORK.exists():
        with STREET_NETWORK.open(encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                street_rows+=1
                try:
                    v=float(r.get('SPEEDLIMIT') or 0)
                    if v>0: speed_limits.append(v)
                except Exception: pass
    tiger, tiger_stats = read_tiger_edges()
    count_stations, count_stats = load_count_stations()
    return signals, road_names, {'street_network_rows':street_rows,'speed_limit_rows':len(speed_limits),'speed_limit_median':median(speed_limits),'major_road_names':len(road_names), **tiger_stats, **count_stats}, tiger, count_stations

def enrich_corridor(c, signals, road_stats, tiger, tms, count_stations):
    # Some supplied GIS exports contain a replacement character where a separator
    # was lost during export; keep the public label readable without changing data.
    for s in signals:
        if s.get('intersection'): s['intersection']=s['intersection'].replace('\ufffd','-')
    endpoints=c['geometry']['coordinates']
    near=[]
    for p in endpoints:
        q=(p[1],p[0])
        ranked=sorted(((distance_m(q,(s['lat'],s['lon'])),s) for s in signals),key=lambda z:z[0])[:3]
        for d,s in ranked:
            if d<=700 and all(s['intersection'] != x['intersection'] for x in near):
                near.append({'intersection':s['intersection'] or 'Unnamed signal','distance_m':round(d)})
    names=[x['intersection'] for x in near[:2]]
    road_hits=[nearest_edge(p[1],p[0],tiger) for p in endpoints]
    road_hits=[x for x in road_hits if x]
    road_names=[x['name'] for x in road_hits if x['name'] and x['name']!='Unnamed road' and x.get('mtfcc','').startswith('S')]
    road_name=Counter(road_names).most_common(1)[0][0] if road_names else None
    if road_name and len(names)>=2: label=f"{road_name} · between {names[0]} and {names[1]}"
    elif road_name and names: label=f"{road_name} · near {names[0]}"
    elif road_name: label=road_name
    elif len(names)>=2: label=f"Between {names[0]} and {names[1]}"
    elif names: label=f"Near {names[0]}"
    else: label='Observed corridor · signal context unavailable'
    c['location_label']=label
    c['road_match']={'name':road_name,'mtfcc':next((x['mtfcc'] for x in road_hits if x['name']==road_name),None),'endpoint_matches':road_hits}
    c['nearby_signals']=near[:3]
    c['road_context']={'signal_matches':len(near),'road_inventory_rows':road_stats['street_network_rows'],'major_road_name_count':road_stats['major_road_names'],'status':'TIGER line geometry matched at corridor endpoints'}
    matched=[]
    if road_name:
        sig=road_signature(road_name)
        for row in tms:
            # Match exact normalized names or shared directional/number signatures.
            if row['signature']==sig or (sig and row['signature'] and sig.issubset(row['signature'])):
                matched.append(row)
    safe_tms=[]
    for row in matched[:4]:
        peak_window=(c.get('comparison') or {}).get('peak','')
        peak_hours=range(7,10) if peak_window=='AM' else range(15,19) if peak_window=='PM' else range(7,10)
        midday_hours=range(10,15)
        row['peak_window']=peak_window or 'AM/PM unavailable'
        row['peak_window_volume']=round(sum(row.get('hourly_median',{}).get(str(h),0) for h in peak_hours),1)
        row['midday_window_volume']=round(sum(row.get('hourly_median',{}).get(str(h),0) for h in midday_hours),1)
        safe_tms.append({k:v for k,v in row.items() if k not in ('signature','hourly_median')})
    c['tms_context']={'matched_sites':safe_tms,'status':'matched TMS count data' if matched else 'no TMS count site matched to this road name'}
    # AADT stations are annual average counts. Match by road signature and proximity
    # to the corridor midpoint, and keep them separate from directional peak counts.
    midpoint=(sum(p[1] for p in endpoints)/len(endpoints), sum(p[0] for p in endpoints)/len(endpoints))
    count_matches=[]
    if road_name:
        sig=road_signature(road_name)
        for row in count_stations:
            if row['aadt2019'] is None or not sig or not row['signature']: continue
            shared=len(sig & row['signature'])
            if shared < max(1, min(2, len(sig))): continue
            d=distance_m((midpoint[0],midpoint[1]),(row['lat'],row['lon']))
            if d <= 5000: count_matches.append((d,row,shared))
    count_matches.sort(key=lambda x:(x[0],-x[2],x[1]['station']))
    c['count_station_context']={'matched_stations':[{'station':r['station'],'address':r['address'],'aadt2019':r['aadt2019'],'distance_m':round(d)} for d,r,_ in count_matches[:4]],
                                'status':'matched 2019 AADT station context' if count_matches else 'no nearby AADT station matched by road name',
                                'use':'annual average daily traffic context only; not a directional peak-window volume'}
    return c

def main():
    raw = INPUT.read_bytes()
    data = json.loads(raw)
    positions=[]
    for i,item in enumerate(data.get('rawSignals', [])):
        p=item.get('position')
        if not p: continue
        try:
            lat,lon=parse_latlng(p.get('LatLng'))
            ts=epoch(p['timestamp']); acc=float(p.get('accuracyMeters', 9999))
            if not (-90<=lat<=90 and -180<=lon<=180): continue
            positions.append({'id':f'p{i}','ts':ts,'lat':lat,'lon':lon,'accuracy':acc,'source':p.get('source','UNKNOWN')})
        except Exception: continue
    positions.sort(key=lambda x:x['ts'])
    activities=[]
    for i,s in enumerate(data.get('semanticSegments', [])):
        a=s.get('activity',{}); c=a.get('topCandidate',{})
        if c.get('type') != 'IN_PASSENGER_VEHICLE': continue
        try:
            activities.append({'id':f'a{i}','start':epoch(s['startTime']),'end':epoch(s['endTime']),'confidence':float(c.get('probability',0))})
        except Exception: pass
    qualified=[]; reject=Counter()
    for a in activities:
        pts=[p for p in positions if a['start']<=p['ts']<=a['end'] and 0<p['accuracy']<=50]
        if a['confidence']<.8: reject['low_activity_confidence']+=1; continue
        if len(pts)<4: reject['too_few_positions']+=1; continue
        ded=[]
        for p in pts:
            if ded and p['ts']==ded[-1]['ts']:
                if p['accuracy']<ded[-1]['accuracy']: ded[-1]=p
            else: ded.append(p)
        runs=[]; cur=[ded[0]]
        for p,q in zip(ded,ded[1:]):
            dt=p['ts']-q['ts']
            dist=111320*math.hypot((p['lat']-q['lat']), (p['lon']-q['lon'])*math.cos(math.radians(p['lat'])))
            if dt>120 or (dt>0 and dist/dt>55):
                if len(cur)>=4: runs.append(cur)
                cur=[q]
            else: cur.append(q)
        if len(cur)>=4: runs.append(cur)
        if not runs: reject['no_continuous_run']+=1; continue
        for ri,run in enumerate(runs): qualified.append({'id':f"{a['id']}-{ri}",'activity_id':a['id'],'confidence':a['confidence'],'points':run})
    # Spatial bins are an evidence-preserving screening grid. They are not road matches.
    cell=0.0045
    windows=defaultdict(list)
    for run in qualified:
        pts=run['points']; cells=[]
        for p in pts:
            c=(round(p['lat']/cell), round(p['lon']/cell))
            if not cells or c!=cells[-1][0]: cells.append((c,p))
        if len(cells)<3: continue
        for j in range(len(cells)-2):
            c0,p0=cells[j]; c1,p1=cells[j+1]; c2,p2=cells[j+2]
            if p2['ts']-p0['ts']<90 or p2['ts']-p0['ts']>1800: continue
            key=(c0,c1,c2)
            windows[key].append({'run_id':run['id'],'day':datetime.fromtimestamp(p0['ts'],timezone.utc).astimezone(NY).date().isoformat(),'start':p0['ts'],'duration':p2['ts']-p0['ts'],'points':[p0,p1,p2]})
    candidates=[]
    for key,obs in windows.items():
        days=sorted(set(o['day'] for o in obs))
        if len(obs)<3 or len(days)<2: continue
        durations=[o['duration'] for o in obs]
        # Broad windows are intentionally descriptive; local time is derived from the export offsets.
        grouped=defaultdict(list)
        for o in obs:
            h=datetime.fromtimestamp(o['start'],timezone.utc).astimezone(NY).hour
            w='AM' if 7<=h<10 else 'Midday' if 10<=h<15 else 'PM' if 15<=h<19 else 'Other'
            grouped[w].append(o['duration'])
        comparisons=[]
        for peak in ('AM','PM'):
            if len(grouped[peak])>=2 and len(grouped['Midday'])>=2:
                diff=median(grouped[peak])-median(grouped['Midday'])
                comparisons.append({'peak':peak,'peak_n':len(grouped[peak]),'midday_n':len(grouped['Midday']),'difference_seconds':round(diff,1)})
        candidates.append({'key':key,'observations':obs,'days':days,'median_seconds':round(median(durations),1),'q25':round(quantile(durations,.25),1),'q75':round(quantile(durations,.75),1),'comparisons':comparisons})
    candidates.sort(key=lambda x:(-max([c['difference_seconds'] for c in x['comparisons']] or [-1]), -len(x['days']), str(x['key'])))
    signals, road_names, road_stats, tiger, count_stations = load_gis_context()
    tms, tms_stats = load_tms(); road_stats.update(tms_stats)
    selected=[]
    for c in candidates:
        if len(selected)>=12: break
        # deterministic overlap suppression using cell identity
        if any(len(set(c['key']) & set(s['key']))/3 > .5 for s in selected): continue
        selected.append(c)
    corridors=[]; all_traversals=[]
    for i,c in enumerate(selected,1):
        pts=[o['points'][0] for o in c['observations']]+[o['points'][-1] for o in c['observations']]
        coords=[(p['lon'],p['lat']) for p in pts]
        geo={'type':'LineString','coordinates':coords[:2]}
        best=max(c['comparisons'], key=lambda z:z['difference_seconds'], default=None)
        flag='supported' if best and best['difference_seconds']>0 and best['peak_n']>=2 and best['midday_n']>=2 else 'exploratory'
        cid=f'C{i:02d}'
        corridors.append(enrich_corridor({'id':cid,'label':f'Observed corridor {i}','status':flag,'sample_count':len(c['observations']),'day_count':len(c['days']),'median_seconds':c['median_seconds'],'q25_seconds':c['q25'],'q75_seconds':c['q75'],'comparison':best,'months':sorted(set(d[:7] for d in c['days'])),'geometry':{'type':'LineString','coordinates':[[round(x,3),round(y,3)] for x,y in geo['coordinates']]},'note':'Screening grid derived from personal GPS history. Signal labels, road names, TMS counts, and county count-station context are matched from supplied exports.'}, signals, road_stats, tiger, tms, count_stations))
        for o in c['observations']:
            all_traversals.append({'corridor_id':cid,'duration_seconds':round(o['duration'],1),'month':o['day'][:7],'window':next((x for x,a,b in [('AM',7,10),('Midday',10,15),('PM',15,19),('Other',0,24)] if a<=datetime.fromtimestamp(o['start'],timezone.utc).astimezone(NY).hour<b),'Other')})
    audit={'input_sha256':hashlib.sha256(raw).hexdigest(),'semantic_segments':len(data.get('semanticSegments',[])),'raw_signals':len(data.get('rawSignals',[])),'positions':len(positions),'vehicle_activities':len(activities),'qualified_runs':len(qualified),'candidate_corridors':len(candidates),'published_corridors':len(corridors),'rejections':dict(reject),'analysis_period':{'start':datetime.fromtimestamp(min([p['ts'] for p in positions]),timezone.utc).isoformat() if positions else None,'end':datetime.fromtimestamp(max([p['ts'] for p in positions]),timezone.utc).isoformat() if positions else None}}
    audit['gis_context']=road_stats | {'signals_loaded':len(signals)}
    manifest={'schema_version':'1.2','methodology_version':'screening-grid-signal-tms-aadt-context-v3','title':'Miami Arterial Evidence Explorer','scope':'Sampled GPS history only; not countywide traffic measurement.','audit':audit,'source_vintages':{'timeline_export':audit['analysis_period'],'signals':'TrafficSignals CSV supplied by user','street_network':'StreetNetwork CSV supplied by user','major_roads':'MajorRoads CSV supplied by user','count_stations':'MDCTrafficCountStation CSV; AADT2019 field'}}
    analysis={'corridors':corridors,'traversals':all_traversals,'quality_summary':audit,'limitations':['Corridors are discovered from repeated spatial cells, not yet matched to public road names.','The source is one driver’s history and is not a vehicle count.','Observed peak–midday differences are descriptive and are not proven removable delay.','AADT station values are 2019 annual averages and are context only; they are not directional peak-window volumes.','No signal phases, queues, or annual BCR are inferred.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'analysis.json').write_text(json.dumps(analysis,indent=2),encoding='utf-8')
    (OUT/'methodology.json').write_text(json.dumps({'defaults':{'accuracy_max_m':50,'max_gap_s':120,'max_jump_mps':55,'activity_confidence':.8,'grid_cell_deg':cell},'formulas':{'comparison':'median(peak duration) - median(midday duration)','scenario_savings':'observed_difference_seconds * assumed_fraction'},'limitations':analysis['limitations']},indent=2),encoding='utf-8')
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
