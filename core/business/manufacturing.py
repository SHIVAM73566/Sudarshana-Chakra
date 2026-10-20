"""Manufacturing & Operations vertical.

Processes bills of materials (BOMs), explodes component requirements, and
exports production planning sheets through the shared business store.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.business.db import BUSINESS_DIR, export_rows, get_store

FEATURE_METADATA = {
    "name": "manufacturing_manager",
    "aliases": ["manufacturing", "bom", "bill_of_materials", "production_planning"],
    "description": (
        "Create and store bills of materials (BOMs), explode component requirements "
        "for a build quantity, and export production sheets to Excel/CSV."
    ),
    "category": "manufacturing",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "create_bom | explode | list | get | export | delete",
            },
            "bom_id": {"type": "STRING", "description": "BOM identifier."},
            "product": {"type": "STRING", "description": "Finished product name."},
            "components": {
                "type": "ARRAY",
                "description": "Components [{name, qty_per_unit, unit_cost}].",
                "items": {"type": "OBJECT"},
            },
            "quantity": {"type": "INTEGER", "description": "Build quantity for action=explode."},
            "output_path": {"type": "STRING", "description": "Destination for action=export."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

_TABLE = "manufacturing"


def execute(**kwargs) -> dict[str, Any]:
    params = kwargs.get("parameters") if isinstance(kwargs.get("parameters"), dict) else kwargs
    params = dict(params or {})
    action = (params.get("action") or "list").strip().lower()
    store = get_store()

    try:
        if action == "create_bom":
            record = {
                "bom_id": str(params.get("bom_id") or f"BOM-{uuid.uuid4().hex[:8].upper()}"),
                "product": str(params.get("product") or "Unnamed product"),
                "components": json.dumps(params.get("components") or [], ensure_ascii=False),
                "quantity": int(params.get("quantity") or 1),
                "created_at": time.time(),
            }
            stored = store.upsert(_TABLE, record)
            return {"success": True, "action": "create_bom", "bom": stored}

        if action == "explode":
            bom_id = str(params.get("bom_id") or "")
            bom = store.get(_TABLE, bom_id)
            if not bom:
                return {"success": False, "error": f"BOM '{bom_id}' not found."}
            try:
                components = json.loads(bom.get("components") or "[]")
            except Exception:
                components = []
            build_qty = int(params.get("quantity") or bom.get("quantity") or 1)
            exploded = []
            total_cost = 0.0
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                per_unit = float(comp.get("qty_per_unit") or comp.get("qty") or 0)
                unit_cost = float(comp.get("unit_cost") or 0)
                required = per_unit * build_qty
                line_cost = required * unit_cost
                total_cost += line_cost
                exploded.append(
                    {
                        "name": comp.get("name") or "component",
                        "required": required,
                        "unit_cost": unit_cost,
                        "line_cost": round(line_cost, 2),
                    }
                )
            return {
                "success": True,
                "action": "explode",
                "product": bom.get("product"),
                "build_quantity": build_qty,
                "components": exploded,
                "total_cost": round(total_cost, 2),
                "spoken_narrative": f"Build requires {len(exploded)} components, total cost {total_cost:.2f}.",
            }

        if action == "get":
            found = store.get(_TABLE, str(params.get("bom_id") or ""))
            if not found:
                return {"success": False, "error": "BOM not found."}
            return {"success": True, "action": "get", "bom": found}

        if action == "delete":
            ok = store.delete(_TABLE, str(params.get("bom_id") or ""))
            return {"success": ok, "action": "delete"}

        if action == "export":
            rows = store.query(_TABLE)
            dest = params.get("output_path") or str(BUSINESS_DIR / "manufacturing_export.xlsx")
            path = export_rows(rows, dest, sheet_name="Manufacturing")
            return {"success": True, "action": "export", "path": path, "rows": len(rows)}

        rows = store.query(_TABLE)
        return {"success": True, "action": "list", "count": len(rows), "boms": rows}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
