"""Command-line interface for fusion-mcp-client."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .client import DEFAULT_URL, FusionMCPClient, FusionMCPError, unwrap_tool_result


def _json_argument(value: str) -> dict[str, Any]:
    try:
        if value.startswith("@"):
            value = Path(value[1:]).read_text(encoding="utf-8")
        data = json.loads(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError("JSON arguments must be an object")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fusion-mcp",
        description="Use Autodesk Fusion's local MCP service from Python or a shell.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("FUSION_MCP_URL", DEFAULT_URL),
        help="MCP endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="List available Fusion MCP tools")

    read = sub.add_parser("read", help="Call fusion_mcp_read with a JSON object")
    read.add_argument(
        "query",
        type=_json_argument,
        help='JSON object, e.g. \'{"queryType":"document","operation":"open"}\'',
    )

    call = sub.add_parser("call", help="Call any MCP tool")
    call.add_argument("name", help="Full MCP tool name")
    call.add_argument(
        "arguments",
        type=_json_argument,
        nargs="?",
        default={},
        help="JSON object or @path/to/arguments.json",
    )

    run = sub.add_parser(
        "run", help="Run a Fusion Python script defining run(_context)"
    )
    run.add_argument("script", help="Script file, or - for standard input")
    run.add_argument(
        "--write",
        action="store_true",
        help="Allow the script to modify the active Fusion design",
    )

    screenshot = sub.add_parser(
        "screenshot", help="Save screenshot directly to a temp file"
    )
    screenshot.add_argument(
        "--direction",
        default="current",
        choices=[
            "current",
            "front",
            "back",
            "bottom",
            "top",
            "left",
            "right",
            "iso-bottom-left",
            "iso-bottom-right",
            "iso-top-left",
            "iso-top-right",
        ],
    )
    screenshot.add_argument("--width", type=int)
    screenshot.add_argument("--height", type=int)
    screenshot.add_argument("--output", type=Path, help="Write to an explicit file")
    screenshot.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for a unique file (default: /tmp/fusion-mcp)",
    )

    save = sub.add_parser("save", help="Save the active Fusion document")
    save.add_argument("--summary", default="Save document", help="Short save summary")
    return parser


def _print(value: Any) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        with FusionMCPClient(args.url, timeout=args.timeout) as fusion:
            if args.command == "tools":
                _print(fusion.list_tools())
            elif args.command == "read":
                _print(fusion.read(**args.query))
            elif args.command == "call":
                _print(unwrap_tool_result(fusion.call_tool(args.name, args.arguments)))
            elif args.command == "run":
                script = (
                    sys.stdin.read()
                    if args.script == "-"
                    else Path(args.script).read_text(encoding="utf-8")
                )
                _print(fusion.execute_script(script, read_only=not args.write))
            elif args.command == "screenshot":
                path = fusion.capture_screenshot(
                    direction=args.direction,
                    width=args.width,
                    height=args.height,
                    output=args.output,
                    output_dir=args.output_dir,
                )
                print(path)
            elif args.command == "save":
                _print(fusion.save_document(args.summary))
    except (FusionMCPError, OSError, ValueError) as exc:
        print(f"fusion-mcp: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
