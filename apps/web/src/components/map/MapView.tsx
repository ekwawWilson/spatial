import "ol/ol.css";

import { authenticatedTileLoader, olStyleFunction, type ApiClient, type Layer } from "@spatial/map-core";
import OlMap from "ol/Map";
import View from "ol/View";
import { Attribution, Rotate, ScaleLine, Zoom } from "ol/control";
import type { Extent } from "ol/extent";
import GeoJSON from "ol/format/GeoJSON";
import type { Geometry } from "ol/geom";
import { LineString, Polygon } from "ol/geom";
import Draw from "ol/interaction/Draw";
import BaseLayer from "ol/layer/Base";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorTileLayer from "ol/layer/VectorTile";
import { transformExtent } from "ol/proj";
import OSM from "ol/source/OSM";
import VectorSource from "ol/source/Vector";
import VectorTileSource from "ol/source/VectorTile";
import { getArea, getLength } from "ol/sphere";
import { Stroke, Style } from "ol/style";
import { useEffect, useRef } from "react";

/** Layers with more features than this are drawn from vector tiles. */
export const GEOJSON_LIMIT = 2000;
/** Tiled layers appear from street level (see the Phase 3 tile performance gate). */
export const TILE_MIN_ZOOM = 14;

export type Tool = "identify" | "measure-length" | "measure-area";

export interface Measurement {
  kind: "length" | "area";
  value: number; // metres or square metres
}

export interface MapViewProps {
  api: ApiClient;
  layers: Layer[];
  /** Increment to reload feature data (e.g. after an edit). */
  dataVersion: number;
  selected: { layerId: number; featureId: number } | null;
  tool: Tool;
  onSelect(selection: { layerId: number; featureId: number } | null): void;
  onMeasure(measurement: Measurement | null): void;
  /** Pointer position in Web Mercator, or null when off the map. */
  onPointer(position: [number, number] | null): void;
  /** Zoom to this WGS 84 extent when it changes. */
  zoomTo: { extent: number[]; seq: number } | null;
}

const GHANA_CENTRE_3857: [number, number] = [-133_000, 870_000];

