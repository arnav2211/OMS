"""
Test GST and Shipping Exclusion Logic in Reports
Tests the _calc_product_sales helper function behavior through API endpoints:
- /api/reports/admin-analytics
- /api/reports/telecaller-sales
- /api/reports/payment-sales

Bug fixes being tested:
1. exclude_gst=true should return product_sales = subtotal + shipping_charge + additional_charges base (no GST)
2. exclude_shipping=true should return product_sales = subtotal + items_gst only (no shipping, no additional charges)
3. Both exclude_gst=true & exclude_shipping=true should return product_sales = subtotal only
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGSTShippingExclusion:
    """Test GST and Shipping exclusion logic in reports"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.admin_id = login_resp.json().get("user", {}).get("id")
        
    def test_admin_analytics_no_exclusions(self):
        """Test admin-analytics with no exclusions - should return grand_total"""
        resp = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=false&exclude_shipping=false")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "product_sales" in data
        assert "total_revenue" in data
        print(f"No exclusions - Total Revenue: {data['total_revenue']}, Product Sales: {data['product_sales']}")
        # product_sales should equal total_revenue when no exclusions
        assert data['product_sales'] == data['total_revenue'], "Without exclusions, product_sales should equal total_revenue"
        
    def test_admin_analytics_exclude_gst_only(self):
        """Test admin-analytics with exclude_gst=true - should exclude all GST"""
        # First get baseline without exclusions
        baseline_resp = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=false&exclude_shipping=false")
        assert baseline_resp.status_code == 200
        baseline = baseline_resp.json()
        
        # Now with exclude_gst
        resp = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=true&exclude_shipping=false")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        print(f"Exclude GST - Total Revenue: {baseline['total_revenue']}, Product Sales (excl GST): {data['product_sales']}")
        
        # product_sales should be less than or equal to total_revenue (GST removed)
        if baseline['total_orders'] > 0:
            assert data['product_sales'] <= baseline['total_revenue'], "With exclude_gst, product_sales should be <= total_revenue"
            
    def test_admin_analytics_exclude_shipping_only(self):
        """Test admin-analytics with exclude_shipping=true - should exclude shipping + additional charges"""
        # First get baseline without exclusions
        baseline_resp = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=false&exclude_shipping=false")
        assert baseline_resp.status_code == 200
        baseline = baseline_resp.json()
        
        # Now with exclude_shipping
        resp = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=false&exclude_shipping=true")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        print(f"Exclude Shipping - Total Revenue: {baseline['total_revenue']}, Product Sales (excl shipping): {data['product_sales']}")
        
        # product_sales should be less than or equal to total_revenue (shipping + additional charges removed)
        if baseline['total_orders'] > 0:
            assert data['product_sales'] <= baseline['total_revenue'], "With exclude_shipping, product_sales should be <= total_revenue"
            
    def test_admin_analytics_exclude_both(self):
        """Test admin-analytics with both exclusions - should return subtotal only"""
        # Get all variations
        no_excl = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=false&exclude_shipping=false").json()
        excl_gst = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=true&exclude_shipping=false").json()
        excl_ship = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=false&exclude_shipping=true").json()
        excl_both = self.session.get(f"{BASE_URL}/api/reports/admin-analytics?period=all&exclude_gst=true&exclude_shipping=true").json()
        
        print(f"No exclusions: {no_excl['product_sales']}")
        print(f"Exclude GST only: {excl_gst['product_sales']}")
        print(f"Exclude Shipping only: {excl_ship['product_sales']}")
        print(f"Exclude Both: {excl_both['product_sales']}")
        
        # Both exclusions should give the lowest value (subtotal only)
        if no_excl['total_orders'] > 0:
            assert excl_both['product_sales'] <= excl_gst['product_sales'], "Both exclusions should be <= GST-only exclusion"
            assert excl_both['product_sales'] <= excl_ship['product_sales'], "Both exclusions should be <= shipping-only exclusion"
            
    def test_telecaller_sales_no_exclusions(self):
        """Test telecaller-sales with no exclusions"""
        resp = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=false")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "product_sales" in data
        assert "total_amount" in data
        print(f"Telecaller Sales - No exclusions: Total={data['total_amount']}, Product Sales={data['product_sales']}")
        
    def test_telecaller_sales_exclude_gst(self):
        """Test telecaller-sales with exclude_gst=true"""
        baseline = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=false").json()
        resp = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=true&exclude_shipping=false")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"Telecaller Sales - Exclude GST: Total={baseline['total_amount']}, Product Sales={data['product_sales']}")
        if baseline['total_orders'] > 0:
            assert data['product_sales'] <= baseline['total_amount'], "With exclude_gst, product_sales should be <= total_amount"
            
    def test_telecaller_sales_exclude_shipping(self):
        """Test telecaller-sales with exclude_shipping=true"""
        baseline = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=false").json()
        resp = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=true")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"Telecaller Sales - Exclude Shipping: Total={baseline['total_amount']}, Product Sales={data['product_sales']}")
        if baseline['total_orders'] > 0:
            assert data['product_sales'] <= baseline['total_amount'], "With exclude_shipping, product_sales should be <= total_amount"
            
    def test_telecaller_sales_exclude_both(self):
        """Test telecaller-sales with both exclusions"""
        excl_gst = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=true&exclude_shipping=false").json()
        excl_ship = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=true").json()
        excl_both = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=true&exclude_shipping=true").json()
        
        print(f"Telecaller Sales - Exclude GST: {excl_gst['product_sales']}")
        print(f"Telecaller Sales - Exclude Shipping: {excl_ship['product_sales']}")
        print(f"Telecaller Sales - Exclude Both: {excl_both['product_sales']}")
        
        if excl_gst['total_orders'] > 0:
            assert excl_both['product_sales'] <= excl_gst['product_sales'], "Both exclusions should be <= GST-only"
            assert excl_both['product_sales'] <= excl_ship['product_sales'], "Both exclusions should be <= shipping-only"
            
    def test_payment_sales_no_exclusions(self):
        """Test payment-sales with no exclusions"""
        resp = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=false")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "product_sales" in data
        assert "total_amount" in data
        print(f"Payment Sales - No exclusions: Total={data['total_amount']}, Product Sales={data['product_sales']}")
        
    def test_payment_sales_exclude_gst(self):
        """Test payment-sales with exclude_gst=true"""
        baseline = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=false").json()
        resp = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=true&exclude_shipping=false")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"Payment Sales - Exclude GST: Total={baseline['total_amount']}, Product Sales={data['product_sales']}")
        if baseline['total_orders'] > 0:
            assert data['product_sales'] <= baseline['total_amount'], "With exclude_gst, product_sales should be <= total_amount"
            
    def test_payment_sales_exclude_shipping(self):
        """Test payment-sales with exclude_shipping=true"""
        baseline = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=false").json()
        resp = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=true")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        print(f"Payment Sales - Exclude Shipping: Total={baseline['total_amount']}, Product Sales={data['product_sales']}")
        if baseline['total_orders'] > 0:
            assert data['product_sales'] <= baseline['total_amount'], "With exclude_shipping, product_sales should be <= total_amount"
            
    def test_payment_sales_exclude_both(self):
        """Test payment-sales with both exclusions"""
        excl_gst = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=true&exclude_shipping=false").json()
        excl_ship = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=true").json()
        excl_both = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=true&exclude_shipping=true").json()
        
        print(f"Payment Sales - Exclude GST: {excl_gst['product_sales']}")
        print(f"Payment Sales - Exclude Shipping: {excl_ship['product_sales']}")
        print(f"Payment Sales - Exclude Both: {excl_both['product_sales']}")
        
        if excl_gst['total_orders'] > 0:
            assert excl_both['product_sales'] <= excl_gst['product_sales'], "Both exclusions should be <= GST-only"
            assert excl_both['product_sales'] <= excl_ship['product_sales'], "Both exclusions should be <= shipping-only"


