# The readiness checklist

*Physical planners and district administrators; everyone in the district can view it.*

Every project has a checklist of what must be in place before the local plan can be prepared. It has five groups: authority and set-up, planning area, base map, existing situation, and people and standards. Open it with **Readiness checklist** at the top of the project's map. Open **Readiness** in the main menu to see every project in the district.

## Items
Click an item's title to see its details. Each item has:
- a **status**: not started, in progress, ready, or verified;
- an **owner** and a **due date**. District administrators pick the owner from the members list; planners can make themselves the owner;
- **notes**, saved when you click away from the box;
- **documents**, such as the Assembly resolution or the public notice. Attach them with the file button.

There are three kinds of item:
- **Document or decision** items, which you mark ready yourself.
- **Map layer** items. These are linked to a layer and measured automatically (see below). A layer named exactly like the item is linked on its own.
- **The planning area**, which follows the boundary's status in the workspace.

## Automatic measures (map-layer items)
| Measure | Meaning |
|---|---|
| Features | how many features the linked layer has |
| Coverage | how much of the planning area has data. The area is divided into about 100 squares; this is the share of the area whose squares hold at least one feature. It needs the planning-area boundary. |
| Attributes | how complete the attributes are. It counts the required fields, or every field if none is marked required. |
| Newest | the age of the most recently changed feature, in days |
| Verified | the share of features confirmed in the field. This fills in once field ground-truthing arrives. |

The measures are recalculated every time the checklist opens, so imports and edits show up straight away.

## Completion rules
Map-layer items can have rules, for example "buildings: coverage at least 90% and attributes at least 80%".
- You can only mark an item **ready** or **verified** when its rules are met. If you try earlier, the checklist tells you what's missing.
- Only **district administrators** can mark an item verified, or change an item that is already verified.
- An item counts as **complete** when it is ready or verified and its rules are still met.
- The **score** is the share of complete items.

## Blockers
The Blockers list shows:
- items marked ready whose rules are no longer met (for example, after data was deleted);
- items that are past their due date;
- a missing planning area, because most other items can't be measured without it.

## Actions on map-layer items
| Action | What it opens |
|---|---|
| **Import** | the import wizard, already set to the item's layer. If the item has no layer yet, the wizard makes a new layer named after the item, in the item's domain. |
| **Export** | the export dialog with the item's layer ticked |
| **Draw** | the editing tools on the item's layer. If the item has no layer yet, one is made first. |
| **Send to field** | makes ground-truthing tasks for field officers. It is disabled until the field app and sync are available. |

## Exports
**Export CSV** gives a spreadsheet of every item with its measures and problems. **Export PDF** gives a printable report.

## The district's template
New projects copy the district's template. District administrators edit it on the **Readiness** page:
- Choose **Customise for this district** to make the district's own copy of the platform default. Then add, edit or remove items and set their rules.
- Existing projects don't change when the template changes. To pick up items added since a project started, choose **Add new template items** on that project's checklist.
- **Revert to the platform default** removes the district's own template.
