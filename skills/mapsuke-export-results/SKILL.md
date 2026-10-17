---
name: mapsuke-export-results
description: Create or export HTML pages, PDFs, and reports from Mapsuke maps, tables, charts, and analysis results. Use only in a Mapsuke session for requests such as "export this as HTML", "save this map as a PDF", "make a document with maps", or "write a survey report". The user need not ask for a report. Do not use for saving raw data layers or QGIS project files, or for a short explanation in chat.
---

# Exporting results

Produce the requested artifact from the current QGIS project or specified data. Scale the content to the request: a map export may need only the map, legend, and sources; a report may also need findings, tables, methods, and limitations.

## Determine what to export

- Identify the requested content from the conversation and project: the current map, a print layout, specified layers, tables, charts, or analysis results. Resolve which view or result "this" refers to before exporting if more than one is plausible.
- Honor an explicit format. "Export as HTML" is enough to select HTML without asking whether the user wants a report. If none is specified, consider PDF for printing and fixed page layouts, or HTML for browser viewing and interaction; state the chosen format.
- For an export of existing work, preserve the requested view, styles, and content. Add layout elements only as needed for the artifact to be understandable. Do not invent a report structure, run new analysis, or redesign the map unless requested or needed to satisfy the export.
- Write any captions or prose in the requested language, otherwise the conversation's language. Keep data values, attribute names, and place names as they appear in the source unless translation is requested.
- Record available data sources, acquisition dates, coverage periods, and analysis conditions where relevant. Do not invent missing provenance or results of analyses that were not run.

## Maps and HTML output

- Apply mapsuke-cartography when creating or improving maps. When exporting an existing map, visually verify the exported view without silently changing the user's design.
- Use interactive HTML maps when exploring locations, layers, or feature details helps the reader; use static QGIS maps when a fixed view communicates the result sufficiently. Check feature count, vertex count, and exported size before choosing an interactive map; simplify data or use a static image if it is too heavy. Follow the projection requirements in mapsuke-cartography when choosing the map technology.
- Choose background layers for the map's purpose: roads and place names for local orientation, a graticule for geographic coordinates, or no background when it adds no useful context.
- Keep HTML assets portable with embedded images/data or accompanying files referenced by relative paths. Account for external scripts and tile services when deciding whether the output will work offline; do not claim offline support without checking it.

## When creating a report

Build on the exported content with the evidence and explanation the reader needs. Keep observed facts separate from interpretation and do not pad pages with a fixed chapter structure.

- Determine the purpose, audience, area and period of interest, and required comparisons. Lead with the results, followed by supporting maps, figures, methods, and limitations.
- Define what is being aggregated and in which units. Investigate missing values, duplicates, row inflation from joins, and the CRS used for area/distance calculations when they affect the results, and record how you handled them.
- Compute numbers from actual aggregation, and keep counts, denominators, units, and rounding consistent. Align comparison conditions and explain anything that cannot be aligned.
- Give tables and figures meaningful titles and units. Include aggregates needed for decisions rather than pasting full attribute tables.
- Distinguish what the data shows, possible explanations, and unverified points. Do not assert causation from correlation alone, and place uncertainty and out-of-scope areas close to the conclusions.

## When using a QGIS print layout

For a new layout, decide paper size, orientation, margins, and the regions for map, text, and legend before placing items. Unless specified, default to A4 with roughly 15 mm outer margins. Preserve an existing layout's dimensions and arrangement when it is the export target.

- Give the map ample space, place legends beside their maps without overlapping content, and align item edges. For a report, keep each page focused and split long text or tables across pages rather than crowding them around the map.
- Place titles, captions, tables, and sources with the actual wording and a font that supports the output's language and script. Confirm the text fits; adjust wrapping, line spacing, and column widths instead of shrinking it to an unreadable size.
- Before exporting, inspect each item's position and size and fix unintended overlaps or content outside the page.

## Export and verify

- Inspect the exported artifact. Render every PDF page to an image; check clipped text, missing glyphs, margins, table overflow, misplaced or missing maps and legends, page breaks, and resolution. For HTML, verify that the page, images, maps, and relative asset paths work, and exercise any interactive controls. Fix problems and re-export.
- Check that the artifact matches the requested map extent, layers, styles, and content. Cross-check any numbers and conditions across text, tables, and figures. If visual or interactive verification is unavailable, state what was verified and what remains unchecked.
- On completion, give the deliverable path, a brief description of its content, verification status, and important limitations. Share or upload externally only when asked.
