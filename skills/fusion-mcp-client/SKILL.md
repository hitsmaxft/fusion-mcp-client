---
name: fusion-mcp-client
description: Inspect, script, save, review and export Autodesk Fusion designs through the local fusion-mcp CLI or Python library; maintain the shared client when reusable capabilities are missing.
---

# Fusion MCP client

Use the installed `fusion-mcp` command. Maintained source: `/Users/bhe/projects/ai/fusion-mcp-client`; public repository: `https://github.com/hitsmaxft/fusion-mcp-client`. Default service: `http://127.0.0.1:27182/mcp`. Read current project instructions and the library README before maintenance.

## Before modeling

Establish the active document ID/version and named parts using `fusion-mcp snapshot`. Read the project's latest requirements; a user's correction supersedes an older model or note. Record these in the project when they are not already clear:

- Axis directions, front/back/top/bottom, mounting face and mating datums.
- Dimensions with their sources: measured, manufacturer drawing, inferred or provisional.
- Requested change, affected parts and dimensions/interfaces to preserve.
- Print orientation and installation/removal direction for functional parts.
- For reference-driven styling: silhouette, primary volumes, cut/recess shapes and rounded transitions; identify which functional surfaces must stay accessible.

Resolve coordinate ambiguity from the existing model and supplied images first. Ask only for information needed to choose safely; continue independent work. Keep project-specific dimensions in the project, not this global skill.

## Editing and review

1. Measure the relevant geometry before editing. For fit changes, check connector axes, insertion travel, cable clearance, fastener reach and assembly sequence as well as solid intersections.
2. Prefer a local feature change that satisfies the request. When broader geometry changes are necessary, explain which dependency requires them and preserve unaffected mating datums.
3. Run Fusion operations sequentially. Use `--expect-document` and, when appropriate, `--expect-version` for scripts that write. The guard runs inside Fusion before user script code; it is not a sandbox and does not prevent a script from switching documents itself.
4. Save meaningful milestones in the existing document. Confirm the observed saved version; a save request being accepted is not proof that asynchronous cloud storage has finished. Use a separate document only when requested or needed for a clearly identified presentation/branch.
5. Compare before/after geometry against the preserved dimensions. Inspect feature warnings, body count and relevant interference, including separately identified intentional press fits.
6. View the affected faces and assembly directly. For enclosure shape changes use side, rear and internal views as needed, comparing the silhouette and transition surfaces to the supplied reference. Verify controls remain reachable and correctly exposed after exterior changes. Topology checks do not establish appearance, printability or real-world fit.

For CAD API pitfalls, recovery and print checks, read [Fusion operations](references/fusion-operations.md). For exports and durable project organization, read [Delivery](references/delivery.md).

## Commands

```sh
fusion-mcp snapshot --output work/before.json
fusion-mcp run work/edit.py --write --expect-document 'DATA_FILE_ID' --expect-version 12
fusion-mcp save --summary 'Describe the actual change' --expect-document 'DATA_FILE_ID'
fusion-mcp screenshot --direction current
fusion-mcp bundle exports/review-v13 --expect-document 'DATA_FILE_ID' --expect-version 13 --body 'root::Housing'
```

`run` sends `readOnly=true` unless `--write` is given; this is an adapter request, not an OS-level sandbox. `snapshot` is read-only. `bundle` exports files without changing geometry or saving the document; it requires a saved, unmodified design and a filesystem shared with Fusion.

`screenshot` decodes directly to a unique user-private file in `/tmp/fusion-mcp` and prints only its path. `--output`, `--output-dir` or `FUSION_MCP_SCREENSHOT_DIR` override the destination. Keep reusable modeling scripts under the project; temporary screenshots may stay in `/tmp`.

## Client maintenance

When a task reveals a reusable client limitation, improve the maintained repository. Keep model-specific geometry out of the transport library. Add focused tests for consequential behavior, run the documented package checks, and distinguish mock tests from live Fusion evidence. Do not mutate the user's design merely to test the client; use read-only probes or an identified disposable document.

The skill source is versioned at `skills/fusion-mcp-client/` in the library repository. Keep that source and the installed skill synchronized, preserving unrelated local metadata. Publish/reinstall when authorized by the task; this skill does not independently grant publishing permission.

```sh
python3 -m unittest discover -s tests -v
uv build
uv tool install --reinstall git+https://github.com/hitsmaxft/fusion-mcp-client.git
fusion-mcp --version
```

Use a relevant live command after installation. `uv tool` exposes the CLI globally; projects importing the Python library need their own dependency declaration. Do not automatically retry a timed-out write: inspect whether Fusion applied it first.
