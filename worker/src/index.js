const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS'
};

function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json' } });
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return response({ error: 'POST prepared community data only.' }, 405);
    let payload;
    try { payload = await request.json(); } catch (_) { return response({ error: 'Invalid JSON.' }, 400); }
    if (payload?.schema_version !== 'community-prepared-v1' || !Array.isArray(payload.runs) || payload.runs.length > 500) return response({ error: 'Unsupported or oversized prepared dataset.' }, 400);
    const submission = crypto.randomUUID();
    const received = new Date().toISOString();
    const statements = [];
    for (const run of payload.runs) {
      if (!run || !['AM', 'Midday', 'PM', 'Other'].includes(run.window)) continue;
      if (!Number.isFinite(run.duration_seconds) || run.duration_seconds < 1 || run.duration_seconds > 86400) continue;
      if (!Number.isFinite(run.observation_count) || run.observation_count < 2 || !Array.isArray(run.points) || run.points.length > 500) continue;
      // Store only the already-coarsened points. Raw Timeline fields are rejected by schema.
      statements.push(env.DB.prepare('INSERT INTO community_runs (submission_id, month, window, duration_seconds, observation_count, points_json, received_at) VALUES (?, ?, ?, ?, ?, ?, ?)').bind(submission, String(run.date || '').slice(0, 7), run.window, Math.round(run.duration_seconds), Math.round(run.observation_count), JSON.stringify(run.points), received));
    }
    if (!statements.length) return response({ error: 'No valid prepared runs found.' }, 400);
    await env.DB.batch(statements);
    return response({ accepted_runs: statements.length, submission_id: submission });
  }
};
