# Basemaps

A basemap is the background map under your layers: streets, satellite imagery, or your district's own aerial photos.

## Choosing a basemap in a project
In a project, the **Basemap** box at the top of the layer panel lists what's available. Pick one, or **None**, and set its opacity with the slider. Your choice is remembered for that project on this device.

If a basemap can't be shown (for example, its API key is missing or no longer valid), a message appears under the list instead of a blank map. Ask your district administrator to fix the key on the **Basemaps** page.

## Managing basemaps (district and system administrators)
Open **Basemaps**.

**Ready-made basemaps:**
| Provider | Key needed | Notes |
|---|---|---|
| OpenStreetMap | no | available from the start |
| Esri World Imagery | no | available from the start |
| Google Maps (roadmap or satellite) | yes | Map Tiles API key from Google Cloud |
| Bing Maps (aerial) | yes | **deprecated**: Bing Maps for Enterprise is being retired and free keys have ended |

**Your own basemap:** add an XYZ, WMS or WMTS service, for example the district's own imagery server.

**API keys** are stored encrypted, can't be viewed once saved, and are never shown in the app. Use **Add key** or **Replace key** to change one. For Google keys, restrict the key to this site's address in Google Cloud, because browsers that show the map can see it.

## Offline use (field devices)
Field devices (from Phase 9) can store basemap tiles for offline work, **but only for sources whose licence allows it**:
- OpenStreetMap, Esri, Google and Bing tiles **may not** be stored offline under their terms, and the platform refuses to package them.
- For your own imagery (e.g. a drone survey) or imagery licensed for offline use, tick "We own this imagery or its licence allows offline use" when adding it.
