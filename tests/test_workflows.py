# ruff: noqa: S102 -- Execute generated, repository-owned scripts against CAD stubs.
import ast
import hashlib
import json
import math
import struct
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_client import PNG

from fusion_mcp_client import (
    FusionMCPClient,
    FusionMCPError,
    FusionToolError,
    unwrap_tool_result,
)
from fusion_mcp_client.fusion_scripts import MARKER, export_script, guarded_script


class GuardTests(unittest.TestCase):
    def test_session_close_timeout_does_not_mask_original_error(self):
        c = FusionMCPClient()
        c.session_id = "test-session"
        with patch(
            "urllib.request.urlopen", side_effect=TimeoutError("close timed out")
        ):
            c.close()
        self.assertIsNone(c.session_id)

    def run_guard(self, expected_id, version, script):
        doc = types.SimpleNamespace(
            name="Part",
            dataFile=types.SimpleNamespace(id="id:A", versionNumber=7),
            isModified=False,
        )
        app = types.SimpleNamespace(activeDocument=doc, touched=False)
        core = types.ModuleType("adsk.core")
        core.Application = types.SimpleNamespace(get=lambda: app)
        fusion = types.ModuleType("adsk.fusion")
        adsk = types.ModuleType("adsk")
        adsk.core, adsk.fusion = core, fusion
        with patch.dict(
            "sys.modules", {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion}
        ):
            ns = {}
            exec(guarded_script(script, expected_id, version), ns)
            try:
                ns["run"](None)
            except RuntimeError:
                self.assertFalse(app.touched, "Guard must precede top-level user code")
                raise
        return app

    SCRIPT = "import adsk.core\nadsk.core.Application.get().touched=True\ndef run(ctx):\n    pass\n"

    def test_wrong_document_prevents_even_top_level_user_mutation(self):
        with self.assertRaisesRegex(RuntimeError, "Document mismatch"):
            self.run_guard("id:B", 7, self.SCRIPT)

    def test_stale_version_prevents_mutation(self):
        with self.assertRaisesRegex(RuntimeError, "Version mismatch"):
            self.run_guard("id:A", 6, self.SCRIPT)

    def test_correct_document_runs_original_script(self):
        self.assertTrue(self.run_guard("id:A", 7, self.SCRIPT).touched)

    def test_version_requires_id_before_network_call(self):
        c = FusionMCPClient()
        with patch.object(c, "call_tool") as call:
            with self.assertRaises(ValueError):
                c.execute_script(self.SCRIPT, expected_version=7)
            call.assert_not_called()

    def test_structured_tool_failure_raises(self):
        with self.assertRaisesRegex(FusionToolError, "bad geometry"):
            unwrap_tool_result(
                {"structuredContent": {"success": False, "message": "bad geometry"}}
            )

    def test_export_refuses_duplicate_matching_names(self):
        # Exercise generated server-side selection before any file export.
        source = export_script(
            {"expected_id": "id:A", "expected_version": 7, "bodies": ["Same"]}
        )
        module = ast.parse(source)
        run_node = next(
            n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "run"
        )
        ns = {
            "OPTIONS": {
                "expected_id": "id:A",
                "expected_version": 7,
                "bodies": ["Same"],
            },
            "_guard": lambda *a: None,
            "_design": lambda: None,
            "_snapshot": lambda: {
                "document": {"modified": False},
                "warnings": [],
                "visible_source_bodies": [],
            },
            "_bodies": lambda d: [
                ("root::Same", types.SimpleNamespace(name="Same")),
                ("Other::Same", types.SimpleNamespace(name="Same")),
            ],
        }
        exec(
            compile(ast.Module(body=[run_node], type_ignores=[]), "<test>", "exec"), ns
        )
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            ns["run"](None)


