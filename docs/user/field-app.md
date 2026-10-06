# The field app (Android)

*Field officers, planners and district administrators.*

The field app lets you take a project out of the office, see its layers with no connection, and record new features with the phone's GPS, a form and photos.

**In this version, what you capture stays on the phone.** Sending it to the office (sync) comes in the next version. Until then, don't uninstall the app or clear its data, or the captures are lost.

## Before you go out
You need a connection for these steps.
1. Open the app. Enter the **server address** your administrator gave you, your **email** and **password**, and sign in.
2. Choose **Download a project**. Pick the project, tick the layers you need, and choose **Download**.
3. If an **offline basemap** is listed, download it too.

Only features inside the project's planning area are downloaded. If the project has no planning area yet, all features come.

After you have signed in once with a connection, the same email and password also work with no connection.

## The offline background map
Google, Bing, Esri and OpenStreetMap don't allow their maps to be stored on a phone. So with no connection, your layers show on a plain background unless the Assembly has its own imagery (for example drone photos) that an administrator has added and marked as allowed offline. When you do have a connection and no offline basemap, OpenStreetMap shows behind your layers.

## On the map
- **Tap a feature** to see its details. **Details and photos** opens its form.
- **Layers** (top right) shows or hides layers.
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

## Seeing what you've captured
The list button (top right of the map) shows everything captured or changed on the phone that hasn't been sent yet. You can open any of them to correct the form, add photos, or delete a capture you made by mistake.

## Storage
**Device** (on the projects screen) shows free space and how much the packages, basemaps and photos use. The app warns you when space is low. A project can't be removed from the phone while it holds captures that haven't been sent.

## Positions and coordinates
The app shows positions in the project's coordinate system (for example Ghana National Grid). These are for you to read in the field. The official coordinates are worked out on the server from the GPS position when captures are sent.
