"""MCP transport over exactly the direct tool vocabulary."""

from __future__ import annotations
import base64, contextlib, json, sys
from pathlib import Path
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

from .identity import GATES, MAX_JSON, INSTRUCTIONS, require

_POINT = dict(
    type="array",
    items=dict(type="integer", minimum=-2000000000, maximum=2000000000),
    minItems=2,
    maxItems=2,
)
_UIDS = dict(type="array", items=dict(type="string"), maxItems=32, uniqueItems=True)
_OPERATIONS = []
for _kind, _props in {
    "replace_chain": dict(
        track_uuids=_UIDS,
        points_nm=dict(type="array", items=_POINT, minItems=2, maxItems=33),
        allow_locked_track_uuids=_UIDS,
    ),
    "repair_chain": dict(
        track_uuids=_UIDS,
        points_nm=dict(type="array", items=_POINT, minItems=2, maxItems=33),
        allow_locked_track_uuids=_UIDS,
        layer=dict(type="string"),
        max_added_length_nm=dict(type="integer", minimum=0, maximum=16000000),
    ),
}.items():
    _OPERATIONS.append(
        dict(
            type="object",
            properties=dict(kind=dict(type="string", const=_kind), **_props),
            required=["kind", *_props],
            additionalProperties=False,
        )
    )

_POSES = dict(
    type="array",
    minItems=1,
    maxItems=8,
    items=dict(
        type="object",
        properties={
            "reference": dict(type="string"),
            "at_nm": _POINT,
            "rotation_deg": dict(type="integer", multipleOf=90),
        },
        required=["reference", "at_nm", "rotation_deg"],
        additionalProperties=False,
    ),
)
_ROUTES = dict(
    type="array",
    maxItems=64,
    items=dict(
        type="object",
        properties={
            "net": dict(type="string"),
            "layer": dict(type="string"),
            "width_nm": dict(type="integer", minimum=1),
            "points_nm": dict(type="array", items=_POINT, minItems=2, maxItems=33),
        },
        required=["net", "layer", "width_nm", "points_nm"],
        additionalProperties=False,
    ),
)
_VIAS = dict(
    type="array",
    maxItems=32,
    items=dict(
        type="object",
        properties={
            "net": dict(type="string"),
            "at_nm": _POINT,
            "diameter_nm": dict(type="integer", minimum=1),
            "drill_nm": dict(type="integer", minimum=1),
        },
        required=["net", "at_nm", "diameter_nm", "drill_nm"],
        additionalProperties=False,
    ),
)
for _kind, _props in {
    "add_connections": dict(routes=_ROUTES, vias=_VIAS),
    "ground_plane_extension": dict(
        zone_uuid=dict(type="string", minLength=1),
        outline_nm=dict(type="array", items=_POINT, minItems=4, maxItems=64),
    ),
    "outline_trim": dict(
        edge_uuid=dict(type="string", minLength=1),
        position_nm=dict(type="integer", minimum=-2000000000, maximum=2000000000),
    ),
    "place_cell": dict(
        poses=_POSES,
        reference_group_uuids=dict(type="array", items=dict(type="string", minLength=1), maxItems=8, uniqueItems=True),
        routes=_ROUTES,
        vias=dict(type="array", maxItems=0, items=_VIAS["items"]),
        max_shift_nm=dict(type="integer", minimum=1, maximum=32000000),
        allow_locked_footprint_uuids=_UIDS,
        allow_locked_track_uuids=dict(
            type="array", items=dict(type="string"), maxItems=256, uniqueItems=True
        ),
    ),
    "power_contour": dict(
        track_uuids=dict(
            type="array",
            items=dict(type="string"),
            minItems=1,
            maxItems=128,
            uniqueItems=True,
        ),
        style=dict(type="string", enum=["square", "chamfer45"]),
        allow_locked_track_uuids=_UIDS,
        allow_grouped_track_uuids=_UIDS,
    ),
    "power_route": dict(
        track_uuids=_UIDS,
        points_nm=dict(type="array", items=_POINT, minItems=2, maxItems=33),
        allow_locked_track_uuids=_UIDS,
    ),
    "bank_collector": dict(
        pad_uuids=dict(
            type="array",
            items=dict(type="string"),
            minItems=2,
            maxItems=32,
            uniqueItems=True,
        ),
        support_track_uuids=_UIDS,
        layer=dict(type="string"),
        chamfer_nm=dict(type="integer", minimum=1, maximum=1000000),
    ),
}.items():
    _OPERATIONS.append(
        dict(
            type="object",
            properties=dict(kind=dict(type="string", const=_kind), **_props),
            required=["kind", *_props],
            additionalProperties=False,
        )
    )

# Preserve the old exact operation contract. The opt-in is a separate closed
# schema alternative, not a newly mandatory field on all existing requests.
_old_cell = next(v for v in _OPERATIONS if v["properties"]["kind"]["const"] == "place_cell")
_OPERATIONS.append(dict(type="object",
    properties=dict(_old_cell["properties"], native_macro=dict(type="boolean", const=True),
        allow_locked_transport_uuids=dict(type="array",items=dict(type="string"),maxItems=128,uniqueItems=True)),
    required=[*_old_cell["required"], "native_macro", "allow_locked_transport_uuids"], additionalProperties=False))

# Explicit existing stage-role opt-in; preserve both original closed schemas.
for _cell_variant in (_old_cell, _OPERATIONS[-1]):
    _OPERATIONS.append(dict(type="object",
        properties=dict(_cell_variant["properties"],
            allow_linear_power_stage_reconstruction=dict(type="boolean")),
        required=[*_cell_variant["required"], "allow_linear_power_stage_reconstruction"],
        additionalProperties=False))

# Optional native-only work span; preserve the old closed alternatives and
# their required fields. Omission retains the original 8-mm compiler default.
_SOURCE_BOUNDARY_SPAN = dict(type="integer", minimum=1, maximum=32000000, default=8000000)
for _cell_variant in _OPERATIONS:
    if _cell_variant["properties"]["kind"]["const"] == "place_cell" and "native_macro" in _cell_variant["properties"]:
        _cell_variant["properties"]["max_source_boundary_span_nm"] = dict(_SOURCE_BOUNDARY_SPAN)

