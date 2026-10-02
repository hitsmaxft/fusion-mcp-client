"""Generate scripts executed in Fusion's Python interpreter (not imported here)."""

import json

MARKER = "FUSION_MCP_RESULT:"

RUNTIME = r"""
import adsk.core, adsk.fusion, json, math, struct
from pathlib import Path

def _document():
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if not doc:
        raise RuntimeError('No active Fusion document')
    data = doc.dataFile
    return {'name': doc.name, 'id': data.id if data else None,
            'version': data.versionNumber if data else None,
            'modified': doc.isModified}

def _guard(expected_id, expected_version):
    state = _document()
    if expected_id is not None and state['id'] != expected_id:
        raise RuntimeError('Document mismatch: expected %r, active %r' % (expected_id, state['id']))
    if expected_version is not None and state['version'] != expected_version:
        raise RuntimeError('Version mismatch: expected %r, active %r' % (expected_version, state['version']))
    return state

def _design():
    d = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    if not d:
        raise RuntimeError('Active product is not a Fusion Design')
    return d

def _bodies(d):
    for b in d.rootComponent.bRepBodies:
        yield 'root::' + b.name, b
    for occurrence in d.rootComponent.allOccurrences:
        for b in occurrence.bRepBodies:
            yield occurrence.fullPathName + '::' + b.name, b

def _snapshot():
    d = _design()
    bodies = []
    for selector, b in _bodies(d):
        bb = b.boundingBox
        bodies.append({'selector': selector, 'name': b.name, 'entity_token': b.entityToken,
            'visible': b.isVisible, 'solid': b.isSolid, 'lumps': b.lumps.count,
            'volume_mm3': b.volume * 1000,
            'bounds_mm': [v * 10 for p in (bb.minPoint, bb.maxPoint) for v in p.asArray()],
            'bad_coedges': sum(e.coEdges.count != 2 for e in b.edges)})
    warnings = []
    for i in range(d.timeline.count):
        e = d.timeline.item(i).entity
        if hasattr(e, 'healthState') and e.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            warnings.append({'name': e.name, 'message': e.errorOrWarningMessage})
    sources = []
    for comp in d.allComponents:
        for feature in comp.features.baseFeatures:
            sources.extend(b.name for b in feature.sourceBodies if b.isVisible)
    return {'document': _document(), 'units': 'mm', 'bodies': bodies,
            'warnings': warnings, 'visible_source_bodies': sources}

def _emit(value):
    print('FUSION_MCP_RESULT:' + json.dumps(value, ensure_ascii=False))
"""


def guarded_script(script: str, expected_id: str | None, version: int | None) -> str:
    # Guard precedes exec, including any top-level user statements. This is an
    # accidental-target check, not a sandbox against scripts switching documents.
    return (
        RUNTIME
        + f"""\ndef run(_context):
    _guard({expected_id!r}, {version!r})
    scope = {{'__name__': '__fusion_user_script__'}}
    exec(compile({script!r}, '<fusion-mcp user script>', 'exec'), scope)
    scope['run'](_context)
"""
    )


def snapshot_script() -> str:
    return RUNTIME + "\ndef run(_context):\n    _emit(_snapshot())\n"


def save_script(summary: str, expected_id: str, version: int | None) -> str:
    return (
        RUNTIME
        + f"""\ndef run(_context):
    before = _guard({expected_id!r}, {version!r})
    accepted = adsk.core.Application.get().activeDocument.save({summary!r})
    if not accepted:
        raise RuntimeError('Fusion did not accept the save request')
    _emit({{'accepted': bool(accepted), 'before': before, 'after': _document()}})
"""
    )


