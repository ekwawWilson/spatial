import { useFocusEffect } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useCallback, useState } from "react";
import { FlatList, Text, View } from "react-native";
import { Button } from "react-native-paper";

import { InspectionCard } from "../../components/InspectionCard";
import { Notice, styles } from "../../components/ui";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import { completeTask, getFeature, listInspections, listLayers, listTasks, reopenTask } from "../../services/db";
import type { LocalFeature, LocalInspection, LocalLayer, LocalTask } from "../../types";
import { labelOf } from "../../utils/forms";

type Props = NativeStackScreenProps<RootStackParamList, "Tasks">;
type Row = LocalTask & { feature: LocalFeature | null; layer: LocalLayer | undefined };

const OUTCOME_TEXT = { confirmed: "Confirmed as recorded", corrected: "Corrected", not_found: "Not found on the ground", "": "" };

/** Features the office asked to have checked on the ground. */
export default function TasksScreen({ navigation, route }: Props) {
  const { projectId } = route.params;
  const [rows, setRows] = useState<Row[]>([]);
  const [inspections, setInspections] = useState<LocalInspection[]>([]);

  const reload = useCallback(async () => {
    const layers = new Map((await listLayers(projectId)).map((l) => [l.id, l]));
    const tasks = await listTasks(projectId);
    setRows(await Promise.all(tasks.map(async (t) => ({ ...t, feature: await getFeature(t.featureUuid), layer: layers.get(t.layerId) }))));
    setInspections(await listInspections(projectId));
  }, [projectId]);

  useFocusEffect(
    useCallback(() => {
      void reload();
    }, [reload]),
  );

  async function finish(task: Row, outcome: "confirmed" | "not_found") {
    await completeTask(task.id, outcome, "");
    await reload();
  }

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.pad}
      data={rows}
      keyExtractor={(row) => String(row.id)}
      ListHeaderComponent={
        <View>
          <Notice>
            Go to each site or feature and compare it with what is recorded. Your answers are sent to the office at the next sync.
          </Notice>
          {inspections.map((item) => (
            <InspectionCard key={item.permit} item={item} onChanged={() => void reload()} />
          ))}
        </View>
      }
      ListEmptyComponent={
        inspections.length ? null : <Text style={[styles.muted, { marginTop: 12 }]}>Nothing to check. New tasks and inspections arrive when you sync.</Text>
      }
      renderItem={({ item }) => (
        <View style={styles.card}>
          <Text style={styles.title}>
            {item.layer?.name ?? "Feature"}
            {item.item && item.item !== item.layer?.name ? ` · ${item.item}` : ""}
          </Text>
          {!item.feature && <Text style={styles.muted}>This feature isn't on this device. Sync, or download its layer.</Text>}
          {item.feature &&
            (item.layer?.schema ?? []).slice(0, 4).map((field) => (
              <Text key={field.name}>
                <Text style={{ fontWeight: "600" }}>{labelOf(field)}: </Text>
                {item.feature!.properties[field.name] === null || item.feature!.properties[field.name] === undefined ? "—" : String(item.feature!.properties[field.name])}
              </Text>
            ))}
          {item.pending ? (
            <View style={styles.row}>
              <Text style={styles.muted}>{OUTCOME_TEXT[item.outcome]} · not yet sent</Text>
              <Button
                compact
                mode="text"
                onPress={async () => {
                  await reopenTask(item.id);
                  await reload();
                }}
              >
                Change
              </Button>
            </View>
          ) : (
            <View style={styles.row}>
              <Button mode="contained" icon="check" disabled={!item.feature} onPress={() => finish(item, "confirmed")}>
                Correct as recorded
              </Button>
              <Button
                mode="contained-tonal"
                icon="pencil"
                disabled={!item.feature}
                onPress={() => navigation.navigate("CaptureForm", { mode: "edit", projectId, layerId: item.layerId, uuid: item.featureUuid, taskId: item.id })}
              >
                Needs correcting
              </Button>
              <Button mode="text" onPress={() => finish(item, "not_found")}>
                Not found
              </Button>
            </View>
          )}
        </View>
      )}
    />
  );
}
