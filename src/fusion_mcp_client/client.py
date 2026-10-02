"""Synchronous Streamable HTTP client for Fusion's local MCP adapter.

The adapter used to develop this package speaks MCP protocol 2025-06-18 and
returns JSON-RPC responses as either JSON or server-sent events. This is a
focused client for that adapter, not a replacement for the full MCP SDK.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from types import TracebackType
from typing import Any

DEFAULT_URL = "http://127.0.0.1:27182/mcp"
PROTOCOL_VERSION = "2025-06-18"


class FusionMCPError(RuntimeError):
    """Base error raised by this package."""


class MCPTransportError(FusionMCPError):
    """The HTTP exchange with the MCP endpoint failed."""


class MCPProtocolError(FusionMCPError):
    """The endpoint returned an invalid or failed JSON-RPC response."""


class FusionToolError(FusionMCPError):
    """A Fusion MCP tool returned ``isError: true``."""


def default_screenshot_dir() -> Path:
    """A stable temporary directory shared across local projects.

    On Unix/macOS this is /tmp/fusion-mcp, rather than macOS's per-process
    $TMPDIR under /var/folders. The environment variable can override it.
    """
    configured = os.environ.get("FUSION_MCP_SCREENSHOT_DIR")
    if configured:
        return Path(configured).expanduser()
    temp_root = Path("/tmp") if Path("/tmp").is_dir() else Path(tempfile.gettempdir())
    return temp_root / "fusion-mcp"


def unwrap_tool_result(result: dict[str, Any]) -> Any:
    """Return structured content or parse Fusion's single JSON text block."""
    if result.get("isError"):
        messages = [
            str(c.get("text", ""))
            for c in result.get("content", [])
            if c.get("type") == "text"
        ]
        raise FusionToolError("; ".join(messages) or "Fusion tool failed")
    if "structuredContent" in result:
        value = result["structuredContent"]
        if isinstance(value, dict) and value.get("success") is False:
            raise FusionToolError(
                str(value.get("error") or value.get("message") or value)
            )
        return value
    blocks = result.get("content", [])
    if len(blocks) == 1 and blocks[0].get("type") == "text":
        value = blocks[0].get("text", "")
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value
        if isinstance(parsed, dict) and parsed.get("success") is False:
            raise FusionToolError(
                str(parsed.get("error") or parsed.get("message") or parsed)
            )
        return parsed
    return result


