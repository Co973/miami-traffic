# Community intake endpoint

GitHub Pages cannot receive uploads. This optional Cloudflare Worker provides the private endpoint used by `send-data.html`.

The browser first creates `community-prepared-v1`. The Worker accepts that schema, validates each run, and stores only the coarsened points and corridor timing fields in a private D1 database. It rejects raw Timeline fields, oversized submissions, invalid windows, and invalid durations.

## Deployment outline

1. Create a Cloudflare D1 database named `miami-community-data`.
2. Put its ID in `wrangler.toml`.
3. Apply `schema.sql` with Wrangler.
4. Deploy the Worker.
5. Set `window.COMMUNITY_UPLOAD_ENDPOINT` in the hosted page to the Worker URL.

Do not publish the D1 database. Add a retention and deletion process before collecting community submissions. The public dashboard should consume only aggregate results that meet minimum sample and day thresholds.
