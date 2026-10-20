"""Finance & Accounting vertical.

Audits ledger entries, generates P&L summaries, tracks ROI, and exports
financial reports through the shared business store.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Any

from core.business.db import BUSINESS_DIR, export_rows, get_store

FEATURE_METADATA = {
    "name": "finance_manager",
    "aliases": ["finance", "accounting", "ledger", "profit_and_loss", "invoice_pipeline"],
    "description": (
        "Record ledger entries, generate profit & loss statements, compute margins "
        "and ROI, and export financial reports to Excel/CSV."
    ),
    "category": "finance",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "add_entry | pnl | ledger | roi | export | list | delete",
            },
            "entry_id": {"type": "STRING", "description": "Ledger entry identifier."},
            "account": {"type": "STRING", "description": "Account name."},
            "entry_type": {"type": "STRING", "description": "revenue | expense | invoice."},
            "category": {"type": "STRING", "description": "Free-form category."},
            "amount": {"type": "NUMBER", "description": "Entry amount."},
            "spend": {"type": "NUMBER", "description": "Investment/spend for action=roi."},
            "returns": {"type": "NUMBER", "description": "Return/income for action=roi."},
            "output_path": {"type": "STRING", "description": "Destination for action=export."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

_TABLE = "finance"


def execute(**kwargs) -> dict[str, Any]:
    params = kwargs.get("parameters") if isinstance(kwargs.get("parameters"), dict) else kwargs
    params = dict(params or {})
    action = (params.get("action") or "ledger").strip().lower()
    store = get_store()

    try:
        if action == "add_entry":
            record = {
                "entry_id": str(params.get("entry_id") or f"E-{uuid.uuid4().hex[:8].upper()}"),
                "account": str(params.get("account") or "General"),
                "entry_type": str(params.get("entry_type") or "expense").lower(),
                "category": str(params.get("category") or ""),
                "amount": float(params.get("amount") or 0.0),
                "created_at": time.time(),
            }
            stored = store.upsert(_TABLE, record)
            return {"success": True, "action": "add_entry", "entry": stored}

        if action == "pnl":
            rows = store.query(_TABLE)
            revenue = sum(float(r.get("amount") or 0) for r in rows if str(r.get("entry_type")) == "revenue")
            expense = sum(float(r.get("amount") or 0) for r in rows if str(r.get("entry_type")) == "expense")
            net = revenue - expense
            margin = (net / revenue * 100.0) if revenue else 0.0
            return {
                "success": True,
                "action": "pnl",
                "revenue": round(revenue, 2),
                "expense": round(expense, 2),
                "net": round(net, 2),
                "margin_pct": round(margin, 2),
                "spoken_narrative": f"Revenue {revenue:.2f}, expense {expense:.2f}, net {net:.2f}, margin {margin:.1f} percent.",
            }

        if action == "roi":
            spend = float(params.get("spend") or 0.0)
            returns = float(params.get("returns") or 0.0)
            roi = ((returns - spend) / spend * 100.0) if spend else 0.0
            return {
                "success": True,
                "action": "roi",
                "spend": spend,
                "returns": returns,
                "roi_pct": round(roi, 2),
                "spoken_narrative": f"ROI is {roi:.1f} percent.",
            }

        if action == "ledger":
            rows = store.query(_TABLE)
            by_category: dict[str, float] = defaultdict(float)
            for r in rows:
                by_category[str(r.get("category") or "uncategorized")] += float(r.get("amount") or 0)
            return {
                "success": True,
                "action": "ledger",
                "count": len(rows),
                "by_category": {k: round(v, 2) for k, v in by_category.items()},
                "entries": rows,
            }

        if action == "delete":
            ok = store.delete(_TABLE, str(params.get("entry_id") or ""))
            return {"success": ok, "action": "delete"}

        if action == "export":
            rows = store.query(_TABLE)
            dest = params.get("output_path") or str(BUSINESS_DIR / "finance_export.xlsx")
            path = export_rows(rows, dest, sheet_name="Finance")
            return {"success": True, "action": "export", "path": path, "rows": len(rows)}

        rows = store.query(_TABLE)
        return {"success": True, "action": "list", "count": len(rows), "entries": rows}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
