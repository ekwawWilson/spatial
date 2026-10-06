# Phase 9 QA: the field app on a device

**Status: open.** The automated checks cover the server side and the app's logic. This check needs an Android phone or tablet, and has not been done yet.

## Set-up
1. Build the APK: `cd apps/mobile && ./build-apk.sh`. Copy it to the phone and install it.
2. On the server, have a project with a planning area and at least two layers (one point, one polygon) with a required field and a pick-list field.

## The gate test (airplane mode)
| # | Step | Expected | Result |
|---|---|---|---|
| 1 | Sign in with a connection | Projects screen opens | |
| 2 | Download the project with both layers | "On this device" shows the feature count and size | |
| 3 | Turn on **airplane mode** | | |
| 4 | Close the app fully, reopen, sign in | Signs in offline; the project is listed | |
| 5 | Open the map | Layers draw in the office's colours; the planning area shows as a dashed line | |
| 6 | Tap a feature | Its attributes show | |
| 7 | Measure a distance and an area | Sensible values in metres and the project's units | |
| 8 | Capture 10 points from GPS, each with a photo | Each shows ±accuracy and "5 readings"; the form refuses a missing required field | |
| 9 | Walk a polygon and a line | The track draws as you walk; both save | |
| 10 | Draw 8 more features on the map | They save | |
| 11 | Close the app fully and reopen (still in airplane mode) | All 20 captures and their photos are still there (list button on the map) | |
| 12 | Open one capture | Accuracy, time and readings are recorded; photos open | |
| 13 | Device screen | Free space, package size and photo size are shown | |
| 14 | Try to remove the project | Refused, because it holds unsent captures | |

## Offline basemap from drone imagery (Phase 11)
| # | Step | Expected | Result |
|---|---|---|---|
| 15 | In the web app, upload a drone orthophoto to the project (Imagery) and set the planning area | The image is Ready | |
| 16 | On the phone, download the project again; choose the offline basemap offered | It downloads; the size is shown | |
| 17 | Airplane mode; open the map | The drone image shows behind the layers, lined up with them | |

Also run steps 1–7 and 10–11 on an emulator (GPS can be simulated there).

## Record
- Device and Android version:
- Date and tester:
- Problems found:
