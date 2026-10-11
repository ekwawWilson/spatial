# Planning and development permits

*Physical Planning Department staff; the district administrator for decisions and fees.*

The platform runs a permit application from the day it is received to the certificate, in the steps and by the dates the Regulations set (L.I. 2384 r.43–46, and LUSPA's Guidelines on Development Permitting). Open a project and choose **Permits**.

## The two permits
- A **development permit** is for building: erecting a building, altering or renovating one, civil and engineering works, regularising an existing structure, redevelopment (r.45(1)). It carries both the planning and the building permission.
- A **planning permit** is for the rest: a temporary structure, a change of use, demolition, an advertisement, subdivision or consolidation, hoarding, excavation, sand winning and quarrying, tree removal, a change of colour scheme (r.44(1)).

## Receiving an application
Choose **Receive an application** and enter the permit, what it is for, the applicant, the proposed use and the number of storeys. Then say where the site is:

- **A parcel on the map:** type the parcel's id. The parcel's shape becomes the site.
- **Its corner coordinates:** one corner per line, easting then northing, in the project's coordinate system (from the site plan).
- **Add it later.**

The application gets its **number** straight away (r.44(7)(b)): district, DP or PP, year, and a running number, for example `SMA/DP/2026/0014`. The site is added to the project's **Permit applications** layer, so it shows on the map.

Enter the date the application was actually **received** if that isn't today: every deadline runs from it.

## The deadlines
Each application shows its four dates, and the list shows the next one due. A date that has passed is in red; **Only those with a deadline passed** filters the list to them.

| Step | Days from receipt | Rule |
|---|---|---|
| Acknowledge receipt in writing | 7 | r.44(6) |
| Technical Sub-Committee: zoning checks and site inspection | 14 | r.44(7) |
| Technical Sub-Committee's report to the Spatial Planning Committee | 21 | r.44(8) |
| Decision, and the certificate where granted | 30 | r.44(10) |

## The steps
The application's page always shows the **next step**.

1. **Acknowledge receipt.** Download the acknowledgement for the applicant: it gives the application number and the dates that follow. It is not a permit.
2. **Documents.** The page lists what this application must carry (r.44(3), r.45(9)) and what is still missing. Add each submitted document against the requirement it meets. A building of two or more storeys needs structural drawings too. Ask for a report "where applicable" (traffic, fire, environmental, and so on) by adding it to the application.
3. **Comments.** Record what the Works Department and other institutions say (r.44(7)(d)), and whether it is an objection.
4. **Site inspection.** Record what was found on each of the points the Regulations list (r.44(7)(f)): plot size and location, access, whether work has started, adjoining development and uses, fire safety, environmental concerns, the parcel's coordinates. Field officers can record inspections.
5. **Report.** The Technical Sub-Committee's findings and recommendation go to the Spatial Planning Committee (r.44(8)). The inspection comes first.
6. **Decision.** The district administrator records the committee's decision (r.44(9)): grant (with any conditions), refuse or defer. A refusal or deferral needs its **reasons**, which go to the applicant in a letter you can download (r.44(13)). A deferred application can be inspected and reported again.
7. **Permit fee and certificate.** Once granted, record the permit fee's receipt (r.44(11)); the district administrator then **issues the permit**. Download the certificate. It is valid for five years.

An application can be **withdrawn** while it is open; its deadlines then stop.

## The automatic checks
When an application is received, and whenever its details change, the platform checks the site against the map (the "initial zoning checks" of r.44(7)(a)):

| Check | What it compares |
|---|---|
| Zone | The zone the site is in, from the zoning layer or the parcel's land use |
| Proposed use | Words in the proposed use against the uses the zone prohibits |
| Plot size and width | The site's area and its width at the street against the zone's minimums |
| Storeys | The number of storeys against the zone's limits |
| Flood-prone land | Whether the site is in a flood-prone area |
| Access | How far the nearest street is |
| Local plan | Whether the site is within a local plan |
| Other applications | Other applications on the same land |

Setbacks and coverage are read off the block plan: the check tells you what the zone asks for, and the area of this plot that may be built on.

Each result is **Meets it**, **Doesn't meet it**, **Look into it** or **Can't tell from the map**. They are advice to the Technical Sub-Committee and the Spatial Planning Committee. They are never the decision.

The checks use the district's standards ([zoning and the national standards](zoning.md)) and the project's layers ([relationships](relationships.md), Layers).

## The certificate and its QR code
The certificate carries a **QR code**. Anyone who scans it, or opens the address printed beside it, sees the Assembly's own record of that permit: its number, who it was issued to, what for, where, and whether it is still in force. No sign-in is needed. A certificate whose details differ from the record has been altered; a code that matches nothing is not from the Assembly.

The certificate's layout is plain for now. When the Assembly supplies its letterhead and the exact Schedule forms, they replace it.

## Fees
The district administrator enters the lines of the Assembly's **fee-fixing resolution** under **Fees**: a processing fee and a permit fee for each kind of permit, or for one category. Staff record each receipt on the application.

## Who can do this
| | Viewer | Field officer | Planner | District administrator |
|---|---|---|---|---|
| See applications | ✓ | ✓ | ✓ | ✓ |
| See the applicant's phone, email and address | | | ✓ | ✓ |
| Record a site inspection | | ✓ | ✓ | ✓ |
| Receive, acknowledge, add documents and comments, report, record receipts | | | ✓ | ✓ |
| Record the committee's decision; issue the permit | | | | ✓ |
| Enter the fees | | | | ✓ |
