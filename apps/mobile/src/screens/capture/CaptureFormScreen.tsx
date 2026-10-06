import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import * as Crypto from "expo-crypto";
import React, { useEffect, useRef, useState } from "react";
import { Alert, Image, KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { Button, Chip, HelperText, SegmentedButtons, TextInput } from "react-native-paper";

import { errorText, Notice, styles } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import type { RootStackParamList } from "../../navigation/AppNavigator";
import { deleteCapture, deletePhoto, getFeature, insertCapture, insertPhoto, listLayers, listPhotos, updateAttributes } from "../../services/db";
import { deleteFile, formatBytes, isStorageLow, takePhoto, type StoredPhoto } from "../../services/files";
import { currentFix } from "../../services/gps";
import type { LocalFeature, LocalLayer, LocalPhoto, SchemaField } from "../../types";
import { initialValues, labelOf, validate, type FormValues } from "../../utils/forms";

type Props = NativeStackScreenProps<RootStackParamList, "CaptureForm">;

/** A photo taken on this screen but not yet saved with the feature. */
interface PendingPhoto extends StoredPhoto {
  latitude: number | null;
  longitude: number | null;
  accuracyM: number | null;
  takenAt: string;
}

export default function CaptureFormScreen({ navigation, route }: Props) {
  const params = route.params;
  const { me } = useAuth();
  const [layer, setLayer] = useState<LocalLayer | null>(null);
  const [feature, setFeature] = useState<LocalFeature | null>(null);
  const [values, setValues] = useState<FormValues>({});
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<LocalPhoto[]>([]);
  const [pending, setPending] = useState<PendingPhoto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The feature's id is fixed from the start, so photos can be named after it.
  const uuid = useRef(params.mode === "edit" ? params.uuid : Crypto.randomUUID()).current;
  const done = useRef(false);

  useEffect(() => {
    (async () => {
      const found = (await listLayers(params.projectId)).find((l) => l.id === params.layerId) ?? null;
      setLayer(found);
      if (params.mode === "edit") {
        const existing = await getFeature(params.uuid);
        setFeature(existing);
        setNotes(existing?.notes ?? "");
        setSaved(await listPhotos(params.uuid));
        if (found) setValues(initialValues(found.schema, existing?.properties));
      } else if (found) {
        setValues(initialValues(found.schema));
      }
    })().catch((err: unknown) => setError(errorText(err)));
  }, [params]);

  // Leaving without saving throws away photos taken on this screen.
  const pendingRef = useRef<PendingPhoto[]>([]);
  pendingRef.current = pending;
  useEffect(
    () => () => {
      if (!done.current) pendingRef.current.forEach((p) => deleteFile(p.path));
    },
    [],
  );

  async function addPhoto() {
    setError(null);
    try {
      const photo = await takePhoto(uuid);
      if (!photo) return;
      const fix = await currentFix();
      setPending((all) => [
        ...all,
        { ...photo, latitude: fix?.latitude ?? null, longitude: fix?.longitude ?? null, accuracyM: fix?.accuracy ?? null, takenAt: new Date().toISOString() },
      ]);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function save() {
    if (!layer || !me) return;
    const result = validate(layer.schema, values);
    if (!result.ok) {
      setErrors(result.errors);
      setError("Some answers need attention.");
      return;
    }
    setErrors({});
    setBusy(true);
    setError(null);
    try {
      if (params.mode === "new") {
        await insertCapture({
          uuid,
          layerId: params.layerId,
          projectId: params.projectId,
          geometry: params.geometry,
          properties: result.properties,
          capturedBy: me.email,
          method: params.method,
          accuracyM: params.accuracyM,
          fixTime: params.fixTime,
          readings: params.readings,
          notes: notes.trim(),
        });
      } else {
        await updateAttributes(uuid, result.properties, notes.trim(), me.email);
      }
      for (const photo of pending) {
        await insertPhoto({ featureUuid: uuid, path: photo.path, width: photo.width, height: photo.height, bytes: photo.bytes, latitude: photo.latitude, longitude: photo.longitude, accuracyM: photo.accuracyM, takenAt: photo.takenAt });
      }
      done.current = true;
      navigation.goBack();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function confirmDelete() {
    Alert.alert("Delete this capture?", "It was made on this device and hasn't been sent to the office. This can't be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          const photos = await deleteCapture(uuid);
          photos.forEach((p) => deleteFile(p.path));
          done.current = true;
          pending.forEach((p) => deleteFile(p.path));
          navigation.goBack();
        },
      },
    ]);
  }

  if (!layer) return <View style={styles.screen}>{error && <Notice kind="error">{error}</Notice>}</View>;

  const set = (name: string, value: string | boolean | null) => setValues((all) => ({ ...all, [name]: value }));

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.screen}>
      <ScrollView contentContainerStyle={styles.pad} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>{layer.name}</Text>
        {params.mode === "new" && (
          <Text style={styles.muted}>
            {params.method === "drawn"
              ? "Drawn on the map."
              : `From GPS${params.accuracyM !== null ? `, ±${params.accuracyM.toFixed(1)} m` : ""}${params.readings ? `, ${params.readings} ${params.method === "gps" ? "readings" : "points"}` : ""}.`}
          </Text>
        )}
        {feature?.state === "synced" && <Text style={styles.muted}>From the office. Saving marks it as changed on this device.</Text>}
        {layer.schema.length === 0 && <Text style={styles.muted}>This layer has no fields to fill in.</Text>}

        {layer.schema.map((field) => (
          <FieldInput key={field.name} field={field} value={values[field.name] ?? null} error={errors[field.name]} onChange={(v) => set(field.name, v)} />
        ))}

        <TextInput mode="outlined" label="Notes" value={notes} onChangeText={setNotes} multiline numberOfLines={3} />

        <Text style={styles.title}>Photos</Text>
        {isStorageLow() && <Notice kind="warning">This device is low on storage. Photos may fail to save.</Notice>}
        <View style={styles.row}>
          {saved.map((photo) => (
            <PhotoTile
              key={`s${photo.id}`}
              uri={photo.path}
              caption={formatBytes(photo.bytes)}
              onRemove={async () => {
                await deletePhoto(photo.id);
                deleteFile(photo.path);
                setSaved((all) => all.filter((p) => p.id !== photo.id));
              }}
            />
          ))}
          {pending.map((photo) => (
            <PhotoTile
              key={photo.path}
              uri={photo.path}
              caption={`${formatBytes(photo.bytes)}${photo.latitude !== null ? " · located" : ""}`}
              onRemove={() => {
                deleteFile(photo.path);
                setPending((all) => all.filter((p) => p.path !== photo.path));
              }}
            />
          ))}
        </View>
        <Button mode="outlined" icon="camera" onPress={addPhoto}>
          Take a photo
        </Button>

        {error && <Notice kind="error">{error}</Notice>}
        <Button mode="contained" onPress={save} loading={busy} disabled={busy}>
          Save on this device
        </Button>
        {feature?.state === "new" && (
          <Button mode="text" textColor="#b3261e" onPress={confirmDelete}>
            Delete this capture
          </Button>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function PhotoTile(props: { uri: string; caption: string; onRemove(): void }) {
  return (
    <View style={{ alignItems: "center", gap: 2 }}>
      <Image source={{ uri: props.uri }} style={{ width: 96, height: 96, borderRadius: 6 }} />
      <Text style={styles.muted}>{props.caption}</Text>
      <Button compact mode="text" onPress={props.onRemove}>
        Remove
      </Button>
    </View>
  );
}

function FieldInput(props: { field: SchemaField; value: string | boolean | null; error?: string; onChange(value: string | boolean | null): void }) {
  const { field, value, error } = props;
  const label = `${labelOf(field)}${field.required ? " *" : ""}`;
  let input: React.ReactNode;
  if (field.type === "boolean") {
    input = (
      <View style={{ gap: 4 }}>
        <Text>{label}</Text>
        <SegmentedButtons
          value={value === true ? "yes" : value === false ? "no" : ""}
          onValueChange={(v) => props.onChange(v === "yes")}
          buttons={[
            { value: "yes", label: "Yes" },
            { value: "no", label: "No" },
          ]}
        />
      </View>
    );
  } else if (field.type === "choice") {
    input = (
      <View style={{ gap: 4 }}>
        <Text>{label}</Text>
        <View style={styles.row}>
          {(field.choices ?? []).map((choice) => (
            <Chip key={String(choice)} selected={String(value ?? "") === String(choice)} onPress={() => props.onChange(String(value ?? "") === String(choice) ? "" : String(choice))}>
              {String(choice)}
            </Chip>
          ))}
        </View>
      </View>
    );
  } else {
    input = (
      <TextInput
        mode="outlined"
        label={label}
        value={typeof value === "string" ? value : ""}
        onChangeText={props.onChange}
        error={Boolean(error)}
        placeholder={field.type === "date" ? "YYYY-MM-DD" : undefined}
        keyboardType={field.type === "integer" ? "number-pad" : field.type === "decimal" ? "decimal-pad" : field.type === "date" ? "numbers-and-punctuation" : "default"}
      />
    );
  }
  return (
    <View>
      {input}
      {error ? (
        <HelperText type="error" visible>
          {error}
        </HelperText>
      ) : null}
    </View>
  );
}
