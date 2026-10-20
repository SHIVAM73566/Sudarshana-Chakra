"""Procurement & Supply Chain vertical.

Automates vendor quote comparisons, purchase-order tracking, and supplier data
normalization persisted through the shared business store.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.business.db import BUSINESS_DIR, export_rows, get_store

FEATURE_METADATA = {
    "name": "procurement_manager",
    "aliases": ["procurement", "purchase_orders", "supplier_manager", "supply_chain"],
    "description": (
        "Create and track purchase orders, compare vendor quotes, and export "
        "procurement/supplier reports to Excel/CSV."
    ),
    "category": "procurement",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "create_po | update_status | list | compare_quotes | export | get | delete",
            },
            "po_number": {"type": "STRING", "description": "Purchase order number."},
            "supplier": {"type": "STRING", "description": "Supplier/vendor name."},
            "items": {"type": "ARRAY", "description": "Line items (name/description strings).", "items": {"type": "OBJECT"}},
            "amount": {"type": "NUMBER", "description": "Total PO amount."},
            "status": {"type": "STRING", "description": "draft | sent | received | cancelled."},
            "quotes": {"type": "ARRAY", "description": "Vendor quotes [{vendor, amount}] for compare_quotes.", "items": {"type": "OBJECT"}},
            "output_path": {"type": "STRING", "description": "Destination for action=export."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

_TABLE = "procurement"


def execute(**kwargs) -> dict[str, Any]:
    params = kwargs.get("parameters") if isinstance(kwargs.get("parameters"), dict) else kwargs
    params = dict(params or {})
    action = (params.get("action") or "list").strip().lower()
    store = get_store()

    try:
        if action == "create_po":
            po = str(params.get("po_number") or f"PO-{uuid.uuid4().hex[:8].upper()}")
            record = {
                "po_number": po,
                "supplier": str(params.get("supplier") or "Unknown supplier"),
                "items": json.dumps(params.get("items") or [], ensure_ascii=False),
                "amount": float(params.get("amount") or 0.0),
                "status": str(params.get("status") or "draft"),
                "created_at": time.time(),
            }
            stored = store.upsert(_TABLE, record)
            return {"success": True, "action": "create_po", "po": stored}

        if action == "update_status":
            po = str(params.get("po_number") or "")
            current = store.get(_TABLE, po)
            if not current:
                return {"success": False, "error": f"PO '{po}' not found."}
            current["status"] = str(params.get("status") or current.get("status") or "draft")
            stored = store.upsert(_TABLE, current)
            return {"success": True, "action": "update_status", "po": stored}

        if action == "compare_quotes":
            quotes = params.get("quotes") or []
            parsed = []
            for q in quotes:
                if isinstance(q, dict):
                    parsed.append({"vendor": str(q.get("vendor") or "vendor"), "amount": float(q.get("amount") or 0.0)})
            if not parsed:
                return {"success": False, "error": "No quotes supplied."}
            parsed.sort(key=lambda x: x["amount"])
            return {
                "success": True,
                "action": "compare_quotes",
                "best": parsed[0],
                "ranked": parsed,
                "spoken_narrative": f"Best quote: {parsed[0]['vendor']} at {parsed[0]['amount']:.2f}.",
            }

        if action == "get":
            found = store.get(_TABLE, str(params.get("po_number") or ""))
            if not found:
                return {"success": False, "error": "PO not found."}
            return {"success": True, "action": "get", "po": found}

        if action == "delete":
            ok = store.delete(_TABLE, str(params.get("po_number") or ""))
            return {"success": ok, "action": "delete"}

        if action == "export":
            rows = store.query(_TABLE)
            dest = params.get("output_path") or str(BUSINESS_DIR / "procurement_export.xlsx")
            path = export_rows(rows, dest, sheet_name="Procurement")
            return {"success": True, "action": "export", "path": path, "rows": len(rows)}

        rows = store.query(_TABLE)
        return {"success": True, "action": "list", "count": len(rows), "orders": rows}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
