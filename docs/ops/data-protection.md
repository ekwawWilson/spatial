# Data protection

*District administrators, system administrators and the Assembly's data protection contact.*

The platform holds personal data: who owns or claims a parcel, occupants' names, phone numbers on permit applications, photographs of people's homes, and staff accounts. Ghana's **Data Protection Act, 2012 (Act 843)** applies to the Assembly as a data controller. This page says what the platform does to help, and what remains the Assembly's responsibility. It is not legal advice.

## What the platform does
| Principle | In the platform |
|---|---|
| Only those who need personal data see it | A layer field can be marked **Restricted**. Its values are then hidden from viewers and field officers everywhere: feature details, attribute tables, map tiles, history, the field app and sync. Planners and district administrators see them. |
| Districts are separate | Each Assembly sees only its own data. The database itself enforces this (row-level security), not only the screens. |
| Accountability | Every change is recorded in the audit log: who, when, what it was before and after. District administrators can read their district's log. |
| Security | Passwords are hashed; accounts lock after repeated wrong passwords; sign-in attempts and uploads are rate limited; API keys are encrypted at rest; `.spp` project files are encrypted with a key only the server holds; HTTPS is expected in production. |
| Access by role | Five roles with a documented permission matrix (`docs/dev/permissions.md`). |
| Getting data out | Data can be exported in standard formats at any time (planners and administrators only). |

## Marking fields as restricted
When a layer is created or imported, open its **Fields** and tick **Restricted** for every field that identifies a person or their property rights: owner or claimant names, phone numbers, ID numbers, tenancy details. This is a decision for the district, layer by layer; the platform doesn't guess.

A restricted field can't be required, so that people who can't see it can still add features.

Free-text **notes** and **photos** captured in the field are not restricted fields. Tell field officers not to write personal details in notes, and to avoid photographing people.

## What stays the Assembly's responsibility
- **Registration** with the Data Protection Commission as a data controller, and renewing it.
- **A lawful purpose and notice:** telling residents what is collected and why, for example at the public notice of the plan.
- **Who gets an account**, and removing accounts when staff leave (deactivate the membership; the audit trail of what they did stays).
- **Requests from data subjects** to see or correct their data: a planner can find and correct a record; the audit log shows its history.
- **Agreements with processors:** whoever hosts the server, and anyone given exports or `.spp` files.
- **Exports and project files leave the platform's protection.** A shapefile or a printed checklist is as safe as wherever it is kept.

## How long data is kept (retention)
The platform keeps data until someone deletes it. A reasonable policy to adopt, adjusting to the Assembly's records rules:

| Data | Keep | How |
|---|---|---|
| Plan data (layers, boundaries, checklists) | For the life of the plan and its review; archive the project afterwards | Project status "archived" |
| Audit log | At least 7 years, as a record of planning decisions | `make prune-audit DAYS=2555` removes older entries |
| Field photos and documents | With the feature or checklist item they belong to | Deleting the feature or item removes them; `make clean-media` removes leftovers |
| Staff accounts | While employed; deactivate on leaving | Members page |
| Backups | 14 days by default | `KEEP_DAYS` in `scripts/backup.sh`; remember that deleted data lives on in backups until they expire |

Deleting a feature removes it from the map and from phones at their next sync. Its earlier versions remain in the audit log until that is pruned.

## If something goes wrong
A lost phone, a leaked export, or an account used by the wrong person may be a breach that must be reported. Act the same day:
1. Deactivate the account concerned (Members), or ask a system administrator.
2. If an `.spp` key may have leaked, rotate it ([organisation keys](spp-keys.md)).
3. Use the audit log to see what the account changed. Reads are not logged; assume anything that account could see was seen.
4. Tell the Assembly's data protection contact, who decides on notifying the Commission and the people affected.
