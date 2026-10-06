import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { ActivityIndicator, View } from "react-native";

import { colors } from "../constants/colors";
import { useAuth } from "../contexts/AuthContext";
import LoginScreen from "../screens/auth/LoginScreen";
import CaptureFormScreen from "../screens/capture/CaptureFormScreen";
import CapturedListScreen from "../screens/capture/CapturedListScreen";
import TasksScreen from "../screens/capture/TasksScreen";
import MapScreen from "../screens/map/MapScreen";
import DownloadScreen from "../screens/projects/DownloadScreen";
import ProjectsScreen from "../screens/projects/ProjectsScreen";
import SettingsScreen from "../screens/settings/SettingsScreen";
import type { CaptureMethod, Geometry } from "../types";

export type RootStackParamList = {
  Projects: undefined;
  Download: { projectId?: number } | undefined;
  Map: { projectId: number };
  CaptureForm:
    | {
        mode: "new";
        projectId: number;
        layerId: number;
        geometry: Geometry;
        method: CaptureMethod;
        accuracyM: number | null;
        fixTime: string | null;
        readings: number | null;
      }
    | { mode: "edit"; projectId: number; layerId: number; uuid: string; /** Saving also reports this ground-truthing task as corrected. */ taskId?: number };
  Captured: { projectId: number };
  Tasks: { projectId: number };
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function AppNavigator() {
  const { ready, me } = useAuth();
  if (!ready) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }
  if (!me) return <LoginScreen />;
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.primary },
        headerTintColor: "#ffffff",
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="Projects" component={ProjectsScreen} options={{ title: "Projects on this device" }} />
      <Stack.Screen name="Download" component={DownloadScreen} options={{ title: "Download for the field" }} />
      <Stack.Screen name="Map" component={MapScreen} options={{ title: "Map" }} />
      <Stack.Screen name="CaptureForm" component={CaptureFormScreen} options={{ title: "Details" }} />
      <Stack.Screen name="Captured" component={CapturedListScreen} options={{ title: "Captured on this device" }} />
      <Stack.Screen name="Tasks" component={TasksScreen} options={{ title: "To check on the ground" }} />
      <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: "Device and account" }} />
    </Stack.Navigator>
  );
}
