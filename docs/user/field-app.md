# The field app (Android)

*Field officers, planners and district administrators.*

The field app lets you take a project out of the office, see its layers with no connection, and record new features with the phone's GPS, a form and photos.

What you capture is saved on the phone straight away and sent to the office when you **sync**. Nothing is lost if there is no connection: it waits on the phone.

## Before you go out
You need a connection for these steps.
1. Open the app. Enter the **server address** your administrator gave you, your **email** and **password**, and sign in.
2. Choose **Download a project**. Pick the project, tick the layers you need, and choose **Download**.
3. If an **offline basemap** is listed, download it too.

Only features inside the project's planning area are downloaded. If the project has no planning area yet, all features come.

After you have signed in once with a connection, the same email and password also work with no connection.

## The offline background map
Google, Bing, Esri and OpenStreetMap don't allow their maps to be stored on a phone. The Assembly's own imagery can be: when the office has [uploaded a drone image](imagery.md) for the project, it is offered as an **offline basemap** after you download the project. Without one, your layers show on a plain background when there is no connection. When you do have a connection and no offline basemap, OpenStreetMap shows behind your layers.

## On the map
- **Tap a feature** to see its details. **Details and photos** opens its form.
- **Layers** (top right) shows or hides layers.
- **My location** (the crosshair, top right) shows where you are as a blue dot and moves the map there.
- **Measure** gives a distance or an area as you tap points. These are measured on the phone, for guidance.

## Capturing
Choose **Capture**, pick the layer, then how:

| Method | Use it for | What happens |
|---|---|---|
| **From GPS** | a point | The app takes 5 readings and averages them, counting the more accurate ones for more. Stand still until it finishes. |
| **Walk it with GPS** | a line or the edge of an area | Walk the line. A point is recorded every 2 m. You can pause, undo the last point, and finish. |
| **Draw on the map** | anything | Tap where the point is, or tap each corner in order. |

Readings worse than ±50 m are ignored. If every reading is that poor, move into the open and try again.

Then fill in the **form**. Fields marked * are required. Add **notes** and **photos** if useful, and choose **Save on this device**.

Each GPS capture stores its accuracy, the time and how many readings it used. Each photo stores where it was taken.

## Sending your work to the office (sync)
When you have a connection, choose **Sync** on the project (projects screen), or **Send to the office now** in the captured list. Sync does three things:
1. sends your new captures, your changes and your ground-truthing answers;
2. uploads photos;
3. brings back what changed in the office, including features deleted there and new features to check.

If the connection drops partway, just sync again. It carries on from where it stopped: nothing is sent twice, and a photo resumes from the part already uploaded.

The list button (top right of the map) shows what is still waiting on the phone:

| Shown as | Meaning |
|---|---|
| **new** / **changed** | Not sent yet. Sync when you have a connection. |
| **conflict: with the office** | Someone in the office changed the same feature before your change arrived. Your version is safe with the office, and a planner decides which to keep. The phone gets the result at a later sync. |
| **Refused: …** | The server wouldn't accept it, for the reason shown (for example a required answer is missing). Open it, fix it, and sync again. |

You can open anything in the list to correct the form, add photos, or delete a capture you made by mistake (before it is sent).

## Checking features on the ground
The office can ask for features to be checked. They arrive when you sync, and the clipboard button on the map lists them. For each one, go to the feature and choose:

| Button | When |
|---|---|
| **Correct as recorded** | It is there and the details are right. |
| **Needs correcting** | It is there but something is wrong. Fix the form and save. |
| **Not found** | It isn't there. |

Your answers go to the office at the next sync. Features you confirm or correct are marked as verified.

## Storage
**Device** (on the projects screen) shows free space and how much the packages, basemaps and photos use. The app warns you when space is low. A project can't be removed from the phone while it holds anything that hasn't been sent.

## Positions and coordinates
The app shows positions in the project's coordinate system (for example Ghana National Grid). These are for you to read in the field. The official coordinates are worked out on the server from the GPS position when captures are sent.
