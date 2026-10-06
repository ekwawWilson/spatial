# Phase 10 QA: sync on a device

**Status: open.** The server side of sync is covered by automated tests. The phone side has unit tests for its decisions, but the full round trip needs an Android phone and has not been done yet.

Do the [Phase 9 device check](phase-9-field-app-on-device.md) first.

## Steps
| # | Step | Expected | Result |
|---|---|---|---|
| 1 | Capture 3 features offline (one with 2 photos), go online, **Sync** | Summary says 3 sent, 2 photos uploaded | |
| 2 | Open the project in the web app | The 3 features are there; clicking one shows who recorded it, the GPS accuracy and the photos | |
| 3 | Sync again straight away | "nothing to send"; no duplicates on the web | |
| 4 | Edit a feature's attribute in the web app, then **Sync** on the phone | The phone shows the new value | |
| 5 | Delete a feature in the web app, then **Sync** | It disappears from the phone's map | |
| 6 | Conflict: edit feature A on the phone (don't sync). Edit A in the web app. Sync the phone | Phone shows A as "conflict: with the office"; the web shows 1 field conflict | |
| 7 | Resolve it in the web app with each option in turn (repeat step 6 for each) | The web feature matches the choice; after the next phone sync the phone matches too | |
| 8 | Take a photo, start **Sync**, and turn on airplane mode while "Uploading photo" shows | An error about the connection; the capture is still listed | |
| 9 | Turn airplane mode off, **Sync** | The photo finishes; on the web there is one photo, and it opens correctly | |
| 10 | In the web app, **Send to field** on a checklist item with a layer. Sync the phone | The clipboard list shows the features to check | |
| 11 | Answer one of each: correct as recorded, needs correcting, not found. Sync | The web checklist's Verified measure rises; the corrected feature shows the new values | |
| 12 | On the web, click a polygon walked with GPS and choose **Use as the planning area** | It becomes the project's draft planning area | |

## Record
- Device and Android version:
- Date and tester:
- Problems found:
