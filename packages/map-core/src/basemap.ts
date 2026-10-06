// Basemap configs -> OpenLayers tile sources.

import type { Options as WMTSOptions } from "ol/source/WMTS";
import BingMaps from "ol/source/BingMaps";
import type ImageTile from "ol/ImageTile";
import TileState from "ol/TileState";
import type TileSource from "ol/source/Tile";
import TileWMS from "ol/source/TileWMS";
import WMTS, { optionsFromCapabilities } from "ol/source/WMTS";
import XYZ from "ol/source/XYZ";
import WMTSCapabilities from "ol/format/WMTSCapabilities";

import type { BasemapConfig } from "./types";

/** A transparent 1x1 image, for tiles outside the imagery. */
const EMPTY_TILE = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

/** Tiles served by this platform's API (the district's own imagery), not an outside service. */
export function isOwnImagery(url: string): boolean {
  return url.startsWith("/api/imagery/");
}

/** Builds the OpenLayers source for a basemap. WMTS needs its capabilities
 * document, fetched here; the other kinds are built directly. */
export async function basemapSource(
  config: BasemapConfig,
  fetchImpl: typeof fetch = fetch,
  /** Loads a tile of the platform's own imagery (which needs the user's sign-in); null for an empty tile. */
  loadOwnTile?: (path: string) => Promise<Blob | null>,
): Promise<TileSource> {
  const attributions = config.attribution ? [config.attribution] : undefined;
  switch (config.kind) {
    case "xyz":
      if (isOwnImagery(config.url) && loadOwnTile) {
        return new XYZ({
          url: config.url,
          attributions,
          minZoom: config.min_zoom,
          // Past the image's own detail the map stretches the last zoom level.
          maxZoom: config.max_zoom,
          tileLoadFunction: (tile, src) => {
            const image = (tile as ImageTile).getImage() as HTMLImageElement;
            loadOwnTile(new URL(src, "http://local").pathname)
              .then((blob) => {
                if (!blob) {
                  image.src = EMPTY_TILE;
                  return;
                }
                const url = URL.createObjectURL(blob);
                image.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
                image.src = url;
              })
              .catch(() => tile.setState(TileState.ERROR));
          },
        });
      }
      return new XYZ({ url: config.url, attributions, minZoom: config.min_zoom, maxZoom: config.max_zoom, crossOrigin: "anonymous" });
    case "wms":
      return new TileWMS({ url: config.url, params: { LAYERS: config.layers, TILED: true }, attributions, crossOrigin: "anonymous" });
    case "bing":
      return new BingMaps({ key: config.key ?? "", imagerySet: config.layers || "Aerial", maxZoom: config.max_zoom });
    case "wmts": {
      const response = await fetchImpl(config.url);
      if (!response.ok) throw new Error(`Couldn't read the WMTS capabilities (HTTP ${response.status}).`);
      const capabilities = new WMTSCapabilities().read(await response.text());
      const options = optionsFromCapabilities(capabilities, { layer: config.layers });
      if (!options) throw new Error(`The WMTS service has no layer called "${config.layers}".`);
      return new WMTS({ ...(options as WMTSOptions), attributions, crossOrigin: "anonymous" });
    }
  }
}
