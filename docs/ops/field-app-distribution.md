# Distributing the field app

*Whoever builds and hands out the Android app.*

## Building
```bash
cd apps/mobile
./build-apk.sh              # an APK to install directly
./build-apk.sh --bump       # raise the version first, so phones accept it as an update
./build-apk.sh --aab        # an app bundle (.aab), the format Google Play requires
```
The first run downloads Java and the Android SDK into your home folder.

## The signing key
Android only installs an update over an app signed with the **same key**.

- By default the script signs with the standard debug key that every React Native project carries. That is fine for trying the app, and builds install over each other, but **anyone can sign with that key**. Don't use it for an app given to staff.
- For real use, make the Assembly's own key once:
  ```bash
  keytool -genkeypair -v -storetype PKCS12 -keystore ~/spatial-field-release.keystore \
    -alias spatial-field -keyalg RSA -keysize 2048 -validity 10000
  ```
  and build with it:
  ```bash
  export SPATIAL_KEYSTORE=~/spatial-field-release.keystore
  export SPATIAL_KEYSTORE_PASSWORD='...'
  export SPATIAL_KEY_ALIAS=spatial-field
  ./build-apk.sh --bump
  ```
  **Keep the keystore file and its password safe, with a copy off the computer.** If it is lost, phones can never be updated in place again: every officer would have to uninstall (losing unsynced captures) and reinstall.

Changing from the debug key to the Assembly's key is such a break. Do it before the app goes to staff.

## Option 1: hand out the APK (side-loading)
Simplest for one Assembly.
1. Put the APK where staff can get it: a shared drive, or send it directly.
2. On each phone: open the file, allow "install unknown apps" for the app used to open it when asked, and install.
3. For an update, build with `--bump` and hand out the new APK. Installing it keeps the data on the phone.

Tell officers to **sync before updating**, as a precaution.

## Option 2: Google Play
For many devices, or automatic updates.
1. A Google Play developer account for the Assembly (a one-off fee, paid to Google).
2. Build with `--aab` and the Assembly's key, and upload it. An **internal testing** or **closed testing** track limits it to listed staff accounts, which suits an internal tool.
3. Google reviews the app. Its listing must explain why it uses location and the camera (to record where features are and to photograph them).

## iPhones and iPads
Not built. The app is written with Expo, which also targets iOS, but building for iOS needs a Mac, an Apple developer account, and testing on a device. The map and database libraries used support iOS. Treat it as a separate piece of work.

## High-accuracy GPS receivers (RTK GNSS)
The app uses whatever position Android provides. External receivers (Emlid, Trimble Catalyst, and similar) come with their own Android app that feeds the receiver's position to the phone in place of the built-in GPS ("mock location"). With that set up, the field app records the receiver's positions and its reported accuracy with no change.

This has **not been tested with a receiver**. Check before relying on it: capture a point on a known control mark and compare.

Phone GPS alone is usually good to 3-5 metres in the open. That suits locating buildings and facilities, not surveying parcel corners.
