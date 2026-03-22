"""
Phase 7 Part 3 Backend Tests
Tests for:
- Field Manager role (same as telecaller but own orders only)
- Accounts role (invoice uploads, payment verification)
- Payment Check System (accounts only)
- Payment Sales report
- Accounts Dashboard
- Role-based access control
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}
ACCOUNTS_CREDS = {"username": "accounts1", "password": "accounts123"}
FIELD_MANAGER_CREDS = {"username": "field1", "password": "field123"}


class TestAuth:
    """Authentication tests for all roles"""
    
    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful: {data['user']['name']}")
    
    def test_accounts_login(self):
        """Test accounts user login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ACCOUNTS_CREDS)
        if response.status_code == 401:
            # Create accounts user if not exists
            admin_token = self._get_admin_token()
            create_resp = requests.post(
                f"{BASE_URL}/api/users",
                json={"username": "accounts1", "password": "accounts123", "name": "Accounts User", "role": "accounts"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            if create_resp.status_code in [200, 201]:
                response = requests.post(f"{BASE_URL}/api/auth/login", json=ACCOUNTS_CREDS)
        
        assert response.status_code == 200, f"Accounts login failed: {response.text}"
        data = response.json()
        assert data["user"]["role"] == "accounts"
        print(f"✓ Accounts login successful: {data['user']['name']}")
    
    def test_field_manager_login(self):
        """Test field manager login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=FIELD_MANAGER_CREDS)
        if response.status_code == 401:
            # Create field_manager user if not exists
            admin_token = self._get_admin_token()
            create_resp = requests.post(
                f"{BASE_URL}/api/users",
                json={"username": "field1", "password": "field123", "name": "Field Manager", "role": "field_manager"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            if create_resp.status_code in [200, 201]:
                response = requests.post(f"{BASE_URL}/api/auth/login", json=FIELD_MANAGER_CREDS)
        
        assert response.status_code == 200, f"Field manager login failed: {response.text}"
        data = response.json()
        assert data["user"]["role"] == "field_manager"
        print(f"✓ Field manager login successful: {data['user']['name']}")
    
    def _get_admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]


class TestUserManagement:
    """Test user creation with new roles"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    def test_create_field_manager_role(self, admin_token):
        """Test creating a field_manager user"""
        # First check if user exists
        users_resp = requests.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        users = users_resp.json()
        existing = [u for u in users if u["username"] == "test_field_mgr"]
        
        if not existing:
            response = requests.post(
                f"{BASE_URL}/api/users",
                json={"username": "test_field_mgr", "password": "test123", "name": "Test Field Manager", "role": "field_manager"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code in [200, 201], f"Failed to create field_manager: {response.text}"
            data = response.json()
            assert data["role"] == "field_manager"
            print("✓ Field manager user created successfully")
        else:
            print("✓ Field manager user already exists")
    
    def test_create_accounts_role(self, admin_token):
        """Test creating an accounts user"""
        users_resp = requests.get(
            f"{BASE_URL}/api/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        users = users_resp.json()
        existing = [u for u in users if u["username"] == "test_accounts"]
        
        if not existing:
            response = requests.post(
                f"{BASE_URL}/api/users",
                json={"username": "test_accounts", "password": "test123", "name": "Test Accounts", "role": "accounts"},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code in [200, 201], f"Failed to create accounts user: {response.text}"
            data = response.json()
            assert data["role"] == "accounts"
            print("✓ Accounts user created successfully")
        else:
            print("✓ Accounts user already exists")
    
    def test_invalid_role_rejected(self, admin_token):
        """Test that invalid roles are rejected"""
        response = requests.post(
            f"{BASE_URL}/api/users",
            json={"username": "invalid_role_user", "password": "test123", "name": "Invalid", "role": "invalid_role"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400, "Invalid role should be rejected"
        print("✓ Invalid role correctly rejected")


class TestPaymentCheckAccess:
    """Test payment check endpoint access control"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    @pytest.fixture
    def accounts_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ACCOUNTS_CREDS)
        if resp.status_code != 200:
            pytest.skip("Accounts user not available")
        return resp.json()["token"]
    
    @pytest.fixture
    def field_manager_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=FIELD_MANAGER_CREDS)
        if resp.status_code != 200:
            pytest.skip("Field manager user not available")
        return resp.json()["token"]
    
    def _get_first_order_id(self, token):
        """Helper to get first order ID"""
        resp = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {token}"}
        )
        orders = resp.json()
        if orders:
            return orders[0]["id"]
        return None
    
    def test_admin_cannot_update_payment_check(self, admin_token):
        """Admin should NOT be able to update payment check status"""
        order_id = self._get_first_order_id(admin_token)
        if not order_id:
            pytest.skip("No orders available for testing")
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/payment-check",
            json={"payment_check_status": "received"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 403, f"Admin should get 403, got {response.status_code}: {response.text}"
        print("✓ Admin correctly denied payment check update (403)")
    
    def test_accounts_can_update_payment_check(self, accounts_token, admin_token):
        """Accounts user CAN update payment check status"""
        order_id = self._get_first_order_id(admin_token)
        if not order_id:
            pytest.skip("No orders available for testing")
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/payment-check",
            json={"payment_check_status": "received"},
            headers={"Authorization": f"Bearer {accounts_token}"}
        )
        assert response.status_code == 200, f"Accounts should be able to update payment check: {response.text}"
        data = response.json()
        assert data["payment_check_status"] == "received"
        print("✓ Accounts user successfully updated payment check status")
    
    def test_field_manager_cannot_update_payment_check(self, field_manager_token, admin_token):
        """Field manager should NOT be able to update payment check"""
        order_id = self._get_first_order_id(admin_token)
        if not order_id:
            pytest.skip("No orders available for testing")
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/payment-check",
            json={"payment_check_status": "received"},
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        assert response.status_code == 403, f"Field manager should get 403, got {response.status_code}"
        print("✓ Field manager correctly denied payment check update (403)")


class TestPaymentSalesReport:
    """Test payment-sales report endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    @pytest.fixture
    def field_manager_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=FIELD_MANAGER_CREDS)
        if resp.status_code != 200:
            pytest.skip("Field manager user not available")
        return resp.json()["token"]
    
    def test_admin_can_access_payment_sales(self, admin_token):
        """Admin can access payment-sales report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/payment-sales?period=today",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Admin should access payment-sales: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "total_amount" in data
        assert "product_sales" in data
        print(f"✓ Admin payment-sales report: {data['total_orders']} orders, ₹{data['total_amount']}")
    
    def test_field_manager_cannot_access_payment_sales(self, field_manager_token):
        """Field manager should NOT access payment-sales report"""
        response = requests.get(
            f"{BASE_URL}/api/reports/payment-sales?period=today",
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        assert response.status_code == 403, f"Field manager should get 403, got {response.status_code}"
        print("✓ Field manager correctly denied payment-sales access (403)")
    
    def test_payment_sales_with_period_filters(self, admin_token):
        """Test payment-sales with different period filters"""
        for period in ["today", "yesterday", "week", "month", "all"]:
            response = requests.get(
                f"{BASE_URL}/api/reports/payment-sales?period={period}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 200, f"Period {period} failed: {response.text}"
        print("✓ Payment-sales works with all period filters")
    
    def test_payment_sales_with_exclude_flags(self, admin_token):
        """Test payment-sales with exclude_gst and exclude_shipping"""
        response = requests.get(
            f"{BASE_URL}/api/reports/payment-sales?period=all&exclude_gst=true&exclude_shipping=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "product_sales" in data
        print(f"✓ Payment-sales with exclusions: product_sales=₹{data['product_sales']}")


class TestAccountsDashboard:
    """Test accounts-dashboard endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    @pytest.fixture
    def accounts_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ACCOUNTS_CREDS)
        if resp.status_code != 200:
            pytest.skip("Accounts user not available")
        return resp.json()["token"]
    
    @pytest.fixture
    def field_manager_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=FIELD_MANAGER_CREDS)
        if resp.status_code != 200:
            pytest.skip("Field manager user not available")
        return resp.json()["token"]
    
    def test_accounts_can_access_dashboard(self, accounts_token):
        """Accounts user can access accounts-dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/reports/accounts-dashboard?period=today",
            headers={"Authorization": f"Bearer {accounts_token}"}
        )
        assert response.status_code == 200, f"Accounts should access dashboard: {response.text}"
        data = response.json()
        # Check all expected metrics
        assert "total_invoices" in data
        assert "gst_without_invoice" in data
        assert "payments_received" in data
        assert "payments_pending" in data
        assert "gst_total" in data
        print(f"✓ Accounts dashboard metrics: invoices={data['total_invoices']}, received={data['payments_received']}, pending={data['payments_pending']}")
    
    def test_admin_can_access_accounts_dashboard(self, admin_token):
        """Admin can also access accounts-dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/reports/accounts-dashboard?period=all",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        print("✓ Admin can access accounts dashboard")
    
    def test_field_manager_cannot_access_accounts_dashboard(self, field_manager_token):
        """Field manager should NOT access accounts-dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/reports/accounts-dashboard?period=today",
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        assert response.status_code == 403, f"Field manager should get 403, got {response.status_code}"
        print("✓ Field manager correctly denied accounts dashboard access (403)")


class TestFieldManagerOrderAccess:
    """Test field manager sees only own orders"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    @pytest.fixture
    def field_manager_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=FIELD_MANAGER_CREDS)
        if resp.status_code != 200:
            pytest.skip("Field manager user not available")
        return resp.json()["token"]
    
    def test_field_manager_sees_own_orders_only(self, field_manager_token, admin_token):
        """Field manager should only see their own orders"""
        # Get field manager's user ID
        me_resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        fm_user_id = me_resp.json()["id"]
        
        # Get orders as field manager
        orders_resp = requests.get(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        # All orders should belong to field manager (or be empty)
        for order in orders:
            assert order.get("telecaller_id") == fm_user_id or "telecaller_id" not in order, \
                f"Field manager sees order not belonging to them: {order.get('order_number')}"
        
        print(f"✓ Field manager sees {len(orders)} orders (all own orders)")
    
    def test_field_manager_view_all_still_shows_own(self, field_manager_token):
        """Even with view_all=true, field manager sees only own orders"""
        me_resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        fm_user_id = me_resp.json()["id"]
        
        orders_resp = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {field_manager_token}"}
        )
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        # Should still only see own orders
        for order in orders:
            assert order.get("telecaller_id") == fm_user_id or "telecaller_id" not in order
        
        print(f"✓ Field manager with view_all=true still sees only own orders ({len(orders)})")


class TestPaymentRecheckLogic:
    """Test payment re-check logic when payment is updated"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    @pytest.fixture
    def accounts_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ACCOUNTS_CREDS)
        if resp.status_code != 200:
            pytest.skip("Accounts user not available")
        return resp.json()["token"]
    
    def _get_first_order_id(self, token):
        resp = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {token}"}
        )
        orders = resp.json()
        if orders:
            return orders[0]["id"]
        return None
    
    def test_recheck_logic_on_payment_update(self, admin_token, accounts_token):
        """When payment is updated on a 'received' order, status should change to 'pending_recheck'"""
        order_id = self._get_first_order_id(admin_token)
        if not order_id:
            pytest.skip("No orders available for testing")
        
        # Step 1: Mark order as received (accounts)
        mark_resp = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/payment-check",
            json={"payment_check_status": "received"},
            headers={"Authorization": f"Bearer {accounts_token}"}
        )
        assert mark_resp.status_code == 200
        assert mark_resp.json()["payment_check_status"] == "received"
        print("  Step 1: Order marked as 'received'")
        
        # Step 2: Update payment amount as admin
        order_resp = requests.get(
            f"{BASE_URL}/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        current_amount = order_resp.json().get("amount_paid", 0)
        new_amount = current_amount + 100  # Change the amount
        
        update_resp = requests.put(
            f"{BASE_URL}/api/orders/{order_id}",
            json={"amount_paid": new_amount, "payment_status": "partial"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert update_resp.status_code == 200
        print(f"  Step 2: Payment updated from {current_amount} to {new_amount}")
        
        # Step 3: Verify status changed to pending_recheck
        check_resp = requests.get(
            f"{BASE_URL}/api/orders/{order_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert check_resp.status_code == 200
        final_status = check_resp.json().get("payment_check_status")
        assert final_status == "pending_recheck", f"Expected 'pending_recheck', got '{final_status}'"
        print("  Step 3: Status correctly changed to 'pending_recheck'")
        print("✓ Payment re-check logic working correctly")


class TestInvoiceEndpoints:
    """Test invoice upload/delete endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    @pytest.fixture
    def accounts_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ACCOUNTS_CREDS)
        if resp.status_code != 200:
            pytest.skip("Accounts user not available")
        return resp.json()["token"]
    
    def _get_gst_order_id(self, token):
        """Get a GST-applicable order"""
        resp = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {token}"}
        )
        orders = resp.json()
        for order in orders:
            if order.get("gst_applicable"):
                return order["id"]
        return None
    
    def test_accounts_can_set_invoice(self, accounts_token, admin_token):
        """Accounts can set invoice URL on GST orders"""
        order_id = self._get_gst_order_id(admin_token)
        if not order_id:
            pytest.skip("No GST orders available")
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/invoice",
            json={"invoice_url": "/api/uploads/test-invoice.pdf"},
            headers={"Authorization": f"Bearer {accounts_token}"}
        )
        assert response.status_code == 200, f"Failed to set invoice: {response.text}"
        print("✓ Accounts can set invoice URL")
    
    def test_accounts_can_delete_invoice(self, accounts_token, admin_token):
        """Accounts can delete invoice"""
        order_id = self._get_gst_order_id(admin_token)
        if not order_id:
            pytest.skip("No GST orders available")
        
        response = requests.delete(
            f"{BASE_URL}/api/orders/{order_id}/invoice",
            headers={"Authorization": f"Bearer {accounts_token}"}
        )
        assert response.status_code == 200
        print("✓ Accounts can delete invoice")


class TestTelecallerSalesReport:
    """Test telecaller-sales report for different roles"""
    
    @pytest.fixture
    def admin_token(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return resp.json()["token"]
    
    def test_telecaller_sales_endpoint(self, admin_token):
        """Test telecaller-sales endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?period=all",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_orders" in data
        assert "total_amount" in data
        assert "product_sales" in data
        print(f"✓ Telecaller sales report: {data['total_orders']} orders")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
