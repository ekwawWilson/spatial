import { useFocusEffect } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useCallback, useState } from "react";
import { FlatList, Text, View } from "react-native";
import { Button } from "react-native-paper";

import { Notice, styles } from "../../components/ui";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import { listLayers, listPhotos, listUnsent } from "../../services/db";
import type { LocalFeature } from "../../types";

type Props = NativeStackScreenProps<RootStackParamList, "Captured">;
type Row = LocalFeature & { layerName: string; photos: number };

export default function CapturedListScreen({ navigation, route }: Props) {
  const { projectId } = route.params;
  const [rows, setRows] = useState<Row[]>([]);

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const names = new Map((await listLayers(projectId)).map((l) => [l.id, l.name]));
        const features = await listUnsent(projectId);
        setRows(await Promise.all(features.map(async (f) => ({ ...f, layerName: names.get(f.layerId) ?? "Layer", photos: (await listPhotos(f.uuid)).length }))));
      })().catch(() => setRows([]));
    }, [projectId]),
  );

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.pad}
      data={rows}
      keyExtractor={(row) => row.uuid}
      ListHeaderComponent={
        <Notice>
          These are saved on this device only. Sending them to the office (sync) comes with the next version of the app; until then,
          don't remove the app or clear its data.
        </Notice>
      }
      ListEmptyComponent={<Text style={[styles.muted, { marginTop: 12 }]}>Nothing captured or changed on this device yet.</Text>}
      renderItem={({ item }) => (
        <View style={styles.card}>
          <Text style={styles.title}>
            {item.layerName} · {item.state === "new" ? "new" : "changed"}
          </Text>
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
