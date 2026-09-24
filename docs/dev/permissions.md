# Roles and permissions

The matrix below mirrors `backend/core/permissions.py`. A test (`test_permissions_doc_matches_code`) fails if the two differ, so update both together.

## Roles
| Role | Scope | Who |
|---|---|---|
| **System administrator** | every district | platform operators; a user flag, not a district role |
| `district_admin` | one district | head of the Physical Planning Department, or their delegate |
| `planner` | one district | physical planners preparing plans |
| `field_officer` | one district | staff capturing data in the field |
| `viewer` | one district | read-only access (other departments, management) |

A person can hold a different role in each district they belong to. System administrators have every permission below in every district.

## Permission matrix
| Permission | Roles |
|---|---|
| `district.view` | district_admin, planner, field_officer, viewer |
| `membership.view` | district_admin |
| `membership.manage` | district_admin |
| `audit.view` | district_admin |
| `crs.manage` | district_admin |
| `project.view` | district_admin, planner, field_officer, viewer |
| `project.edit` | district_admin, planner |
| `layer.edit` | district_admin, planner |
| `feature.edit` | district_admin, planner |
| `basemap.manage` | district_admin |

## System administrator only
- Set the system default coordinate system, add coordinate systems for every district, and pin the transformation used between two systems.
- Create and edit regions and districts (districts are deactivated, never deleted).
- Manage user accounts: create, deactivate, unlock, send password reset, grant system admin.
- View the audit log across all districts.

## Rules enforced beyond the matrix
- A district always keeps at least one active `district_admin`.
- System administrators can't deactivate themselves or remove their own system admin flag.
- Every district-scoped request must name its district (`X-District-ID` header). The database refuses rows from any other district (row-level security), even if application code forgets to filter.

## Planned permissions (added in later phases)
| Phase | Permissions |
|---|---|
| 5 | `data.import`, `data.export` |
| 7 | `checklist.edit` |
| 8 | `project.package` (.spp save/open) |
| 9–10 | `field.capture`, `field.sync`, `conflict.resolve` |
| 12 | `relations.run` |
