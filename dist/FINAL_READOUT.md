# Miami Arterial Evidence Explorer — final readout

## What the finished version gives the county

The tool is a static, locally processed evidence explorer built from one supplied Google Timeline export and public or county-provided transportation data. It identifies repeated sampled road segments, compares the sampled driver's AM or PM travel time with the sampled midday travel time when the minimum counts are met, and displays nearby signals, road inventory, FDOT traffic counts, and county count-station context.

It is a screening tool for deciding where staff might investigate. It is not a countywide congestion study, a signal-performance study, or a representative estimate of all drivers' travel times.

## Final input audit

- 1,098 semantic segments
- 66,834 raw signals
- 14,485 usable position records parsed
- 176 vehicle activity segments
- 42 qualified continuous GPS runs
- 123 activities rejected for too few usable positions
- 11 activities retained only in the audit because activity confidence was below the primary threshold
- 40 candidate repeated corridors
- 12 corridors published in the explorer
- 6,037 supplied traffic-signal records
- 184,057 FDOT TMS records, including 8,107 Miami-Dade records and 26 site-direction groups
- 424 county count stations, including 284 with 2019 AADT
- 116,397 StreetNetwork rows and 825 MajorRoads names
- TIGER/Line 2023 Miami-Dade road geometry for endpoint context

The raw GPS coverage runs from September 4 through October 4, 2026. The semantic history contains the broader July 6–October 4 period, but the measurement analysis uses the raw positions.

## Supported findings

### C01 — SW 77th Avenue

- 6 accepted traversals across 4 days
- AM sample: 3 traversals
- Midday sample: 3 traversals
- Observed AM–midday median difference: **113 seconds**
- Median traversal time: 243.5 seconds

### C02 — SW 77th Avenue / Dadeland area

- 4 accepted traversals across 4 days
- AM sample: 2 traversals
- Midday sample: 2 traversals
- Observed AM–midday median difference: **48.5 seconds**
- Median traversal time: 133.5 seconds

These are the only two headline findings in the current dataset. They are descriptive differences in one driver's sampled trips. They do not prove removable congestion, a signal fault, or a treatment benefit.

## Exploratory corridors

The remaining published corridors have repeated observations but do not meet the current comparison requirement for both a peak and midday sample. They remain visible so the county can see evidence gaps rather than mistaking missing comparisons for zero delay.

The most useful exploratory locations include Palmetto Expressway near Bird Road, SW 8th Street/Tamiami Trail, SW 16th Street, SW 112th Avenue, SW 92nd Avenue, and SW 12th Street.

## What the supporting data adds

- Signal points identify nearby intersections worth checking. The file does not include signal timing plans, phases, offsets, or queue observations.
- FDOT TMS data supplies hourly count context at matched locations. It is the only count source used for conditional peak-window scenario arithmetic.
- County count-station data supplies nearby 2019 AADT context. AADT is an annual average and is not used as directional peak traffic.
- StreetNetwork, MajorRoads, and TIGER geometry improve road labels and context. They do not convert the personal traces into a representative traffic sample.
- GTFS data is available for a later SUMO or transit scenario model, but it is not treated as observed automobile traffic in this release.

## What a council presentation can responsibly say

“This student-led tool found two repeated locations where the sampled driver's morning travel time was higher than the sampled midday travel time. It combines those observations with county signal and traffic-count context to identify locations for engineering review. The results are a screening signal, not a countywide congestion estimate or a prediction of project benefits.”

## What remains unsupported

- Countywide congestion levels
- Actual signal coordination or phase failure
- Queue lengths or turn movements
- Causal explanations for the observed differences
- Representative traffic volumes for every corridor
- Guaranteed travel-time savings from a proposed treatment
- Annual benefit-cost ratios without externally supplied and defensible assumptions

## Hosting

Upload the contents of `dist/` to any static host. The private Timeline file and private evidence records are not included. The portable package is `miami-explorer-portable.tar.gz`.
