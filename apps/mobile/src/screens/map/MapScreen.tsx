import { Camera, GeoJSONSource, Layer, Map as MapLibreMap, RasterSource, type CameraRef, type MapRef } from "@maplibre/maplibre-react-native";
import { useFocusEffect } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import * as Network from "expo-network";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { Button, Checkbox, IconButton, Modal, Portal, SegmentedButtons } from "react-native-paper";

import { errorText, Notice, styles as ui } from "../../components/ui";
import { colors } from "../../constants/colors";
import { APP_CONFIG } from "../../constants/config";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import { getFeature, getProject, listFeatures, listLayers, setLayerVisible } from "../../services/db";
import { watchFixes } from "../../services/gps";
import type { CaptureMethod, Fix, LocalFeature, LocalLayer, LocalProject, Position } from "../../types";
import { formatPosition } from "../../utils/crs";
import { averageFixes, bounds, buildGeometry, extendTrack, formatArea, formatDistance, pathLength, positions, ringArea, usable } from "../../utils/geo";
import { labelOf } from "../../utils/forms";
import { paintFor } from "../../utils/mapStyle";

type Props = NativeStackScreenProps<RootStackParamList, "Map">;

type Mode =
  | { kind: "browse" }
  | { kind: "measure"; shape: "distance" | "area" }
  | { kind: "pick-layer" }
  | { kind: "pick-method"; layer: LocalLayer }
  | { kind: "gps-point"; layer: LocalLayer }
  | { kind: "gps-track"; layer: LocalLayer; walking: boolean }
  | { kind: "draw"; layer: LocalLayer };

const BLANK_STYLE = {
  version: 8 as const,
  sources: {},
  layers: [{ id: "background", type: "background" as const, paint: { "background-color": colors.mapBackground } }],
};

type Collection = GeoJSON.FeatureCollection;

function collection(features: LocalFeature[]): Collection {
  return {
    type: "FeatureCollection",
    features: features.map((f) => ({
      type: "Feature",
      id: f.localId,
      geometry: f.geometry as GeoJSON.Geometry,
      properties: { ...f.properties, __uuid: f.uuid, __state: f.state },
    })),
  };
}

function sketch(points: Position[], closed: boolean): Collection {
  const features: GeoJSON.Feature[] = points.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: p }, properties: {} }));
  if (points.length >= 2) {
    const line = closed && points.length >= 3 ? [...points, points[0]!] : points;
    features.push({ type: "Feature", geometry: { type: "LineString", coordinates: line }, properties: {} });
  }
  return { type: "FeatureCollection", features };
}

