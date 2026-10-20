# Features from the map (OpenStreetMap)

*Planners and district administrators (anyone who may import data).*

A basemap is a picture: you can't select or name what is on it. This tool brings in the **streets, buildings, rivers, land use and places** that OpenStreetMap records inside an area, as ordinary layers of your project. You can then edit them, correct them and name them like any other layer.

Open a project; the panel **Features from the map** is in the left-hand column, under the basemap.

## 1. Mark the area
- **The planning area:** the project's boundary (see [Editing features and making the planning area](editing-and-boundaries.md)).
- **What's on screen now:** zoom and pan the map to the area first.
- **An area I draw on the map:** press **Draw the area**, click its corners on the map, and double-click to finish.

Bring in up to **60 km²** at a time: a town or a few communities. For a whole district, do it in parts; nothing is brought in twice.

## 2. Choose what to bring in
| Choice | Layer made | Fields |
| --- | --- | --- |
| Streets and roads | Streets (OpenStreetMap), domain D | name, road class, surface, lanes, one-way, reference |
| Buildings | Buildings (OpenStreetMap), domain C | name, building type, storeys, house number, street |
| Rivers, streams and drains | Waterways (OpenStreetMap), domain F | name, kind, width |
| Land use, parks and open spaces | Land use (OpenStreetMap), domain B | name, land use, leisure, natural |
| Schools, clinics, markets and other places | Places (OpenStreetMap), domain E | name, amenity, shop |

Every feature also keeps its **OpenStreetMap id**.

## 3. Bring in features
It runs in the background: OpenStreetMap can take a minute to answer. When it is done the panel says how many of each kind came in, and the new layers appear in the layer list.

- Streets, rivers and land use are **cut at the edge of the area**; buildings and places are kept whole.
- The layers are in the **project's coordinate system**.
- Run it again (on a bigger area, or later when OpenStreetMap has more) and only what is **new** is added: features already in the project are left as they are, with your corrections.

## Then: edit and name
- Select a layer to see its **attribute table**: type a street's name in the *name* column.
- Use the editing tools (**Edit vertices**, **Split**, **Merge**, **Delete**) to correct lines and shapes against the imagery.
- To number the properties along the streets, set **Streets (OpenStreetMap)** as the project's streets and **Buildings (OpenStreetMap)** as its properties (Relationships, Layers), then use [Street addressing](addressing.md).

## Good to know
- OpenStreetMap is mapped by volunteers. In many Ghanaian towns the main roads are complete but side streets, names and buildings are partial. **Check it on the ground or against your drone imagery before relying on it.**
- The data is © OpenStreetMap contributors, under the Open Database Licence: credit OpenStreetMap on plans that use it.
- Satellite or Google imagery can't be turned into lines this way: only OpenStreetMap's own data can be brought in.
