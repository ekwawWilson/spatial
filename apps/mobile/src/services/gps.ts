// GPS readings from the phone.

import * as Location from "expo-location";

import type { Fix } from "../types";

export class GpsUnavailable extends Error {}

export async function ensureGps(): Promise<void> {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) {
    throw new GpsUnavailable("Location permission is off. Allow it for this app in the phone's settings.");
  }
  if (!(await Location.hasServicesEnabledAsync())) {
    throw new GpsUnavailable("Location is switched off on this phone. Turn it on and try again.");
  }
}

function toFix(location: Location.LocationObject): Fix {
  return {
    longitude: location.coords.longitude,
    latitude: location.coords.latitude,
    accuracy: location.coords.accuracy,
    timestamp: location.timestamp,
  };
}

/** Streams readings (about one a second) until the returned function is called. */
export async function watchFixes(onFix: (fix: Fix) => void, onError: (message: string) => void): Promise<() => void> {
  await ensureGps();
  const subscription = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.BestForNavigation, timeInterval: 1000, distanceInterval: 0 },
    (location) => onFix(toFix(location)),
    (reason) => onError(String(reason)),
  );
  return () => subscription.remove();
}

/** One reading, for geotagging a photo. Null if the phone can't give one. */
export async function currentFix(): Promise<Fix | null> {
  try {
    await ensureGps();
    return toFix(await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }));
  } catch {
    return null;
  }
}

/** One reading, to show where the phone is on the map. Throws GpsUnavailable with the reason. */
export async function locateOnce(): Promise<Fix> {
  await ensureGps();
  try {
    return toFix(await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }));
  } catch {
    throw new GpsUnavailable("The phone couldn't find its position. Try again in the open, away from tall buildings.");
  }
}
