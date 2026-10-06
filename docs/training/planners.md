# Course for planners and administrators (2 days)

By the end, each trainee has taken one community from nothing to a project with a planning area, layers, a checklist under way and its relationships worked out.

**Each trainee needs:** a computer with a current browser, an account, and the practice files.

## Day 1

### Session 1: finding your way (45 min)
Guide: [Signing in](../user/signing-in.md), [Projects, layers and the map](../user/projects-and-layers.md).

**Exercise 1.** Sign in. Create a project named after yourself. Note which coordinate system it uses.
*You should have:* an empty map with the project's name at the top, and "EPSG:2136" beside it.

### Session 2: coordinate systems (45 min)
Guide: [Coordinate systems](../user/coordinate-systems.md).
Explain: the Ghana National Grid in feet; GPS gives latitude and longitude; converting between them has a stated accuracy of a few metres unless better parameters are supplied.

**Exercise 2.** In Coordinate systems, convert the point E 1,190,600 N 337,700 (Ghana National Grid) to latitude and longitude. Read out the accuracy the page states.
*You should have:* about 5.6000° north, 0.2001° west (in Accra), and the same answer as everyone else.

### Session 3: bringing data in (1 h 30)
Guide: [Importing and exporting data](../user/import-export.md).

**Exercise 3.** Import `shp/buildings.zip`. Then import `sample.dxf` and notice what the wizard asks for that the shapefile didn't.
*You should have:* a buildings layer with 6 features; and you can explain why the CAD file needed its coordinate system confirmed.

**Exercise 4.** Import `sample.gpkg` and take the parcels, streets, communities, drains and flood zones as separate layers. Set a colour for each. Colour the parcels by land use.
*You should have:* six layers, each a different colour, drawn in a sensible order (areas at the bottom, lines and points on top).

### Session 4: the planning area (1 h 30)
Guide: [Editing features and making the planning area](../user/editing-and-boundaries.md).

**Exercise 5.** Make the planning area three ways, replacing it each time: draw it around the parcels with snapping on; type four corner coordinates; enter a traverse of four legs from bearings and distances.
*You should have:* an area and perimeter each time, and for the traverse a closing error and an accuracy ratio. Say whether 1 in 5,000 is good enough.

**Exercise 6.** Mark the planning area as agreed. Try to edit it. Ask the administrator in your group to approve it.
*You should have:* seen that an agreed boundary is locked, and that only an administrator approves.

### Session 5: editing and history (1 h)
**Exercise 7.** Draw a new building snapped to a parcel corner. Move a vertex. Undo, redo. Change an attribute in the table. Open the feature's history and restore its first version.
*You should have:* the feature back as it started, with every step still listed in its history.

## Day 2

### Session 6: the readiness checklist (1 h 30)
Guide: [The readiness checklist](../user/readiness-checklist.md).

**Exercise 8.** Open the checklist. Attach any PDF to "Assembly decision to prepare the plan" and mark it ready. Open "Buildings and land use": read its measures and what it still needs.
*You should have:* a score above 0%, and you can say why the buildings item can't be marked ready yet.

**Exercise 9 (administrators).** Customise the district's template: add an item "Chief's written consent". Create a new project and check the item is there.

### Session 7: imagery (45 min)
Guide: [Drone and satellite imagery](../user/imagery.md).

**Exercise 10.** Upload `drone_ortho.tif`. When it is ready, choose it as the basemap and zoom to the buildings.
*You should have:* the image behind your layers, with building outlines sitting on the light squares.

### Session 8: relationships and standards (1 h 30)
Guide: [Relationships between features](../user/relationships.md).

**Exercise 11.** Open Relationships. Check the suggested layers, save, and run.
*You should have:* 6 properties, 1 in a flood-prone area, 1 breaking a standard. Find which building floods and which breaks the setback.

**Exercise 12.** Show the drain links. Confirm one and reject one. Run again.
*You should have:* your two decisions unchanged after the run.

**Exercise 13 (administrators).** Add a standard for the residential zone: at most 1 floor. Run again.
*You should have:* three more breaches, for the two-storey buildings.

### Session 9: working with the field (1 h)
Guide: [Field data in the office](../user/field-sync.md). Run this with the field officers' course if you can.

**Exercise 14.** Send the buildings to the field for checking. When an officer has synced, find a feature they captured: who recorded it, how accurately, and its photo.

**Exercise 15.** With an officer: both change the same building (they on the phone without syncing, you in the office), then they sync. Resolve the conflict by picking one value from each side.
*You should have:* a building with the merged values, and both versions in its history.

### Session 10: keeping work safe (45 min)
Guide: [Project files (.spp)](../user/project-files.md), [The audit log](../user/audit-log.md).

**Exercise 16.** Save your project as `.spp`. Open the file as a new project. Try to open it in a zip program.
*You should have:* a second copy of your project, and a file other programs can't read.

**Exercise 17.** Export the buildings as a shapefile and open it in QGIS.

### Session 11: personal data (30 min, administrators and planners)
Guide: [Data protection](../ops/data-protection.md).

**Exercise 18.** Add a field "owner" to the parcels and mark it restricted. Type a made-up name. Sign in as the viewer account and look at the same parcel.
*You should have:* "restricted" where the name is, for the viewer.

Discuss: which fields in your real data should be restricted? Who will be the Assembly's data protection contact?

### Close (15 min)
Each trainee names one thing they will do with the platform in the next week.
