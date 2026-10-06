#!/usr/bin/env bash
#
# Build the Spatial Field app as a release APK.
#
#   ./build-apk.sh             build with the current version
#   ./build-apk.sh --bump      raise the version first (0.1.0 -> 0.1.1, code 1 -> 2)
#   ./build-apk.sh --aab       build an app bundle (.aab) for Google Play instead
#
# Signing: set SPATIAL_KEYSTORE, SPATIAL_KEYSTORE_PASSWORD and SPATIAL_KEY_ALIAS
# to sign with the Assembly's own key (docs/ops/field-app-distribution.md).
# Without them the build is signed with the standard debug key: fine for
# trying the app, not for giving to staff.
#
# Installs whatever is missing, into your home folder only (no sudo):
#   - Java 17 (Eclipse Temurin)                 -> ~/.local/jdk-17
#   - Android command-line tools, SDK 36,
#     build-tools 36.0.0, NDK 27.1              -> ~/Android/Sdk
# Anything already present is reused, so later runs only build.
#
# The android/ folder is generated from app.json by Expo each time (don't edit
# it by hand). The APK is signed with Expo's standard debug key, the same on
# every build, so each build installs over the last. A Play Store release
# needs its own signing key.
# Output: android/app/build/outputs/apk/release/Spatial_Field-<version>.apk

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$APP_DIR/android"
JDK_DIR="${JDK_DIR:-$HOME/.local/jdk-17}"
SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
CMDLINE_TOOLS_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
JDK_URL="https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
SDK_PACKAGES=("platform-tools" "platforms;android-36" "build-tools;36.0.0" "ndk;27.1.12297006")

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✔\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

BUMP=false
AAB=false
for arg in "$@"; do
  case "$arg" in
    --bump) BUMP=true ;;
    --aab) AAB=true ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) die "Unknown option: $arg (use --bump, --aab or --help)" ;;
  esac
done
if [[ -n "${SPATIAL_KEYSTORE:-}" ]]; then
  [[ -f "$SPATIAL_KEYSTORE" ]] || die "SPATIAL_KEYSTORE=$SPATIAL_KEYSTORE doesn't exist."
  [[ -n "${SPATIAL_KEYSTORE_PASSWORD:-}" && -n "${SPATIAL_KEY_ALIAS:-}" ]] || die "Set SPATIAL_KEYSTORE_PASSWORD and SPATIAL_KEY_ALIAS too."
  export SPATIAL_KEYSTORE_PASSWORD  # apksigner reads it from the environment
fi

# ── 1. Basic tools ────────────────────────────────────────────────────────────
step "Checking basic tools"
for tool in curl unzip tar node npm python3; do
  command -v "$tool" >/dev/null 2>&1 || die "'$tool' is not installed. Install it first (e.g. sudo apt install $tool)."
done
ok "curl, unzip, tar, python3, node $(node -v), npm"

# ── 2. Java 17 ────────────────────────────────────────────────────────────────
step "Java 17"
java_major() { "$1" -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -1; }
JAVA_BIN=""
if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/java" && "$(java_major "$JAVA_HOME/bin/java")" == "17" ]]; then
  JAVA_BIN="$JAVA_HOME/bin/java"
elif command -v java >/dev/null 2>&1 && [[ "$(java_major "$(command -v java)")" == "17" ]]; then
  JAVA_BIN="$(command -v java)"
  JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$JAVA_BIN")")")"
elif [[ -x "$JDK_DIR/bin/java" ]]; then
  JAVA_HOME="$JDK_DIR"
  JAVA_BIN="$JDK_DIR/bin/java"
else
  echo "    Downloading Java 17 (about 190 MB)…"
  tmp="$(mktemp -d)"
  curl -fSL --progress-bar -o "$tmp/jdk.tar.gz" "$JDK_URL"
  mkdir -p "$JDK_DIR"
  tar -xzf "$tmp/jdk.tar.gz" -C "$JDK_DIR" --strip-components=1
  rm -rf "$tmp"
  JAVA_HOME="$JDK_DIR"
  JAVA_BIN="$JDK_DIR/bin/java"
fi
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"
ok "$("$JAVA_BIN" -version 2>&1 | head -1)  ($JAVA_HOME)"

# ── 3. Android SDK ────────────────────────────────────────────────────────────
step "Android SDK"
SDKMANAGER="$SDK_DIR/cmdline-tools/latest/bin/sdkmanager"
if [[ ! -x "$SDKMANAGER" ]]; then
  echo "    Downloading Android command-line tools (about 150 MB)…"
  tmp="$(mktemp -d)"
  curl -fSL --progress-bar -o "$tmp/cmdtools.zip" "$CMDLINE_TOOLS_URL"
  mkdir -p "$SDK_DIR/cmdline-tools"
  unzip -q "$tmp/cmdtools.zip" -d "$tmp"
  rm -rf "$SDK_DIR/cmdline-tools/latest"
  mv "$tmp/cmdline-tools" "$SDK_DIR/cmdline-tools/latest"
  rm -rf "$tmp"
fi
export ANDROID_HOME="$SDK_DIR"
export ANDROID_SDK_ROOT="$SDK_DIR"
export PATH="$SDK_DIR/cmdline-tools/latest/bin:$SDK_DIR/platform-tools:$PATH"
ok "command-line tools in $SDK_DIR"

echo "    Accepting Android SDK licences…"
yes | "$SDKMANAGER" --sdk_root="$SDK_DIR" --licenses >/dev/null 2>&1 || true

missing=()
for pkg in "${SDK_PACKAGES[@]}"; do
  dir="$SDK_DIR/${pkg//;//}"
  [[ -d "$dir" ]] || missing+=("$pkg")
