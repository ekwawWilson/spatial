import { useFocusEffect } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useCallback, useState } from "react";
import { FlatList, Text, View } from "react-native";
import { Button } from "react-native-paper";

import { errorText, Notice, styles } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { syncProject } from "../../services/sync";
import { describe } from "../../utils/syncPlan";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import { listLayers, listPhotos, listUnsent } from "../../services/db";
import type { LocalFeature } from "../../types";

type Props = NativeStackScreenProps<RootStackParamList, "Captured">;
type Row = LocalFeature & { layerName: string; photos: number };

export default function CapturedListScreen({ navigation, route }: Props) {
  const { projectId } = route.params;
  const { api, offline } = useAuth();
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const names = new Map((await listLayers(projectId)).map((l) => [l.id, l.name]));
    const features = await listUnsent(projectId);
    setRows(await Promise.all(features.map(async (f) => ({ ...f, layerName: names.get(f.layerId) ?? "Layer", photos: (await listPhotos(f.uuid)).length }))));
  }, [projectId]);

  useFocusEffect(
    useCallback(() => {
      reload().catch(() => setRows([]));
    }, [reload]),
  );

  async function send() {
    setBusy(true);
    setError(null);
    try {
      setMessage(describe(await syncProject(api, projectId, setMessage)));
    } catch (err) {
      setMessage(null);
      setError(errorText(err));
    } finally {
      setBusy(false);
      await reload().catch(() => undefined);
    }
  }

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.pad}
      data={rows}
      keyExtractor={(row) => row.uuid}
      ListHeaderComponent={
        <View style={{ gap: 8 }}>
          {message && <Notice>{message}</Notice>}
          {error && <Notice kind="error">{error}</Notice>}
          <Button mode="contained" icon="sync" loading={busy} disabled={busy || offline} onPress={send}>
            Send to the office now
          </Button>
          {offline && <Text style={styles.muted}>No connection. Everything here is safe on this device until you sync.</Text>}
        </View>
      }
      ListEmptyComponent={<Text style={[styles.muted, { marginTop: 12 }]}>Nothing waiting to be sent.</Text>}
      renderItem={({ item }) => (
        <View style={styles.card}>
          <Text style={styles.title}>
            {item.layerName} · {item.state === "new" ? "new" : item.state === "conflict" ? "conflict: with the office" : "changed"}
          </Text>
          {item.syncError ? <Text style={{ color: "#b3261e" }}>Refused: {item.syncError}</Text> : null}
          <Text style={styles.muted}>
            {item.capturedAt?.slice(0, 16).replace("T", " ")} · {item.geometry.type}
            {item.method === "drawn" ? " · drawn" : item.method ? " · GPS" : ""}
            {item.accuracyM !== null ? ` ±${item.accuracyM.toFixed(1)} m` : ""} · {item.photos} photo(s)
          </Text>
          <Button mode="text" onPress={() => navigation.navigate("CaptureForm", { mode: "edit", projectId, layerId: item.layerId, uuid: item.uuid })}>
            Open
          </Button>
        </View>
      )}
    />
  );
}
