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
