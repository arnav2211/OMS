"""
Phase 4 Tests - CitSpray OMS
Tests for new features:
1. Print endpoint auth via query param (token=JWT)
2. Delete order (permanent deletion replacing cancel)
3. All Orders page with payment status filter
4. Role-based visibility (telecaller/dispatch can't see executive name & formulations when viewing all)
5. Dashboard shows only Recent Orders (first 10)
6. Custom date range for Executive Reports and Telecaller sales
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://order-search-1.preview.emergentagent.com")


@pytest.fixture(scope="module")
def admin_token():
    """Login as admin and return token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def api_session():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def telecaller_setup(admin_token, api_session):
    """Create a telecaller user for testing and return their token"""
    # Create telecaller
    api_session.headers.update({"Authorization": f"Bearer {admin_token}"})
    create_res = api_session.post(f"{BASE_URL}/api/users", json={
        "username": "test_tc_phase4",
        "password": "testpass123",
        "name": "Test Telecaller P4",
        "role": "telecaller"
    })
    # May already exist from previous tests - that's OK
    if create_res.status_code not in [200, 400]:
        pytest.fail(f"Failed to create telecaller: {create_res.text}")
    
    # Login as telecaller
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "test_tc_phase4",
        "password": "testpass123"
    })
    if login_res.status_code != 200:
        pytest.fail(f"Failed to login as telecaller: {login_res.text}")
    
    tc_data = login_res.json()
    return {"token": tc_data["token"], "user": tc_data["user"]}