TOOL_PARAMETERS = {
    "boards": {},
    "inspect": {
        "board": {"type": "string"},
        "region_nm": {"type": ["array", "null"], "items": {"type": "integer"}},
        "limit": {"type": "integer", "minimum": 1, "maximum": 32},
        "references": dict(
            type=["array", "null"], items=dict(type="string"), maxItems=32
        ),
        "nets": dict(type=["array", "null"], items=dict(type="string"), maxItems=32),
    },
    "issues": {
        "board": dict(type="string"),
        "offset": dict(type="integer", minimum=0),
        "limit": dict(type="integer", minimum=1, maximum=32),
    },
    "stage": {
        "board": {"type": "string"},
        "expected_source_sha256": {"type": "string"},
        "intent": {"type": "string"},
        "target_issue_ids": dict(type="array", items=dict(type="string", minLength=64, maxLength=64),
                                 maxItems=32, uniqueItems=True),
        "target_field_issue_ids": dict(type="array", items=dict(type="string", pattern="^[a-f0-9]{64}$"),
                                       maxItems=32, uniqueItems=True),
        "operations": dict(
            type="array", items=dict(oneOf=_OPERATIONS), minItems=1, maxItems=8
        ),
    },
    "check": {
        "job": {"type": "string"},
        "gate": {
            "type": "string",
            "enum": [
                *GATES,
                "ordinary_delta",
                "current_pair",
                "kelvin_pair",
                "assembly_pair",
                "route_contract",
            ],
        },
    },
    "status": {"job": dict(type="string")},
    "validate": {"job": dict(type="string")},
    "campaign": {"limit": dict(type="integer", minimum=1, maximum=64)},
    "fork": {
        "job": dict(type="string"),
        "expected_candidate_sha256": dict(type="string"),
    },
    "plan_cell": {
        "board": dict(type="string"),
        "allow_linear_power_stage_reconstruction": dict(type="boolean"),
        "poses": _POSES,
        "reference_group_uuids": dict(type="array", items=dict(type="string", minLength=1), maxItems=8, uniqueItems=True),
        "allow_locked_footprint_uuids": _UIDS,
        "allow_locked_track_uuids": dict(
            type="array", items=dict(type="string"), maxItems=256, uniqueItems=True
        ),
        "max_shift_nm": dict(type="integer", minimum=1, maximum=32000000),
        "offset": dict(type="integer", minimum=0),
        "limit": dict(type="integer", minimum=1, maximum=32),
    },
    "grid": {
        "center_nm": _POINT,
        "rows": dict(type="integer", minimum=1, maximum=8),
        "columns": dict(type="integer", minimum=1, maximum=8),
        "pitch_nm": dict(type="integer", minimum=1, maximum=10000000),
    },
    "row": {
        "board": dict(type="string"),
        "references": dict(
            type="array",
            items=dict(type="string"),
            minItems=2,
            maxItems=8,
            uniqueItems=True,
        ),
        "axis": dict(type="string", enum=["x", "y"]),
        "origin_nm": _POINT,
        "pitch_nm": dict(type="integer", minimum=1, maximum=50000000),
        "rotation_deg": dict(type=["integer", "null"], multipleOf=90),
    },
    "verdict": {"job": {"type": "string"}},
    "select": {
        "job": {"type": "string"},
        "expected_candidate_sha256": {"type": "string"},
        "visual_review": {"type": "string"},
    },
    "render": {
        "job": {"type": "string"},
        "layer": {"type": "string"},
        "region_nm": {"type": ["array", "null"], "items": {"type": "integer"}},
        "guide": dict(
            type=["string", "null"],
            enum=[None, "F.Fab", "B.Fab", "F.Silkscreen", "B.Silkscreen"],
        ),
    },
}
REQUIRED = {
    "boards": [],
    "inspect": ["board"],
    "stage": ["board", "expected_source_sha256", "intent", "operations"],
    "check": ["job", "gate"],
    "verdict": ["job"],
    "select": ["job", "expected_candidate_sha256", "visual_review"],
    "render": ["job", "layer"],
}
REQUIRED.update(
    status=["job"],
    validate=["job"],
    campaign=[],
    fork=["job", "expected_candidate_sha256"],
    issues=["board"],
    plan_cell=["board", "poses"],
    grid=["center_nm", "rows", "columns", "pitch_nm"],
    row=["board", "references", "axis", "origin_nm", "pitch_nm"],
)
DESCRIPTIONS = {
    "boards": "List only the exact pinned nine-board checkpoint; no newest-file fallback.",
    "inspect": "Inspect native objects, route opportunities, repeated parts and actual power-zone intent. Returns integer nm, not inferred current ratings.",
    "stage": "Author an atomic private candidate using the closed received actor catalog. Optional target_issue_ids name exact source craft findings that must disappear. Explicit UUIDs/coordinates only. No baseline overwrite or admission.",
    "check": "Run one bounded independent check on the exact candidate. Failure/timeout remains failed/unknown.",
    "verdict": "Require all independent evidence; return review nonregression only, never manufacturing approval or automatic publication.",
    "select": "After independent checks and native visual review, select a private child for suite replay. Never overwrite originals or authorize release.",
    "render": "Generate actual saved native before/after copper SVGs for model visual review; never synthetic fill.",
}
DESCRIPTIONS.update(
    status="Read exact-candidate validation progress or completion; never restart a failed decision.",
    validate="Start a finite independent checklist in the background. At most two candidates; no search/retry/redesign loop.",
    campaign="Read durable decisions and completion/failure events; a plateau requires model replanning.",
    fork="Adopt a selected checked child as the next model work parent; original suite controls remain immutable.",
    plan_cell="Derive source-owned cuts and routing obligations for explicit poses before authoring a connected placement.",
    grid="Plan an exactly centered regular via grid. This grants no process, collision, thermal or current authority.",
)
DESCRIPTIONS["row"] = (
    "Compile a model-selected functional group to exact row/column poses. Stage those poses with explicit connected-cell routes; no blind global snapping."
)
DESCRIPTIONS["issues"] = (
    "Read a bounded, source-bound native/craft/field issue map with UUIDs, references, nets and a legend. Does not waive inherited faults."
)
DESCRIPTIONS["stage"] = (
    "Author explicit private route, connected-cell or source-retaining power-contour geometry. Independent checks and native visual review remain mandatory."
)


