# Spatial Field (Android field app)

An **Expo (React Native)** app for field officers: download a project while connected, then view its layers, capture features from GPS or by drawing, fill in forms and take photos with no connection.

Laid out like the hirepurchase mobile app: `App.tsx`, then `src/screens`, `services`, `contexts`, `navigation`, `constants`, `utils`, `types`.

## What it does (Phase 9)
- Sign in with a platform account. After one sign-in with a connection, the same email and password also work offline.
- Download a project's chosen layers (features inside the planning area) into the phone's own database.
- Offline map: layers in the office's styles, a layer list, tap a feature for its details, measure distance and area.
- Capture points (average of 5 GPS readings), lines and areas (walk them, or tap corners on the map). GPS accuracy, time and number of readings are stored with each capture.
- Forms come from each layer's fields: required fields, pick-lists, defaults, type checks.
- Photos from the camera, shrunk and compressed, tagged with where they were taken. Notes.
- Storage: free space, package and photo sizes, and a warning when space is low.

**Not yet:** sending captures to the office (sync) is Phase 10. Until then captures stay on the device.

## Build an APK
```bash
./build-apk.sh           # build
./build-apk.sh --bump    # raise the version first
```
The first run downloads Java 17 and the Android SDK into your home folder if they aren't there (no sudo). The APK lands in `android/app/build/outputs/apk/release/`.

The `android/` folder is generated from `app.json` on every build. Don't edit it; change `app.json` instead.

## Develop
```bash
npm install
npm run typecheck
npm test
npx expo run:android     # needs a phone or emulator; this app can't run in Expo Go
```
The map (MapLibre) and the database need native code, so Expo Go won't work. Use a built APK or `expo run:android`.

This folder is a standalone npm project. It is not part of the repository's pnpm workspace.

## Where things are
| Path | What |
|---|---|
| `src/services/api.ts` | calls to the server |
| `src/services/db.ts` | the phone's database (SQLite) |
| `src/services/gps.ts`, `files.ts` | GPS, photos, offline basemap files |
| `src/utils/geo.ts`, `forms.ts`, `verifier.ts`, `mapStyle.ts` | logic with unit tests in `__tests__/` |
| `src/screens/map/MapScreen.tsx` | the map, identify, measure, capture |
| `src/screens/capture/CaptureFormScreen.tsx` | the form, notes and photos |
