# Field data in the office: sync, conflicts and ground-truthing

*Physical planners and district administrators.*

Field officers capture data on the [field app](field-app.md) and sync it. This page covers what you see in the web app.

## What arrives from the field
New features appear in their layer as soon as the officer syncs. Click one on the map: its details show that it was **recorded in the field**, by whom, when, how (GPS point, GPS walk, or drawn) and the GPS accuracy, with links to its **photos**.

GPS positions arrive as latitude and longitude. The server converts them to the layer's coordinate system, with the same conversion used everywhere else on the platform.

## Using a walked boundary as the planning area
If an officer walked the edge of the community with GPS (as a polygon in any polygon layer), click that feature and choose **Use as the planning area**. It becomes the project's draft boundary, recorded as made from a GPS walk. Check its accuracy before you rely on it: phone GPS is usually good to a few metres, not to survey standard.

## Conflicts
A conflict happens when an officer changes a feature on the phone, and someone changes the same feature in the office before the officer syncs. The platform never guesses: the office's version stays as it is, and the officer's version waits for a decision.

Open **Field conflicts** at the top of the project (the number shows how many are waiting) and choose **Compare**. Each field shows the office value and the field value side by side; the ones that differ are highlighted.

| Choice | Result |
|---|---|
| **Keep the office version** | Nothing changes. The field version is set aside. |
| **Keep the field version** | The officer's values replace the office's. |
| **Save the values picked above** | For each field that differs, pick office or field, then save. Tick the shape box to take the officer's shape as well. |

Whatever you choose is saved as a new version, so the feature's history keeps both sides. The officer's phone picks up the result at their next sync. Planners and district administrators can resolve conflicts; everyone in the district can see them.

## Ground-truthing: sending features to be checked
On the [readiness checklist](readiness-checklist.md), open a map-layer item and choose **Send to field**. This makes a task for every feature in the item's layer that isn't verified yet. Officers receive the tasks at their next sync and answer each one:

- **Confirmed** or **corrected:** the feature is marked verified (a correction also arrives as a normal change to the feature).
- **Not found:** the feature is left as it is for you to look into.

The item's **Verified** measure rises as answers come in. Choosing **Send to field** again only sends features that still aren't verified and aren't already out.

## If something looks wrong
- **A capture hasn't arrived:** the officer may not have synced, or the server refused it (the phone shows the reason). Nothing is lost on the phone until it is sent.
- **A photo is missing:** photos upload after the feature, in pieces. On a poor connection they can take a few syncs.
- **A feature was deleted in the office:** phones remove it at their next sync, unless the officer has unsent changes to it.