done
if (( ${#missing[@]} )); then
  echo "    Installing: ${missing[*]} (the NDK is about 1 GB — this is the slow part)…"
  "$SDKMANAGER" --sdk_root="$SDK_DIR" "${missing[@]}"
fi
ok "SDK 36, build-tools 36.0.0, NDK 27.1 installed"

# ── 4. JavaScript dependencies ────────────────────────────────────────────────
step "App dependencies"
if [[ ! -d "$APP_DIR/node_modules/react-native" ]]; then
  echo "    node_modules missing — running npm install…"
  (cd "$APP_DIR" && npm install)
fi
ok "node_modules present"

# ── 5. Version (kept in app.json) ─────────────────────────────────────────────
read_version() { python3 -c 'import json,sys; e=json.load(open(sys.argv[1]))["expo"]; print(e["version"], e["android"]["versionCode"])' "$APP_DIR/app.json"; }
read -r name code <<<"$(read_version)"
if $BUMP; then
  step "Raising the version"
  python3 - "$APP_DIR/app.json" "$APP_DIR/package.json" <<'PY'
import json, sys
app = json.load(open(sys.argv[1]))
expo = app["expo"]
major, minor, patch = expo["version"].split(".")
expo["version"] = f"{major}.{minor}.{int(patch) + 1}"
expo["android"]["versionCode"] += 1
json.dump(app, open(sys.argv[1], "w"), indent=2); open(sys.argv[1], "a").write("\n")
package = json.load(open(sys.argv[2]))
package["version"] = expo["version"]
json.dump(package, open(sys.argv[2], "w"), indent=2); open(sys.argv[2], "a").write("\n")
PY
  old="$name (code $code)"
  read -r name code <<<"$(read_version)"
  ok "$old → $name (code $code)"
fi

# ── 6. Android project from app.json ──────────────────────────────────────────
step "Generating the Android project"
(cd "$APP_DIR" && npx expo prebuild --platform android --no-install)
echo "sdk.dir=$SDK_DIR" > "$ANDROID_DIR/local.properties"
ok "android/ generated; local.properties → $SDK_DIR"

# ── 7. Build ──────────────────────────────────────────────────────────────────
TASK=assembleRelease; KIND=APK
if $AAB; then TASK=bundleRelease; KIND="app bundle"; fi
step "Building release $KIND — version $name (code $code)"
cd "$ANDROID_DIR"
chmod +x ./gradlew
# Slow or patchy connections: wait longer per download and retry the build.
# Gradle keeps what it already downloaded, so each retry carries on from there.
GRADLE_NET=(-Dorg.gradle.internal.http.socketTimeout=180000
            -Dorg.gradle.internal.http.connectionTimeout=180000
            -Dorg.gradle.internal.repository.max.retries=5)
for attempt in 1 2 3 4 5; do
  if ./gradlew "${GRADLE_NET[@]}" "$TASK"; then break; fi
  (( attempt == 5 )) && die "Build failed 5 times. If it was the network, run ./build-apk.sh again — downloads resume."
  echo "    Build attempt $attempt failed — retrying in 15 s (downloads so far are kept)…"
  sleep 15
done

if $AAB; then
  AAB_IN="$ANDROID_DIR/app/build/outputs/bundle/release/app-release.aab"
  [[ -f "$AAB_IN" ]] || die "Build finished but $AAB_IN was not found."
  AAB_OUT="$ANDROID_DIR/app/build/outputs/bundle/release/Spatial_Field-$name.aab"
  cp "$AAB_IN" "$AAB_OUT"
  step "Done"
  if [[ -n "${SPATIAL_KEYSTORE:-}" ]]; then
    jarsigner -keystore "$SPATIAL_KEYSTORE" -storepass "$SPATIAL_KEYSTORE_PASSWORD" "$AAB_OUT" "$SPATIAL_KEY_ALIAS" >/dev/null
    ok "Signed with $SPATIAL_KEY_ALIAS from $SPATIAL_KEYSTORE"
  else
    echo "    Signed with the debug key: Google Play won't accept it. Set SPATIAL_KEYSTORE (see --help)."
  fi
  ok "App bundle: $AAB_OUT"
  ok "Size: $(du -h "$AAB_OUT" | cut -f1)"
  exit 0
fi

APK_IN="$ANDROID_DIR/app/build/outputs/apk/release/app-release.apk"
[[ -f "$APK_IN" ]] || die "Build finished but $APK_IN was not found."
APK_OUT="$ANDROID_DIR/app/build/outputs/apk/release/Spatial_Field-$name.apk"
cp "$APK_IN" "$APK_OUT"

step "Done"
ok "APK: $APK_OUT"
ok "Size: $(du -h "$APK_OUT" | cut -f1)"
APKSIGNER="$SDK_DIR/build-tools/36.0.0/apksigner"
if [[ -n "${SPATIAL_KEYSTORE:-}" ]]; then
  [[ -x "$APKSIGNER" ]] || die "apksigner not found at $APKSIGNER."
  "$APKSIGNER" sign --ks "$SPATIAL_KEYSTORE" --ks-key-alias "$SPATIAL_KEY_ALIAS" \
    --ks-pass env:SPATIAL_KEYSTORE_PASSWORD --key-pass env:SPATIAL_KEYSTORE_PASSWORD "$APK_OUT"
  ok "Signed with $SPATIAL_KEY_ALIAS from $SPATIAL_KEYSTORE"
else
  echo "    Signed with the debug key: fine for trying the app, not for giving to staff (see --help)."
fi
if [[ -x "$APKSIGNER" ]]; then
  cert="$("$APKSIGNER" verify --print-certs "$APK_OUT" 2>/dev/null | sed -n 's/.*certificate SHA-256 digest: //p' | head -1)"
  ok "Signed, certificate SHA-256: ${cert:-unknown}"
fi
