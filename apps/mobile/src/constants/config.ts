export const APP_CONFIG = {
  name: "Spatial Field",
  /** Shown on the sign-in screen until the user enters their server's address. */
  defaultServer: "",
  /** GPS readings averaged for one point, unless the user changes it. */
  defaultAveraging: 5,
  /** Warn when the device has less free space than this. */
  lowStorageBytes: 200 * 1024 * 1024,
  /** Longest side of a stored photo, in pixels. */
  photoMaxSide: 1600,
  photoQuality: 0.7,
  /** Walk mode records a position when the device has moved this far (metres). */
  trackMinDistance: 2,
  /** Readings worse than this (metres) are ignored when averaging or tracking. */
  maxUsableAccuracy: 50,
};
