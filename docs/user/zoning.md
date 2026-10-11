# Zoning and the national standards

*Planners; district administrators for adopting standards.*

The platform carries LUSPA's **Revised Zoning Guidelines and Planning Standards (2025)**: the 36 zones with their codes and colours, and, for the residential zones, the site standards and the permissible and prohibited uses. The Regulations require zoning schemes and development to conform to them (L.I. 2384 r.29(2), r.47). Open a project and choose **Zoning**.

## The national zones
The **National zones and standards** table lists every zone: its colour, its code (Re A, CBD, LI…), its name, and for the residential zones the site standards:

| Zone | Smallest plot | Narrowest at the street | Most coverage | Storeys | Setbacks: front / side / back |
|---|---|---|---|---|---|
| Re A, low density | 930 m² | 70 ft (21.3 m) | 40% | up to 2 | 6 / 3 / 5 m |
| Re B, medium density | 647 m² | 50 ft (15.2 m) | 50% | up to 3 | 6 / 3 / 3 m |
| Re C, high-rise apartments | 4,047 m² | — | 75% | at least 3 | 6 / 3 / 3 m |
| Re D, high density (low-rise) | 182 m² | 40 ft (12.2 m) | 60% | 1 to 3 | 3 / 1.5 / 1.5 m |
| Re Z, redevelopment | 1,011 m² | 70 ft (21.3 m) | 75% | at least 3 | 2.5 / 2.5 / 3 m |

Open **Permissible and prohibited uses** under a zone's name to read them.

The values were typed in from LUSPA's published document. If your copy of the standards differs, tell your district administrator, who can correct the district's standard (below).

## Using the codes in your zoning layer
Give the zoning layer a field for the zone (by default called `zone`) and enter the national codes. They are recognised however they are written: "Re A", "ReA", "re a" and "Residential Zone A" are the same zone. A value that isn't a national zone ("Chief's palace") is kept as the district's own word.

Tell the project which layer holds the zoning under **Relationships → Layers**.

## Adopting the standards for the district
A district administrator opens **Relationships → Development standards** and chooses **Adopt LUSPA's 2025 standards**. That adds one standard for each residential zone, marked "LUSPA 2025". From the next run, every property is checked against the standard of the zone it stands in.

- The district may **tighten or correct** a standard: choose **Edit**. It is then the district's own, and adopting again leaves it alone.
- Zones without site standards in the national document (business, industrial and others) can be given standards by the district: **Add a standard** with the zone's code.

## What is checked
For each property, against its zone's standard:

| Check | How it is measured |
|---|---|
| **Front, side and back setbacks** | The plot's edges nearest a street are its front, the farthest its back, the rest its sides. The building's distance to each is compared with the standard. |
| **Plot width** | The length of the plot's front. |
| **Plot size and coverage** | The plot's area, and the share of it that is built on. |
| **Storeys** | The property's number of floors against the fewest and the most allowed. |
| **Prohibited use** | Words in the property's recorded use that suggest a use the zone prohibits (a filling station, a factory). Shown as **inferred**: a person confirms or rejects it. |

Setbacks from the front, sides and back need a **streets** layer. Without one, or for a plot with no street within about 200 m, the front isn't known: the smallest of the three setbacks is then asked of every side, and the breach says so.

A breach is advice for a planner and the committees to look into. It is not a decision.

## Colouring the zoning layer
**Colour the zoning layer in the national colours** sets the layer's style by zone, using the standards' colour codes, so plans read the same in every district. Zones the standards draw with a pattern (stripes, dots) get their background colour. Values that aren't national zones are left grey and listed.

## The zoning scheme register
Record each zoning scheme under **Zoning scheme register**: its name, status, and the dates the structure plan was approved, the scheme was approved, it took effect and a copy went to LUSPA. The register then shows what the Regulations ask and whether it has been met:

| Duty | Rule |
|---|---|
| Prepare the scheme within **90 days** of the structure plan's approval | r.29(1) |
| Send a copy to LUSPA within **28 days** of the scheme's approval | r.29(6) |
| Update the scheme on its schedule (every 60 months unless you set another) | r.29(3) |

Overdue duties are shown in red.

## Who can do this
Everyone in the district can see the zones, the standards and the register. Planners and district administrators record schemes and colour the zoning layer. Only district administrators adopt or change the district's standards.
