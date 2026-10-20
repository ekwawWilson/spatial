# Returns and data exchange

*Everyone can see the return. Only district administrators issue and revoke keys.*

Choose **Returns and data exchange** in the left menu.

## The return
What the district's planning authority did in a **quarter** or a **year**, counted from the platform's records, for the Land Use and Spatial Planning Authority (LUSPA), the Regional Coordinating Council and the Assembly's own performance assessment:

- **Permits:** applications received (development and planning), decided, granted, refused, certificates issued, the share decided within the 30 days, and the average days to a decision.
- **Re-zoning, change of use, subdivision and consolidation:** received, approved, refused.
- **Enforcement:** cases opened (by contravention), notices served (by form), cases closed (by outcome), cost recovered.
- **Local plans:** commenced, draft on display, approved; consultations held and comments received.
- **Public Data Room:** requests for information received, and the share answered within 5 days.
- **Rates and betterment:** bills issued and the amount billed; betterment schemes completed.

Pick the period, then **Download as PDF** to file it, or **as CSV** to put it in a spreadsheet. It carries no names, only figures.

## Data exchange with national bodies
A **key** lets a national body read the district's records directly from the platform, instead of waiting for files:

| May read | What they get |
| --- | --- |
| Permits | each permit decided: number, kind, use, storeys, status, dates, and the site on the map |
| Plans | each local plan approved: name, locality, approval date, the planning area |
| Zoning | each zone drawn on the map, with its national code |
| Enforcement | each notice served: notice, form, contravention, dates, place |
| Returns | the return for any quarter or year |

Map data comes as **GeoJSON in WGS 84**, which QGIS, ArcGIS and every web map read directly. **No names or contacts ever leave.**

### Issuing a key
1. Under **Issue a key**, say who it is for (for example *LUSPA, Accra*) and tick what it may read.
2. **Issue the key.** The key appears **once**: copy it and send it to them securely (not by plain email or WhatsApp).
3. They read with the key in a header, for example:
   ```
   GET https://<your site>/api/exchange/v1/permits/?since=2026-07-01
   Authorization: Key SMA.xxxxxxxx…
   ```
   `since` returns only what was decided, approved or served since that date. The return takes `?period=2026-Q3` or `?period=2026`.

Every read is counted (*Last used*) and recorded in the audit log. **Revoke** a key the moment it is no longer needed, or if it may have leaked; it stops working at once.
