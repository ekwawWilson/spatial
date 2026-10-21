import { useFocusEffect } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useCallback, useState } from "react";
import { Alert, FlatList, Pressable, Text, View } from "react-native";
import { Button, Chip } from "react-native-paper";

import { errorText, Notice, styles } from "../../components/ui";
import { colors } from "../../constants/colors";
import { useAuth } from "../../contexts/AuthContext";
import { listProjects, projectCounts, removeProject } from "../../services/db";
import { deleteFile, formatBytes, freeBytes, isStorageLow } from "../../services/files";
import { syncProject } from "../../services/sync";
import { describe } from "../../utils/syncPlan";
import { ago, stale } from "../../utils/when";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import type { LocalProject } from "../../types";

type Props = NativeStackScreenProps<RootStackParamList, "Projects">;
type Row = LocalProject & Awaited<ReturnType<typeof projectCounts>>;

/** A count to tap: what is waiting, and where to deal with it. */
function Count({ value, label, onPress, alert }: { value: number; label: string; onPress: () => void; alert?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${value} ${label}`}
      style={({ pressed }) => ({
        flex: 1,
        minHeight: 64,
        paddingVertical: 8,
        paddingHorizontal: 6,
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 8,
        borderWidth: 1,
        borderColor: alert && value ? colors.warning : colors.border,
        backgroundColor: pressed ? colors.background : colors.surface,
      })}
    >
      <Text style={{ fontSize: 22, fontWeight: "700", color: alert && value ? colors.warning : colors.text }}>{value}</Text>
      <Text style={[styles.muted, { textAlign: "center" }]}>{label}</Text>
    </Pressable>
  );
}

export default function ProjectsScreen({ navigation }: Props) {
  const { api, me, offline, districtId, setDistrict, can } = useAuth();
  const [syncing, setSyncing] = useState<number | null>(null);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [projects, setProjects] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const rows = await listProjects(districtId);
      setProjects(await Promise.all(rows.map(async (p) => ({ ...p, ...(await projectCounts(p.id)) }))));
    } catch (err) {
      setError(errorText(err));
    }
  }, [districtId]);

  useFocusEffect(
    useCallback(() => {
      void reload();
    }, [reload]),
  );

  async function sync(projectId: number) {
    setSyncing(projectId);
    setError(null);
    try {
      setSyncNote(describe(await syncProject(api, projectId, setSyncNote)));
    } catch (err) {
      setSyncNote(null);
      setError(errorText(err));
    } finally {
      setSyncing(null);
      void reload();
    }
  }

  function confirmRemove(project: Row) {
    if (project.unsent > 0) {
      Alert.alert(
        "Can't remove yet",
        `${project.unsent} item(s) captured on this device haven't been sent to the office. Removing the project would lose them.`,
      );
      return;
    }
    Alert.alert("Remove from this device?", `${project.name} stays on the server. You can download it again.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: async () => {
          const result = await removeProject(project.id);
          if (result.removed) deleteFile(project.basemapPath);
          void reload();
        },
      },
    ]);
  }

  return (
    <View style={styles.screen}>
      <FlatList
        contentContainerStyle={styles.pad}
        data={projects}
        keyExtractor={(p) => String(p.id)}
        ListHeaderComponent={
          <View style={{ gap: 10 }}>
            {offline && <Notice kind="warning">No connection: working from what's on this device. Downloads need a connection.</Notice>}
            {isStorageLow() && (
              <Notice kind="warning">This device is low on storage ({formatBytes(freeBytes())} free). Free some space before capturing photos.</Notice>
            )}
            {error && <Notice kind="error">{error}</Notice>}
            {syncNote && <Notice>{syncNote}</Notice>}
            {me && me.memberships.length > 1 && (
              <View style={styles.row}>
                {me.memberships.map((m) => (
                  <Chip key={m.district.id} selected={m.district.id === districtId} onPress={() => setDistrict(m.district.id)}>
                    {m.district.name}
                  </Chip>
                ))}
              </View>
            )}
            <View style={styles.row}>
              <Button mode="contained" icon="download" disabled={offline || !can("field.package")} onPress={() => navigation.navigate("Download")}>
                Download a project
              </Button>
              <Button mode="text" icon="cog" onPress={() => navigation.navigate("Settings")}>
                Device
              </Button>
            </View>
            {!can("field.package") && !offline && <Text style={styles.muted}>Your role in this district can't download projects for the field.</Text>}
          </View>
        }
        ListEmptyComponent={<Text style={[styles.muted, { marginTop: 16 }]}>No projects on this device yet. Download one while you have a connection.</Text>}
        renderItem={({ item }) => {
          const toSend = item.unsent + item.answered;
          return (
            <View style={styles.card}>
              <Text style={styles.title}>{item.name}</Text>
              <Text style={[styles.muted, stale(item.lastSync) && toSend ? { color: colors.warning } : null]}>
                {[item.community, item.crs.code].filter(Boolean).join(" · ")} · last synced {ago(item.lastSync)}
              </Text>
              <View style={[styles.row, { flexWrap: "nowrap", marginVertical: 4 }]}>
                <Count value={item.tasks} label="to check" onPress={() => navigation.navigate("Tasks", { projectId: item.id })} />
                <Count value={item.inspections} label="inspections" onPress={() => navigation.navigate("Tasks", { projectId: item.id })} />
                <Count value={toSend} label="not sent" alert onPress={() => (item.unsent || !item.answered ? navigation.navigate("Captured", { projectId: item.id }) : navigation.navigate("Tasks", { projectId: item.id }))} />
              </View>
              <Button mode="contained" icon="map" contentStyle={{ height: 48 }} onPress={() => navigation.navigate("Map", { projectId: item.id })}>
                Open the map
              </Button>
              <Button
                mode="contained-tonal"
                icon="sync"
                contentStyle={{ height: 48 }}
                loading={syncing === item.id}
                disabled={offline || syncing !== null}
                onPress={() => sync(item.id)}
              >
                {offline ? "Sync when back online" : toSend ? `Sync now: send ${toSend}` : "Sync now"}
              </Button>
              <Text style={styles.muted}>
                Package {formatBytes(item.packageBytes)}
                {item.basemapPath ? ` · offline basemap ${formatBytes(item.basemapBytes)}` : " · no offline basemap"} · downloaded {item.downloadedAt.slice(0, 10)}
              </Text>
              <View style={styles.row}>
                <Button mode="text" compact disabled={offline} onPress={() => navigation.navigate("Download", { projectId: item.id })}>
                  Change layers
                </Button>
                <Button mode="text" compact textColor={colors.danger} onPress={() => confirmRemove(item)}>
                  Remove
                </Button>
              </View>
            </View>
          );
        }}
      />
    </View>
  );
}
