# Project files (.spp)

*Physical planners and district administrators.*

A `.spp` file is a whole project in one protected file. Use it to keep a copy of an unfinished plan, to move a project to another office's server, or to hand a project to a colleague in another district.

Only this platform can open a `.spp` file, and only on a server that holds your organisation's key. Other programs (QGIS, a zip tool, a database viewer) can't read anything in it. To give data to other software, use **Export** instead (see [Importing and exporting data](import-export.md)).

## Your work is saved as you go
Every change you make in a project is saved on the server straight away, so there is no "save" step and nothing is lost if you close the browser. A `.spp` file is a copy of the project at the moment you save the file.

## What a file contains
- every layer with its features, in the layer's own coordinate system, exactly as stored;
- attributes, field definitions and styles;
- each feature's earlier versions (its history);
- the planning area and its status;
- the readiness checklist: statuses, notes, due dates and attached documents;
- the list of basemaps the district uses.

It does **not** contain basemap API keys, user accounts or passwords.

## Saving a file
Open the project and choose **Save as .spp** at the top. The file downloads with the project's name and the date and time.

## Opening a file
1. Go to **Projects**.
2. Under **Open a project file (.spp)**, choose the file.
3. When it finishes, a summary shows what was created, with a link to the project.

Opening always makes a **new project** in the district you're working in. Nothing that already exists is changed.
- If a project with the same name is already there, the new one gets a number after its name, for example "Kasoa local plan (2)".
- If the project used a custom coordinate system that this district doesn't have, it is added to the district.
- Basemaps the district doesn't have are added if you are a district administrator. Otherwise the summary lists them so an administrator can add them. Basemaps that need a key must have the key entered again.
- Checklist owners are kept when the same person (by email) is a member of this district.

## If a file won't open
| Message | What it means |
|---|---|
| "…protected with the organisation key '…', which this server doesn't have" | The file was saved on a server with a different key. Ask your system administrator: the two servers need to share a key. |
| "The file's key couldn't be unlocked…" | This server has a key with the same name, but it isn't the same key. |
| "The file is damaged or has been altered…" | The file changed after it was saved (a bad copy or download, or someone edited it). Get a fresh copy. |
| "This isn't a .spp project file." | The file is something else, such as a shapefile or a zip. Use **Import data** for those. |
| "…made by a newer version of the platform" | Update this server, then open the file again. |
| "…uses EPSG:…, which isn't enabled on this server" | A system administrator must enable that coordinate system first. |

## Who can do this
Planners and district administrators can save and open files. Every save and open is recorded with who did it and when.
