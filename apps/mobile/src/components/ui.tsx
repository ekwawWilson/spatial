import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors } from "../constants/colors";

export function Notice({ kind = "info", children }: { kind?: "info" | "warning" | "error"; children: React.ReactNode }) {
  const color = kind === "error" ? colors.danger : kind === "warning" ? colors.warning : colors.muted;
  return (
    <View style={[styles.notice, { borderLeftColor: color }]} accessibilityRole={kind === "error" ? "alert" : undefined}>
      <Text style={{ color: kind === "info" ? colors.text : color }}>{children}</Text>
    </View>
  );
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  pad: { padding: 16, gap: 12 },
  card: { backgroundColor: colors.surface, borderRadius: 8, padding: 14, borderWidth: 1, borderColor: colors.border, gap: 6 },
  title: { fontSize: 17, fontWeight: "600", color: colors.text },
  muted: { color: colors.muted, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  notice: { borderLeftWidth: 3, paddingLeft: 10, paddingVertical: 6, backgroundColor: colors.surface },
});
