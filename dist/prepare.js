const $ = (s) => document.querySelector(s);
const consent = $('#consent');
const fileInput = $('#timeline');
const button = $('#prepare');
const uploadButton = $('#upload');
const result = $('#result');
const prepareState = { file: null, prepared: null };
consent.addEventListener('change', () => { button.disabled = !(consent.checked && prepareState.file); });
fileInput.addEventListener('change', () => { prepareState.file = fileInput.files?.[0] || null; button.disabled = !(consent.checked && prepareState.file); });

function epoch(value) { return Date.parse(String(value).replace('Z', '+00:00')) / 1000; }
function parsePoint(item) {
  const p = item?.position;
  if (!p) return null;
  let lat, lon;
  try {
    if (p.LatLng) [lat, lon] = String(p.LatLng).split(',').slice(0, 2).map(v => parseFloat(v.replace(/[^0-9+-.]/g, '')));
    else { lat = Number(p.latitudeE7) / 1e7; lon = Number(p.longitudeE7) / 1e7; }
    const ts = epoch(p.timestamp), accuracy = Number(p.accuracyMeters);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(ts) || !Number.isFinite(accuracy)) return null;
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    return { ts, lat, lon, accuracy };
  } catch (_) { return null; }
}
function distanceM(a, b) { const k = Math.cos((a.lat + b.lat) * Math.PI / 360); return 111320 * Math.hypot(a.lat - b.lat, (a.lon - b.lon) * k); }
function localParts(ts) {
  const d = new Date(ts * 1000);
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hour12: false }).formatToParts(d);
  const x = Object.fromEntries(parts.map(p => [p.type, p.value]));
  const hour = Number(x.hour) % 24;
  return { date: `${x.year}-${x.month}-${x.day}`, window: hour >= 7 && hour < 10 ? 'AM' : hour >= 10 && hour < 15 ? 'Midday' : hour >= 15 && hour < 19 ? 'PM' : 'Other', bucket: `${x.hour}:00` };
}
function roundCoord(v) { return Math.round(v * 1000) / 1000; }
function roundedTime(ts) { return Math.floor(ts / 900) * 900; }

button.addEventListener('click', async () => {
  result.hidden = false; result.textContent = 'Preparing locally…'; button.disabled = true;
  try {
    const data = JSON.parse(await prepareState.file.text());
    const positions = (data.rawSignals || []).map(parsePoint).filter(Boolean).sort((a, b) => a.ts - b.ts);
    const activities = (data.semanticSegments || []).flatMap((s, i) => {
      const a = s.activity, c = a?.topCandidate;
      if (c?.type !== 'IN_PASSENGER_VEHICLE' || Number(c.probability || 0) < .8) return [];
      const start = epoch(s.startTime), end = epoch(s.endTime);
      return Number.isFinite(start) && Number.isFinite(end) ? [{ id: `a${i}`, start, end }] : [];
    });
    const runs = [];
    for (const a of activities) {
      const pts = positions.filter(p => p.ts >= a.start && p.ts <= a.end && p.accuracy > 0 && p.accuracy <= 50);
      const dedup = []; for (const p of pts) { if (!dedup.length || p.ts !== dedup[dedup.length - 1].ts || p.accuracy < dedup[dedup.length - 1].accuracy) dedup.push(p); }
      let current = dedup.length ? [dedup[0]] : [];
      const flush = () => { if (current.length >= 4) runs.push(current); };
      for (let i = 1; i < dedup.length; i++) {
        const p = dedup[i], q = dedup[i - 1], gap = p.ts - q.ts;
        if (gap > 120 || (gap > 0 && distanceM(p, q) / gap > 55)) { flush(); current = [p]; } else current.push(p);
      }
      flush();
    }
    const safeRuns = runs.map((run, i) => {
      const trimmed = run.slice(2, -2);
      if (trimmed.length < 2) return null;
      const start = trimmed[0], end = trimmed[trimmed.length - 1], local = localParts(start.ts);
      return { run: `R${String(i + 1).padStart(4, '0')}`, date: local.date, window: local.window, time_bucket: local.bucket, duration_seconds: Math.round(end.ts - start.ts), observation_count: trimmed.length, points: trimmed.map(p => ({ time_bucket: new Date(roundedTime(p.ts) * 1000).toISOString(), lat: roundCoord(p.lat), lon: roundCoord(p.lon) })) };
    }).filter(Boolean);
    const output = { schema_version: 'community-prepared-v1', created_at: new Date().toISOString(), privacy: { coordinate_precision: '0.001 degrees', time_precision: '15 minutes', endpoints_trimmed: true, raw_records_excluded: true }, runs: safeRuns };
    prepareState.prepared = JSON.stringify(output); uploadButton.disabled = false;
    const blob = new Blob([prepareState.prepared], { type: 'application/json' });
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'miami-community-trip-data-prepared.json'; link.click(); URL.revokeObjectURL(link.href);
    result.textContent = `Prepared ${safeRuns.length} privacy-reduced vehicle runs. Review the downloaded file before sharing it. Raw Timeline records never left this browser.`;
  } catch (error) { result.textContent = `The file could not be prepared: ${error.message}`; }
  button.disabled = !(consent.checked && prepareState.file);
});

uploadButton.addEventListener('click', () => {
  if (!prepareState.prepared) return;
  const blob = new Blob([prepareState.prepared], { type: 'application/json' });
  const download = document.createElement('a'); download.href = URL.createObjectURL(blob); download.download = 'miami-community-trip-data-prepared.json'; download.click(); URL.revokeObjectURL(download.href);
  const subject = encodeURIComponent('Miami community trip data');
  const body = encodeURIComponent('I prepared the attached file using the Miami Arterial Evidence Explorer. I understand it contains coarsened trip observations for voluntary research sharing.');
  window.location.href = `mailto:surren83@gmail.com?subject=${subject}&body=${body}`;
  result.hidden = false; result.textContent = 'The prepared file was downloaded and an email draft was opened. Attach the file before sending.';
});
