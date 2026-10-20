"""Tests for the enterprise business verticals, local store and tool registry.

Everything runs against temporary directories so the developer's real
``%LOCALAPPDATA%/SudarshanaAI/business`` data is never touched.
"""

import pytest

from core.business import db as business_db
from core.business import finance, inventory, manufacturing, marketing, procurement


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Fresh SQLite store per test; never the developer's real business data."""
    store = business_db.BusinessStore(tmp_path / "business.sqlite3")
    monkeypatch.setattr(business_db, "_store", store, raising=False)
    monkeypatch.setattr(business_db, "get_store", lambda: store)
    yield store
    store.close()


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #

def test_inventory_add_and_low_stock(isolated_db):
    assert inventory.execute(action="add", sku="S1", name="Bolt", quantity=3, reorder_level=10)["success"]
    result = inventory.execute(action="low_stock")
    assert result["count"] == 1
    assert result["items"][0]["sku"] == "S1"


def test_inventory_adjust_uses_delta(isolated_db):
    inventory.execute(action="add", sku="S1", quantity=5)
    adjusted = inventory.execute(action="adjust", sku="S1", quantity=7)
    assert adjusted["item"]["quantity"] == 12


def test_inventory_export_xlsx(isolated_db):
    inventory.execute(action="add", sku="S1", name="Bolt", quantity=1)
    out = isolated_db.db_path.parent / "inv.xlsx"
    result = inventory.execute(action="export", output_path=str(out))
    assert result["success"] and result["path"].endswith(".xlsx")


# --------------------------------------------------------------------------- #
# Procurement
# --------------------------------------------------------------------------- #

def test_procurement_compare_quotes_picks_lowest(isolated_db):
    result = procurement.execute(
        action="compare_quotes",
        quotes=[{"vendor": "B", "amount": 500}, {"vendor": "A", "amount": 300}],
    )
    assert result["best"]["vendor"] == "A"


def test_procurement_po_status_update(isolated_db):
    procurement.execute(action="create_po", po_number="PO-9", supplier="Acme", amount=100)
    updated = procurement.execute(action="update_status", po_number="PO-9", status="received")
    assert updated["po"]["status"] == "received"


# --------------------------------------------------------------------------- #
# Finance
# --------------------------------------------------------------------------- #

def test_finance_pnl_and_margin(isolated_db):
    finance.execute(action="add_entry", entry_id="E1", entry_type="revenue", amount=10000)
    finance.execute(action="add_entry", entry_id="E2", entry_type="expense", amount=4000)
    pnl = finance.execute(action="pnl")
    assert pnl["net"] == 6000
    assert pnl["margin_pct"] == 60.0


def test_finance_roi(isolated_db):
    assert finance.execute(action="roi", spend=1000, returns=2500)["roi_pct"] == 150.0


# --------------------------------------------------------------------------- #
# Manufacturing
# --------------------------------------------------------------------------- #

def test_manufacturing_bom_explosion(isolated_db):
    manufacturing.execute(
        action="create_bom",
        bom_id="B1",
        product="Chair",
        components=[
            {"name": "legs", "qty_per_unit": 4, "unit_cost": 3.0},
            {"name": "seat", "qty_per_unit": 1, "unit_cost": 10.0},
        ],
    )
    exploded = manufacturing.execute(action="explode", bom_id="B1", quantity=10)
    assert exploded["total_cost"] == 220.0
    assert len(exploded["components"]) == 2


# --------------------------------------------------------------------------- #
# Marketing
# --------------------------------------------------------------------------- #

def test_marketing_metrics(isolated_db):
    result = marketing.execute(
        action="add_campaign",
        campaign_id="C1",
        channel="meta",
        spend=100,
        impressions=10000,
        clicks=200,
        conversions=20,
    )
    assert result["ctr_pct"] == 2.0
    assert result["cpc"] == 0.5
    assert result["cpa"] == 5.0


# --------------------------------------------------------------------------- #
# At-rest encryption
# --------------------------------------------------------------------------- #

def test_amounts_encrypted_at_rest(isolated_db):
    finance.execute(action="add_entry", entry_id="E1", entry_type="revenue", amount=1234567)
    isolated_db.close()
    raw = isolated_db.db_path.read_bytes()
    assert b"1234567" not in raw


def test_encrypted_column_roundtrip():
    token = business_db.EncryptedColumn("secret-value")
    assert token != "secret-value"
    assert business_db.decrypt_column(token) == "secret-value"


# --------------------------------------------------------------------------- #
# Tool registry facade
# --------------------------------------------------------------------------- #

def test_registry_exposes_business_verticals(isolated_db):
    from core.tool_registry import get_registry

    reg = get_registry()
    reg.initialize(force=True)
    for tool_name in (
        "inventory_manager",
        "procurement_manager",
        "finance_manager",
        "manufacturing_manager",
        "marketing_manager",
    ):
        assert reg.has_tool(tool_name)


def test_registry_execute_routes_business_tool(isolated_db):
    from core.tool_registry import get_registry

    reg = get_registry()
    result = reg.execute("inventory_manager", {"action": "add", "sku": "Z1", "quantity": 1})
    assert result.get("success")
