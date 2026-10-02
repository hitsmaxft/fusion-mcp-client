# fusion-mcp-client

A small Python library and command-line tool for Autodesk Fusion's **local** MCP
endpoint. It grew from scripts used to inspect and edit a live Fusion design.
It uses only the Python standard library at runtime.

The default endpoint is `http://127.0.0.1:27182/mcp`. Fusion must be running
with its MCP service enabled. The client speaks the adapter's MCP `2025-06-18`
initialize/session flow; it is deliberately narrower than a general MCP SDK.

## Install for all your projects

```sh
uv tool install git+https://github.com/hitsmaxft/fusion-mcp-client.git
fusion-mcp --version
```

`uv tool install` keeps the command in an isolated, persistent tool environment
on your user `PATH`. For use as an importable library in a project, add the Git
repository as a dependency instead:

```sh
uv add git+https://github.com/hitsmaxft/fusion-mcp-client.git
```

## Command line

```sh
fusion-mcp tools
fusion-mcp read '{"queryType":"document","operation":"open"}'
fusion-mcp run inspect.py                    # read-only by default
fusion-mcp run edit.py --write               # permit design changes
fusion-mcp screenshot --direction iso-top-right --width 1400 --height 900
fusion-mcp save --summary 'Add printable rail'
```

`screenshot` decodes the image and writes a unique file directly under
`/tmp/fusion-mcp` by default, then prints **only its absolute path**. This
stable temporary directory is accessible to other projects running under the
same user; the command never dumps screenshot base64 into the terminal. Use
`--output path.png`, `--output-dir directory`, or
`FUSION_MCP_SCREENSHOT_DIR` to choose another location. Files are created with
user-only permissions because screenshots may contain private design data.

Set `FUSION_MCP_URL` or pass `--url` before the subcommand for another endpoint.
The `read` and `call` commands accept JSON objects; `call` also accepts
`@arguments.json`.

## Python

```python
from fusion_mcp_client import FusionMCPClient

with FusionMCPClient() as fusion:
    document = fusion.read(queryType="document", operation="open")
    print(document)

    image_path = fusion.capture_screenshot(direction="current")
    print(image_path)  # /tmp/fusion-mcp/fusion-....png

    result = fusion.execute_script(
        "def run(_context: str):\n    print('Fusion is connected')\n"
    )
    print(result)
```

`execute_script` is read-only by default. Pass `read_only=False` only for a
script that intentionally modifies the active design. `call_tool` exposes the
raw MCP tool result when you need a tool not covered by the convenience methods.

## Development

```sh
python3 -m unittest discover -s tests -v
uv build
```

The tests use a local mock HTTP server and do not need Fusion. A live Fusion
smoke test requires its MCP listener on port 27182.

## 中文速览

安装后可在任意项目中运行 `fusion-mcp screenshot`，截图会自动解码到
`/tmp/fusion-mcp`，命令只输出文件路径。`fusion-mcp run script.py` 默认只读；
确实要修改 Fusion 文档时再加 `--write`。`base` 与 `holder` 等实体的建模逻辑
由你提供的 Fusion 脚本决定，本库只负责 MCP 通讯和文件导出。

## Document-aware workflows (0.2)

Inspect the active design before editing:

```sh
fusion-mcp snapshot --output work/before.json
fusion-mcp run work/edit.py --write --expect-document 'DATA_FILE_ID' --expect-version 12
fusion-mcp save --summary 'Adjusted mounting clearance' --expect-document 'DATA_FILE_ID'
```

The optional guard checks `dataFile.id` and `versionNumber` **inside Fusion before
executing user code**, including top-level script statements. A mismatch stops
execution. It does not sandbox Python or stop a script from switching documents
itself. Without guard arguments, existing `run`/`save` behavior is unchanged.
A version check identifies a saved revision; it does not prove that there are no
unsaved edits. `snapshot` reports `modified` separately.

`snapshot` reports assembly-context BRep bodies (bounds in mm), selectors,
entity tokens, solid/coedge status, timeline warnings and visible BaseFeature
source bodies. It is a read-only inventory, not a physical-fit certification.

## Export a review bundle

```sh
fusion-mcp bundle exports/review-v13 \
  --expect-document 'DATA_FILE_ID' --expect-version 13 \
  --body 'root::Housing' --body 'root::Front cover'
```

This command requires the same local filesystem as Fusion, a **new** output
folder, and a saved/unmodified active design. Select bodies explicitly by a
snapshot selector or a unique exact name. Duplicate/ambiguous selections fail.

The bundle contains:

- `design.f3d`: the complete design, including reference geometry.
- `part-NN.stl` and `.obj`: selected single solids in **mm**, retaining assembly
  coordinates; `manifest.json` maps file stems to original selectors.
- `current.png`: the current Fusion viewport at 1600×1200, without changing the
  camera or visibility. Existing grids/background remain as displayed.
- `snapshot.json` and `manifest.json`: observed document ID/version, inventory,
  export checks, file sizes and SHA-256 hashes.

Mesh tolerance defaults to 0.01 mm (`--tolerance-mm`). Single-solid and coedge
checks run before export. These do not establish full mesh topology, print
orientation, material strength or actual component fit; the manifest explicitly
marks physical fit and complete mesh topology as unverified.

A failed or timed-out operation leaves `INCOMPLETE` in its output folder. Never
publish that folder as a completed delivery. A timeout can occur after Fusion
has applied an operation: inspect its state before retrying. The client never
automatically replays writes. It does not coordinate different CLI processes;
keep Fusion operations sequential.

Python equivalents:

```python
with FusionMCPClient() as fusion:
    state = fusion.snapshot()
    fusion.execute_script(script, read_only=False,
                          expected_document_id=state["document"]["id"],
                          expected_version=state["document"]["version"])
    # Save and inspect the observed saved version before exporting.
    fusion.export_bundle("exports/review", bodies=["root::Housing"],
                         expected_document_id=state["document"]["id"])
```

A guarded save returns whether Fusion accepted the request and the document
metadata observed immediately before/after. It does not wait for asynchronous
cloud storage completion. The `readOnly` adapter argument is not an OS sandbox.

Validation for 0.2.0: automated tests cover document guards before user code,
mesh unit conversion/serialization, bundle checksums and interrupted exports.
Live Fusion checks covered snapshots, wrong-document refusal, modified-design
export refusal and unchanged before/after inventory. A successful complete
bundle export has not yet been verified against live Fusion.

## Agent skill

The maintained skill is in [`skills/fusion-mcp-client`](skills/fusion-mcp-client/SKILL.md).
It covers coordinate/requirement baselines, bounded geometry changes, mating and
print checks, recovery, and version-consistent delivery. Project-specific CAD
parameters belong in the project. The CLI installation does not automatically
install the skill; copy that skill folder to your configured skills directory.
