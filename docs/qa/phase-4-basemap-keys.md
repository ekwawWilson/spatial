# QA: Phase 4 basemaps with real provider keys

**Status:** not yet run. Needs real Google Map Tiles API and Bing keys.

## Steps
1. On **Basemaps**, add *Google Maps (satellite)* with a valid key, then open a project and choose it: satellite tiles appear.
2. Replace the key with an invalid one (e.g. change a character): the project shows "Google rejected the API key…".
3. Remove the key: the project shows "…needs an API key".
4. Repeat 1–3 for *Google Maps (roadmap)*, and for *Bing Maps (aerial)* if a key is still available.
5. Add a WMS or WMTS service you know (e.g. a national mapping agency's): tiles appear aligned with OSM.

## Record
| Date | Tester | Provider | Result | Notes |
|---|---|---|---|---|
| | | | | |
