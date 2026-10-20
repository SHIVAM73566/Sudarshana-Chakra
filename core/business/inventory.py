"""Inventory Management vertical.

Tracks stock levels, raises automated reorder alerts, and exports inventory
reconciliation sheets via the shared business store.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.business.db import export_rows, get_store

FEATURE_METADATA = {
    "name": "inventory_manager",
    "aliases": ["inventory", "stock_manager", "supply_inventory"],
    "description": (
        "Track stock levels, compute low-stock reorder alerts, adjust quantities, "
        "and export inventory reports to Excel/CSV."
    ),
    "category": "inventory",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "add | update | adjust | low_stock | list | export | delete | get",
            },
            "sku": {"type": "STRING", "description": "Stock keeping unit identifier."},
            "name": {"type": "STRING", "description": "Item name."},
            "quantity": {"type": "INTEGER", "description": "Quantity on hand (add/update) or delta (adjust)."},
            "reorder_level": {"type": "INTEGER", "description": "Threshold below which a reorder alert fires."},
            "unit_cost": {"type": "NUMBER", "description": "Cost per unit."},
            "location": {"type": "STRING", "description": "Warehouse/bin location."},
            "output_path": {"type": "STRING", "description": "Destination for action=export (.xlsx or .csv)."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

_TABLE = "inventory"


def _record(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": str(params.get("sku") or uuid.uuid4().hex[:8].upper()),
        "name": str(params.get("name") or "Unnamed item"),
        "quantity": int(params.get("quantity") or 0),
        "reorder_level": int(params.get("reorder_level") or 0),
        "unit_cost": float(params.get("unit_cost") or 0.0),
        "location": str(params.get("location") or ""),
        "updated_at": time.time(),
    }


def execute(**kwargs) -> dict[str, Any]:
    params = kwargs.get("parameters") if isinstance(kwargs.get("parameters"), dict) else kwargs
    params = dict(params or {})
    action = (params.get("action") or "list").strip().lower()
    store = get_store()

    try:
        if action in ("add", "update"):
            rec = _record(params)
            stored = store.upsert(_TABLE, rec)
            return {"success": True, "action": action, "item": stored}

        if action == "adjust":
            sku = str(params.get("sku") or "")
            current = store.get(_TABLE, sku)
            if not current:
                return {"success": False, "error": f"SKU '{sku}' not found."}
            delta = int(params.get("quantity") or 0)
            current["quantity"] = int(current.get("quantity") or 0) + delta
            current["updated_at"] = time.time()
            stored = store.upsert(_TABLE, current)
            return {"success": True, "action": "adjust", "delta": delta, "item": stored}

        if action == "low_stock":
            items = store.query(_TABLE)
            low = [i for i in items if int(i.get("quantity") or 0) <= int(i.get("reorder_level") or 0)]
            return {
                "success": True,
                "action": "low_stock",
                "count": len(low),
                "items": low,
                "spoken_narrative": f"{len(low)} item(s) at or below reorder level.",
            }

        if action == "get":
            item = store.get(_TABLE, str(params.get("sku") or ""))
            if not item:
                return {"success": False, "error": "SKU not found."}
            return {"success": True, "action": "get", "item": item}

        if action == "delete":
            ok = store.delete(_TABLE, str(params.get("sku") or ""))
            return {"success": ok, "action": "delete"}

        if action == "export":
            rows = store.query(_TABLE)
            dest = params.get("output_path") or _default_path()
            path = export_rows(rows, dest, sheet_name="Inventory")
            return {"success": True, "action": "export", "path": path, "rows": len(rows)}

        rows = store.query(_TABLE)
        return {"success": True, "action": "list", "count": len(rows), "items": rows}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def _default_path() -> str:
    from core.business.db import BUSINESS_DIR

    return str(BUSINESS_DIR / "inventory_export.xlsx")
