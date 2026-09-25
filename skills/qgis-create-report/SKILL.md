---
name: qgis-create-report
description: Create or update a report with maps, summary tables, and explanations grounded in QGIS layers or analysis results. Use when asked for a survey report, a write-up of analysis results, or a document with maps. Do not use for simply saving a layer or giving a short explanation in chat.
---

# Creating reports

Build a report from the current QGIS project or the specified data so readers can understand both the results and the evidence behind them. Generate numbers and maps from the actual data, and keep observed facts separate from interpretation.

## Confirm purpose and evidence

- From the conversation, determine the purpose, audience, area and period of interest, required comparisons, output format, and destination. Ask only about unknowns that would change the conclusions; use reasonable defaults for presentation details.
- Write the report in the language the user requested; if none was specified, use the language of the conversation. Keep data values, attribute names, and place names as they appear in the source unless translation is requested.
- If no format is specified, consider a PDF from a QGIS print layout when map placement or printing is central, or HTML when text and tables dominate, and state which format you chose. Check in advance that the required output features are available.
- Run live QGIS inspection, aggregation, and map generation through the plugin's Python bridge. Identify target layers by ID and check their actual attributes, CRS, extent, and filter/selection state.
- Define what is being aggregated and in which units. Investigate missing values, duplicates, row inflation from joins, and the CRS used for area/distance calculations when they affect the results, and record how you handled them.
- Record data sources, acquisition dates, coverage periods, and analysis conditions. Do not fill in unknown sources or results of analyses that were not run.

## Assemble content and maps

Lead with the results the reader wants, followed by as much of the supporting maps, figures, methods, and limitations as needed. Do not pad pages with a fixed chapter structure; scale the report to the request.

- Compute numbers from actual aggregation, and keep counts, denominators, units, and rounding consistent. When comparing, align extents, periods, and classification criteria, and explain anything that cannot be aligned.
- Design each map following `../qgis-cartography/SKILL.md` (projection, extent, classification, symbols, labels, legend, and other map elements).
- When embedding maps in an HTML report, check the feature count, vertex count, and exported data size. Use a Leaflet.js map only for lightweight data that displays smoothly in a browser. Use a latitude/longitude graticule as the default background, with readable tick values and units. For heavy data, render a static map image in QGIS and embed it instead of making the viewer load large numbers of features.
- Give tables and figures meaningful titles and units. Include the aggregates needed for decisions rather than pasting full attribute tables.
- Distinguish what the data shows, possible explanations, and unverified points. Do not assert causation from correlation alone, and place uncertainty and out-of-scope areas close to the conclusions.

## When using a QGIS print layout

Limit each page to one topic. Decide paper size, orientation, margins, and the regions for map, text, and legend before placing items. Unless specified, default to A4 with roughly 15 mm outer margins. Build a reading hierarchy of heading → key points → map → legend and sources, and keep font sizes, colors, and spacing consistent across pages. Keep colors and decoration minimal, prioritizing the legibility of the map and conclusions.

- Make the map the main element and give it ample space. Do not cram long text or summary tables onto the same page; trim content or split pages if it does not fit. Align item edges, and leave space between figures and text and at the bottom for sources and notes.
- Fix the map's extent, scale, visible layers, and styles in the layout rather than relying on the current canvas state. Do not overlap the legend with the map or text.
- Place the title, body text, tables, legend, and sources with the actual wording and a font that supports the report's language and script. Confirm the text fits within label frames, and adjust wrapping, line spacing, and column widths. Do not shrink text to an unreadable size to make it fit. Estimate table rows and column widths, and split long tables.
- Before exporting, inspect each item's position and size and fix anything that extends off the page or overlaps unintentionally. After exporting the PDF, render every page to an image with whatever means are available and inspect it visually for clipped text, insufficient margins, missing maps or legends, and resolution. Fix any problems and re-export.

## Export and verify

- Write the deliverable to the destination the user specified. If none was given, ask for it before exporting, offering concrete paths such as beside the project file; keep intermediate images and data in a temporary directory. Follow the permissions granted in the conversation when overwriting existing files; if overwriting was not authorized, use a non-conflicting file name.
- Confirm the export result and that the file exists, and inspect the actual deliverable with whatever viewing or rendering means are available. Check the map extent, legend-to-color correspondence, clipped text, correct rendering of the report's script (no missing glyphs), table overflow, page breaks, and image resolution. If Leaflet.js was used, also confirm that the map actually displays and is interactive.
- Cross-check the numbers and conditions in the text, tables, and maps. If no visual inspection is possible, report what was verified separately from the layout that remains unverified.
- On completion, briefly give the deliverable path, key results, verification status, and important limitations. Share or upload externally only when asked.

If reuse is also requested (e.g. "I want to produce the same report next time"), read `../qgis-save-processing-script/SKILL.md` and package the work as a Processing tool with input data, dates, and output destination as parameters. Registration is not required for a one-off report.
