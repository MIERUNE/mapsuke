---
name: mapsuke-create-report
description: Create or update reports with maps, summary tables, and explanations from the live project through Mapsuke, the assistant inside QGIS. Use only in a Mapsuke session when asked for a survey report, a write-up of analysis results, or a document with maps. The user need not mention Mapsuke or QGIS. Do not use for simply saving a layer or giving a short explanation in chat.
---

# Creating reports

Build a report from the current QGIS project or the specified data so readers can understand both the results and the evidence behind them. Keep observed facts separate from interpretation.

## Confirm purpose and evidence

- From the conversation, determine the purpose, audience, area and period of interest, required comparisons, output format, and destination.
- Write the report in the language the user requested; if none was specified, use the language of the conversation. Keep data values, attribute names, and place names as they appear in the source unless translation is requested.
- If no format is specified, consider a PDF from a QGIS print layout when map placement or printing is central, or HTML when text and tables dominate, and state which format you chose. Check in advance that the required output features are available.
- Define what is being aggregated and in which units. Investigate missing values, duplicates, row inflation from joins, and the CRS used for area/distance calculations when they affect the results, and record how you handled them.
- Record data sources, acquisition dates, coverage periods, and analysis conditions. Do not fill in unknown sources or results of analyses that were not run.

## Assemble content and maps

Lead with the results the reader wants, followed by as much of the supporting maps, figures, methods, and limitations as needed. Do not pad pages with a fixed chapter structure; scale the report to the request.

- Compute numbers from actual aggregation, and keep counts, denominators, units, and rounding consistent. When comparing, align extents, periods, and classification criteria, and explain anything that cannot be aligned.
- Design and visually verify each map following the mapsuke-cartography skill.
- For HTML reports, use interactive maps only when exploring locations, layers, or feature details helps the reader; use static QGIS maps when a fixed view communicates the result sufficiently. Before choosing an interactive map, check feature count, vertex count, and exported size to ensure smooth display; simplify data or use a static image if it is too heavy. Choose background layers for the map's purpose: roads and place names for local orientation, a graticule for geographic coordinates, or no background when it adds no useful context. Follow the projection requirements in mapsuke-cartography when choosing the map technology.
- Give tables and figures meaningful titles and units. Include the aggregates needed for decisions rather than pasting full attribute tables.
- Distinguish what the data shows, possible explanations, and unverified points. Do not assert causation from correlation alone, and place uncertainty and out-of-scope areas close to the conclusions.

## When using a QGIS print layout

Limit each page to one topic. Decide paper size, orientation, margins, and the regions for map, text, and legend before placing items. Unless specified, default to A4 with roughly 15 mm outer margins. Build a reading hierarchy of heading → key points → map → legend and sources, and keep font sizes, colors, and spacing consistent across pages. Keep colors and decoration minimal, prioritizing the legibility of the map and conclusions.

- Make the map the main element and give it ample space. Do not cram long text or summary tables onto the same page; trim content or split pages if it does not fit. Align item edges, and leave space between figures and text and at the bottom for sources and notes.
- Place legends beside their maps without overlapping map content or text.
- Place the title, body text, tables, legend, and sources with the actual wording and a font that supports the report's language and script. Confirm the text fits within label frames, and adjust wrapping, line spacing, and column widths. Do not shrink text to an unreadable size to make it fit. Estimate table rows and column widths, and split long tables.
- Before exporting, inspect each item's position and size and fix anything that extends off the page or overlaps unintentionally.

## Export and verify

- Inspect the exported document, rendering every PDF page to an image. Check for clipped text, missing glyphs, insufficient margins, table overflow, misplaced or missing maps and legends, page breaks, and image resolution. Fix problems and re-export. For HTML, also check that embedded maps display and any interactive controls work.
- Cross-check the numbers and conditions in the text, tables, and maps. If no visual inspection is possible, report what was verified separately from the layout that remains unverified.
- On completion, briefly give the deliverable path, key results, verification status, and important limitations. Share or upload externally only when asked.
