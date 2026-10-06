# Field app (Android)

A placeholder until **Phase 9** builds it.

The app will be an **Expo (React Native)** project, laid out like the hirepurchase mobile app: `App.tsx`, `src/screens`, `src/services`, `src/contexts`, `src/navigation`, a prebuilt `android/` folder and a `build-apk.sh` that builds a release APK on a developer machine.

It shares `@spatial/map-core`'s API client, types and coordinate maths with the web app. The map itself is MapLibre (native), because the web app's OpenLayers map only runs in a browser.
