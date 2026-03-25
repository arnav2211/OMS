"""
Phase 16 Backend Tests - New Features:
1. Admin Analytics with period filter (today/yesterday/week/month) using IST timezone
2. Customer alias field (create, search)
3. Mark Packed / Undo Packed endpoints (admin/packaging only)
4. Telecaller sales with period filter
"""
import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests for different roles"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        return data["token"]
    
    def test_packaging_login(self):
        """Test packaging role login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_packaging_user",
            "password": "test123"
        })
        assert response.status_code == 200, f"Packaging login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "packaging"
        return data["token"]
    
    def test_dispatch_login(self):
        """Test dispatch role login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_dispatch_user",
            "password": "test123"
        })
        assert response.status_code == 200, f"Dispatch login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "dispatch"
        return data["token"]


@pytest.fixture
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Admin login failed")


@pytest.fixture
def packaging_token():
    """Get packaging auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "test_packaging_user",
        "password": "test123"
    })
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Packaging login failed")


@pytest.fixture
def dispatch_token():
    """Get dispatch auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "test_dispatch_user",
        "password": "test123"
    })
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Dispatch login failed")


class TestAdminAnalytics:
    """Test admin analytics endpoint with period filters"""
    
    def test_admin_analytics_today(self, admin_token):
        """Test admin analytics with period=today"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=today", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "total_revenue" in data
        assert "product_sales" in data
        assert "status_counts" in data
        assert "telecaller_stats" in data
        print(f"Today analytics: {data['total_orders']} orders, ₹{data['total_revenue']} revenue")
    
    def test_admin_analytics_yesterday(self, admin_token):
        """Test admin analytics with period=yesterday"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=yesterday", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "total_revenue" in data
        print(f"Yesterday analytics: {data['total_orders']} orders, ₹{data['total_revenue']} revenue")
    
    def test_admin_analytics_week(self, admin_token):
        """Test admin analytics with period=week"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=week", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"Week analytics: {data['total_orders']} orders, ₹{data['total_revenue']} revenue")
    
    def test_admin_analytics_month(self, admin_token):
        """Test admin analytics with period=month (default)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/admin-analytics?period=month", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"Month analytics: {data['total_orders']} orders, ₹{data['total_revenue']} revenue")
    
    def test_admin_analytics_with_exclusions(self, admin_token):
        """Test admin analytics with GST and shipping exclusions"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/admin-analytics?period=month&exclude_gst=true&exclude_shipping=true",
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "product_sales" in data
        print(f"Product sales (excl GST+shipping): ₹{data['product_sales']}")


class TestCustomerAlias:
    """Test customer alias field functionality"""
    
    def test_create_customer_with_alias(self, admin_token):
        """Test creating customer with alias field"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        import random
        unique_phone = f"98{random.randint(10000000, 99999999)}"
        customer_data = {
            "name": "TEST_Phase16_Customer_Alias",
            "gst_no": "",
            "phone_numbers": [unique_phone],
            "email": "test_alias@example.com",
            "alias": "TestAlias16"
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=headers)
        assert response.status_code == 200, f"Failed to create customer: {response.text}"
        data = response.json()
        assert data["alias"] == "TestAlias16", f"Alias not saved correctly: {data}"
        assert data["name"] == "TEST_Phase16_Customer_Alias"
        print(f"Created customer with alias: {data['alias']}")
        return data["id"]
    
    def test_search_customer_by_alias(self, admin_token):
        """Test searching customer by alias"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        import random
        unique_phone = f"97{random.randint(10000000, 99999999)}"
        unique_alias = f"UniqueAlias{random.randint(1000, 9999)}"
        # First create a customer with unique alias
        customer_data = {
            "name": "TEST_Phase16_SearchAlias",
            "phone_numbers": [unique_phone],
            "alias": unique_alias
        }
        create_resp = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=headers)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        
        # Search by alias
        response = requests.get(f"{BASE_URL}/api/customers?search={unique_alias}", headers=headers)
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()
        # Check if customer with alias is in results
        found = any(c.get("alias") == unique_alias for c in data)
        assert found, f"Customer with alias not found in search results: {data}"
        print(f"Found customer by alias search: {unique_alias}")
    
    def test_update_customer_alias(self, admin_token):
        """Test updating customer alias"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        import random
        unique_phone = f"96{random.randint(10000000, 99999999)}"
        # Create customer
        customer_data = {
            "name": "TEST_Phase16_UpdateAlias",
            "phone_numbers": [unique_phone],
            "alias": "OldAlias16"
        }
        create_resp = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=headers)
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        customer = create_resp.json()
        customer_id = customer["id"]
        
        # Update alias - need to send full customer data as per CustomerCreate model
        update_resp = requests.put(
            f"{BASE_URL}/api/customers/{customer_id}",
            json={
                "name": customer["name"],
                "phone_numbers": customer["phone_numbers"],
                "gst_no": customer.get("gst_no", ""),
                "email": customer.get("email", ""),
                "alias": "NewAlias16"
            },
            headers=headers
        )
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        updated = update_resp.json()
        assert updated["alias"] == "NewAlias16", f"Alias not updated: {updated}"
        print(f"Updated customer alias from OldAlias16 to NewAlias16")


