"""Unit tests for the DTDC carrier risk calculation.

These import server.py directly rather than going over HTTP, because the
arithmetic is self-contained and the boundary cases are the whole point.
"""
import os
import sys
import math

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    calc_carrier_risk,
    build_additional_charges,
    CARRIER_RISK_LABEL,
    CARRIER_RISK_MIN_AMOUNT,
    CARRIER_RISK_RATE,
    CARRIER_RISK_GST_PERCENT,
)


class TestCarrierRiskAmount:
    """C = max(100, ceil(0.02 * base / (1 - 0.02 * 1.18)))"""

    def test_minimum_applies_below_threshold(self):
        for base in [0, 1, 500, 1000, 4000, 4881]:
            assert calc_carrier_risk(base)["amount"] == CARRIER_RISK_MIN_AMOUNT

    def test_4882_is_the_exact_boundary(self):
        """The worked example: 4882 + 100 + 18% = 5000, and 2% of 5000 is 100."""
        result = calc_carrier_risk(4882)
        assert result["amount"] == 100
        assert result["gst_amount"] == 18.0
        invoice_value = 4882 + result["amount"] + result["gst_amount"]
        assert invoice_value == 5000
        assert round(invoice_value * CARRIER_RISK_RATE, 2) == 100.0

    def test_two_percent_takes_over_above_the_threshold(self):
        assert calc_carrier_risk(4883)["amount"] == 101
        assert calc_carrier_risk(5000)["amount"] == 103
        assert calc_carrier_risk(10000)["amount"] == 205
        assert calc_carrier_risk(100000)["amount"] == 2049

    def test_charge_always_covers_two_percent_of_the_final_invoice(self):
        """The charge inflates the invoice, so it must still cover 2% of the result."""
        for base in [0, 4882, 4883, 5000, 7500, 23456, 100000, 999999]:
            result = calc_carrier_risk(base)
            invoice_value = base + result["amount"] + result["gst_amount"]
            assert result["amount"] + 1e-9 >= invoice_value * CARRIER_RISK_RATE
            assert result["amount"] >= CARRIER_RISK_MIN_AMOUNT

    def test_amount_is_rounded_up_to_whole_rupees(self):
        for base in [4883, 5000, 6789, 12345, 98765]:
            amount = calc_carrier_risk(base)["amount"]
            assert amount == math.ceil(amount)

    def test_rounding_up_never_overshoots_by_a_full_rupee(self):
        """Guards the round-before-ceil: a whole extra rupee means float noise."""
        for base in [4882, 5000, 10000, 50000]:
            exact = CARRIER_RISK_RATE * base / (1 - CARRIER_RISK_RATE * 1.18)
            amount = calc_carrier_risk(base)["amount"]
            if amount > CARRIER_RISK_MIN_AMOUNT:
                assert amount - exact < 1.0

    def test_gst_amount_and_label(self):
        result = calc_carrier_risk(5126)
        assert result["name"] == CARRIER_RISK_LABEL
        assert result["amount"] == 105
        assert result["gst_percent"] == CARRIER_RISK_GST_PERCENT
        assert result["gst_amount"] == 18.9

    def test_without_gst_the_divisor_drops_the_gst_term(self):
        result = calc_carrier_risk(10000, 0)
        assert result["gst_percent"] == 0
        assert result["gst_amount"] == 0
        assert result["amount"] == math.ceil(10000 * CARRIER_RISK_RATE / 0.98)

    def test_negative_and_none_base_fall_back_to_the_minimum(self):
        assert calc_carrier_risk(-500)["amount"] == CARRIER_RISK_MIN_AMOUNT
        assert calc_carrier_risk(None)["amount"] == CARRIER_RISK_MIN_AMOUNT


class TestBuildAdditionalCharges:
    def test_no_carrier_risk_row_when_flag_is_off(self):
        charges, total, gst = build_additional_charges(
            [{"name": "Insurance", "amount": 50, "gst_percent": 0}], False, False, 1000
        )
        assert len(charges) == 1
        assert total == 50
        assert gst == 0

    def test_carrier_risk_row_is_appended(self):
        charges, total, gst = build_additional_charges([], True, True, 4882)
        assert len(charges) == 1
        assert charges[0]["name"] == CARRIER_RISK_LABEL
        assert total == 100
        assert gst == 18.0

    def test_carrier_risk_is_levied_on_other_charges_too(self):
        """Other additional charges are part of the invoice value the 2% is taken on."""
        base = 4000
        others = [{"name": "Insurance", "amount": 900, "gst_percent": 0}]
        charges, total, gst = build_additional_charges(others, True, True, base)
        carrier = next(c for c in charges if c["name"] == CARRIER_RISK_LABEL)
        # Levied on 4000 + 900, not on 4000 alone.
        assert carrier["amount"] == calc_carrier_risk(4900)["amount"]
        assert total == 900 + carrier["amount"]
        assert gst == carrier["gst_amount"]

    def test_client_supplied_carrier_risk_row_is_replaced_not_trusted(self):
        charges, total, _ = build_additional_charges(
            [{"name": "carrier risk", "amount": 99999, "gst_percent": 18}], True, True, 4882
        )
        assert len([c for c in charges if c["name"] == CARRIER_RISK_LABEL]) == 1
        assert total == 100

    def test_client_supplied_carrier_risk_row_is_dropped_when_flag_is_off(self):
        charges, total, gst = build_additional_charges(
            [{"name": "Carrier Risk", "amount": 500, "gst_percent": 18}], True, False, 4882
        )
        assert charges == []
        assert total == 0
        assert gst == 0

    def test_no_gst_on_carrier_risk_when_invoice_is_not_gst(self):
        charges, total, gst = build_additional_charges([], False, True, 10000)
        assert gst == 0
        assert charges[0]["gst_percent"] == 0
        assert total == calc_carrier_risk(10000, 0)["amount"]

    def test_grand_total_matches_the_worked_example(self):
        """4882 of goods with carrier risk lands on a 5000 grand total."""
        base = 4882
        charges, total, gst = build_additional_charges([], True, True, base)
        assert math.ceil(base + total + gst) == 5000
