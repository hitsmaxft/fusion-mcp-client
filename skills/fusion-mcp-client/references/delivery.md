# Delivery and project continuity

## Current-version package

Keep the current model and printing entrypoints obvious. Include relevant F3D, separate STL/OBJ, assembly/exploded views, dimensions with sources, print orientation, hardware/assembly notes and outstanding measurements. Distinguish reference bodies from printable parts. Put superseded exports under an explicit historical directory.

`fusion-mcp bundle` exports the complete F3D plus explicitly selected solid bodies, a current-viewport PNG, a snapshot and a checksum manifest. STL/OBJ are in mm and retain assembly coordinates. The command checks single-solid/coedge validity, but does not claim complete mesh topology, physical fit or printability validation. It refuses an existing output folder and leaves `INCOMPLETE` after a failure or timeout. Inspect Fusion before trying again in a new folder.

The current-viewport capture does not change camera/visibility. Other screenshot directions can change the current camera through the adapter. For manual review/exploded captures, record the original camera, active document and visibility and restore them after capture; do not assume every screenshot method restores state.

## Persistence

Store reusable scripts and parameters under the project. Use `/tmp/fusion-mcp` for temporary screenshots and transient files, not the only copy of a modeling procedure. Mark historical scripts with hardcoded paths or state dependencies as operation records unless they have actually been made reproducible.

Record the observed Fusion document ID/version and export units. Capture screenshots and exports from the same geometry revision; verify file presence, lengths and hashes before claiming delivery. For important shape changes inspect the actual exported views. A successful API response alone is insufficient.

## Reporting

Describe what changed, what was preserved, what was checked and what remains provisional. Reference screenshots should not be replaced by generated concept images when reporting the actual CAD result. Separate CAD checks, mesh checks, slice review and physical testing. Reuse original component mounts only when their dimensions and actual model ownership are understood.

## Publication

Use the repository and visibility authorized by the user. Preserve original local work, stage project-specific files and documentation, and verify remote visibility and commit after pushing. A public client/skill repository must not receive a user's private CAD files or project-specific identifiers. Keep vendor references attributed; chat-only images should not be claimed as archived files.
