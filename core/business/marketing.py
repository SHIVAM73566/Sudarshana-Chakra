"""Marketing & Content vertical.

Analyzes ad-campaign performance (CTR, CPC, CPA, ROAS), ranks campaigns, and
exports marketing analytics through the shared business store.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.business.db import BUSINESS_DIR, export_rows, get_store

FEATURE_METADATA = {
    "name": "marketing_manager",
    "aliases": ["marketing", "campaign_analytics", "ad_performance", "advertising"],
    "description": (
        "Record marketing campaign metrics, compute CTR/CPC/CPA/ROAS and ROI, rank "
        "campaigns, and export analytics to Excel/CSV."
    ),
    "category": "marketing",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "add_campaign | analyze | list | get | export | delete",
            },
            "campaign_id": {"type": "STRING", "description": "Campaign identifier."},
            "channel": {"type": "STRING", "description": "meta | google | linkedin | email | etc."},
            "spend": {"type": "NUMBER", "description": "Total ad spend."},
            "impressions": {"type": "INTEGER", "description": "Impressions served."},
            "clicks": {"type": "INTEGER", "description": "Clicks recorded."},
            "conversions": {"type": "INTEGER", "description": "Conversions recorded."},
            "revenue": {"type": "NUMBER", "description": "Attributed revenue (for ROAS/ROI)."},
            "output_path": {"type": "STRING", "description": "Destination for action=export."},
        },
        "required": [],
    },
    "version": "1.0.0",
    "active": True,
}

_TABLE = "marketing"


def _metrics(row: dict[str, Any]) -> dict[str, Any]:
    spend = float(row.get("spend") or 0.0)
    impressions = int(row.get("impressions") or 0)
    clicks = int(row.get("clicks") or 0)
    conversions = int(row.get("conversions") or 0)
    ctr = (clicks / impressions * 100.0) if impressions else 0.0
    cpc = (spend / clicks) if clicks else 0.0
    cpa = (spend / conversions) if conversions else 0.0
    return {
        "ctr_pct": round(ctr, 3),
        "cpc": round(cpc, 3),
        "cpa": round(cpa, 3),
        "conversions": conversions,
    }


def execute(**kwargs) -> dict[str, Any]:
    params = kwargs.get("parameters") if isinstance(kwargs.get("parameters"), dict) else kwargs
    params = dict(params or {})
    action = (params.get("action") or "list").strip().lower()
    store = get_store()

    try:
        if action == "add_campaign":
            record = {
                "campaign_id": str(params.get("campaign_id") or f"CMP-{uuid.uuid4().hex[:8].upper()}"),
                "channel": str(params.get("channel") or "unknown"),
                "spend": float(params.get("spend") or 0.0),
                "impressions": int(params.get("impressions") or 0),
                "clicks": int(params.get("clicks") or 0),
                "conversions": int(params.get("conversions") or 0),
                "created_at": time.time(),
            }
            stored = store.upsert(_TABLE, record)
            return {"success": True, "action": "add_campaign", "campaign": stored, **{k: v for k, v in _metrics(stored).items()}}

        if action == "analyze":
            rows = store.query(_TABLE)
            analyzed = []
            for r in rows:
                m = _metrics(r)
                revenue = float(params.get("revenue") or 0.0) if params.get("campaign_id") == r.get("campaign_id") else 0.0
                spend = float(r.get("spend") or 0.0)
                roas = (revenue / spend) if spend and revenue else 0.0
                roi = ((revenue - spend) / spend * 100.0) if spend and revenue else 0.0
                analyzed.append({**r, **m, "roas": round(roas, 3), "roi_pct": round(roi, 2)})
            analyzed.sort(key=lambda x: x.get("roas") or x.get("ctr_pct") or 0, reverse=True)
            return {
                "success": True,
                "action": "analyze",
                "count": len(analyzed),
                "campaigns": analyzed,
                "spoken_narrative": f"Analyzed {len(analyzed)} campaign(s).",
            }

        if action == "get":
            found = store.get(_TABLE, str(params.get("campaign_id") or ""))
            if not found:
                return {"success": False, "error": "Campaign not found."}
            return {"success": True, "action": "get", "campaign": {**found, **_metrics(found)}}

        if action == "delete":
            ok = store.delete(_TABLE, str(params.get("campaign_id") or ""))
            return {"success": ok, "action": "delete"}

        if action == "export":
            rows = [{**r, **_metrics(r)} for r in store.query(_TABLE)]
            dest = params.get("output_path") or str(BUSINESS_DIR / "marketing_export.xlsx")
            path = export_rows(rows, dest, sheet_name="Marketing")
            return {"success": True, "action": "export", "path": path, "rows": len(rows)}

        rows = store.query(_TABLE)
        return {"success": True, "action": "list", "count": len(rows), "campaigns": rows}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
