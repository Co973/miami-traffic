import json, math, hashlib, sys
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict, Counter

INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r'C:\Users\ragha\Downloads\Timeline.json')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('outputs/miami-explorer')
OUT.mkdir(parents=True, exist_ok=True)

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
        corridors.append({'id':cid,'label':f'Observed corridor {i}','status':flag,'sample_count':len(c['observations']),'day_count':len(c['days']),'median_seconds':c['median_seconds'],'q25_seconds':c['q25'],'q75_seconds':c['q75'],'comparison':best,'months':sorted(set(d[:7] for d in c['days'])),'geometry':{'type':'LineString','coordinates':[[round(x,3),round(y,3)] for x,y in geo['coordinates']]},'note':'Screening grid derived from personal GPS history; road name and signal attribution require public geography matching.'})
        for o in c['observations']:
            all_traversals.append({'corridor_id':cid,'duration_seconds':round(o['duration'],1),'month':o['day'][:7],'window':next((x for x,a,b in [('AM',7,10),('Midday',10,15),('PM',15,19),('Other',0,24)] if a<=datetime.fromtimestamp(o['start'],timezone.utc).astimezone(NY).hour<b),'Other')})
    audit={'input_sha256':hashlib.sha256(raw).hexdigest(),'semantic_segments':len(data.get('semanticSegments',[])),'raw_signals':len(data.get('rawSignals',[])),'positions':len(positions),'vehicle_activities':len(activities),'qualified_runs':len(qualified),'candidate_corridors':len(candidates),'published_corridors':len(corridors),'rejections':dict(reject),'analysis_period':{'start':datetime.fromtimestamp(min([p['ts'] for p in positions]),timezone.utc).isoformat() if positions else None,'end':datetime.fromtimestamp(max([p['ts'] for p in positions]),timezone.utc).isoformat() if positions else None}}
    manifest={'schema_version':'1.0','methodology_version':'screening-grid-v1','title':'Miami Arterial Evidence Explorer','scope':'Sampled GPS history only; not countywide traffic measurement.','audit':audit,'source_vintages':{'timeline_export':audit['analysis_period'],'road_geometry':'not bundled in this run','signals':'not bundled in this run'}}
    analysis={'corridors':corridors,'traversals':all_traversals,'quality_summary':audit,'limitations':['Corridors are discovered from repeated spatial cells, not yet matched to public road names.','The source is one driver’s history and is not a vehicle count.','Observed peak–midday differences are descriptive and are not proven removable delay.','No signal phases, queues, or annual BCR are inferred.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'analysis.json').write_text(json.dumps(analysis,indent=2),encoding='utf-8')
    (OUT/'methodology.json').write_text(json.dumps({'defaults':{'accuracy_max_m':50,'max_gap_s':120,'max_jump_mps':55,'activity_confidence':.8,'grid_cell_deg':cell},'formulas':{'comparison':'median(peak duration) - median(midday duration)','scenario_savings':'observed_difference_seconds * assumed_fraction'},'limitations':analysis['limitations']},indent=2),encoding='utf-8')
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