class BundleTests(unittest.TestCase):
    def test_generated_export_writes_mesh_in_mm(self):
        # Run the actual generated exporter against a tetrahedron CAD stub.
        # This verifies serialization and units, not Autodesk API compatibility.
        nsobj = types.SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            options = {
                "expected_id": "id:A",
                "expected_version": 7,
                "bodies": ["Part"],
                "folder": tmp,
                "tolerance_mm": 0.01,
            }
            module = ast.parse(export_script(options))
            run_node = next(
                n
                for n in module.body
                if isinstance(n, ast.FunctionDef) and n.name == "run"
            )
            mesh = nsobj(
                triangleCount=4,
                nodeCoordinatesAsDouble=[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1],
                nodeIndices=[0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3],
            )
            calc = nsobj(setQuality=lambda q: None, calculate=lambda: mesh)
            body = nsobj(
                name="Part",
                isSolid=True,
                lumps=nsobj(count=1),
                edges=[],
                meshManager=nsobj(createMeshCalculator=lambda: calc),
                volume=1 / 6,
            )
            state = {
                "document": {"modified": False, "id": "id:A", "version": 7},
                "warnings": [],
                "visible_source_bodies": [],
            }

            def archive(path):
                with zipfile.ZipFile(path, "w") as z:
                    z.writestr("fixture", "not real CAD")
                return True

            def screenshot(path, width, height):
                Path(path).write_bytes(PNG)
                return True

            design = nsobj(
                exportManager=nsobj(
                    createFusionArchiveExportOptions=lambda p: p, execute=archive
                )
            )
            adsk = nsobj(
                fusion=nsobj(
                    TriangleMeshQualityOptions=nsobj(HighQualityTriangleMesh=1)
                ),
                core=nsobj(
                    Application=nsobj(
                        get=lambda: nsobj(
                            activeViewport=nsobj(saveAsImageFile=screenshot)
                        )
                    )
                ),
            )
            emitted = []
            ns = {
                "OPTIONS": options,
                "Path": Path,
                "math": math,
                "struct": struct,
                "json": json,
                "adsk": adsk,
                "_guard": lambda *a: None,
                "_design": lambda: design,
                "_snapshot": lambda: state,
                "_bodies": lambda d: [("root::Part", body)],
                "_emit": emitted.append,
            }
            exec(
                compile(ast.Module(body=[run_node], type_ignores=[]), "<test>", "exec"),
                ns,
            )
            ns["run"](None)
            self.assertAlmostEqual(calc.surfaceTolerance, 0.001)
            obj = (Path(tmp) / "part-01.obj").read_text()
            self.assertIn("v 10.000000000 0.000000000 0.000000000", obj)
            stl = (Path(tmp) / "part-01.stl").read_bytes()
            self.assertEqual(len(stl), 84 + 4 * 50)
            self.assertEqual(struct.unpack_from("<I", stl, 80)[0], 4)
            triangle = struct.unpack_from("<12fH", stl, 84)
            self.assertEqual(triangle[6:9], (0.0, 10.0, 0.0))
            self.assertEqual(emitted[0]["parts"][0]["triangles"], 4)
            self.assertFalse(emitted[0]["checks"]["physical_fit_verified"])

    def fake_export(self, script, **kwargs):
        node = next(
            n
            for n in ast.parse(script).body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "OPTIONS" for t in n.targets)
        )
        options = json.loads(ast.literal_eval(node.value.args[0]))
        folder = Path(options["folder"])
        with zipfile.ZipFile(folder / "design.f3d", "w") as z:
            z.writestr("test", "archive fixture, not real CAD")
        (folder / "current.png").write_bytes(PNG)
        (folder / "snapshot.json").write_text("{}")
        (folder / "part-01.obj").write_text("# fixture\n")
        (folder / "part-01.stl").write_bytes(b"fixture")
        return {
            "message": MARKER
            + json.dumps({"document": {"id": "id:A", "version": 7}, "units": "mm"})
        }

    def test_bundle_manifest_hashes_and_completion_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = FusionMCPClient()
            with patch.object(
                c, "execute_script", side_effect=self.fake_export
            ) as call:
                out = c.export_bundle(
                    Path(tmp) / "new",
                    bodies=["Part"],
                    expected_document_id="id:A",
                    expected_version=7,
                )
            call.assert_called_once()
            self.assertFalse((out / "INCOMPLETE").exists())
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["units"], "mm")
            for item in manifest["files"]:
                self.assertEqual(
                    item["sha256"],
                    hashlib.sha256((out / item["path"]).read_bytes()).hexdigest(),
                )

    def test_existing_folder_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = FusionMCPClient()
            with patch.object(c, "execute_script") as call:
                with self.assertRaises(FileExistsError):
                    c.export_bundle(tmp, bodies=["Part"], expected_document_id="id:A")
                call.assert_not_called()

    def test_lost_response_leaves_incomplete_and_never_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = FusionMCPClient()
            with patch.object(
                c, "execute_script", side_effect=TimeoutError("lost")
            ) as call:
                with self.assertRaisesRegex(FusionMCPError, "incomplete"):
                    c.export_bundle(
                        Path(tmp) / "new", bodies=["Part"], expected_document_id="id:A"
                    )
                call.assert_called_once()
            self.assertTrue((Path(tmp) / "new/INCOMPLETE").exists())
            self.assertFalse((Path(tmp) / "new/manifest.json").exists())

    def test_missing_server_files_cannot_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = FusionMCPClient()
            with (
                patch.object(
                    c, "execute_script", return_value={"message": MARKER + "{}"}
                ),
                self.assertRaisesRegex(FusionMCPError, "Missing exported file"),
            ):
                c.export_bundle(
                    Path(tmp) / "new", bodies=["Part"], expected_document_id="id:A"
                )
            self.assertTrue((Path(tmp) / "new/INCOMPLETE").exists())


if __name__ == "__main__":
    unittest.main()
