---
name: qgis-cartography
description: Design a map in QGIS so it communicates its message, covering projection, extent and scale, classification, colors, symbols, labels, and map elements such as legends and scale bars. Use when asked to make, style, or improve a map, whether shown on the canvas, placed in a print layout, or embedded in a report. Do not use for analysis that produces no map.
---

# Designing maps

Make each map answer one clear question for its audience. Decide what the reader must compare or find, then choose the projection, extent, symbology, and map elements to serve that, keeping everything else visually quiet.

## Clarify the message

- From the conversation, determine the map's purpose, audience, area of interest, and medium (canvas, print layout, image, or web). Ask only about unknowns that would change the design; use reasonable defaults for the rest.
- Choose a map type suited to the data: choropleth for rates or densities over areas, proportional or graduated symbols for counts or magnitudes, dot density for distributions, isolines or continuous rasters for fields, and categorized symbols for classes. Do not use a choropleth for raw counts over areas of different size; normalize by area or population, or use symbols.
- Inspect the actual layers through the plugin's Python bridge: attributes, value ranges, null values, CRS, extent, and feature count, before deciding classes or styles.

## Choose the map projection

Choose the display projection from what the map must let readers compare, not from the source data's CRS or the canvas CRS. Distortion matters most for wide extents (a country, continent, or the world); at municipal scale, a local projected CRS such as the Japan Plane Rectangular CS (EPSG:6669–6687) or UTM is usually sufficient.

- Comparing sizes, densities, or distributions (choropleths, dot density, land use, population, damage extent, accumulated precipitation per area): use an equal-area projection such as Albers Equal Area Conic (mid-latitude regions), Lambert Azimuthal Equal Area (continents or polar regions), or Equal Earth / Mollweide (world).
- Preserving local shapes and directions (weather charts with fronts, isobars, and wind; navigation; flow direction): use a conformal projection, as in WMO/JMA practice: Lambert Conformal Conic for mid-latitudes, Polar Stereographic for high latitudes, and Mercator near the equator.
- Showing distance or direction from one point (epicenter, airport, facility service range): use Azimuthal Equidistant centered on that point.
- World or continental overviews with no single property to preserve: use a compromise projection such as Winkel Tripel, Robinson, or Equal Earth. Do not use Web Mercator (EPSG:3857) for wide-area thematic maps, because it greatly inflates high-latitude areas.
- Center conic and azimuthal projections on the map extent (central meridian, standard parallels, or projection center), creating a custom CRS from a PROJ string when no suitable EPSG code exists.
- Set the projection on the layout map item, the export's rendering CRS, or the project display CRS with the user's consent, rather than rewriting source data. Keep area and distance calculations in an appropriate equal-area/projected CRS or ellipsoidal measurement, independent of the display projection.
- XYZ/web tile basemaps are in Web Mercator, and reprojecting them blurs imagery and labels. When a non-Mercator projection matters, prefer a vector basemap or graticule; if a tile basemap is required, explain the trade-off. Web maps such as Leaflet.js also display in Web Mercator, so use a static image when a non-Mercator projection is needed there.
- State the projection used (and why, if it is not obvious) in the map caption or notes.

## Extent and scale

- Frame the area of interest with a little context around it, and fix the extent and scale explicitly rather than relying on the current canvas state. When maps are compared, use the same extent, scale, and classification.
- Match detail to scale: generalize or hide layers that become clutter at small scales, and use scale-dependent visibility or simplified data where needed.
- Add an inset or locator map when readers may not recognize the area.

## Classification and color

- Choose class breaks from the data distribution and purpose: natural breaks for clustered data, quantiles for ranking, equal intervals or round-number breaks for easy reading, and fixed thresholds for regulatory or domain-defined levels. Use around 4–7 classes, and check that no class is empty or dominates unintentionally.
- Use a sequential palette for ordered magnitudes, a diverging palette only when there is a meaningful midpoint (zero, average, or target), and a qualitative palette for unordered categories. Prefer colorblind-safe palettes such as ColorBrewer or viridis, and keep lightness monotonic in sequential schemes.
- Follow domain conventions where they exist (e.g. hazard levels, land-use codes, official color schemes for precipitation or seismic intensity).
- Do not render missing, suppressed, or out-of-scope data the same as zero or the lowest class; give it a distinct neutral symbol and explain it in the legend.

## Symbols, draw order, and labels

- Put the thematic layer on top and make reference layers (boundaries, roads, water, basemap) lighter or thinner so they support rather than compete. Order layers so points and lines are not hidden by polygons.
- Size proportional symbols by area, not radius, and draw large symbols beneath small ones. Avoid heavy outlines and effects that add noise.
- Label only features the reader needs, with a font that supports the map's language and script. Use buffers or halos for legibility over busy backgrounds, avoid overlaps, and check label placement at the final scale and resolution.

## Map elements

- Include a legend for every symbol that needs explanation, with a clear title, units, and classes that match the rendered colors. Omit layers that do not need explanation, such as basemaps.
- Add a scale bar when distances matter and a north arrow when orientation is not obvious or north is not up; omit them on small-scale maps where they would mislead because of distortion. Use a graticule when geographic position or projection shape matters.
- Credit data sources and basemap attribution, and include the date or period of the data when relevant.

## Apply and verify

- Keep track of any changes to existing layer styles, visibility, or the project CRS, and restore them afterward unless the user asked for a permanent change. Prefer layout-specific settings (locked layers and styles, map themes) for output maps.
- Render the finished map to an image (the canvas, or the layout map at output size) and look at it, checking legibility, class and legend correspondence, label collisions, hidden features, and projection. Fix problems and re-render before reporting.