export default function MapScreen({ navigation, route }: Props) {
  const { projectId } = route.params;
  const mapRef = useRef<MapRef>(null);
  const cameraRef = useRef<CameraRef>(null);
  const [project, setProject] = useState<LocalProject | null>(null);
  const [layers, setLayers] = useState<LocalLayer[]>([]);
  const [data, setData] = useState<Record<number, LocalFeature[]>>({});
  const [mode, setMode] = useState<Mode>({ kind: "browse" });
  const [points, setPoints] = useState<Position[]>([]); // measuring or drawing
  const [fixes, setFixes] = useState<Fix[]>([]); // readings for a GPS point
  const [track, setTrack] = useState<Fix[]>([]); // a walked line or area
  const [lastFix, setLastFix] = useState<Fix | null>(null);
  const [selected, setSelected] = useState<LocalFeature | null>(null);
  const [showLayers, setShowLayers] = useState(false);
  const [online, setOnline] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const p = await getProject(projectId);
      const ls = await listLayers(projectId);
      const rows: Record<number, LocalFeature[]> = {};
      for (const layer of ls) rows[layer.id] = await listFeatures(layer.id);
      setProject(p);
      setLayers(ls);
      setData(rows);
      if (p) navigation.setOptions({ title: p.name });
    } catch (err) {
      setError(errorText(err));
    }
  }, [navigation, projectId]);

  // Reload when coming back from the form, so a new capture appears.
  useFocusEffect(
    useCallback(() => {
      void reload();
      void Network.getNetworkStateAsync().then((state) => setOnline(Boolean(state.isInternetReachable ?? state.isConnected)));
    }, [reload]),
  );

  // GPS runs only while a GPS capture is on screen.
  const gpsWanted = mode.kind === "gps-point" || mode.kind === "gps-track";
  const walking = mode.kind === "gps-track" && mode.walking;
  const modeRef = useRef({ kind: mode.kind, walking });
  modeRef.current = { kind: mode.kind, walking };
  useEffect(() => {
    if (!gpsWanted) return;
    let stop: (() => void) | null = null;
    let cancelled = false;
    watchFixes(
      (fix) => {
        setLastFix(fix);
        if (modeRef.current.kind === "gps-point") {
          setFixes((all) => (all.length >= APP_CONFIG.defaultAveraging ? all : [...all, fix]));
        } else if (modeRef.current.walking) {
          setTrack((all) => extendTrack(all, fix, APP_CONFIG.trackMinDistance, APP_CONFIG.maxUsableAccuracy));
        }
      },
      (message) => setError(message),
    )
      .then((remove) => {
        if (cancelled) remove();
        else stop = remove;
      })
      .catch((err: unknown) => {
        setError(errorText(err));
        setMode({ kind: "browse" });
      });
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [gpsWanted]);

  const collections = useMemo(() => {
    const result: Record<number, Collection> = {};
    for (const layer of layers) result[layer.id] = collection(data[layer.id] ?? []);
    return result;
  }, [layers, data]);

  const initialBounds = useMemo(() => {
    if (project?.bbox) return project.bbox;
    return bounds(Object.values(data).flat().flatMap((f) => positions(f.geometry)));
  }, [project, data]);

  function reset() {
    setMode({ kind: "browse" });
    setPoints([]);
    setFixes([]);
    setTrack([]);
    setError(null);
  }

  async function identify(point: [number, number]) {
    const map = mapRef.current;
    if (!map) return;
    const ids = layers.filter((l) => l.visible).flatMap((l) => [`fill-${l.id}`, `line-${l.id}`, `circle-${l.id}`]);
    const hits = await map.queryRenderedFeatures(
      [
        [point[0] - 16, point[1] - 16],
        [point[0] + 16, point[1] + 16],
      ],
      { layers: ids },
    );
    const uuid = hits.map((h) => h.properties?.__uuid as string | undefined).find(Boolean);
    setSelected(uuid ? await getFeature(uuid) : null);
  }

  function finish(layer: LocalLayer, vertices: Position[], method: CaptureMethod, accuracyM: number | null, fixTime: number | null, readings: number | null) {
    const built = buildGeometry(layer.geometryType, vertices);
    if ("problem" in built) {
      setError(built.problem);
      return;
    }
    reset();
    navigation.navigate("CaptureForm", {
      mode: "new",
      projectId,
      layerId: layer.id,
      geometry: built.geometry,
      method,
      accuracyM,
      fixTime: fixTime === null ? null : new Date(fixTime).toISOString(),
      readings,
    });
  }

  if (!project) {
    return <View style={ui.screen}>{error ? <Notice kind="error">{error}</Notice> : <Text style={{ padding: 16 }}>Loading…</Text>}</View>;
  }

  const average = mode.kind === "gps-point" ? averageFixes(fixes, APP_CONFIG.maxUsableAccuracy) : null;
  const trackPoints: Position[] = track.map((f) => [f.longitude, f.latitude]);
  const drawing = mode.kind === "draw" || mode.kind === "measure";
  const sketchPoints = mode.kind === "gps-track" ? trackPoints : drawing ? points : [];
  const sketchClosed =
    (mode.kind === "measure" && mode.shape === "area") ||
    ((mode.kind === "draw" || mode.kind === "gps-track") && mode.layer.geometryType === "polygon");
  const editableLayers = layers.filter((l) => l.name !== "Planning area");
  const basemapUrl = project.basemapPath ? `mbtiles://${project.basemapPath.replace(/^file:\/\//, "")}` : null;

  return (
    <View style={ui.screen}>
      <MapLibreMap
        ref={mapRef}
        style={{ flex: 1 }}
        mapStyle={BLANK_STYLE}
        attribution={false}
        logo={false}
        compass
        scaleBar
        onPress={(event) => {
          const { lngLat, point } = event.nativeEvent;
          if (drawing) setPoints((all) => [...all, [lngLat[0], lngLat[1]]]);
          else if (mode.kind === "browse") void identify([point[0], point[1]]);
        }}
      >
        <Camera ref={cameraRef} initialViewState={initialBounds ? { bounds: initialBounds, padding: { top: 60, right: 40, bottom: 160, left: 40 } } : { center: [-1.2, 7.9], zoom: 5 }} />

        {/* Online only: shown when there is a connection and no offline basemap. Its terms forbid storing it. */}
        {online && !basemapUrl && (
          <RasterSource id="osm" tiles={["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]} tileSize={256} maxzoom={19} attribution="© OpenStreetMap contributors">
            <Layer id="osm-tiles" type="raster" />
          </RasterSource>
        )}
        {basemapUrl && (
          <RasterSource id="offline-basemap" url={basemapUrl} tileSize={256}>
            <Layer id="offline-basemap-tiles" type="raster" />
          </RasterSource>
        )}

        {project.boundary && (
          <GeoJSONSource id="planning-area" data={{ type: "Feature", geometry: project.boundary as GeoJSON.Geometry, properties: {} }}>
            <Layer id="planning-area-line" type="line" paint={{ "line-color": colors.accent, "line-width": 3, "line-dasharray": [2, 1] }} />
          </GeoJSONSource>
        )}

        {[...layers].reverse().map((layer) => {
          if (!layer.visible) return null;
          const paint = paintFor(layer.geometryType, layer.style);
          return (
            <GeoJSONSource key={layer.id} id={`layer-${layer.id}`} data={collections[layer.id] ?? { type: "FeatureCollection", features: [] }}>
              {paint.fill && <Layer id={`fill-${layer.id}`} type="fill" paint={paint.fill as never} />}
              {paint.line && <Layer id={`line-${layer.id}`} type="line" paint={paint.line as never} />}
              {paint.circle && <Layer id={`circle-${layer.id}`} type="circle" paint={paint.circle as never} />}
            </GeoJSONSource>
          );
        })}

        {selected && (
          <GeoJSONSource id="selected" data={{ type: "Feature", geometry: selected.geometry as GeoJSON.Geometry, properties: {} }}>
            <Layer id="selected-line" type="line" paint={{ "line-color": "#ffd400", "line-width": 4 }} />
            <Layer id="selected-point" type="circle" filter={["==", ["geometry-type"], "Point"]} paint={{ "circle-radius": 9, "circle-color": "#ffd400", "circle-opacity": 0.6 }} />
          </GeoJSONSource>
        )}

        <GeoJSONSource id="sketch" data={sketch(sketchPoints, sketchClosed)}>
          <Layer id="sketch-line" type="line" paint={{ "line-color": colors.accent, "line-width": 2.5 }} />
          <Layer id="sketch-points" type="circle" filter={["==", ["geometry-type"], "Point"]} paint={{ "circle-radius": 4, "circle-color": "#ffffff", "circle-stroke-color": colors.accent, "circle-stroke-width": 2 }} />
        </GeoJSONSource>

        {gpsWanted && lastFix && (
          <GeoJSONSource id="gps" data={{ type: "Feature", geometry: { type: "Point", coordinates: [lastFix.longitude, lastFix.latitude] }, properties: {} }}>
            <Layer id="gps-dot" type="circle" paint={{ "circle-radius": 7, "circle-color": "#1a73e8", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 }} />
          </GeoJSONSource>
        )}
      </MapLibreMap>

      <View style={local.topRight}>
        <IconButton mode="contained" icon="layers" accessibilityLabel="Layers" onPress={() => setShowLayers(true)} />
        <IconButton mode="contained" icon="format-list-bulleted" accessibilityLabel="Captured on this device" onPress={() => navigation.navigate("Captured", { projectId })} />
        <IconButton mode="contained" icon="clipboard-check-outline" accessibilityLabel="Features to check on the ground" onPress={() => navigation.navigate("Tasks", { projectId })} />
        {gpsWanted && lastFix && (
          <IconButton mode="contained" icon="crosshairs-gps" accessibilityLabel="Centre on my position" onPress={() => cameraRef.current?.easeTo({ center: [lastFix.longitude, lastFix.latitude], zoom: 18, duration: 400 })} />
        )}
      </View>

      <View style={local.panel}>
        {error && <Notice kind="error">{error}</Notice>}

        {mode.kind === "browse" && !selected && (
          <View style={ui.row}>
            <Button mode="contained" icon="plus" disabled={editableLayers.length === 0} onPress={() => setMode({ kind: "pick-layer" })}>
              Capture
            </Button>
            <Button mode="contained-tonal" icon="ruler" onPress={() => setMode({ kind: "measure", shape: "distance" })}>
              Measure
            </Button>
            <Text style={ui.muted}>Tap a feature to see its details.</Text>
          </View>
        )}

        {mode.kind === "browse" && selected && (
          <FeatureSheet
            feature={selected}
            layer={layers.find((l) => l.id === selected.layerId)}
            project={project}
            onClose={() => setSelected(null)}
            onEdit={() => {
              const feature = selected;
              setSelected(null);
              navigation.navigate("CaptureForm", { mode: "edit", projectId, layerId: feature.layerId, uuid: feature.uuid });
            }}
          />
        )}

        {mode.kind === "measure" && (
          <View style={{ gap: 8 }}>
            <SegmentedButtons
              value={mode.shape}
              onValueChange={(shape) => setMode({ kind: "measure", shape: shape as "distance" | "area" })}
              buttons={[
                { value: "distance", label: "Distance" },
                { value: "area", label: "Area" },
              ]}
            />
            <Text style={ui.title}>
              {mode.shape === "distance"
                ? formatDistance(pathLength(points), project.crs.unit_to_metre, project.crs.units)
                : points.length >= 3
                  ? formatArea(ringArea(points))
                  : "Tap at least 3 corners"}
            </Text>
            <Text style={ui.muted}>Tap the map to add points. Measured on the device, for guidance.</Text>
            <View style={ui.row}>
              <Button mode="text" onPress={() => setPoints((all) => all.slice(0, -1))} disabled={points.length === 0}>
                Undo
              </Button>
              <Button mode="text" onPress={() => setPoints([])} disabled={points.length === 0}>
                Clear
              </Button>
              <Button mode="contained-tonal" onPress={reset}>
                Done
              </Button>
            </View>
          </View>
        )}

        {mode.kind === "pick-layer" && (
          <View style={{ gap: 6 }}>
            <Text style={ui.title}>Capture into which layer?</Text>
            <ScrollView style={{ maxHeight: 220 }}>
              {editableLayers.map((layer) => (
                <Button key={layer.id} mode="outlined" style={{ marginBottom: 6 }} onPress={() => setMode({ kind: "pick-method", layer })}>
                  {layer.name} ({layer.geometryType})
                </Button>
              ))}
            </ScrollView>
            <Button mode="text" onPress={reset}>
              Cancel
            </Button>
          </View>
        )}

        {mode.kind === "pick-method" && (
          <View style={{ gap: 6 }}>
            <Text style={ui.title}>{mode.layer.name}: how?</Text>
            {mode.layer.geometryType === "point" ? (
              <Button mode="contained" icon="crosshairs-gps" onPress={() => setMode({ kind: "gps-point", layer: mode.layer })}>
                From GPS (average of {APP_CONFIG.defaultAveraging} readings)
              </Button>
            ) : (
              <Button mode="contained" icon="walk" onPress={() => setMode({ kind: "gps-track", layer: mode.layer, walking: true })}>
                Walk it with GPS
              </Button>
            )}
            <Button mode="contained-tonal" icon="gesture-tap" onPress={() => setMode({ kind: "draw", layer: mode.layer })}>
              Draw on the map
            </Button>
            <Button mode="text" onPress={reset}>
              Cancel
            </Button>
          </View>
        )}

        {mode.kind === "gps-point" && (
          <View style={{ gap: 6 }}>
            <Text style={ui.title}>GPS point for {mode.layer.name}</Text>
            <Text>
              {lastFix ? `Now: ±${lastFix.accuracy?.toFixed(1) ?? "?"} m` : "Waiting for a position…"} · readings {fixes.length}/{APP_CONFIG.defaultAveraging}
              {fixes.length > 0 ? ` (${usable(fixes, APP_CONFIG.maxUsableAccuracy).length} usable)` : ""}
            </Text>
            {average && (
              <Text>
                Average: ±{average.accuracy.toFixed(1)} m · {formatPosition(project.crs, average.position)}
              </Text>
            )}
            {fixes.length >= APP_CONFIG.defaultAveraging && !average && (
              <Notice kind="warning">Every reading was worse than ±{APP_CONFIG.maxUsableAccuracy} m. Move into the open and try again.</Notice>
            )}
            <View style={ui.row}>
              <Button
                mode="contained"
                disabled={!average || fixes.length < APP_CONFIG.defaultAveraging}
                onPress={() => average && finish(mode.layer, [average.position], "gps", average.accuracy, average.timestamp, average.readings)}
              >
                Use this position
              </Button>
              <Button mode="text" onPress={() => setFixes([])}>
                Start again
              </Button>
              <Button mode="text" onPress={reset}>
                Cancel
              </Button>
            </View>
          </View>
        )}

        {mode.kind === "gps-track" && (
          <View style={{ gap: 6 }}>
            <Text style={ui.title}>
              Walking {mode.layer.geometryType === "polygon" ? "the edge of an area" : "a line"} for {mode.layer.name}
            </Text>
            <Text>
              {lastFix ? `Now: ±${lastFix.accuracy?.toFixed(1) ?? "?"} m` : "Waiting for a position…"} · {track.length} points ·{" "}
              {formatDistance(pathLength(trackPoints), project.crs.unit_to_metre, project.crs.units)}
              {mode.layer.geometryType === "polygon" && track.length >= 3 ? ` · ${formatArea(ringArea(trackPoints))}` : ""}
            </Text>
            <Text style={ui.muted}>
              A point is recorded every {APP_CONFIG.trackMinDistance} m. Readings worse than ±{APP_CONFIG.maxUsableAccuracy} m are skipped. Keep the screen on.
            </Text>
            <View style={ui.row}>
              <Button mode="contained-tonal" icon={mode.walking ? "pause" : "play"} onPress={() => setMode({ ...mode, walking: !mode.walking })}>
                {mode.walking ? "Pause" : "Resume"}
              </Button>
              <Button
                mode="contained"
                onPress={() =>
                  finish(
                    mode.layer,
                    trackPoints,
                    "gps_track",
                    track.length ? Math.max(...track.map((f) => f.accuracy ?? 0)) : null,
                    track.length ? track[track.length - 1]!.timestamp : null,
                    track.length,
                  )
                }
              >
                Finish
              </Button>
              <Button mode="text" onPress={() => setTrack((all) => all.slice(0, -1))} disabled={track.length === 0}>
                Undo point
              </Button>
              <Button mode="text" onPress={reset}>
                Cancel
              </Button>
            </View>
          </View>
        )}

        {mode.kind === "draw" && (
          <View style={{ gap: 6 }}>
            <Text style={ui.title}>Drawing in {mode.layer.name}</Text>
            <Text style={ui.muted}>
              {mode.layer.geometryType === "point" ? "Tap where the point is." : "Tap each corner in order."} {points.length} point(s).
            </Text>
            <View style={ui.row}>
              <Button mode="contained" onPress={() => finish(mode.layer, points, "drawn", null, null, null)} disabled={points.length === 0}>
                Finish
              </Button>
              <Button mode="text" onPress={() => setPoints((all) => all.slice(0, -1))} disabled={points.length === 0}>
                Undo
              </Button>
              <Button mode="text" onPress={reset}>
                Cancel
              </Button>
            </View>
          </View>
        )}
      </View>

      <Portal>
        <Modal visible={showLayers} onDismiss={() => setShowLayers(false)} contentContainerStyle={local.modal}>
          <Text style={ui.title}>Layers</Text>
          <ScrollView style={{ maxHeight: 360 }}>
            {layers.map((layer) => (
              <Checkbox.Item
                key={layer.id}
                label={`${layer.name} (${(data[layer.id] ?? []).length})`}
                status={layer.visible ? "checked" : "unchecked"}
                onPress={async () => {
                  await setLayerVisible(layer.id, !layer.visible);
                  setLayers((all) => all.map((l) => (l.id === layer.id ? { ...l, visible: !l.visible } : l)));
                }}
              />
            ))}
          </ScrollView>
          <Text style={ui.muted}>
            {project.basemapPath
              ? `Offline basemap: ${project.basemapName}`
              : online
                ? "Background: OpenStreetMap (needs a connection; it can't be stored on the device)."
                : "No offline basemap: layers show on a plain background."}
          </Text>
          <Button onPress={() => setShowLayers(false)}>Close</Button>
        </Modal>
      </Portal>
    </View>
  );
}

function FeatureSheet(props: { feature: LocalFeature; layer: LocalLayer | undefined; project: LocalProject; onClose(): void; onEdit(): void }) {
  const { feature, layer, project } = props;
  const first = positions(feature.geometry)[0];
  const stateText =
    feature.state === "new"
      ? "Captured on this device, not yet sent"
      : feature.state === "edited"
        ? "Changed on this device, not yet sent"
        : feature.state === "conflict"
          ? "Changed here and in the office: the office is settling it"
          : "In step with the office";
  return (
    <View style={{ gap: 4 }}>
      <View style={[ui.row, { justifyContent: "space-between" }]}>
        <Text style={ui.title}>{layer?.name ?? "Feature"}</Text>
        <IconButton icon="close" accessibilityLabel="Close" size={18} onPress={props.onClose} />
      </View>
      <Text style={ui.muted}>
        {stateText}
        {feature.verified ? " · verified" : ""}
      </Text>
      <ScrollView style={{ maxHeight: 150 }}>
        {(layer?.schema ?? []).map((field) => (
          <Text key={field.name}>
            <Text style={{ fontWeight: "600" }}>{labelOf(field)}: </Text>
            {feature.properties[field.name] === null || feature.properties[field.name] === undefined ? "—" : String(feature.properties[field.name])}
          </Text>
        ))}
        {feature.method && (
          <Text style={ui.muted}>
            {feature.method === "drawn" ? "Drawn on the map" : feature.method === "gps" ? `GPS, ${feature.readings} readings` : `GPS walk, ${feature.readings} points`}
            {feature.accuracyM !== null ? ` · ±${feature.accuracyM.toFixed(1)} m` : ""}
            {feature.fixTime ? ` · ${feature.fixTime.slice(0, 16).replace("T", " ")}` : ""}
          </Text>
        )}
        {first && <Text style={ui.muted}>{formatPosition(project.crs, first)}</Text>}
        {feature.notes ? <Text style={ui.muted}>Notes: {feature.notes}</Text> : null}
      </ScrollView>
      {layer && layer.name !== "Planning area" && (
        <Button mode="contained-tonal" icon="pencil" onPress={props.onEdit}>
          Details and photos
        </Button>
      )}
    </View>
  );
}

const local = StyleSheet.create({
  topRight: { position: "absolute", top: 8, right: 8 },
  panel: { backgroundColor: colors.surface, padding: 12, borderTopWidth: 1, borderTopColor: colors.border, gap: 8 },
  modal: { backgroundColor: colors.surface, margin: 24, padding: 16, borderRadius: 8, gap: 8 },
});
