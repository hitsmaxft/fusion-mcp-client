import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from fusion_mcp_client import FusionMCPClient, FusionToolError, unwrap_tool_result
from fusion_mcp_client.cli import main

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


class MCPHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list] = []
    sse_tools: ClassVar[bool] = False

    def log_message(self, _format, *args):
        pass

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append((payload, dict(self.headers)))
        method = payload["method"]
        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if (
            method != "initialize"
            and self.headers.get("MCP-Session-Id") != "test-session"
        ):
            self.send_error(400, "missing session")
            return
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "serverInfo": {"name": "test", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [{"name": "fusion_mcp_read"}, {"name": "fusion_mcp_execute"}]
            }
        elif method == "tools/call":
            params = payload["params"]
            if (
                params["name"] == "fusion_mcp_read"
                and params["arguments"].get("queryType") == "screenshot"
            ):
                import base64

                result = {
                    "content": [
                        {
                            "type": "image",
                            "mimeType": "image/png",
                            "data": base64.b64encode(PNG).decode(),
                        }
                    ]
                }
            else:
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"success": True, "received": params},
                                ensure_ascii=False,
                            ),
                        }
                    ]
                }
        else:
            self.send_error(404)
            return
        message = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        if method == "tools/list" and type(self).sse_tools:
            notice = {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {},
            }
            body = (
                "data: "
                + json.dumps(notice)
                + "\n\n"
                + "data: "
                + json.dumps(message)
                + "\n\n"
            ).encode()
            content_type = "text/event-stream"
        else:
            body = json.dumps(message).encode()
            content_type = "application/json"
        self.send_response(200)
        if method == "initialize":
            self.send_header("MCP-Session-Id", "test-session")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self):
        self.send_response(200)
        self.end_headers()


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/mcp"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        MCPHandler.requests = []
        MCPHandler.sse_tools = False

    def test_session_and_script_read_only_default(self):
        with FusionMCPClient(self.url) as fusion:
            self.assertEqual(len(fusion.list_tools()), 2)
            result = fusion.execute_script("def run(_context: str):\n    print('ok')\n")
        self.assertTrue(result["success"])
        methods = [payload["method"] for payload, _ in MCPHandler.requests]
        self.assertEqual(
            methods[:4],
            ["initialize", "notifications/initialized", "tools/list", "tools/call"],
        )
        self.assertEqual(
            MCPHandler.requests[3][0]["params"]["arguments"]["object"]["readOnly"], True
        )
        self.assertEqual(MCPHandler.requests[3][1]["Mcp-Session-Id"], "test-session")

    def test_sse_response_can_follow_progress_notification(self):
        MCPHandler.sse_tools = True
        with FusionMCPClient(self.url) as fusion:
            self.assertEqual(fusion.list_tools()[0]["name"], "fusion_mcp_read")

    def test_screenshot_is_decoded_to_shared_temp_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(os.environ, {"FUSION_MCP_SCREENSHOT_DIR": directory}),
                FusionMCPClient(self.url) as fusion,
            ):
                path = fusion.capture_screenshot(direction="top", width=640, height=480)
            self.assertEqual(path.parent, Path(directory).resolve())
            self.assertEqual(path.read_bytes(), PNG)
            args = MCPHandler.requests[-1][0]["params"]["arguments"]
            self.assertEqual(args["direction"], "top")
            self.assertEqual(args["width"], 640)

    def test_cli_screenshot_prints_only_file_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    ["--url", self.url, "screenshot", "--output-dir", directory]
                )
            self.assertEqual(code, 0)
            lines = output.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(Path(lines[0]).read_bytes(), PNG)

    def test_tool_error_is_raised(self):
        with self.assertRaises(FusionToolError):
            unwrap_tool_result(
                {
                    "isError": True,
                    "content": [{"type": "text", "text": "script failed"}],
                }
            )


if __name__ == "__main__":
    unittest.main()