class TestMarkPackedUndoPacked:
    """Test mark-packed and undo-packed endpoints"""
    
    def test_mark_packed_as_admin(self, admin_token):
        """Test marking order as packed by admin"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Find an order in new or packaging status
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        # Find order in new/packaging status
        target_order = None
        for order in orders:
            if order.get("status") in ["new", "packaging"]:
                target_order = order
                break
        
        if not target_order:
            pytest.skip("No order in new/packaging status to test mark-packed")
        
        order_id = target_order["id"]
        original_status = target_order["status"]
        
        # Mark as packed
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/mark-packed", headers=headers)
        assert response.status_code == 200, f"Mark packed failed: {response.text}"
        data = response.json()
        assert data["status"] == "packed", f"Status not changed to packed: {data['status']}"
        print(f"Order {target_order['order_number']} marked as packed (was {original_status})")
        
        # Undo packed to restore original state
        undo_resp = requests.put(f"{BASE_URL}/api/orders/{order_id}/undo-packed", headers=headers)
        assert undo_resp.status_code == 200
        print(f"Order restored to packaging status")
    
    def test_mark_packed_as_packaging(self, packaging_token):
        """Test marking order as packed by packaging role"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        
        # Find an order in new or packaging status
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        target_order = None
        for order in orders:
            if order.get("status") in ["new", "packaging"]:
                target_order = order
                break
        
        if not target_order:
            pytest.skip("No order in new/packaging status to test")
        
        order_id = target_order["id"]
        
        # Mark as packed
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/mark-packed", headers=headers)
        assert response.status_code == 200, f"Packaging role mark packed failed: {response.text}"
        data = response.json()
        assert data["status"] == "packed"
        print(f"Packaging role marked order {target_order['order_number']} as packed")
        
        # Undo to restore
        requests.put(f"{BASE_URL}/api/orders/{order_id}/undo-packed", headers=headers)
    
    def test_mark_packed_forbidden_for_dispatch(self, dispatch_token):
        """Test that dispatch role cannot mark orders as packed"""
        headers = {"Authorization": f"Bearer {dispatch_token}"}
        
        # Get any order
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        if orders_resp.status_code != 200 or not orders_resp.json():
            pytest.skip("No orders available")
        
        order_id = orders_resp.json()[0]["id"]
        
        # Try to mark as packed - should fail
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/mark-packed", headers=headers)
        assert response.status_code == 403, f"Dispatch should not be able to mark packed: {response.status_code}"
        print("Dispatch role correctly forbidden from marking packed")
    
    def test_undo_packed_as_admin(self, admin_token):
        """Test undo packed by admin"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Find a packed order
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        packed_order = None
        for order in orders:
            if order.get("status") == "packed":
                packed_order = order
                break
        
        if not packed_order:
            # Create one by marking an order as packed first
            for order in orders:
                if order.get("status") in ["new", "packaging"]:
                    mark_resp = requests.put(f"{BASE_URL}/api/orders/{order['id']}/mark-packed", headers=headers)
                    if mark_resp.status_code == 200:
                        packed_order = mark_resp.json()
                        break
        
        if not packed_order:
            pytest.skip("No packed order available to test undo")
        
        order_id = packed_order["id"]
        
        # Undo packed
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/undo-packed", headers=headers)
        assert response.status_code == 200, f"Undo packed failed: {response.text}"
        data = response.json()
        assert data["status"] == "packaging", f"Status not reverted to packaging: {data['status']}"
        print(f"Order {packed_order['order_number']} reverted from packed to packaging")
    
    def test_undo_packed_only_on_packed_orders(self, admin_token):
        """Test that undo-packed only works on packed orders"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Find an order NOT in packed status
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        non_packed_order = None
        for order in orders:
            if order.get("status") != "packed":
                non_packed_order = order
                break
        
        if not non_packed_order:
            pytest.skip("All orders are packed")
        
        order_id = non_packed_order["id"]
        
        # Try to undo packed - should fail
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/undo-packed", headers=headers)
        assert response.status_code == 400, f"Should fail on non-packed order: {response.status_code}"
        print(f"Correctly rejected undo-packed on {non_packed_order['status']} order")


class TestTelecallerSales:
    """Test telecaller sales report with period filters"""
    
    def test_telecaller_sales_today(self, admin_token):
        """Test telecaller sales with period=today"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/telecaller-sales?period=today", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "total_amount" in data
        assert "product_sales" in data
        print(f"Telecaller sales today: {data['total_orders']} orders, ₹{data['total_amount']}")
    
    def test_telecaller_sales_week(self, admin_token):
        """Test telecaller sales with period=week"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/telecaller-sales?period=week", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"Telecaller sales this week: {data['total_orders']} orders")
    
    def test_telecaller_sales_month(self, admin_token):
        """Test telecaller sales with period=month"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/telecaller-sales?period=month", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"Telecaller sales this month: {data['total_orders']} orders")


class TestDispatchAccess:
    """Test dispatch endpoint access for packaging role"""
    
    def test_packaging_can_update_dispatch_fields(self, packaging_token):
        """Test that packaging role can update shipping method"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        
        # Get orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        # Find non-dispatched order
        target_order = None
        for order in orders:
            if order.get("status") != "dispatched":
                target_order = order
                break
        
        if not target_order:
            pytest.skip("No non-dispatched order available")
        
        order_id = target_order["id"]
        
        # Update shipping method
        response = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/shipping-method",
            json={"shipping_method": "courier", "courier_name": "DTDC"},
            headers=headers
        )
        assert response.status_code == 200, f"Packaging should be able to update shipping: {response.text}"
        print(f"Packaging role updated shipping method for order {target_order['order_number']}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_customers(self, admin_token):
        """Remove test customers created during tests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/customers", headers=headers)
        if response.status_code == 200:
            customers = response.json()
            for customer in customers:
                if customer.get("name", "").startswith("TEST_Phase16"):
                    requests.delete(f"{BASE_URL}/api/customers/{customer['id']}", headers=headers)
                    print(f"Deleted test customer: {customer['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
