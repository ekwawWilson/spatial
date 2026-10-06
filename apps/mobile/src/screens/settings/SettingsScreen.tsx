import { useFocusEffect } from "@react-navigation/native";
import React, { useCallback, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { Button } from "react-native-paper";

import { Notice, styles } from "../../components/ui";
import { APP_CONFIG } from "../../constants/config";
import { useAuth } from "../../contexts/AuthContext";
import { countUnsent, listProjects, photoBytes } from "../../services/db";
import { formatBytes, freeBytes, isStorageLow } from "../../services/files";

export default function SettingsScreen() {
  const { me, server, offline, membership, signOut } = useAuth();
  const [usage, setUsage] = useState({ packages: 0, basemaps: 0, photos: 0, unsent: 0, projects: 0 });

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const projects = await listProjects(null);
        setUsage({
          projects: projects.length,
          packages: projects.reduce((sum, p) => sum + p.packageBytes, 0),
          basemaps: projects.reduce((sum, p) => sum + p.basemapBytes, 0),
          photos: await photoBytes(),
          unsent: await countUnsent(),
        });
      })().catch(() => undefined);
    }, []),
  );

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.pad}>
      <View style={styles.card}>
        <Text style={styles.title}>Account</Text>
        <Text>{me?.email}</Text>
        <Text style={styles.muted}>
          {membership ? `${membership.district.name} · ${membership.role.replace("_", " ")}` : "No district"} · {server}
        </Text>
        <Text style={styles.muted}>{offline ? "Signed in without a connection." : "Signed in with the server."}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>Storage on this device</Text>
        {isStorageLow() && <Notice kind="warning">Low on storage. Free some space before capturing more photos.</Notice>}
        <Text>Free: {formatBytes(freeBytes())}</Text>
        <Text>
          {usage.projects} project package(s): {formatBytes(usage.packages)}
        </Text>
        <Text>Offline basemaps: {usage.basemaps ? formatBytes(usage.basemaps) : "none"}</Text>
        <Text>Photos: {usage.photos ? formatBytes(usage.photos) : "none"}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>Captured, not yet sent</Text>
        <Text>{usage.unsent} item(s)</Text>
        <Text style={styles.muted}>
          Sending to the office (sync) comes with the next version of the app. Captures stay on this device until then, and signing
          out keeps them.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.title}>GPS capture</Text>
        <Text style={styles.muted}>
          A GPS point is the average of {APP_CONFIG.defaultAveraging} readings, weighted towards the more accurate ones. Readings worse than
          ±{APP_CONFIG.maxUsableAccuracy} m are ignored. Walk mode records a point every {APP_CONFIG.trackMinDistance} m.
        </Text>
      </View>

      <Button mode="outlined" onPress={() => void signOut()}>
        Sign out
      </Button>
    </ScrollView>
  );
}
