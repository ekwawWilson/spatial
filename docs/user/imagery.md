# Drone and satellite imagery

*Physical planners and district administrators.*

The Assembly's own images can be loaded into a project: a drone orthophoto as a background map, and an elevation model for contour lines. Open **Imagery** at the top of the project.

## What you can upload
A **GeoTIFF** (`.tif`), up to 500 MB. It must be:
- **georeferenced:** the file itself says where on the ground it is. Drone software (Pix4D, DroneDeploy, WebODM, Agisoft) exports this as "orthomosaic GeoTIFF";
- **north-up** (not rotated);
- in a **known coordinate system**. If the file doesn't say which, choose it in the upload form.

Ordinary photos (JPEG from the drone's card) can't be used: they must be processed into an orthomosaic first.

## Uploading
1. Choose the file and the **kind**: orthophoto, or elevation model.
2. Give it a name, the date it was **captured**, and who captured it. If the file carries a capture date, it is filled in for you.
3. Choose **Upload**. The image is checked and converted in the background; the list shows **Ready** when it is done, or **Failed** with the reason.

The image is stored in its own coordinate system and is not altered. The map draws it in place alongside your layers.

## Using an orthophoto
- **As a basemap:** it appears in the project's **Basemap** list as "*name* (imagery)", for everyone in the district.
- **In the field, offline:** because it is the Assembly's own data, it may be stored on phones. When a field officer downloads the project, the image is offered as an **offline basemap**, covering the planning area. Set the planning area first.
- **On the readiness checklist:** the "Recent imagery" item shows how many images the project has, the newest capture date and the pixel size. It can be marked ready when the newest image is under 12 months old. Correct a wrong capture date in the imagery list.

## Elevation models and contours
Upload a single-band elevation GeoTIFF (a DSM or DTM from the drone software) as kind **Elevation model**. When it is ready, enter a **contour interval** (in the model's height units, usually metres) and choose **Make contours**.

The lines go into a layer called **Topography (contours)**, in the project's coordinate system, each with its elevation. Making contours again replaces the earlier lines. The checklist's topography item picks the layer up by its name.

A drone surface model includes roofs and trees, so its contours follow them. For ground contours, use a terrain model (DTM) if your software produces one.

## If an upload fails
| Message | What to do |
|---|---|
| "The image isn't georeferenced…" | Export it from the drone software as a GeoTIFF orthomosaic. |
| "The image doesn't say which coordinate system it uses…" | Upload again and choose the coordinate system. |
| "The image is rotated…" | Export it north-up. |
| "An elevation model has one band…" | You uploaded a colour image as an elevation model. Choose kind Orthophoto. |
| "…isn't enabled on this server" (when making contours) | A system administrator must enable that coordinate system. |

## Who can do this
Planners and district administrators upload, edit and delete imagery. Everyone in the district can see it.
