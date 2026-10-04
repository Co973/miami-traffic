# Miami Arterial Evidence Explorer

Static GitHub Pages site for a student-led Miami-Dade traffic evidence project.

The site uses a sanitized bundle generated from one private Google Timeline export and supplied public/county transportation data. It highlights repeated sampled travel-time differences and adds signal, road, FDOT count, and county count-station context.

The result is a screening tool. It does not measure countywide congestion, represent all drivers, identify a signal fault, or guarantee treatment benefits.

## GitHub Pages

The deployable site is in the repository root. Enable **Settings → Pages → GitHub Actions**. Pushing to `main` runs `.github/workflows/pages.yml` and publishes the page at the repository's GitHub Pages URL.

The root contains only the sanitized static dataset and site assets. The private Timeline export and raw coordinate records are not included.

The **Send us your data** page is a transparency-first local preparation tool. It never uploads a raw Timeline export. A participant can review the privacy-reduced file before choosing whether to share it through a future intake process.

The automatic-upload contract is in `worker/`. GitHub Pages is the public front end; the optional private Cloudflare Worker and D1 database receive only the prepared schema. Set the deployed Worker URL in `config.js` before enabling collection.

## Local rebuild

The analysis script is in `work/build_explorer.py`. It expects the source exports at the local paths used during analysis and writes the sanitized bundle to `outputs/miami-explorer/`. To refresh the static site locally:

```powershell
python work/build_explorer.py
Copy-Item -Path outputs/miami-explorer/* -Destination . -Force
```

Do not commit private source exports. Review `FINAL_READOUT.md` before presenting results to the county.
