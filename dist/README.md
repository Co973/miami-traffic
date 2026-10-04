# Miami Arterial Evidence Explorer

This is a static site. Upload the contents of `dist/` to any static host.

The private Timeline export is not included. The published bundle contains only sanitized aggregate results, coarsened corridor geometry, county signal context, and methodology metadata.

To rebuild after changing the source export:

```powershell
python work/build_explorer.py
Copy-Item outputs/miami-explorer/* dist -Force
```

The current analysis uses repeated spatial cells from the Timeline export, matches corridor endpoints to the supplied TIGER/Line 2023 Miami-Dade road geometry, enriches those corridors with nearby county signal labels, and attaches matching FDOT TMS hourly count summaries where available. StreetNetwork and MajorRoads are used as inventory context. The dashboard calculates a conditional annual person-time value only when a supported GPS comparison and matched TMS volume both exist. The published geometry remains coarsened for privacy.