def dispatch(workbench, name, args):
    require(
        name in TOOL_PARAMETERS and type(args) is dict,
        "known_workbench_tool_and_object_arguments_required",
    )
    require(
        set(args) <= TOOL_PARAMETERS[name].keys()
        and set(REQUIRED[name]) <= args.keys(),
        "exact_tool_arguments_required",
    )
    return getattr(workbench, name)(**args)


def serve(workbench, stdin=sys.stdin, stdout=sys.stdout):
    """Small standard MCP 2025-06-18 stdio tool server, no SDK/network needed."""
    initialized = False
    for line in iter(lambda: stdin.readline(MAX_JSON + 1), ""):
        message = None
        try:
            require(len(line.encode()) <= MAX_JSON, "bounded_mcp_message_required")
            message = json.loads(line)
            require(
                type(message) is dict and message.get("jsonrpc") == "2.0",
                "jsonrpc_2_request_required",
            )
            method = message.get("method")
            params = message.get("params", {})
            if method == "notifications/initialized":
                initialized = True
                continue
            if "id" not in message:
                continue
            if method == "initialize":
                result = dict(
                    protocolVersion="2025-06-18",
                    capabilities={"tools": {"listChanged": False}},
                    serverInfo={"name": "cec-agentic-design", "version": "0.2.0"},
                    instructions=INSTRUCTIONS,
                )
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                require(initialized, "mcp_initialization_required")
                result = dict(
                    tools=[
                        dict(
                            name=n,
                            description=DESCRIPTIONS[n],
                            inputSchema=dict(
                                type="object",
                                properties=p,
                                required=REQUIRED[n],
                                additionalProperties=False,
                            ),
                            annotations=dict(
                                readOnlyHint=n == "boards",
                                destructiveHint=False,
                                openWorldHint=False,
                            ),
                        )
                        for n, p in TOOL_PARAMETERS.items()
                    ]
                )
            elif method == "tools/call":
                require(initialized, "mcp_initialization_required")
                with contextlib.redirect_stdout(sys.stderr):
                    try:
                        value = dispatch(
                            workbench, params.get("name"), params.get("arguments", {})
                        )
                    except Exception as exc:
                        value = dict(
                            ok=False,
                            error=type(exc).__name__ + ":" + str(exc),
                            release_authority=False,
                        )
                content = [
                    dict(
                        type="text",
                        text=json.dumps(value, separators=(",", ":"), allow_nan=False),
                    )
                ]
                if params.get("name") == "render" and value.get("ok") is True:
                    for side, preview in value.get("previews", {}).items():
                        image_path = Path(preview["path"]).resolve()
                        require(
                            image_path.is_relative_to(workbench.workspace)
                            and image_path.stat().st_size <= 2 * 1024 * 1024
                            and inspection.sha(image_path) == preview["sha256"],
                            "exact_private_native_preview_required",
                        )
                        content.extend(
                            [
                                dict(
                                    type="text", text=side + " — actual native copper"
                                ),
                                dict(
                                    type="image",
                                    mimeType="image/png",
                                    data=base64.b64encode(
                                        image_path.read_bytes()
                                    ).decode(),
                                ),
                            ]
                        )
                result = dict(
                    content=content,
                    structuredContent=value,
                    isError=value.get("ok") is not True,
                )
            else:
                raise ValueError("unsupported_mcp_method")
            response = dict(jsonrpc="2.0", id=message["id"], result=result)
        except Exception as exc:
            response = dict(
                jsonrpc="2.0",
                id=message.get("id") if type(message) is dict else None,
                error=dict(code=-32602, message=str(exc)),
            )
        stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        stdout.flush()
