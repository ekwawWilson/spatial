// Map editing interactions (OpenLayers). Geometry leaves the map as GeoJSON in
// Web Mercator (EPSG:3857); the server converts it to the layer's CRS with the
// platform's operation (geometry_crs), so the map never decides coordinates of
// record on its own.

import type { GeoJSONGeometry } from "@spatial/map-core";
import type OlMap from "ol/Map";
import type Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import type { Geometry } from "ol/geom";
import Draw from "ol/interaction/Draw";
import type Interaction from "ol/interaction/Interaction";
import Modify from "ol/interaction/Modify";
import Select from "ol/interaction/Select";
import Snap from "ol/interaction/Snap";
import Translate from "ol/interaction/Translate";
import { shiftKeyOnly } from "ol/events/condition";
import type BaseLayer from "ol/layer/Base";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";

export type EditMode = "draw" | "modify" | "move" | "delete" | "split" | "select-many";

export interface EditSettings {
  layerId: number;
  geometryType: "point" | "line" | "polygon";
  mode: EditMode;
  /** Snap to these layers' vertices and edges (loaded layers only). */
  snapLayerIds: number[];
  /** Snapping distance in screen pixels. */
  snapTolerance: number;
}

export interface EditCallbacks {
  onDrawn(geometry: GeoJSONGeometry): void;
  onReshaped(featureId: number, geometry: GeoJSONGeometry): void;
  onDeleteRequested(featureId: number): void;
  onSplitLine(geometry: GeoJSONGeometry): void;
  onSelectMany(featureIds: number[]): void;
}

const format = new GeoJSON();

export function toGeoJSON(geometry: Geometry): GeoJSONGeometry {
  return format.writeGeometryObject(geometry) as unknown as GeoJSONGeometry;
}

const DRAW_TYPE = { point: "Point", line: "LineString", polygon: "Polygon" } as const;

function sourceOf(layer: BaseLayer | undefined): VectorSource | null {
  return layer instanceof VectorLayer ? (layer.getSource() as VectorSource) : null;
}

/** Installs the interactions for one editing mode; returns a function that
 * removes them. Returns null (and does nothing) if the layer isn't editable on
 * the map (e.g. a very large layer drawn from tiles). */
export function installEditing(
  map: OlMap,
  layers: Map<number, BaseLayer>,
  settings: EditSettings,
  callbacks: EditCallbacks,
): (() => void) | null {
  const target = layers.get(settings.layerId);
  const source = sourceOf(target);
  if (!source || !(target instanceof VectorLayer)) return null;
  const interactions: Interaction[] = [];
  const scratch = new VectorSource();

  switch (settings.mode) {
    case "draw": {
      const draw = new Draw({ source: scratch, type: DRAW_TYPE[settings.geometryType] });
      draw.on("drawend", (event) => {
        callbacks.onDrawn(toGeoJSON(event.feature.getGeometry()!));
        setTimeout(() => scratch.clear());
      });
      interactions.push(draw);
      break;
    }
    case "split": {
      const draw = new Draw({ source: scratch, type: "LineString" });
      draw.on("drawend", (event) => {
        callbacks.onSplitLine(toGeoJSON(event.feature.getGeometry()!));
        setTimeout(() => scratch.clear());
      });
      interactions.push(draw);
      break;
    }
    case "modify":
    case "move": {
      const select = new Select({ layers: [target] });
      interactions.push(select);
      if (settings.mode === "modify") {
        const modify = new Modify({ features: select.getFeatures() });
        modify.on("modifyend", (event) => {
          for (const feature of event.features.getArray() as Feature<Geometry>[]) {
            callbacks.onReshaped(Number(feature.getId()), toGeoJSON(feature.getGeometry()!));
          }
        });
        interactions.push(modify);
      } else {
        const translate = new Translate({ features: select.getFeatures() });
        translate.on("translateend", (event) => {
          for (const feature of event.features.getArray() as Feature<Geometry>[]) {
            callbacks.onReshaped(Number(feature.getId()), toGeoJSON(feature.getGeometry()!));
          }
        });
        interactions.push(translate);
      }
      break;
    }
    case "delete": {
      const select = new Select({ layers: [target] });
      select.on("select", (event) => {
        const feature = event.selected[0];
        if (feature) callbacks.onDeleteRequested(Number(feature.getId()));
        select.getFeatures().clear();
      });
      interactions.push(select);
      break;
    }
    case "select-many": {
      const select = new Select({ layers: [target], toggleCondition: shiftKeyOnly, multi: true });
      select.on("select", () => {
        callbacks.onSelectMany(select.getFeatures().getArray().map((f) => Number(f.getId())));
      });
      interactions.push(select);
      break;
    }
  }

  // Snap goes last so it sees pointer events before the others.
  const snapSources = [source, ...settings.snapLayerIds.map((id) => sourceOf(layers.get(id)))];
  for (const snapSource of new Set(snapSources)) {
    if (snapSource) interactions.push(new Snap({ source: snapSource, pixelTolerance: settings.snapTolerance }));
  }
  const scratchLayer = new VectorLayer({ source: scratch, zIndex: 9_999 });
  map.addLayer(scratchLayer);
  for (const interaction of interactions) map.addInteraction(interaction);
  return () => {
    for (const interaction of interactions) map.removeInteraction(interaction);
    map.removeLayer(scratchLayer);
  };
}

/** Draws one polygon (e.g. a planning area) and hands it over in EPSG:3857,
 * snapping to the given layers. Returns a function that removes it. */
export function installPolygonDraw(
  map: OlMap,
  layers: Map<number, BaseLayer>,
  snapLayerIds: number[],
  onDrawn: (geometry: GeoJSONGeometry) => void,
): () => void {
  const scratch = new VectorSource();
  const scratchLayer = new VectorLayer({ source: scratch, zIndex: 9_999 });
  const draw = new Draw({ source: scratch, type: "Polygon" });
  draw.on("drawend", (event) => {
    onDrawn(toGeoJSON(event.feature.getGeometry()!));
    setTimeout(() => scratch.clear());
  });
  const snaps = snapLayerIds
    .map((id) => sourceOf(layers.get(id)))
    .filter((s): s is VectorSource => s !== null)
    .map((source) => new Snap({ source, pixelTolerance: 10 }));
  map.addLayer(scratchLayer);
  map.addInteraction(draw);
  for (const snap of snaps) map.addInteraction(snap);
  return () => {
    map.removeInteraction(draw);
    for (const snap of snaps) map.removeInteraction(snap);
    map.removeLayer(scratchLayer);
  };
}
