---
name: qgis-save-processing-script
description: Save, register, or update work done in QGIS as a reusable single-file Processing script. Use for requests such as "save this process", "make this a tool I can use next time", or "reuse this workflow". Do not use for running a process once or merely saving result data.
---

# Saving work as a reusable Processing script

Turn processing performed in the conversation, or a specified workflow, into a tool that can be run from the Processing toolbox with different inputs. If the user specifies a different format, follow that instead.

## Organize what to save

- Identify the processing whose results have been verified, the required inputs, the adjustable conditions, and the outputs. Do not save exploratory code or failed attempts as-is.
- Run live QGIS inspection, registration, and verification through the plugin's Python bridge. Do not manipulate the current project from a separate process.
- Check whether a related tool already exists in the standard `script` provider, and read the help of related tools. When improving an existing tool, update it under the same `NAME`.
- Check the current registration contract with `processing.algorithmHelp('geotaro:add_tool')`. If it is unavailable, report that limitation; do not silently switch to another saving method.

## Make the definition self-contained

- Define a single `QgsProcessingAlgorithm` subclass implementing `createInstance()`, `name()`, `displayName()`, `initAlgorithm()`, `processAlgorithm()`, and `shortHelpString()`.
- `NAME` must start with a lowercase ASCII letter, contain only lowercase ASCII letters, digits, and underscores, and match `name()`. Display names and help text may use the user's language.
- Expose layers, extents, distances, dates/times, output destinations, and similar values as appropriate Processing parameters. Make distance units, CRS, and handling of selected features explicit, and do not depend on chat variables, fixed layer IDs, or `iface`.
- Put the processing logic in `processAlgorithm()` and return the declared output keys and results. Pass appropriate `context` and `feedback` to nested Processing calls. For long-running work, report progress and handle cancellation, and do not unconditionally move GUI or project access to worker threads.
- Do not modify data or make network requests at the top level or during initialization. Return specific errors for missing or invalid inputs.
- Include helper functions, QPT/QML XML strings, and small settings in the same file. Do not depend on generated separate modules, `sys.path` changes, or adjacent files. If an API requires a file path, keep temporary files only as long as needed and clean them up on failure too.
- Do not embed information that changes per run, such as observation data; accept it as input. Describe the purpose, assumptions, inputs/outputs, units, and usage in `shortHelpString()`.

## Verify with the registered tool

Register with `processing.run('geotaro:add_tool', {'NAME': name, 'SOURCE': source})` and check the returned `ALGORITHM_ID` and `FILE`. Leave the persistent storage location to the registration tool.

Successful registration does not mean the processing works, and testing is part of the request; do not ask whether to test. Pass the returned ID to `processing.run()` and run it with small representative inputs and temporary outputs. Do not run destructive tests. Check results appropriate to the purpose, such as layer validity, feature counts, attributes, CRS, and saved file contents. If display is involved, also check post-processing, loading, and styling.

If the tool offers multiple modes, verify the main modes and representative invalid inputs. Verify fetching logic with permitted real network requests; do not treat mocked responses alone as proof that it works. Do not silently substitute unavailable data, such as another date. If something fails, fix it under the same `NAME` and rerun the failed checks.

On completion, report the tool's name, `ALGORITHM_ID`, storage location, how to find it in the toolbox, and the inputs and results actually verified. If verification was not possible due to permissions, services, data, or run limits, state the blocker and the unverified scope, and do not report the tool as working.
