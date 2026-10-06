import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { ActivityIndicator, Button, Checkbox, RadioButton } from "react-native-paper";

import { errorText, Notice, styles } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { getProject, savePackage, setBasemap, setLastPull } from "../../services/db";
import { deleteFile, downloadBasemap, formatBytes, freeBytes } from "../../services/files";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import type { OfflineBasemap, ServerLayer, ServerProject } from "../../types";

type Props = NativeStackScreenProps<RootStackParamList, "Download">;

export default function DownloadScreen({ navigation, route }: Props) {
  const { api, districtId } = useAuth();
  const [projects, setProjects] = useState<ServerProject[] | null>(null);
  const [projectId, setProjectId] = useState<number | null>(route.params?.projectId ?? null);
  const [layers, setLayers] = useState<ServerLayer[] | null>(null);
  const [chosen, setChosen] = useState<number[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ bytes: number; features: number; kept: number; basemaps: OfflineBasemap[]; clipped: boolean } | null>(null);
  const [basemapNote, setBasemapNote] = useState<string | null>(null);

  useEffect(() => {
    api
      .projects()
      .then(setProjects)
      .catch((err: unknown) => setError(errorText(err)));
  }, [api, districtId]);

  useEffect(() => {
    setLayers(null);
    setDone(null);
    if (projectId === null) return;
    api
      .layers(projectId)
      .then((rows) => {
        setLayers(rows);
        setChosen(rows.map((l) => l.id));
      })
      .catch((err: unknown) => setError(errorText(err)));
  }, [api, projectId]);

  async function download() {
    if (projectId === null) return;
    setBusy("Downloading the package…");
    setError(null);
    try {
      const pkg = await api.fieldPackage(projectId, chosen);
      const bytes = JSON.stringify(pkg).length;
      setBusy("Saving to this device…");
      const { kept } = await savePackage(pkg, bytes);
      // Later syncs only need what changed after this package was made.
      await setLastPull(pkg.project.id, pkg.generated_at);
      setDone({ bytes, features: pkg.feature_total, kept, basemaps: pkg.offline_basemaps, clipped: pkg.clipped_to_boundary });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  async function getBasemap(basemap: OfflineBasemap) {
    if (projectId === null) return;
    setBusy(`Downloading ${basemap.name}…`);
    setError(null);
    setBasemapNote(null);
    try {
      const previous = (await getProject(projectId))?.basemapPath ?? null;
      const request = await api.basemapRequest(projectId, basemap.id);
      const file = await downloadBasemap(projectId, request.url, request.headers);
      if (previous && previous !== file.path) deleteFile(previous);
      await setBasemap(projectId, file.path, basemap.name, file.bytes);
      setBasemapNote(`${basemap.name} saved for offline use (${formatBytes(file.bytes)}).`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  const total = (layers ?? []).filter((l) => chosen.includes(l.id)).reduce((sum, l) => sum + l.feature_count, 0);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.pad}>
      {error && <Notice kind="error">{error}</Notice>}
      <Text style={styles.muted}>Free space on this device: {formatBytes(freeBytes())}</Text>

      <View style={styles.card}>
        <Text style={styles.title}>1. Project</Text>
        {projects === null && !error && <ActivityIndicator />}
        {projects?.length === 0 && <Text style={styles.muted}>This district has no projects yet.</Text>}
        <RadioButton.Group value={projectId === null ? "" : String(projectId)} onValueChange={(v) => setProjectId(Number(v))}>
          {projects?.map((p) => <RadioButton.Item key={p.id} value={String(p.id)} label={`${p.name}${p.community ? ` (${p.community})` : ""}`} />)}
        </RadioButton.Group>
      </View>

      {projectId !== null && (
        <View style={styles.card}>
          <Text style={styles.title}>2. Layers to take</Text>
          {layers === null && <ActivityIndicator />}
          {layers?.length === 0 && <Text style={styles.muted}>This project has no layers yet. Add them in the office first.</Text>}
          {layers?.map((layer) => (
            <Checkbox.Item
              key={layer.id}
              label={`${layer.name} · ${layer.geometry_type} · ${layer.feature_count} features`}
              status={chosen.includes(layer.id) ? "checked" : "unchecked"}
              onPress={() => setChosen((ids) => (ids.includes(layer.id) ? ids.filter((i) => i !== layer.id) : [...ids, layer.id]))}
            />
          ))}
          <Text style={styles.muted}>
            {total} features in the chosen layers. Only those inside the planning area are downloaded, when the project has one.
          </Text>
          <Button mode="contained" icon="download" onPress={download} disabled={busy !== null || chosen.length === 0}>
            Download
          </Button>
        </View>
      )}

      {busy && (
        <View style={styles.row}>
          <ActivityIndicator />
          <Text>{busy}</Text>
        </View>
      )}

      {done && (
        <View style={styles.card}>
          <Text style={styles.title}>On this device</Text>
          <Text>
            {done.features} features, {formatBytes(done.bytes)}
            {done.clipped ? ", inside the planning area" : " (the project has no planning area yet, so all were taken)"}.
          </Text>
          {done.kept > 0 && <Text style={styles.muted}>{done.kept} feature(s) you changed on this device were left as they are.</Text>}
          <Text style={[styles.title, { marginTop: 8 }]}>Offline basemap</Text>
          {done.basemaps.length === 0 ? (
            <Text style={styles.muted}>
              None available. Google, Bing, Esri and OpenStreetMap don't allow their maps to be stored on a device. The Assembly's own
              imagery (for example drone photos) can be, once an administrator adds it and marks it as allowed offline. Without one,
              your layers show on a plain background when there is no connection.
            </Text>
          ) : (
            done.basemaps.map((b) => (
              <Button key={b.id} mode="outlined" icon="map-plus" disabled={busy !== null} onPress={() => getBasemap(b)}>
                Download {b.name}
              </Button>
            ))
          )}
          {basemapNote && <Notice>{basemapNote}</Notice>}
          <Button mode="contained" icon="map" onPress={() => projectId !== null && navigation.replace("Map", { projectId })}>
            Open the map
          </Button>
        </View>
      )}
    </ScrollView>
  );
}
