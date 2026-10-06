# Relationships between features

*Physical planners and district administrators; everyone in the district can view them.*

The platform works out how the features of a project relate to one another, so you can ask questions like "which properties flood?", "which buildings are too close to their boundary?" and "which communities have no school nearby?". Open **Relationships** at the top of the project.

## The twelve relationships
| From | Link | To | How it is worked out |
|---|---|---|---|
| Property | belongs to | Community | the community that covers most of it |
| Property | falls within | Local plan | the plan that covers at least half of it |
| Property | falls within | Structure plan | the same |
| Community | contains | Infrastructure | facilities inside the community |
| Property | is located on | Street | the nearest street within 100 m |
| Property | is served by | Road | a road within 30 m |
| Property | is affected by | Flood risk | it touches a flood-prone area |
| Property | is connected to | Drain | the nearest drain within 15 m: **a guess, to be confirmed** |
| Property | has | Development permit | the permit names the property's id, or sits on it |
| Development | violates | Planning regulation | it breaks the district's standard for its zone |
| Infrastructure | serves | Population | population units within 1 km of the facility |
| Project | addresses | Development need | a need of the same kind within 500 m: **a guess, to be confirmed** |

Distances and areas here are measured in metres for analysis. They are not survey measurements.

## 1. Say which layer holds what
Layers can be called anything, so the project has to say which one holds the properties, the streets, the flood-prone areas and so on. Under **Which layer holds what**, the platform suggests layers from their names. Check them, change any that are wrong, and choose **Save**. Parts you leave as "Not in this project" are skipped.

## 2. Run
Choose **Run now**. The table shows what each step found, and which steps were skipped because a layer isn't set. The relationships are also worked out again **every night**, and shortly **after edits** (a changed property is refreshed on its own; a changed street or flood area refreshes the project).

A run changes as little as possible: links that are still true are left exactly as they were.

## 3. Check the guesses
Each link records how it was made:

| How it was made | Meaning |
|---|---|
| **Calculated** | Follows from the geometry or the attributes (a building touches a flood area). |
| **Inferred** | Likely but not certain, with how sure the platform is (the nearest drain is probably the one the property uses). |
| **Confirmed by a person** | Someone checked it. |

Under **Links**, pick a kind of link and tick **Only those to check** to see the guesses. For each, choose **Confirm** or **Reject**. From then on no run will change or remake that link. **Undo** hands it back to the platform.

## Development standards
District administrators set what is allowed in each zone under **Development standards**: minimum setback from the plot boundary, maximum floors, maximum plot coverage, minimum plot size, whether a permit is required, and whether building in a flood-prone area is allowed.

- A standard's **zone** is matched to the parcel's land use (or to the zoning layer, if the project has one).
- The standard with an empty zone is the district's **default**, used for any other zone.
- With no standards at all, a 3 m setback is checked.
- Standards apply to every project in the district, from the next run.

Breaches appear under **Links** as "Properties violates a planning standard", with what was measured and what is required. A breach is a flag for a planner to look into, not a legal finding.

## Totals
**Totals** summarises the project and each community: how many properties, how many in flood-prone areas, without road access, with no drain nearby, breaking a standard, and how many facilities each community has. The headline figures also appear on the readiness checklist.

## On the map
Click any feature: its details list what it is **linked to** ("is located on Main Street", "is affected by F-001"), including links pointing at it from other features.

## Who can do this
Planners and district administrators set the layers, run, and confirm or reject links. District administrators set the standards.
