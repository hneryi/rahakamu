"""Data layer: as-of cut, BOM-safe CSVs, per-customer slices, labels, basket parity."""

from __future__ import annotations

from datetime import date

import pytest

from app import db
from app.analytics.baskets import classify
from app.analytics.labels import merchant_label
from app.config import settings


def test_no_transactions_after_as_of() -> None:
    assert db.scalar("SELECT max(tx_date) FROM cache.main.tx") <= settings.as_of_date


def test_customers_postal_code_keeps_leading_zeros() -> None:
    c = db.get_customer("CUST00001")
    assert c["postal_code"] == "00990" and c["age"] == 63
    assert db.scalar("SELECT count(*) FROM customers") == 5100


def test_unknown_customer_raises() -> None:
    with pytest.raises(db.CustomerNotFound):
        db.get_customer("CUST99999")


def test_slice_matches_base_table() -> None:
    cid = "CUST00584"
    sliced = db.scalar("SELECT count(*) FROM tx WHERE customer_id = ?", [cid])
    base = db.scalar("SELECT count(*) FROM cache.main.tx WHERE customer_id = ?", [cid])
    assert sliced == base > 300


def test_python_classifier_matches_sql() -> None:
    rows = db.query(
        "SELECT category, mcc_code, tx_amount_eur, is_recurring, is_outlier, basket "
        "FROM cache.main.tx USING SAMPLE 20000 ROWS"
    )
    mismatches = [r for r in rows if classify(r) != r["basket"]]
    assert not mismatches, mismatches[:3]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"category": "Housing", "tx_amount_eur": -900.0}, "fixed"),
        ({"category": "Groceries", "mcc_code": 5411, "tx_amount_eur": -40.0}, "fixed"),
        ({"category": "Groceries", "mcc_code": 5499, "tx_amount_eur": -4.0}, "leak"),
        ({"category": "Health", "mcc_code": 5912, "tx_amount_eur": -12.0}, "irregular"),
        ({"category": "Home & Tech", "mcc_code": 5732, "tx_amount_eur": -90.0}, "leak"),
        ({"category": "Home & Tech", "mcc_code": 5732, "tx_amount_eur": -900.0}, "irregular"),
        ({"category": "Transportation", "mcc_code": 4121, "tx_amount_eur": -25.0}, "leak"),
        ({"category": "Transportation", "mcc_code": 4111, "tx_amount_eur": -3.0}, "fixed"),
        ({"category": "Transportation", "mcc_code": 5541, "tx_amount_eur": -95.0}, "irregular"),
        ({"category": "Restaurants", "mcc_code": 5812, "tx_amount_eur": -30.0, "is_recurring": True}, "fixed"),
        ({"category": "Salary", "tx_amount_eur": 2500.0}, "income"),
        ({"category": "Salary Sweep", "tx_amount_eur": -2500.0}, "saving"),
    ],
)
def test_basket_rules(row: dict, expected: str) -> None:
    assert classify(row) == expected


def test_merchant_labels_are_generic() -> None:
    assert merchant_label("MRC-GRO-0035", 5411, "Groceries") == "Grocery store #35"
    assert merchant_label("MRC-TRN-0003", 4121, "Transportation").endswith("#3")
    assert merchant_label(None, None, "Housing") == "Rent / housing"
    assert "MRC" not in merchant_label("MRC-RES-0038", None, "Restaurants")


def test_as_of_is_a_date() -> None:
    assert isinstance(settings.as_of_date, date)
