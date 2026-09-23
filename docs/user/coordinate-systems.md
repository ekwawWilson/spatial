# Coordinate systems

Open **Coordinate systems** in the menu.

## Which system new projects use
Every project records the coordinate system its data is in. A new project starts with:
1. **your personal default**, if you've set one; otherwise
2. **the district default**, set by the district administrator; otherwise
3. **the system default**, set by system administrators (initially the Ghana National Grid, EPSG:2136).

Changing any default only affects projects created afterwards. **Existing projects and their coordinates never change.**

## Built-in systems
| Code | Name | Units | Use |
|---|---|---|---|
| EPSG:2136 | Accra / Ghana National Grid | Gold Coast feet | survey and cadastral work (default) |
| EPSG:25000 | Leigon / Ghana Metre Grid | metres | metre-based national grid |
| EPSG:2137 | Accra / TM 1 NW | metres | defined for **offshore** Ghana; prefer EPSG:25000 onshore |
| EPSG:4168 | Accra (geographic) | degrees | latitude/longitude on the Accra datum |
| EPSG:32630 / 32631 | UTM 30N / 31N (WGS 84) | metres | GPS-based mapping; 31N east of 0° |
| EPSG:4326 | WGS 84 | degrees | GPS, GeoJSON, KML |
| EPSG:3857 | Web Mercator | metres | web basemaps only; don't measure in it |

## Converting coordinates, and how accurate it is
Paste coordinates (one point per line) and choose **From** and **To**. The result names the transformation used and its accuracy.

**Within one datum** (e.g. Ghana National Grid ↔ Accra geographic) conversion is exact.

**Between the Accra (or Leigon) datum and WGS 84**, for example between survey plans and GPS or satellite imagery, the published transformations are only accurate to about **±6 m** (the best one) or **±25 m** (the others). Positions from GPS or imagery can therefore sit several metres from surveyed boundaries even when both are correct. For boundary work, compare like with like, or obtain better transformation parameters from the Survey and Mapping Division.

Converting a point and converting it back always returns the original coordinates.

## Adding a local or project grid
District administrators can add a coordinate system for their district, and system administrators for all districts. Paste the definition (WKT or PROJ string) supplied by the surveyor, choose **Check definition** to see what it is, then **Add**. EPSG systems can't be added this way; ask a system administrator to enable them.

## Choosing the transformation (system administrators)
Under **Transformation between two systems**, pick two systems to see every published transformation and its accuracy. **Use this** makes one the standard for that pair, in both directions and for everyone. **Go back to the most accurate available** removes the choice.
