// Vector tile loading through the authenticated API (tiles are district data).

import type { Tile } from "ol";
import type { FeatureLike } from "ol/Feature";
import type VectorTile from "ol/VectorTile";
import MVT from "ol/format/MVT";
import TileState from "ol/TileState";

import type { ApiClient } from "./api";

/** An OpenLayers tileLoadFunction that fetches tiles with the user's token and
 * district header; empty tiles (HTTP 204) load as no features. */
export function authenticatedTileLoader(api: Pick<ApiClient, "fetchTile">, layerId: number) {
  const format = new MVT();
  return (tile: Tile) => {
    const vectorTile = tile as VectorTile<FeatureLike>;
    const [z, x, y] = vectorTile.getTileCoord();
    vectorTile.setLoader(async (extent, _resolution, projection) => {
      try {
        const data = await api.fetchTile(layerId, z!, x!, y!);
        if (!data) return [];
        return format.readFeatures(data, { extent, featureProjection: projection });
      } catch {
        vectorTile.setState(TileState.ERROR);
        return [];
      }
    });
  };
}