export function MapView(props: MapViewProps) {
  const target = useRef<HTMLDivElement>(null);
  const map = useRef<OlMap | null>(null);
  const layerById = useRef(new Map<number, BaseLayer>());
  const measureSource = useRef(new VectorSource());
  const latest = useRef(props);
  latest.current = props;

  // Create the map once.
  useEffect(() => {
    if (!target.current) return;
    const measureLayer = new VectorLayer({
      source: measureSource.current,
      zIndex: 10_000,
      style: new Style({ stroke: new Stroke({ color: "#e4572e", width: 2, lineDash: [6, 4] }) }),
    });
    const olMap = new OlMap({
      target: target.current,
      layers: [new TileLayer({ source: new OSM(), zIndex: -1 }), measureLayer],
      view: new View({ center: GHANA_CENTRE_3857, zoom: 7 }),
      controls: [new Zoom(), new Rotate({ autoHide: false, tipLabel: "Reset north" }), new ScaleLine(), new Attribution()],
    });
    olMap.on("singleclick", (event) => {
      if (latest.current.tool !== "identify") return;
      let hit: { layerId: number; featureId: number } | null = null;
      olMap.forEachFeatureAtPixel(event.pixel, (feature, layer) => {
        const layerId = layer?.get("layerId") as number | undefined;
        const featureId = feature.getId();
        if (layerId !== undefined && featureId !== undefined) {
          hit = { layerId, featureId: Number(featureId) };
          return true;
        }
        return false;
      });
      latest.current.onSelect(hit);
    });
    olMap.on("pointermove", (event) => {
      latest.current.onPointer([event.coordinate[0]!, event.coordinate[1]!]);
    });
    target.current.addEventListener("mouseleave", () => latest.current.onPointer(null));
    map.current = olMap;
    return () => {
      olMap.setTarget(undefined);
      map.current = null;
    };
  }, []);

  // Keep the app's layers in sync: add, update, remove.
  useEffect(() => {
    const olMap = map.current;
    if (!olMap) return;
    const wanted = new Set(props.layers.map((l) => l.id));
    for (const [id, olLayer] of layerById.current) {
      if (!wanted.has(id)) {
        olMap.removeLayer(olLayer);
        layerById.current.delete(id);
      }
    }
    for (const layer of props.layers) {
      const tiled = layer.feature_count > GEOJSON_LIMIT;
      let olLayer = layerById.current.get(layer.id);
      if (olLayer && olLayer.get("tiled") !== tiled) {
        olMap.removeLayer(olLayer);
        olLayer = undefined;
      }
      if (!olLayer) {
        olLayer = tiled ? tiledLayer(props.api, layer) : geojsonLayer(layer);
        olLayer.set("layerId", layer.id);
        olLayer.set("tiled", tiled);
        layerById.current.set(layer.id, olLayer);
        olMap.addLayer(olLayer);
      }
      olLayer.setVisible(layer.visible);
      olLayer.setOpacity(layer.opacity);
      olLayer.setZIndex(layer.order);
      const selectedId = props.selected?.layerId === layer.id ? props.selected.featureId : null;
      (olLayer as VectorLayer | VectorTileLayer).setStyle(
        olStyleFunction(layer.style, (id) => selectedId !== null && Number(id) === selectedId),
      );
    }
  }, [props.api, props.layers, props.selected]);

  // (Re)load GeoJSON-backed layers when their data may have changed.
  useEffect(() => {
    for (const layer of props.layers) {
      const olLayer = layerById.current.get(layer.id);
      if (!olLayer || olLayer.get("tiled")) {
        const source = (olLayer as VectorTileLayer | undefined)?.getSource();
        source?.refresh();
        continue;
      }
      const source = (olLayer as VectorLayer).getSource() as VectorSource<import("ol/Feature").default<Geometry>>;
      props.api
        .listFeatures(layer.id, { limit: GEOJSON_LIMIT })
        .then((page) => {
          const features = new GeoJSON().readFeatures(page, { featureProjection: "EPSG:3857" });
          source.clear();
          source.addFeatures(features);
        })
        .catch(() => source.clear());
    }
  }, [props.api, props.layers, props.dataVersion]);

  // Measuring tools.
  useEffect(() => {
    const olMap = map.current;
    if (!olMap || props.tool === "identify") return;
    measureSource.current.clear();
    props.onMeasure(null);
    const draw = new Draw({ source: measureSource.current, type: props.tool === "measure-length" ? "LineString" : "Polygon" });
    draw.on("drawstart", () => measureSource.current.clear());
    draw.on("drawend", (event) => {
      const geometry = event.feature.getGeometry();
      if (geometry instanceof LineString) latest.current.onMeasure({ kind: "length", value: getLength(geometry) });
      if (geometry instanceof Polygon) latest.current.onMeasure({ kind: "area", value: getArea(geometry) });
    });
    olMap.addInteraction(draw);
    return () => {
      olMap.removeInteraction(draw);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.tool]);

  useEffect(() => {
    const olMap = map.current;
    if (!olMap || !props.zoomTo) return;
    const extent = transformExtent(props.zoomTo.extent as Extent, "EPSG:4326", "EPSG:3857");
    olMap.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 19, duration: 300 });
  }, [props.zoomTo]);

  return <div ref={target} className="map" role="application" aria-label="Map" />;
}

function geojsonLayer(layer: Layer): VectorLayer {
  return new VectorLayer({ source: new VectorSource(), style: olStyleFunction(layer.style) });
}

function tiledLayer(api: ApiClient, layer: Layer): VectorTileLayer {
  return new VectorTileLayer({
    minZoom: TILE_MIN_ZOOM,
    source: new VectorTileSource({ tileLoadFunction: authenticatedTileLoader(api, layer.id), url: `layer-${layer.id}/{z}/{x}/{y}` }),
    style: olStyleFunction(layer.style),
  });
}
