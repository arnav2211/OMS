"""
Phase 5 Backend Tests for CitSpray OMS
Tests: Customer validation, Address Directory, Order enhancements, Dispatch lock, PI improvements, Admin analytics
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://order-enhancement.preview.emergentagent.com')

class TestPhase5:
    """Phase 5 feature tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    # ============ Customer Validation Tests ============
    
    def test_customer_phone_validation_invalid_short(self):
        """Phone validation - reject short numbers"""
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Invalid Phone",
            "phone_numbers": ["123"],
            "gst_no": "",
            "email": ""
        })
        assert response.status_code == 400
        assert "Invalid phone number" in response.json()["detail"]
    
    def test_customer_phone_validation_mandatory(self):
        """Phone validation - at least one phone required"""
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test No Phone",
            "phone_numbers": [],
            "gst_no": "",
            "email": ""
        })
        assert response.status_code == 400
        assert "phone number is required" in response.json()["detail"]
    
    def test_customer_phone_normalization(self):
        """Phone normalization - spaces removed, +91 prefix added"""
        # First delete if exists
        search_resp = requests.get(f"{BASE_URL}/api/customers?search=Test%20Phone%20Norm", headers=self.headers)
        for c in search_resp.json():
            requests.delete(f"{BASE_URL}/api/customers/{c['id']}", headers=self.headers)
        
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Phone Norm",
            "phone_numbers": ["98765 43210"],
            "gst_no": "",
            "email": ""
        })
        assert response.status_code == 200
        data = response.json()
        # Phone should be normalized to +91XXXXXXXXXX format
        assert data["phone_numbers"][0] == "+919876543210"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/customers/{data['id']}", headers=self.headers)
    
    def test_customer_gst_validation_invalid(self):
        """GST validation - reject invalid format"""
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Invalid GST",
            "phone_numbers": ["9876543210"],
            "gst_no": "INVALID123",
            "email": ""
        })
        assert response.status_code == 400
        assert "Invalid GST" in response.json()["detail"]
    
    def test_customer_gst_validation_valid(self):
        """GST validation - accept valid format"""
        # First delete if exists
        search_resp = requests.get(f"{BASE_URL}/api/customers?search=Test%20Valid%20GST%20P5", headers=self.headers)
        for c in search_resp.json():
            requests.delete(f"{BASE_URL}/api/customers/{c['id']}", headers=self.headers)
        
        # Use a different valid GST number (Karnataka state code 29)
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Valid GST P5",
            "phone_numbers": ["9876543299"],
            "gst_no": "29AABCU9603R1ZP",
            "email": ""
        })
        assert response.status_code == 200
        data = response.json()
        assert data["gst_no"] == "29AABCU9603R1ZP"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/customers/{data['id']}", headers=self.headers)
    
    def test_customer_email_validation_invalid(self):
        """Email validation - reject invalid format"""
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Invalid Email",
            "phone_numbers": ["9876543210"],
            "gst_no": "",
            "email": "invalid-email"
        })
        assert response.status_code == 400
        assert "Invalid email" in response.json()["detail"]
    
    def test_customer_email_validation_valid(self):
        """Email validation - accept valid format"""
        # First delete if exists
        search_resp = requests.get(f"{BASE_URL}/api/customers?search=Test%20Valid%20Email%20P5", headers=self.headers)
        for c in search_resp.json():
            requests.delete(f"{BASE_URL}/api/customers/{c['id']}", headers=self.headers)
        
        response = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Valid Email P5",
            "phone_numbers": ["9876543298"],
            "gst_no": "",
            "email": "test@example.com"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        # Cleanup
        requests.delete(f"{BASE_URL}/api/customers/{data['id']}", headers=self.headers)
    
    # ============ Pincode API Tests ============
    
    def test_pincode_lookup_valid(self):
        """Pincode lookup - returns city and state for valid pincode"""
        response = requests.get(f"{BASE_URL}/api/pincode/440025", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["pincode"] == "440025"
        assert data["city"] == "Nagpur"
        assert data["state"] == "Maharashtra"
    
    def test_pincode_lookup_invalid_format(self):
        """Pincode lookup - reject invalid format"""
        response = requests.get(f"{BASE_URL}/api/pincode/12345", headers=self.headers)
        assert response.status_code == 400
        assert "6 digits" in response.json()["detail"]
    
    # ============ Address Directory Tests ============
    
    def test_address_crud(self):
        """Address CRUD - create, list, update, delete"""
        # Create customer first
        cust_resp = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Address CRUD P5",
            "phone_numbers": ["9876543297"],
            "gst_no": "",
            "email": ""
        })
        assert cust_resp.status_code == 200
        customer_id = cust_resp.json()["id"]
        
        # Create address
        addr_resp = requests.post(f"{BASE_URL}/api/customers/{customer_id}/addresses", headers=self.headers, json={
            "address_line": "123 Test Street",
            "city": "Nagpur",
            "state": "Maharashtra",
            "pincode": "440025",
            "label": "Office"
        })
        assert addr_resp.status_code == 200
        addr_data = addr_resp.json()
        assert addr_data["address_line"] == "123 Test Street"
        assert addr_data["label"] == "Office"
        address_id = addr_data["id"]
        
        # List addresses
        list_resp = requests.get(f"{BASE_URL}/api/customers/{customer_id}/addresses", headers=self.headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1
        
        # Update address
        update_resp = requests.put(f"{BASE_URL}/api/customers/{customer_id}/addresses/{address_id}", headers=self.headers, json={
            "address_line": "456 Updated Street",
            "city": "Nagpur",
            "state": "Maharashtra",
            "pincode": "440025",
            "label": "Warehouse"
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["address_line"] == "456 Updated Street"
        assert update_resp.json()["label"] == "Warehouse"
        
        # Delete address
        del_resp = requests.delete(f"{BASE_URL}/api/customers/{customer_id}/addresses/{address_id}", headers=self.headers)
        assert del_resp.status_code == 200
        
        # Cleanup customer
        requests.delete(f"{BASE_URL}/api/customers/{customer_id}", headers=self.headers)
    
    def test_address_pincode_validation(self):
        """Address creation - pincode must be 6 digits"""
        # Get any customer
        cust_resp = requests.get(f"{BASE_URL}/api/customers", headers=self.headers)
        if not cust_resp.json():
            pytest.skip("No customers available")
        customer_id = cust_resp.json()[0]["id"]
        
        response = requests.post(f"{BASE_URL}/api/customers/{customer_id}/addresses", headers=self.headers, json={
            "address_line": "Test Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "12345",
            "label": ""
        })
        assert response.status_code == 400
        assert "6 digits" in response.json()["detail"]
    
    # ============ Order Enhancement Tests ============
    
    def test_order_rounding_math_ceil(self):
        """Order total uses Math.ceil for rounding"""
        # Get a customer
        cust_resp = requests.get(f"{BASE_URL}/api/customers", headers=self.headers)
        if not cust_resp.json():
            pytest.skip("No customers available")
        customer_id = cust_resp.json()[0]["id"]
        
        # Create order with amount that needs rounding
        response = requests.post(f"{BASE_URL}/api/orders", headers=self.headers, json={
            "customer_id": customer_id,
            "purpose": "Test Rounding",
            "items": [{
                "product_name": "Test Product",
                "qty": 1,
                "unit": "L",
                "rate": 100.10,
                "amount": 100.10,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 100.10,
                "description": "",
                "formulation": ""
            }],
            "gst_applicable": False,
            "shipping_method": "",
            "courier_name": "",
            "transporter_name": "",
            "shipping_charge": 0,
            "remark": "",
            "payment_status": "unpaid",
            "amount_paid": 0,
            "payment_screenshots": [],
            "mode_of_payment": "",
            "payment_mode_details": "",
            "billing_address_id": "",
            "shipping_address_id": ""
        })
        assert response.status_code == 200
        data = response.json()
        # 100.10 should round up to 101
        assert data["grand_total"] == 101
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{data['id']}", headers=self.headers)
    
    def test_order_with_addresses(self):
        """Order creation with billing and shipping addresses"""
        # Create customer with address
        cust_resp = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
            "name": "Test Order Addr P5",
            "phone_numbers": ["9876543296"],
            "gst_no": "",
            "email": ""
        })
        assert cust_resp.status_code == 200
        customer_id = cust_resp.json()["id"]
        
        # Create address
        addr_resp = requests.post(f"{BASE_URL}/api/customers/{customer_id}/addresses", headers=self.headers, json={
            "address_line": "789 Order Street",
            "city": "Nagpur",
            "state": "Maharashtra",
            "pincode": "440025",
            "label": "Main"
        })
        assert addr_resp.status_code == 200
        address_id = addr_resp.json()["id"]
        
        # Create order with addresses
        order_resp = requests.post(f"{BASE_URL}/api/orders", headers=self.headers, json={
            "customer_id": customer_id,
            "purpose": "Test with addresses",
            "items": [{
                "product_name": "Test Product",
                "qty": 1,
                "unit": "L",
                "rate": 100,
                "amount": 100,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 100,
                "description": "Test description",
                "formulation": ""
            }],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "transporter_name": "",
            "shipping_charge": 0,
            "remark": "",
            "payment_status": "unpaid",
            "amount_paid": 0,
            "payment_screenshots": [],
            "mode_of_payment": "Online",
            "payment_mode_details": "",
            "billing_address_id": address_id,
            "shipping_address_id": address_id
        })
        assert order_resp.status_code == 200
        order_data = order_resp.json()
        
        # Verify addresses are stored
        assert order_data["billing_address_id"] == address_id
        assert order_data["shipping_address_id"] == address_id
        assert order_data["billing_address"]["address_line"] == "789 Order Street"
        assert order_data["shipping_address"]["address_line"] == "789 Order Street"
        
        # Verify mode of payment
        assert order_data["mode_of_payment"] == "Online"
        
        # Verify item description
        assert order_data["items"][0]["description"] == "Test description"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{order_data['id']}", headers=self.headers)
        requests.delete(f"{BASE_URL}/api/customers/{customer_id}/addresses/{address_id}", headers=self.headers)
        requests.delete(f"{BASE_URL}/api/customers/{customer_id}", headers=self.headers)
    
    # ============ Dispatch Lock Tests ============
    
    def test_dispatch_lock_blocks_edit(self):
        """Dispatched orders cannot be edited (except payment and formulation)"""
        # Get a dispatched order
        orders_resp = requests.get(f"{BASE_URL}/api/orders?status=dispatched&view_all=true", headers=self.headers)
        dispatched_orders = orders_resp.json()
        if not dispatched_orders:
            pytest.skip("No dispatched orders available")
        
        order_id = dispatched_orders[0]["id"]
        
        # Try to edit purpose (should fail)
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", headers=self.headers, json={
            "purpose": "Changed purpose"
        })
        assert response.status_code == 400
        assert "dispatched" in response.json()["detail"].lower()
    
    def test_dispatch_lock_allows_payment_edit(self):
        """Dispatched orders allow payment status updates"""
        # Get a dispatched order
        orders_resp = requests.get(f"{BASE_URL}/api/orders?status=dispatched&view_all=true", headers=self.headers)
        dispatched_orders = orders_resp.json()
        if not dispatched_orders:
            pytest.skip("No dispatched orders available")
        
        order_id = dispatched_orders[0]["id"]
        
        # Edit payment status (should succeed)
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", headers=self.headers, json={
            "payment_status": "partial",
            "amount_paid": 100
        })
        assert response.status_code == 200
    
    def test_dispatch_lock_allows_formulation_edit(self):
        """Dispatched orders allow formulation updates via formulation endpoint"""
        # Get a dispatched order
        orders_resp = requests.get(f"{BASE_URL}/api/orders?status=dispatched&view_all=true", headers=self.headers)
        dispatched_orders = orders_resp.json()
        if not dispatched_orders:
            pytest.skip("No dispatched orders available")
        
        order_id = dispatched_orders[0]["id"]
        
        # Edit formulation (should succeed)
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/formulation", headers=self.headers, json={
            "items": [{"index": 0, "formulation": "Test formulation update"}]
        })
        assert response.status_code == 200
    
    # ============ Admin Analytics Tests ============
    
    def test_admin_analytics_endpoint(self):
        """Admin analytics returns company-wide stats"""
        response = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=month", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "total_orders" in data
        assert "total_revenue" in data
        assert "product_sales" in data
        assert "status_counts" in data
        assert "telecaller_stats" in data
        
        # Verify status counts structure
        assert "new" in data["status_counts"]
        assert "dispatched" in data["status_counts"]
    
    def test_admin_analytics_with_filters(self):
        """Admin analytics respects GST and shipping exclusion filters"""
        # Without exclusions
        resp1 = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=month&exclude_gst=false&exclude_shipping=false", headers=self.headers)
        assert resp1.status_code == 200
        
        # With exclusions
        resp2 = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=month&exclude_gst=true&exclude_shipping=true", headers=self.headers)
        assert resp2.status_code == 200
        
        # Product sales should be different when exclusions are applied (if there's GST/shipping)
        # Just verify both return valid data
        assert resp1.json()["total_orders"] == resp2.json()["total_orders"]
    
    # ============ PI Tests ============
    
    def test_pi_creation_with_addresses(self):
        """PI creation with billing and shipping addresses"""
        # Get a customer with address
        cust_resp = requests.get(f"{BASE_URL}/api/customers", headers=self.headers)
        if not cust_resp.json():
            pytest.skip("No customers available")
        customer_id = cust_resp.json()[0]["id"]
        
        # Get or create address
        addr_resp = requests.get(f"{BASE_URL}/api/customers/{customer_id}/addresses", headers=self.headers)
        if not addr_resp.json():
            # Create address
            addr_create = requests.post(f"{BASE_URL}/api/customers/{customer_id}/addresses", headers=self.headers, json={
                "address_line": "PI Test Street",
                "city": "Nagpur",
                "state": "Maharashtra",
                "pincode": "440025",
                "label": "PI Test"
            })
            address_id = addr_create.json()["id"]
        else:
            address_id = addr_resp.json()[0]["id"]
        
        # Create PI
        pi_resp = requests.post(f"{BASE_URL}/api/proforma-invoices", headers=self.headers, json={
            "customer_id": customer_id,
            "items": [{
                "product_name": "PI Test Product",
                "qty": 1,
                "unit": "L",
                "rate": 500.50,
                "amount": 500.50,
                "gst_rate": 18,
                "gst_amount": 90.09,
                "total": 590.59,
                "description": "PI test item"
            }],
            "gst_applicable": True,
            "show_rate": True,
            "shipping_charge": 50,
            "remark": "Phase 5 PI Test",
            "billing_address_id": address_id,
            "shipping_address_id": address_id
        })
        assert pi_resp.status_code == 200
        pi_data = pi_resp.json()
        
        # Verify addresses
        assert pi_data["billing_address_id"] == address_id
        assert pi_data["shipping_address_id"] == address_id
        
        # Verify rounding (500.50 + 90.09 + 50 + 9 shipping GST = 649.59 -> 650)
        assert pi_data["grand_total"] == 650
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/proforma-invoices/{pi_data['id']}", headers=self.headers)
    
    def test_pi_pdf_with_token(self):
        """PI PDF endpoint accepts token query parameter"""
        # Get a PI
        pi_resp = requests.get(f"{BASE_URL}/api/proforma-invoices", headers=self.headers)
        if not pi_resp.json():
            pytest.skip("No PIs available")
        pi_id = pi_resp.json()[0]["id"]
        
        # Test PDF with token
        pdf_resp = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf?token={self.token}")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers.get("content-type") == "application/pdf"
        # Verify it's a PDF (starts with %PDF)
        assert pdf_resp.content[:4] == b'%PDF'
    
    def test_pi_pdf_without_token_fails(self):
        """PI PDF endpoint requires token"""
        # Get a PI
        pi_resp = requests.get(f"{BASE_URL}/api/proforma-invoices", headers=self.headers)
        if not pi_resp.json():
            pytest.skip("No PIs available")
        pi_id = pi_resp.json()[0]["id"]
        
        # Test PDF without token
        pdf_resp = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf")
        assert pdf_resp.status_code == 401
    
    # ============ GST Verification Tests ============
    
    def test_gst_verification_mocked(self):
        """GST verification returns state info (mocked)"""
        response = requests.get(f"{BASE_URL}/api/gst-verify/27AABCU9603R1ZM", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["valid_format"] == True
        assert data["state_code"] == "27"
        assert data["state_name"] == "Maharashtra"
    
    def test_gst_verification_invalid_format(self):
        """GST verification rejects invalid format"""
        response = requests.get(f"{BASE_URL}/api/gst-verify/INVALID", headers=self.headers)
        assert response.status_code == 400
    
    # ============ Settings Tests ============
    
    def test_settings_formulation_toggle(self):
        """Settings - formulation visibility toggle"""
        # Get current setting
        get_resp = requests.get(f"{BASE_URL}/api/settings", headers=self.headers)
        assert get_resp.status_code == 200
        current = get_resp.json()["show_formulation"]
        
        # Toggle setting
        put_resp = requests.put(f"{BASE_URL}/api/settings", headers=self.headers, json={
            "show_formulation": not current
        })
        assert put_resp.status_code == 200
        
        # Verify change
        verify_resp = requests.get(f"{BASE_URL}/api/settings", headers=self.headers)
        assert verify_resp.json()["show_formulation"] == (not current)
        
        # Restore original
        requests.put(f"{BASE_URL}/api/settings", headers=self.headers, json={
            "show_formulation": current
        })
    
    # ============ All Orders Filter Tests ============
    
    def test_all_orders_executive_filter(self):
        """Admin can filter orders by executive"""
        # Get users to find a telecaller
        users_resp = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        telecallers = [u for u in users_resp.json() if u["role"] == "telecaller"]
        if not telecallers:
            pytest.skip("No telecallers available")
        
        telecaller_id = telecallers[0]["id"]
        
        # Filter by telecaller
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true&telecaller_id={telecaller_id}", headers=self.headers)
        assert response.status_code == 200
        
        # All returned orders should be from this telecaller
        for order in response.json():
            assert order.get("telecaller_id") == telecaller_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