@pytest.fixture(scope="module")
def customer_and_order(telecaller_setup):
    """Create test customer and order, return IDs"""
    headers = {"Authorization": f"Bearer {telecaller_setup['token']}", "Content-Type": "application/json"}
    
    # Create customer
    cust_res = requests.post(f"{BASE_URL}/api/customers", headers=headers, json={
        "name": "Test Customer Phase4",
        "phone_numbers": ["9999888877"],
        "billing_address": {"address": "123 Test St", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
        "shipping_address": {"address": "123 Test St", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"}
    })
    if cust_res.status_code not in [200, 400]:
        pytest.fail(f"Failed to create customer: {cust_res.text}")
    
    customer_id = cust_res.json().get("id") if cust_res.status_code == 200 else None
    
    # If customer exists (400), find it
    if not customer_id:
        list_res = requests.get(f"{BASE_URL}/api/customers?search=9999888877", headers=headers)
        customers = list_res.json()
        if customers:
            customer_id = customers[0]["id"]
    
    # Create order with courier shipping
    order_res = requests.post(f"{BASE_URL}/api/orders", headers=headers, json={
        "customer_id": customer_id,
        "purpose": "Test order for Phase 4",
        "items": [{"product_name": "P4 Test Item", "qty": 2, "unit": "Kg", "rate": 500, "amount": 1000, "gst_rate": 18, "formulation": "Secret Recipe P4"}],
        "gst_applicable": True,
        "shipping_method": "courier",
        "courier_name": "DTDC",
        "shipping_charge": 100,
        "payment_status": "partial",
        "amount_paid": 500
    })
    
    if order_res.status_code != 200:
        pytest.fail(f"Failed to create order: {order_res.text}")
    
    order = order_res.json()
    return {"customer_id": customer_id, "order_id": order["id"], "order_number": order["order_number"]}


class TestPrintEndpointAuth:
    """Test print endpoint accepts token via query param"""
    
    def test_print_with_token_returns_pdf(self, admin_token, customer_and_order):
        """Print endpoint should return PDF when valid token provided via query param"""
        order_id = customer_and_order["order_id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}/print?token={admin_token}")
        
        assert response.status_code == 200, f"Print should work with token param: {response.text}"
        assert "application/pdf" in response.headers.get("content-type", ""), "Should return PDF"
    
    def test_print_without_token_returns_401(self, customer_and_order):
        """Print endpoint should return 401 when no token provided"""
        order_id = customer_and_order["order_id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}/print")
        
        assert response.status_code == 401, f"Should return 401 without token: {response.status_code}"
    
    def test_print_with_empty_token_returns_401(self, customer_and_order):
        """Print endpoint should return 401 when empty token provided"""
        order_id = customer_and_order["order_id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}/print?token=")
        
        assert response.status_code == 401, f"Should return 401 with empty token: {response.status_code}"
    
    def test_print_with_invalid_token_returns_401(self, customer_and_order):
        """Print endpoint should return 401 when invalid token provided"""
        order_id = customer_and_order["order_id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}/print?token=invalid_jwt_token")
        
        assert response.status_code == 401, f"Should return 401 with invalid token: {response.status_code}"


class TestDeleteOrder:
    """Test permanent order deletion (replaces cancel)"""
    
    def test_delete_order_endpoint_exists(self, telecaller_setup, customer_and_order):
        """DELETE /api/orders/{id} endpoint should exist"""
        headers = {"Authorization": f"Bearer {telecaller_setup['token']}"}
        
        # Create a test order specifically for deletion
        create_res = requests.post(f"{BASE_URL}/api/orders", headers={
            **headers, "Content-Type": "application/json"
        }, json={
            "customer_id": customer_and_order["customer_id"],
            "purpose": "Order to delete",
            "items": [{"product_name": "Delete Test", "qty": 1, "unit": "Pc", "rate": 100, "amount": 100}],
            "shipping_method": "office_collection",
            "payment_status": "unpaid"
        })
        
        if create_res.status_code != 200:
            pytest.skip(f"Could not create order for deletion test: {create_res.text}")
        
        order_to_delete_id = create_res.json()["id"]
        
        # Delete the order
        delete_res = requests.delete(f"{BASE_URL}/api/orders/{order_to_delete_id}", headers=headers)
        assert delete_res.status_code == 200, f"Delete should succeed: {delete_res.text}"
        assert "permanently deleted" in delete_res.json().get("message", "").lower(), "Should say permanently deleted"
        
        # Verify order no longer exists
        get_res = requests.get(f"{BASE_URL}/api/orders/{order_to_delete_id}", headers=headers)
        assert get_res.status_code == 404, "Deleted order should return 404"
    
    def test_delete_requires_auth(self):
        """Delete should require authentication"""
        response = requests.delete(f"{BASE_URL}/api/orders/some-fake-id")
        assert response.status_code in [401, 403], "Delete should require auth"
    
    def test_admin_can_delete(self, admin_token, telecaller_setup, customer_and_order):
        """Admin should be able to delete orders"""
        # Create order as telecaller
        tc_headers = {"Authorization": f"Bearer {telecaller_setup['token']}", "Content-Type": "application/json"}
        create_res = requests.post(f"{BASE_URL}/api/orders", headers=tc_headers, json={
            "customer_id": customer_and_order["customer_id"],
            "purpose": "Admin delete test",
            "items": [{"product_name": "Admin Delete Test", "qty": 1, "unit": "Pc", "rate": 50}],
            "shipping_method": "office_collection",
            "payment_status": "unpaid"
        })
        
        if create_res.status_code != 200:
            pytest.skip("Could not create order")
        
        order_id = create_res.json()["id"]
        
        # Delete as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        delete_res = requests.delete(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        assert delete_res.status_code == 200, "Admin should delete successfully"


class TestAllOrdersEndpoint:
    """Test All Orders API with view_all=true parameter"""
    
    def test_view_all_orders_admin(self, admin_token):
        """Admin can view all orders with view_all=true"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=headers)
        
        assert response.status_code == 200, f"Should return orders: {response.text}"
        orders = response.json()
        assert isinstance(orders, list), "Should return list of orders"
        
        # Admin should see telecaller_name
        if orders:
            # At least one order should have telecaller_name (if admin created it, may not have)
            pass  # Just verify the endpoint works
    
    def test_view_all_orders_telecaller_hides_executive(self, telecaller_setup):
        """Telecaller viewing all orders should NOT see executive name"""
        headers = {"Authorization": f"Bearer {telecaller_setup['token']}"}
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=headers)
        
        assert response.status_code == 200, f"Should return orders: {response.text}"
        orders = response.json()
        
        # Telecaller should NOT see telecaller_name when view_all=true
        for order in orders:
            assert "telecaller_name" not in order or order.get("telecaller_name") is None, \
                f"Telecaller should not see telecaller_name when view_all=true: {order}"
    
    def test_view_all_orders_strips_formulations_for_telecaller(self, telecaller_setup):
        """Telecaller viewing all orders should NOT see formulations"""
        headers = {"Authorization": f"Bearer {telecaller_setup['token']}"}
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=headers)
        
        assert response.status_code == 200
        orders = response.json()
        
        for order in orders:
            for item in order.get("items", []):
                assert "formulation" not in item or not item.get("formulation"), \
                    f"Telecaller should not see formulation when view_all=true: {item}"


class TestTelecallerSalesCustomDateRange:
    """Test custom date range for telecaller sales report"""
    
    def test_telecaller_sales_supports_date_from_date_to(self, telecaller_setup):
        """Telecaller sales endpoint should accept date_from and date_to params"""
        headers = {"Authorization": f"Bearer {telecaller_setup['token']}"}
        
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?period=custom&date_from=2025-01-01&date_to=2025-12-31",
            headers=headers
        )
        
        assert response.status_code == 200, f"Should return sales data: {response.text}"
        data = response.json()
        assert "total_orders" in data, "Should have total_orders"
        assert "total_amount" in data, "Should have total_amount"
        assert "product_sales" in data, "Should have product_sales"
    
    def test_telecaller_sales_custom_range_filters_by_date(self, telecaller_setup):
        """Custom date range should filter orders by created_at"""
        headers = {"Authorization": f"Bearer {telecaller_setup['token']}"}
        
        # Query with a very old date range that should return 0 orders
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?period=custom&date_from=2020-01-01&date_to=2020-01-02",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_orders"] == 0, "Old date range should return 0 orders"


class TestExecutiveReportsCustomDateRange:
    """Test custom date range for admin executive reports"""
    
    def test_admin_can_view_telecaller_with_custom_range(self, admin_token, telecaller_setup):
        """Admin should be able to view telecaller sales with custom date range"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        tc_id = telecaller_setup["user"]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={tc_id}&period=custom&date_from=2025-01-01&date_to=2026-12-31",
            headers=headers
        )
        
        assert response.status_code == 200, f"Should return sales data: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "product_sales" in data


class TestPaymentStatusFilter:
    """Test payment status filtering on orders"""
    
    def test_orders_have_payment_status(self, admin_token, customer_and_order):
        """Orders should have payment_status field"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/{customer_and_order['order_id']}", headers=headers)
        
        assert response.status_code == 200
        order = response.json()
        assert "payment_status" in order, "Order should have payment_status"
        assert order["payment_status"] in ["unpaid", "partial", "full"], f"Invalid payment status: {order['payment_status']}"
    
    def test_all_orders_include_payment_status(self, admin_token):
        """All orders API should include payment_status for filtering"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=headers)
        
        assert response.status_code == 200
        orders = response.json()
        
        for order in orders:
            assert "payment_status" in order, f"Order {order.get('order_number')} missing payment_status"


class TestDispatchCannotSeeFormulations:
    """Test that dispatch role cannot see formulations when viewing all orders"""
    
    def test_create_dispatch_user(self, admin_token):
        """Create dispatch user for testing"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        response = requests.post(f"{BASE_URL}/api/users", headers=headers, json={
            "username": "test_dispatch_p4",
            "password": "testpass123",
            "name": "Test Dispatch P4",
            "role": "dispatch"
        })
        # May already exist
        assert response.status_code in [200, 400], f"User creation unexpected error: {response.text}"
    
    def test_dispatch_view_all_hides_formulations(self, admin_token):
        """Dispatch viewing all orders should not see formulations"""
        # Login as dispatch
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_dispatch_p4",
            "password": "testpass123"
        })
        
        if login_res.status_code != 200:
            pytest.skip("Dispatch user not available")
        
        dispatch_token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {dispatch_token}"}
        
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=headers)
        assert response.status_code == 200
        
        orders = response.json()
        for order in orders:
            for item in order.get("items", []):
                assert "formulation" not in item or not item.get("formulation"), \
                    f"Dispatch should not see formulation when view_all=true"


class TestDashboardRecentOrdersOnly:
    """Test that dashboard shows only recent orders (not all)"""
    
    def test_orders_endpoint_returns_all_by_default(self, telecaller_setup):
        """Default orders endpoint (without view_all) should return user's orders"""
        headers = {"Authorization": f"Bearer {telecaller_setup['token']}"}
        response = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        
        assert response.status_code == 200
        orders = response.json()
        
        # This returns the telecaller's own orders (filtered by telecaller_id)
        # The frontend will slice to first 10 for "recent"
        assert isinstance(orders, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
