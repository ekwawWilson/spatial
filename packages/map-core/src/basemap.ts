// Basemap configs -> OpenLayers tile sources.

import type { Options as WMTSOptions } from "ol/source/WMTS";
import BingMaps from "ol/source/BingMaps";
import type TileSource from "ol/source/Tile";
import TileWMS from "ol/source/TileWMS";
import WMTS, { optionsFromCapabilities } from "ol/source/WMTS";
import XYZ from "ol/source/XYZ";
import WMTSCapabilities from "ol/format/WMTSCapabilities";

import type { BasemapConfig } from "./types";

/** Builds the OpenLayers source for a basemap. WMTS needs its capabilities
 * document, fetched here; the other kinds are built directly. */
export async function basemapSource(config: BasemapConfig, fetchImpl: typeof fetch = fetch): Promise<TileSource> {
  const attributions = config.attribution ? [config.attribution] : undefined;
  switch (config.kind) {
    case "xyz":
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
