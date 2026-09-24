# Editing features and making the planning area

*Physical planners and district administrators.*

## Editing on the map
Select a layer's name in the Layers panel. The **Editing** bar appears above its table.

| Tool | What it does |
|---|---|
| **Draw** | click to add points or corners; double-click to finish a line or polygon |
| **Edit vertices** | click a feature, then drag its corners; click an edge to add a corner |
| **Move** | click a feature and drag it |
| **Split** | first click the feature with Identify, then choose Split and draw a line across it |
| **Select to merge** | shift-click touching features, then **Merge**; the first one keeps its values |
| **Delete** | click a feature (you're asked to confirm) |

**Snapping:** while drawing or editing, the pointer jumps to nearby corners and edges of the layers ticked under **Snap to**, within the distance you set (in screen pixels). Use it to make parcels meet exactly.

**Undo / Redo** step back and forward through your edits in this session. Every step is saved, so nothing is lost.

Layers with more than 2,000 features can't be edited on the map in this version.

## History
Click a feature (Identify), then **History**. You'll see every version: when, who, and what changed. **Restore this version** makes an earlier version current again. The restore is recorded as a new version, so the history is never rewritten.

## The planning area
The **Planning area** panel shows the project's boundary and checks it:
- **Area** in hectares, acres and m², and **perimeter** in metres and, for feet-based projects, Gold Coast feet.
- **Neighbours:** overlaps with other planning areas in the district (with the overlapping area), and gaps under 2 m that suggest the boundaries should meet.
- **District:** whether any part falls outside the district boundary. A system administrator must load that boundary first.

Ways to make the boundary:
- **Draw** it on the map (snapping helps you follow existing parcels).
- **Enter coordinates:** type or paste the corners, one per line, in any coordinate system. They're converted to the project's.
- **Bearings and distances:** enter the start point and each leg as the surveyor booked it (e.g. `N 45 30 00 E` and a distance in the project's units). You'll see the **misclosure** and the **accuracy ratio** (e.g. *1 in 20,000*). Tick **Adjust (Bowditch)** to spread the misclosure over the legs, as surveyors do. A ratio below about 1 in 5,000 is flagged as suspicious.
- **Import** it from a file (Import data), as a polygon in the Planning area layer.

### Status
**Draft → Agreed with stakeholders → Approved.**
- Planners mark a valid boundary as agreed.
- Only district administrators approve it, or reopen an approved one.
- While a boundary is agreed or approved it can't be changed, not even through the Planning area layer, until it's moved back to draft.
