// Files on the device: photos, offline basemaps, and how much room is left.

import { Directory, File, Paths } from "expo-file-system";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";

import { APP_CONFIG } from "../constants/config";

function folder(name: string): Directory {
  const directory = new Directory(Paths.document, name);
  if (!directory.exists) directory.create({ intermediates: true });
  return directory;
}

export function freeBytes(): number {
  return Paths.availableDiskSpace;
}

export function isStorageLow(): boolean {
  return freeBytes() < APP_CONFIG.lowStorageBytes;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export class CameraUnavailable extends Error {}

export interface StoredPhoto {
  path: string;
  width: number;
  height: number;
  bytes: number;
}

/** Takes a photo with the camera, shrinks and compresses it, and stores it in
 * the app's own folder. Null if the user cancels. */
export async function takePhoto(featureUuid: string): Promise<StoredPhoto | null> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) {
    throw new CameraUnavailable("Camera permission is off. Allow it for this app in the phone's settings.");
  }
  const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 1, exif: false });
  const asset = shot.canceled ? null : shot.assets?.[0];
  if (!asset) return null;

  const context = ImageManipulator.manipulate(asset.uri);
  const landscape = asset.width >= asset.height;
  if (Math.max(asset.width, asset.height) > APP_CONFIG.photoMaxSide) {
    context.resize(landscape ? { width: APP_CONFIG.photoMaxSide } : { height: APP_CONFIG.photoMaxSide });
  }
  const rendered = await context.renderAsync();
  const saved = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: APP_CONFIG.photoQuality });

  const target = new File(folder("photos"), `${featureUuid}-${Date.now()}.jpg`);
  const temporary = new File(saved.uri);
  temporary.copy(target);
  temporary.delete();
  return { path: target.uri, width: saved.width, height: saved.height, bytes: target.size ?? 0 };
}

export function deleteFile(path: string | null): void {
  if (!path) return;
  try {
    const file = new File(path);
    if (file.exists) file.delete();
  } catch {
    // already gone
  }
}

/** Downloads an offline basemap (MBTiles) for a project. Returns where it is and its size. */
export async function downloadBasemap(projectId: number, url: string, headers: Record<string, string>): Promise<{ path: string; bytes: number }> {
  const target = new File(folder("basemaps"), `project-${projectId}.mbtiles`);
  if (target.exists) target.delete();
  const file = await File.downloadFileAsync(url, target, { headers });
  // A refusal from the server arrives as a small JSON message, not a tile database.
  const head = new TextDecoder().decode(new Uint8Array(await file.slice(0, 15).arrayBuffer()));
  if (head !== "SQLite format 3") {
    let message = "The server didn't send a basemap.";
    try {
      const body = JSON.parse(file.textSync()) as Record<string, unknown>;
      const parts = Object.values(body).flat().filter((v): v is string => typeof v === "string");
      if (parts.length) message = parts.join(" ");
    } catch {
      // keep the general message
    }
    file.delete();
    throw new Error(message);
  }
  return { path: file.uri, bytes: file.size ?? 0 };
}