class FusionMCPClient:
    """A small reusable client for Fusion's local MCP endpoint.

    Use as a context manager so the server session is closed when possible::

        with FusionMCPClient() as fusion:
            print(fusion.list_tools())
    """

    def __init__(self, url: str | None = None, *, timeout: float = 120.0) -> None:
        self.url = url or os.environ.get("FUSION_MCP_URL", DEFAULT_URL)
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("MCP URL must use HTTP or HTTPS")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self.session_id: str | None = None
        self.protocol_version = PROTOCOL_VERSION
        self._initialized = False
        self._next_id = 1

    def __enter__(self) -> FusionMCPClient:  # noqa: PYI034 - keep Python 3.10 support
        self.initialize()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        if self._initialized:
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _post(self, message: dict[str, Any], expected_id: int | None) -> dict[str, Any]:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                session = response.headers.get("MCP-Session-Id")
                if session:
                    self.session_id = session
                content_type = response.headers.get("Content-Type", "")
                if expected_id is None:
                    response.read()
                    return {}
                if "text/event-stream" in content_type:
                    reply = self._read_sse(response, expected_id)
                else:
                    raw = response.read()
                    try:
                        reply = json.loads(raw)
                    except (TypeError, ValueError) as exc:
                        raise MCPProtocolError("Expected a JSON-RPC response") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode("utf-8", "replace").strip()
            raise MCPTransportError(
                f"HTTP {exc.code} from {self.url}: {detail}"
            ) from exc
        except (TimeoutError, ConnectionError) as exc:
            raise MCPTransportError(
                "Connection timed out or broke; Fusion may still be executing. "
                "Inspect the active document before retrying a write."
            ) from exc
        except urllib.error.URLError as exc:
            raise MCPTransportError(
                f"Could not reach {self.url}: {exc.reason}"
            ) from exc
        if not isinstance(reply, dict) or reply.get("id") != expected_id:
            raise MCPProtocolError(f"Expected JSON-RPC response id {expected_id}")
        if "error" in reply:
            error = reply["error"]
            message = error.get("message", error) if isinstance(error, dict) else error
            raise MCPProtocolError(str(message))
        if "result" not in reply:
            raise MCPProtocolError("JSON-RPC response has no result")
        return reply["result"]

    @staticmethod
    def _read_sse(response: Any, expected_id: int) -> dict[str, Any]:
        data_lines: list[str] = []
        for raw_line in response:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif not line and data_lines:
                payload = "\n".join(data_lines)
                data_lines.clear()
                try:
                    event = json.loads(payload)
                except ValueError as exc:
                    raise MCPProtocolError("Invalid JSON in MCP SSE event") from exc
                if isinstance(event, dict) and event.get("id") == expected_id:
                    return event
        if data_lines:
            try:
                event = json.loads("\n".join(data_lines))
            except ValueError as exc:
                raise MCPProtocolError("Invalid JSON in final MCP SSE event") from exc
            if isinstance(event, dict) and event.get("id") == expected_id:
                return event
        raise MCPProtocolError(
            f"MCP SSE stream ended without response id {expected_id}"
        )

    def _request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        return self._post(payload, request_id)

    def initialize(self) -> dict[str, Any]:
        if self._initialized:
            return {"protocolVersion": self.protocol_version}
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fusion-mcp-client", "version": "0.2.0"},
            },
        )
        if not isinstance(result, dict):
            raise MCPProtocolError("initialize result is not an object")
        self.protocol_version = str(result.get("protocolVersion", PROTOCOL_VERSION))
        self._initialized = True
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, None)
        return result

    def close(self) -> None:
        if self.session_id:
            request = urllib.request.Request(
                self.url,
                headers={
                    "MCP-Session-Id": self.session_id,
                    "MCP-Protocol-Version": self.protocol_version,
                },
                method="DELETE",
            )
            try:
                with urllib.request.urlopen(request, timeout=min(self.timeout, 5.0)):
                    pass
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
            ):
                # Session termination is optional in the 2025 MCP transport.
                pass
        self.session_id = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        result = self._request("tools/list")
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            raise MCPProtocolError("tools/list response has no tools array")
        return tools

    def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._ensure_initialized()
        result = self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        if not isinstance(result, dict):
            raise MCPProtocolError("tools/call result is not an object")
        return result

    def read(self, **query: Any) -> Any:
        if "queryType" not in query:
            raise ValueError("read requires queryType")
        return unwrap_tool_result(self.call_tool("fusion_mcp_read", query))

    def execute_script(
        self,
        script: str,
        *,
        read_only: bool = True,
        expected_document_id: str | None = None,
        expected_version: int | None = None,
    ) -> Any:
        if "def run(" not in script:
            raise ValueError("Fusion script must define run(_context: str)")
        self._validate_expectation(expected_document_id, expected_version)
        if expected_document_id is not None:
            from .fusion_scripts import guarded_script

            script = guarded_script(script, expected_document_id, expected_version)
        arguments = {
            "featureType": "script",
            "object": {"script": script, "readOnly": read_only},
        }
        return unwrap_tool_result(self.call_tool("fusion_mcp_execute", arguments))

    def save_document(
        self,
        summary: str = "Save document",
        *,
        expected_document_id: str | None = None,
        expected_version: int | None = None,
    ) -> Any:
        self._validate_expectation(expected_document_id, expected_version)
        if expected_document_id is not None:
            from .fusion_scripts import save_script

            return self._script_result(
                self.execute_script(
                    save_script(summary, expected_document_id, expected_version),
                    read_only=False,
                )
            )
        arguments = {
            "featureType": "document",
            "object": {
                "operation": "save",
                "userMessageSummary": summary,
            },
        }
        return unwrap_tool_result(self.call_tool("fusion_mcp_execute", arguments))

    @staticmethod
    def _validate_expectation(document_id: str | None, version: int | None) -> None:
        if document_id is not None and (
            not isinstance(document_id, str) or not document_id.strip()
        ):
            raise ValueError("expected_document_id must be a nonempty string")
        if version is not None:
            if not document_id:
                raise ValueError("expected_version requires expected_document_id")
            if type(version) is not int or version < 1:
                raise ValueError("expected_version must be a positive integer")

    @staticmethod
    def _script_result(result: Any) -> dict[str, Any]:
        from .fusion_scripts import MARKER

        message = result.get("message", "") if isinstance(result, dict) else result
        if not isinstance(message, str):
            raise MCPProtocolError("Fusion script returned no textual result")
        lines = [
            line[len(MARKER) :]
            for line in message.splitlines()
            if line.startswith(MARKER)
        ]
        if len(lines) != 1:
            raise MCPProtocolError("Fusion script returned no unique result marker")
        try:
            value = json.loads(lines[0])
        except ValueError as exc:
            raise MCPProtocolError("Invalid Fusion script result JSON") from exc
        if not isinstance(value, dict):
            raise MCPProtocolError("Fusion script result is not an object")
        return value

    def snapshot(self) -> dict[str, Any]:
        """Read document identity, assembly body bounds (mm), and feature warnings."""
        from .fusion_scripts import snapshot_script

        return self._script_result(self.execute_script(snapshot_script()))

    def export_bundle(
        self,
        output: str | Path,
        *,
        bodies: list[str],
        expected_document_id: str,
        expected_version: int | None = None,
        tolerance_mm: float = 0.01,
    ) -> Path:
        """Export saved local Fusion design and explicit bodies into a new folder.

        Requires a shared filesystem with Fusion. A failed/timed-out export
        keeps its INCOMPLETE marker; it is never automatically replayed.
        """
        from .fusion_scripts import export_script

        self._validate_expectation(expected_document_id, expected_version)
        if not expected_document_id:
            raise ValueError("export_bundle requires expected_document_id")
        if not bodies or any(not isinstance(b, str) or not b.strip() for b in bodies):
            raise ValueError(
                "Select at least one body by exact name or snapshot selector"
            )
        if len(set(bodies)) != len(bodies):
            raise ValueError("Duplicate body selectors")
        if not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
            raise ValueError("tolerance_mm must be finite and positive")
        folder = Path(output).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=False, mode=0o700)
        incomplete = folder / "INCOMPLETE"
        incomplete.write_text(
            "Export has not completed. Do not treat this directory as a verified delivery.\n"
        )
        options = {
            "folder": str(folder),
            "bodies": bodies,
            "expected_id": expected_document_id,
            "expected_version": expected_version,
            "tolerance_mm": tolerance_mm,
        }
        try:
            result = self._script_result(self.execute_script(export_script(options)))
            required = ["design.f3d", "current.png", "snapshot.json"]
            required += [
                f"part-{i:02d}.{ext}"
                for i in range(1, len(bodies) + 1)
                for ext in ("obj", "stl")
            ]
            for name in required:
                if not (folder / name).is_file() or not (folder / name).stat().st_size:
                    raise MCPProtocolError("Missing exported file: " + name)
            if not zipfile.is_zipfile(folder / "design.f3d"):
                raise MCPProtocolError("Fusion archive is not a ZIP container")
            if (
                not (folder / "current.png")
                .read_bytes()
                .startswith(b"\x89PNG\r\n\x1a\n")
            ):
                raise MCPProtocolError("Exported screenshot is not a PNG")
            result["files"] = [
                {
                    "path": name,
                    "bytes": (folder / name).stat().st_size,
                    "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest(),
                }
                for name in required
            ]
            (folder / "manifest.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            incomplete.unlink()
            return folder
        except Exception as exc:
            raise FusionMCPError(
                f"Bundle incomplete at {folder}: {exc}. Inspect Fusion before retrying."
            ) from exc

    def capture_screenshot(
        self,
        *,
        direction: str = "current",
        width: int | None = None,
        height: int | None = None,
        output: str | Path | None = None,
        output_dir: str | Path | None = None,
    ) -> Path:
        """Capture, decode, and save a Fusion screenshot in one call.

        Default output is a unique file under /tmp/fusion-mcp (or the directory
        selected by FUSION_MCP_SCREENSHOT_DIR). No base64 is printed or returned.
        """
        query: dict[str, Any] = {"queryType": "screenshot", "direction": direction}
        if width is not None:
            query["width"] = width
        if height is not None:
            query["height"] = height
        result = self.call_tool("fusion_mcp_read", query)
        if result.get("isError"):
            unwrap_tool_result(result)
        images = [
            block for block in result.get("content", []) if block.get("type") == "image"
        ]
        if len(images) != 1:
            raise MCPProtocolError(
                f"Expected one screenshot image, found {len(images)}"
            )
        image = images[0]
        mime = image.get("mimeType", "image/png")
        suffixes = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        if mime not in suffixes:
            raise MCPProtocolError(f"Unsupported screenshot MIME type: {mime}")
        try:
            pixels = base64.b64decode(image["data"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise MCPProtocolError(
                "Screenshot is missing valid base64 image data"
            ) from exc
        folder = (
            Path(output_dir).expanduser() if output_dir else default_screenshot_dir()
        )
        target = Path(output).expanduser() if output else None
        if target is not None:
            folder = target.parent
        folder.mkdir(parents=True, exist_ok=True, mode=0o755)
        fd, temporary = tempfile.mkstemp(
            prefix="fusion-", suffix=suffixes[mime], dir=folder
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(pixels)
            if target is not None:
                os.replace(temporary, target)
                return target.resolve()
            return Path(temporary).resolve()
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
