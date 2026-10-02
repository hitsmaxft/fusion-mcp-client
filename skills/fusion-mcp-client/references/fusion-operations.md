# Fusion operations and observed pitfalls

## Geometry and assembly

- Name the actual part, datum and affected faces before changing geometry. Screen direction, model axes and print orientation are separate choices.
- For connectors, compare both mating axes and insertion depth. Two nonintersecting placeholders can still be disconnected or misaligned.
- Calculate the required component/cable envelope before increasing or reducing the enclosure. An estimated envelope must remain labeled as estimated.
- For screws, check all requested locations, tool access, bearing material and engagement independently. Do not move a module's original holes merely to simplify exterior styling.
- Track intentional interference, such as a friction rib, separately from unexpected collisions. Do not treat every overlap as an error or every zero-overlap result as an assembly pass.
- Derive reference shapes from their construction: a rounded rectangular volume intersected by a single inclined cut should retain that continuous construction, rather than be approximated by unrelated planar facets. Compare side/rear silhouettes and transition tangency before adding vents or cosmetic detail.

## Printing

Choose the bed-contact face before claiming that a clip, slot or button is printable. Check continuity through layers, bridges/overhangs, thin root sections and load direction. A wide base and narrower upper section may help a linked button module; the choice still depends on its orientation and material. Separate CAD validity, mesh validity, slicing, physical fit and strength evidence.

## Native API observations

These were observed in the local Fusion installation; verify them when versions change.

- After `BaseFeature.finishEdit()`, a retained handle can refer to a source body. Reacquire the result body through the feature/result collection before assigning appearance, name or visibility. Check `sourceBodies` and `bodies` if historical geometry appears as a ghost. Hide only source bodies belonging to the operation being reviewed; avoid blanket changes to unrelated user geometry.
- Check edge coedge incidence when diagnosing a closed-solid topology defect. `edge.faces.count` alone is insufficient at seam edges.
- Suppressing an old feature may invalidate downstream face/edge references. Inspect dependencies and use an appropriate local replacement or saved baseline rather than repeatedly suppressing a broken chain.
- Large temporary Boolean operations have failed with coincident faces in this environment. When that failure occurs, isolate the smallest failing operation; clipping individual additions before joining can help. Do not change geometry solely to silence an error without reviewing the result.
- Closed voids may be intentional. Determine their location, size and role before filling them; never remove all `isVoid` shells as a general cleanup rule.
- `BRepMeshCalculator` can export controlled meshes in cm internally; convert vertices to mm explicitly. Validate the exported mesh independently when it is a printing deliverable.
- Some past scripts used `gc.disable()` around suspected SWIG/GC instability. It is an environment-specific workaround, not a demonstrated universal fix. Do not disable GC globally by default; if needed, record the Fusion version/reason and scope the workaround.

## Failure and recovery

A timeout or lost response does not show whether a script completed, partially ran or rolled back. Inspect active document identity, timeline, body inventory and outputs before retrying. File writes may survive even when geometry is rolled back. Avoid parallel MCP edits and do not restart a busy Fusion merely because a request is slow.

When a crash is confirmed, follow the user's restart authorization; preserve recoverable work and identify the document/version reopened. Verify the service listener after restart. If diagnosing the crash is requested, use the newest CER/macOS crash report/AppLog and keep network symptoms separate from an established crash cause.
