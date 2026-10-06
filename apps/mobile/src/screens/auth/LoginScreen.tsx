import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { Button, TextInput } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { errorText, Notice, styles } from "../../components/ui";
import { colors } from "../../constants/colors";
import { APP_CONFIG } from "../../constants/config";
import { useAuth } from "../../contexts/AuthContext";
import { loadProfile } from "../../services/authStore";

export default function LoginScreen() {
  const { signIn, server: savedServer } = useAuth();
  const [server, setServer] = useState(savedServer || APP_CONFIG.defaultServer);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadProfile().then((profile) => profile && setEmail((current) => current || profile.email));
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await signIn(server, email.trim(), password);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.pad, { paddingTop: 48 }]} keyboardShouldPersistTaps="handled">
          <Text style={{ fontSize: 26, fontWeight: "700", color: colors.primary }}>{APP_CONFIG.name}</Text>
          <Text style={styles.muted}>Sign in with your planning platform account.</Text>
          <TextInput
            mode="outlined"
            label="Server address"
            placeholder="planning.example.gov.gh"
            value={server}
            onChangeText={setServer}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
          <TextInput
            mode="outlined"
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
          />
          <TextInput mode="outlined" label="Password" value={password} onChangeText={setPassword} secureTextEntry onSubmitEditing={submit} />
          {error && <Notice kind="error">{error}</Notice>}
          <Button mode="contained" onPress={submit} loading={busy} disabled={busy || !email || !password || !server}>
            Sign in
          </Button>
          <View>
            <Text style={styles.muted}>
              After you have signed in once with a connection, the same email and password also work with no connection, for
              the projects already downloaded to this device.
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
