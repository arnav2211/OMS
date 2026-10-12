"""Make PI from an order: the order's discount must reach the PI.

Regression for CS-1437, where a discounted order produced a PI with no
discount line because the order's negative "Discount" charge row was clamped
to zero while the charges were normalised. Runs without a live server: the
database layer is stubbed in memory.
"""
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_make_pi_discount")
os.environ.setdefault("JWT_SECRET", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import server  # noqa: E402


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self, order):
        self.orders = _Coll([order])
        self.proforma_invoices = _Coll()


ADMIN = {"id": "u1", "name": "Admin", "role": "admin", "username": "admin"}


def _order(**over):
    base = {
        "id": "ord-1437", "order_number": "CS-1437", "company": "citspray",
        "customer_id": "c1", "customer_name": "Acme", "gst_applicable": True,
        "items": [
            {"item_name": "Lemon Oil", "qty": 2, "unit": "kg", "rate": 1000, "amount": 2000,
             "gst_rate": 18, "gst_amount": 360, "total": 2360, "formulation": "secret",
             "discount": 0, "discount_is_percent": False},
            {"item_name": "Rose Oil", "qty": 1, "unit": "kg", "rate": 3000, "amount": 3000,
             "gst_rate": 18, "gst_amount": 540, "total": 3540, "formulation": "secret",
             "discount": 0, "discount_is_percent": False},
        ],
        "shipping_charge": 0, "shipping_gst": 0,
        "additional_charges": [{"name": "Discount", "amount": -500, "gst_percent": 0, "gst_amount": -90}],
        "carrier_risk_applicable": False,
        "subtotal": 5000, "total_gst": 810, "grand_total": 5310,
        "discount": 500, "discount_gst": 90, "discount_label": "Discount",
        "discount_enabled": True, "discount_mode": "total", "discount_value": 10, "discount_is_percent": True,
        "free_samples": [], "remark": "",
    }
    base.update(over)
    return base


def _make_pi(order, gst_applicable=True, monkeypatch=None):
    db = _DB(order)
    monkeypatch.setattr(server, "db", db)

    async def _num(company, kind):
        return "PI-TEST"
    monkeypatch.setattr(server, "next_document_number", _num)
    req = server.MakePIRequest(gst_applicable=gst_applicable, show_rate=True, pi_date="2026-10-12")
    return asyncio.run(server.make_pi_from_order(order["id"], req, ADMIN))


def _discount_rows(pi):
    return [c for c in pi["additional_charges"] if float(c["amount"]) < 0]


def test_manual_percent_discount_reaches_pi(monkeypatch):
    pi = _make_pi(_order(), True, monkeypatch)
    rows = _discount_rows(pi)
    assert len(rows) == 1
    assert rows[0]["name"] == "Discount"
    assert rows[0]["amount"] == -500
    assert rows[0]["gst_amount"] == -90
    assert pi["subtotal"] == 5000
    assert pi["total_gst"] == 810          # 900 on the items, 90 reversed by the discount
    assert pi["grand_total"] == 5310       # 5000 + 900 - 500 - 90
    # config travels so the PI edit screen keeps the discount
    assert pi["discount_enabled"] is True
    assert pi["discount_mode"] == "total"
    assert pi["discount_value"] == 10
    assert pi["discount_is_percent"] is True
    # no zero-amount leftover of the old clamped row
    assert all(float(c["amount"]) != 0 for c in pi["additional_charges"])


def test_manual_discount_follows_pi_gst_choice(monkeypatch):
    pi = _make_pi(_order(), False, monkeypatch)
    rows = _discount_rows(pi)
    assert rows[0]["amount"] == -500
    assert rows[0]["gst_amount"] == 0
    assert pi["total_gst"] == 0
    assert pi["grand_total"] == 4500


def test_per_item_discount_reaches_pi(monkeypatch):
    order = _order(discount_mode="items", discount_value=0, discount_is_percent=False)
    order["items"][0]["discount"] = 200
    order["items"][1]["discount"] = 10
    order["items"][1]["discount_is_percent"] = True
    pi = _make_pi(order, True, monkeypatch)
    rows = _discount_rows(pi)
    assert rows[0]["amount"] == -500          # 200 + 10% of 3000
    assert rows[0]["gst_amount"] == -90
    assert pi["grand_total"] == 5310


def test_website_discount_keeps_amount_and_label(monkeypatch):
    order = _order(discount_enabled=False, discount_mode="total", discount_value=0, discount_is_percent=False,
                   website_order=True, discount_label="Discount (WELCOME10)",
                   additional_charges=[{"name": "Discount (WELCOME10)", "amount": -500, "gst_percent": 0, "gst_amount": -90}])
    pi = _make_pi(order, True, monkeypatch)
    rows = _discount_rows(pi)
    assert rows[0]["name"] == "Discount (WELCOME10)"
    assert rows[0]["amount"] == -500
    assert rows[0]["gst_amount"] == -90
    assert pi["grand_total"] == 5310
    assert pi["discount_enabled"] is True
    assert pi["discount_value"] == 500
    assert pi["discount_is_percent"] is False


def test_legacy_order_with_only_the_row(monkeypatch):
    order = _order()
    for k in ("discount", "discount_gst", "discount_enabled", "discount_mode", "discount_value", "discount_is_percent"):
        order.pop(k, None)
    pi = _make_pi(order, True, monkeypatch)
    rows = _discount_rows(pi)
    assert rows[0]["amount"] == -500
    assert pi["grand_total"] == 5310


def test_order_without_discount_is_unchanged(monkeypatch):
    order = _order(discount=0, discount_gst=0, discount_enabled=False, discount_value=0, discount_is_percent=False,
                   additional_charges=[{"name": "Packing", "amount": 100, "gst_percent": 18, "gst_amount": 18}])
    pi = _make_pi(order, True, monkeypatch)
    assert _discount_rows(pi) == []
    assert [c["name"] for c in pi["additional_charges"]] == ["Packing"]
    assert pi["discount_enabled"] is False
    assert pi["grand_total"] == 5000 + 900 + 118
