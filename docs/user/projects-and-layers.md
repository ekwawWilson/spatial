# Projects, layers and the map

## Plan projects
Open **Projects**. Each project is a piece of planning work, for example a local plan for one community. Planners and district administrators can create projects; everyone in the district can open them.

A new project takes the **default coordinate system** (see [Coordinate systems](coordinate-systems.md)) unless you pick another. **A project's coordinate system is fixed once it's created**, so coordinates never change meaning later.

Deleting a project archives it; nothing is lost.

## Layers
In a project, the **Layers** panel lists layers grouped by data domain (A. Territory … J. Planning & policy). For each layer you can:
- **show or hide** it with the checkbox, and set its **opacity** with the slider;
- **Zoom** to its features;
- move it **↑ up or ↓ down** (layers higher in the list are drawn on top);
- change its **Style**: one colour for everything, or a colour per value of a field (e.g. by land use), with optional labels;
- change its **Fields**: names, types (text, whole number, number, yes/no, date, choice), required, and choices;
- **Delete** it, with its features.

Add a layer with **Add a layer**: give it a name, a data domain and whether it holds points, lines or polygons.

### Changing fields safely
The platform won't let a change silently lose data:
- Changing a field's type (e.g. text to whole number) is refused if existing values wouldn't fit. The message lists the features to fix first.
- Removing a field that still holds values asks you to confirm, because those values are deleted from every feature. The change is recorded in the audit log.

## The map
- **Identify**: click a feature to see its details.
- **Measure distance / Measure area**: click points; double-click to finish. Distances are shown in metres or kilometres and, for projects in feet, also in Gold Coast feet. Areas are shown in m², hectares and acres. Measurements are ground distances (geodesic), not map distances.
- Bottom-left: the pointer's position **in the project's coordinate system**.
- Scale bar bottom-left, north arrow top-right (click it to turn the map back to north-up).

Very large layers (over 2,000 features) are drawn from zoom level 14 (roughly neighbourhood scale) upwards, so the map stays quick.

## Attribute table
Select a layer's name to open its table below the map. Sort by clicking a column heading, and narrow the rows with **Filter**.

**Double-click a value to edit it**, then press Enter to save or Esc to cancel. The platform checks the value against the field's rules. If someone else changed the same feature since you opened the table, your edit isn't saved: you'll see a message and the table reloads with their version, so nobody's work is silently overwritten.
