import { useFocusEffect } from "@react-navigation/native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useCallback, useState } from "react";
import { Alert, FlatList, Text, View } from "react-native";
import { Button, Chip } from "react-native-paper";

import { errorText, Notice, styles } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { countUnsent, listProjects, removeProject } from "../../services/db";
import { deleteFile, formatBytes, freeBytes, isStorageLow } from "../../services/files";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import type { LocalProject } from "../../types";

type Props = NativeStackScreenProps<RootStackParamList, "Projects">;

export default function ProjectsScreen({ navigation }: Props) {
  const { me, offline, districtId, setDistrict, can } = useAuth();
  const [projects, setProjects] = useState<(LocalProject & { unsent: number })[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const rows = await listProjects(districtId);
      setProjects(await Promise.all(rows.map(async (p) => ({ ...p, unsent: await countUnsent(p.id) }))));
    } catch (err) {
      setError(errorText(err));
    }
  }, [districtId]);

  useFocusEffect(
    useCallback(() => {
      void reload();
    }, [reload]),
  );

  function confirmRemove(project: LocalProject & { unsent: number }) {
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
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.title}>{item.name}</Text>
            <Text style={styles.muted}>
              {[item.community, item.crs.code].filter(Boolean).join(" · ")} · downloaded {item.downloadedAt.slice(0, 10)}
            </Text>
            <Text style={styles.muted}>
              Package {formatBytes(item.packageBytes)}
              {item.basemapPath ? ` · offline basemap ${formatBytes(item.basemapBytes)}` : " · no offline basemap"}
              {item.unsent ? ` · ${item.unsent} captured, not yet sent` : ""}
            </Text>
            <View style={styles.row}>
              <Button mode="contained-tonal" icon="map" onPress={() => navigation.navigate("Map", { projectId: item.id })}>
                Open
              </Button>
              <Button mode="text" disabled={offline} onPress={() => navigation.navigate("Download", { projectId: item.id })}>
                Update
              </Button>
              <Button mode="text" textColor="#b3261e" onPress={() => confirmRemove(item)}>
                Remove
              </Button>
            </View>
          </View>
        )}
      />
    </View>
  );
}
