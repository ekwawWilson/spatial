import React, { useState } from "react";
import { Linking, Text, View } from "react-native";
import { Button, TextInput } from "react-native-paper";

import { completeInspection, reopenInspection } from "../services/db";
import type { LocalInspection } from "../types";
import { styles } from "./ui";

/** One permit site inspection (r.44(7)(f)): the Regulations' points, answered on site. */
export function InspectionCard({ item, onChanged }: { item: LocalInspection; onChanged(): void }) {
  const [open, setOpen] = useState(false);
  const [findings, setFindings] = useState<Record<string, string>>(item.findings);
  const [summary, setSummary] = useState(item.summary);
  const answered = Object.values(findings).filter((v) => v.trim()).length;

  async function save() {
    await completeInspection(item.permit, findings, summary, new Date().toISOString().slice(0, 10));
    setOpen(false);
    onChanged();
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>
        Site inspection · {item.number}
      </Text>
      <Text>
        {item.title}
        {item.storeys !== null ? `, ${item.storeys} storey(s)` : ""}
      </Text>
      {item.dueOn && <Text style={styles.muted}>Due by {item.dueOn} (r.44(7))</Text>}
      {item.syncError && <Text style={{ color: "#c0352b" }}>The office refused it: {item.syncError}</Text>}
      {item.centre && (
        <Button compact mode="text" icon="map-marker" onPress={() => void Linking.openURL(`geo:${item.centre![1]},${item.centre![0]}?q=${item.centre![1]},${item.centre![0]}(${encodeURIComponent(item.number)})`)}>
          Directions to the site
        </Button>
      )}
      {item.pending ? (
        <View style={styles.row}>
          <Text style={styles.muted}>Inspected {item.inspectedOn} · not yet sent</Text>
          <Button
            compact
            mode="text"
            onPress={async () => {
              await reopenInspection(item.permit);
              onChanged();
            }}
          >
            Change
          </Button>
        </View>
      ) : open ? (
        <View>
          {item.points.map((point) => (
            <TextInput
              key={point.code}
              mode="outlined"
              label={point.label}
              value={findings[point.code] ?? ""}
              onChangeText={(text) => setFindings({ ...findings, [point.code]: text })}
              multiline
              style={{ marginTop: 8 }}
            />
          ))}
          <TextInput mode="outlined" label="Summary and recommendation" value={summary} onChangeText={setSummary} multiline numberOfLines={3} style={{ marginTop: 8 }} />
          <View style={styles.row}>
            <Button mode="contained" icon="check" disabled={!answered && !summary.trim()} onPress={() => void save()}>
              Save the inspection
            </Button>
            <Button mode="text" onPress={() => setOpen(false)}>
              Cancel
            </Button>
          </View>
        </View>
      ) : (
        <View style={styles.row}>
          <Button mode="contained" icon="clipboard-check" onPress={() => setOpen(true)}>
            Inspect the site
          </Button>
        </View>
      )}
    </View>
  );
}