class TestTelecallerDashboardExclusion:
    """Test exclusion logic from telecaller perspective"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as telecaller and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as telecaller
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_tc_payment",
            "password": "test123"
        })
        if login_resp.status_code != 200:
            pytest.skip("Telecaller test_tc_payment not available")
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
    def test_telecaller_own_sales_exclusions(self):
        """Test telecaller can see their own sales with exclusions"""
        # No exclusions
        no_excl = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=false")
        assert no_excl.status_code == 200
        
        # With GST exclusion
        excl_gst = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=true&exclude_shipping=false")
        assert excl_gst.status_code == 200
        
        # With shipping exclusion
        excl_ship = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=false&exclude_shipping=true")
        assert excl_ship.status_code == 200
        
        # With both exclusions
        excl_both = self.session.get(f"{BASE_URL}/api/reports/telecaller-sales?period=all&exclude_gst=true&exclude_shipping=true")
        assert excl_both.status_code == 200
        
        print(f"Telecaller own sales - No excl: {no_excl.json()['product_sales']}")
        print(f"Telecaller own sales - Excl GST: {excl_gst.json()['product_sales']}")
        print(f"Telecaller own sales - Excl Ship: {excl_ship.json()['product_sales']}")
        print(f"Telecaller own sales - Excl Both: {excl_both.json()['product_sales']}")
        
    def test_telecaller_payment_sales_exclusions(self):
        """Test telecaller can see payment-received sales with exclusions"""
        # No exclusions
        no_excl = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=false")
        assert no_excl.status_code == 200
        
        # With GST exclusion
        excl_gst = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=true&exclude_shipping=false")
        assert excl_gst.status_code == 200
        
        # With shipping exclusion
        excl_ship = self.session.get(f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=false&exclude_shipping=true")
        assert excl_ship.status_code == 200
        
        print(f"Telecaller payment sales - No excl: {no_excl.json()['product_sales']}")
        print(f"Telecaller payment sales - Excl GST: {excl_gst.json()['product_sales']}")
        print(f"Telecaller payment sales - Excl Ship: {excl_ship.json()['product_sales']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