EXPORT = r"""
def run(_context):
    _guard(OPTIONS['expected_id'], OPTIONS['expected_version'])
    d = _design()
    before = _snapshot()
    if before['document']['modified']:
        raise RuntimeError('Save the design and confirm its version before exporting a bundle')
    if before['warnings'] or before['visible_source_bodies']:
        raise RuntimeError('Resolve timeline warnings and visible BaseFeature source bodies before export')
    inventory = list(_bodies(d))
    chosen = []
    for requested in OPTIONS['bodies']:
        matches = [(s, b) for s, b in inventory if s == requested or b.name == requested]
        if len(matches) != 1:
            raise RuntimeError('Body selector must match exactly one body: %r (%d matches)' % (requested, len(matches)))
        selector, b = matches[0]
        if any(selector == s for s, _ in chosen):
            raise RuntimeError('Duplicate body selection: ' + selector)
        if not b.isSolid or b.lumps.count != 1 or any(e.coEdges.count != 2 for e in b.edges):
            raise RuntimeError('Body is not a single closed solid: ' + selector)
        chosen.append((selector, b))
    folder = Path(OPTIONS['folder'])
    parts = []
    for number, (selector, b) in enumerate(chosen, 1):
        stem = 'part-%02d' % number
        calc = b.meshManager.createMeshCalculator()
        calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.HighQualityTriangleMesh)
        calc.surfaceTolerance = OPTIONS['tolerance_mm'] / 10
        mesh = calc.calculate()
        if not mesh or mesh.triangleCount < 1:
            raise RuntimeError('No mesh: ' + selector)
        xyz, indices = mesh.nodeCoordinatesAsDouble, mesh.nodeIndices
        vertices = [tuple(v * 10 for v in xyz[i:i+3]) for i in range(0, len(xyz), 3)]
        faces = [tuple(indices[i:i+3]) for i in range(0, len(indices), 3)]
        # Mesh coordinates and all exported positions are in assembly context, mm.
        with (folder / (stem + '.obj')).open('w') as f:
            f.write('# Units: mm; Fusion assembly coordinates\n')
            for vertex in vertices:
                f.write('v %.9f %.9f %.9f\n' % vertex)
            for face in faces:
                f.write('f %d %d %d\n' % tuple(i + 1 for i in face))
        with (folder / (stem + '.stl')).open('wb') as f:
            f.write(b'Fusion MCP; units mm'.ljust(80, b'\0'))
            f.write(struct.pack('<I', len(faces)))
            for face in faces:
                a, b0, c = [vertices[i] for i in face]
                u = [b0[i]-a[i] for i in range(3)]
                v = [c[i]-a[i] for i in range(3)]
                n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
                length = math.sqrt(sum(x*x for x in n))
                if length == 0:
                    raise RuntimeError('Degenerate exported triangle: ' + selector)
                f.write(struct.pack('<12fH', *(x/length for x in n), *a, *b0, *c, 0))
        parts.append({'selector': selector, 'stem': stem, 'triangles': len(faces),
                      'cad_volume_mm3': b.volume * 1000})
    archive = d.exportManager.createFusionArchiveExportOptions(str(folder / 'design.f3d'))
    if not d.exportManager.execute(archive):
        raise RuntimeError('Fusion archive export failed')
    # Capture current camera and visibility in the same call; do not change either.
    if not adsk.core.Application.get().activeViewport.saveAsImageFile(str(folder / 'current.png'), 1600, 1200):
        raise RuntimeError('Viewport capture failed')
    after = _snapshot()
    if before != after:
        raise RuntimeError('Design state changed during export; bundle is incomplete')
    (folder / 'snapshot.json').write_text(json.dumps(before, ensure_ascii=False, indent=2))
    _emit({'document': before['document'], 'units': 'mm', 'parts': parts,
           'checks': {'single_solid': True, 'coedges': True,
                      'physical_fit_verified': False, 'mesh_topology_verified': False}})
"""


def export_script(options: dict) -> str:
    return (
        RUNTIME + "\nOPTIONS = json.loads(" + repr(json.dumps(options)) + ")\n" + EXPORT
    )
