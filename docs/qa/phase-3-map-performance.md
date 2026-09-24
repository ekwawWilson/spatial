# QA: Phase 3 map performance with 100,000 features

**Status:** not yet run (needs a machine with Docker).

The automated gate (`projects/tests/test_projects.py::test_tiles_for_a_100k_feature_layer_are_fast`) times tile responses. This manual check confirms panning feels smooth in a real browser.

## Steps
1. `make up seed`, then sign in as `sma.planner@example.test`.
2. Create a project, add a polygon layer, and load 100k features. The simplest way is the SQL from the automated test, run in `docker compose exec db psql`, using the new layer's id and the district id.
3. Open the project, zoom to the layer, and pan and zoom between levels 14 and 18 for a minute.

## Record
| Date | Tester | Browser / machine | Tile times seen (DevTools) | Smooth? | Notes |
|---|---|---|---|---|---|
| | | | | | |
