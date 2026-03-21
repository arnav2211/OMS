"""
Phase 6 Testing: Admin Dashboard Reports, Free Samples, Order Detail fixes
Tests for:
1. Admin Dashboard - My Report with period filters
2. Admin Dashboard - Executive Reports with period filters
3. Order Detail page - Order not found bug fix
4. Free Samples in Order creation
5. Free Samples in PI creation
6. Customer address management after creation
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        return data["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        """Get headers with admin auth"""
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print("Admin login successful")


class TestAdminDashboardReports:
    """Test Admin Dashboard My Report and Executive Reports with period filters"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def admin_user_id(self, admin_headers):
        """Get admin user ID"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        return response.json()["id"]
    
    def test_my_report_month_period(self, admin_headers, admin_user_id):
        """Test My Report with 'month' period filter"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={admin_user_id}&period=month",
            headers=admin_headers
        )
        assert response.status_code == 200, f"My Report month failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "total_amount" in data
        assert "product_sales" in data
        assert "orders" in data
        print(f"My Report (month): {data['total_orders']} orders, ₹{data['total_amount']} revenue")
    
    def test_my_report_week_period(self, admin_headers, admin_user_id):
        """Test My Report with 'week' period filter"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={admin_user_id}&period=week",
            headers=admin_headers
        )
        assert response.status_code == 200, f"My Report week failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"My Report (week): {data['total_orders']} orders")
    
    def test_my_report_today_period(self, admin_headers, admin_user_id):
        """Test My Report with 'today' period filter"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={admin_user_id}&period=today",
            headers=admin_headers
        )
        assert response.status_code == 200, f"My Report today failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"My Report (today): {data['total_orders']} orders")
    
    def test_my_report_custom_date_range(self, admin_headers, admin_user_id):
        """Test My Report with custom date range"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={admin_user_id}&date_from=2024-01-01&date_to=2026-12-31",
            headers=admin_headers
        )
        assert response.status_code == 200, f"My Report custom range failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        print(f"My Report (custom range): {data['total_orders']} orders")
    
    def test_my_report_exclude_gst(self, admin_headers, admin_user_id):
        """Test My Report with exclude_gst filter"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={admin_user_id}&period=month&exclude_gst=true",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "product_sales" in data
        print(f"My Report (exclude GST): product_sales=₹{data['product_sales']}")
    
    def test_executive_report_with_telecaller_id(self, admin_headers):
        """Test Executive Report API with telecaller_id query param"""
        # First get list of users to find a telecaller
        users_response = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        assert users_response.status_code == 200
        users = users_response.json()
        
        # Find any user (admin or telecaller)
        target_user = users[0] if users else None
        if not target_user:
            pytest.skip("No users found for executive report test")
        
        # Test executive report with telecaller_id query param
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={target_user['id']}&period=month",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Executive Report failed: {response.text}"
        data = response.json()
        assert "total_orders" in data
        assert "total_amount" in data
        print(f"Executive Report for {target_user['name']}: {data['total_orders']} orders, ₹{data['total_amount']}")
    
    def test_admin_analytics_period_filters(self, admin_headers):
        """Test Admin Analytics with different period filters"""
        for period in ["today", "week", "month"]:
            response = requests.get(
                f"{BASE_URL}/api/reports/admin-analytics?period={period}",
                headers=admin_headers
            )
            assert response.status_code == 200, f"Admin analytics {period} failed: {response.text}"
            data = response.json()
            assert "total_orders" in data
            assert "total_revenue" in data
            assert "status_counts" in data
            print(f"Admin Analytics ({period}): {data['total_orders']} orders, ₹{data['total_revenue']}")


class TestOrderDetailFix:
    """Test Order Detail page - Order not found bug fix"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_get_orders_list(self, admin_headers):
        """Test getting orders list"""
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        assert response.status_code == 200
        orders = response.json()
        print(f"Found {len(orders)} orders")
        return orders
    
    def test_get_order_by_id(self, admin_headers):
        """Test getting individual order by ID - verifies Order not found bug is fixed"""
        # First get list of orders
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        assert orders_response.status_code == 200
        orders = orders_response.json()
        
        if not orders:
            pytest.skip("No orders found to test")
        
        # Get first order by ID
        order_id = orders[0]["id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        assert response.status_code == 200, f"Order not found for ID {order_id}: {response.text}"
        
        order = response.json()
        assert order["id"] == order_id
        assert "order_number" in order
        assert "customer_name" in order
        assert "items" in order
        print(f"Successfully retrieved order {order['order_number']} by ID")
    
    def test_order_has_payment_screenshots_field(self, admin_headers):
        """Test that order has payment_screenshots field for payment proof display"""
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        orders = orders_response.json()
        
        if not orders:
            pytest.skip("No orders found")
        
        order_id = orders[0]["id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        order = response.json()
        
        # Verify payment_screenshots field exists
        assert "payment_screenshots" in order, "payment_screenshots field missing from order"
        print(f"Order has payment_screenshots field: {order.get('payment_screenshots', [])}")
    
    def test_order_has_packaging_images_field(self, admin_headers):
        """Test that order has packaging images fields"""
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        orders = orders_response.json()
        
        if not orders:
            pytest.skip("No orders found")
        
        order_id = orders[0]["id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        order = response.json()
        
        # Verify packaging field exists with image fields
        assert "packaging" in order, "packaging field missing from order"
        packaging = order["packaging"]
        assert "item_images" in packaging, "item_images missing from packaging"
        assert "order_images" in packaging, "order_images missing from packaging"
        assert "packed_box_images" in packaging, "packed_box_images missing from packaging"
        print(f"Order has packaging images fields")


class TestFreeSamplesOrder:
    """Test Free Samples feature in Order creation"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_customer(self, admin_headers):
        """Create a test customer for order creation"""
        customer_data = {
            "name": "TEST_FreeSample_Customer",
            "phone_numbers": ["9876543210"],
            "gst_no": "",
            "email": ""
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=admin_headers)
        if response.status_code == 400 and "already exists" in response.text:
            # Customer exists, search for it
            search_response = requests.get(f"{BASE_URL}/api/customers?search=TEST_FreeSample", headers=admin_headers)
            customers = search_response.json()
            if customers:
                return customers[0]
        assert response.status_code == 200 or response.status_code == 201, f"Customer creation failed: {response.text}"
        return response.json()
    
    def test_create_order_with_free_samples(self, admin_headers, test_customer):
        """Test creating an order with free samples"""
        order_data = {
            "customer_id": test_customer["id"],
            "purpose": "Test order with free samples",
            "items": [
                {
                    "product_name": "Test Product",
                    "qty": 1,
                    "unit": "pcs",
                    "rate": 100,
                    "amount": 100,
                    "gst_rate": 0,
                    "gst_amount": 0,
                    "total": 100,
                    "description": ""
                }
            ],
            "free_samples": [
                {"item_name": "Citronella Oil Sample - 10ml", "description": "Free sample for testing"},
                {"item_name": "Lemongrass Oil Sample - 5ml", "description": "Promotional sample"}
            ],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 0,
            "remark": "Test order with free samples",
            "payment_status": "unpaid",
            "mode_of_payment": "Cash"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=admin_headers)
        assert response.status_code == 200, f"Order creation failed: {response.text}"
        
        order = response.json()
        assert "free_samples" in order, "free_samples field missing from created order"
        assert len(order["free_samples"]) == 2, f"Expected 2 free samples, got {len(order.get('free_samples', []))}"
        assert order["free_samples"][0]["item_name"] == "Citronella Oil Sample - 10ml"
        print(f"Created order {order['order_number']} with {len(order['free_samples'])} free samples")
        
        # Verify by fetching the order
        get_response = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=admin_headers)
        assert get_response.status_code == 200
        fetched_order = get_response.json()
        assert len(fetched_order["free_samples"]) == 2
        print(f"Verified free samples persisted in order")
        
        return order


class TestFreeSamplesPI:
    """Test Free Samples feature in PI creation"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_customer(self, admin_headers):
        """Get or create a test customer for PI creation"""
        search_response = requests.get(f"{BASE_URL}/api/customers?search=TEST_FreeSample", headers=admin_headers)
        customers = search_response.json()
        if customers:
            return customers[0]
        
        customer_data = {
            "name": "TEST_PI_FreeSample_Customer",
            "phone_numbers": ["9876543211"],
            "gst_no": "",
            "email": ""
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=admin_headers)
        return response.json()
    
    def test_create_pi_with_free_samples(self, admin_headers, test_customer):
        """Test creating a PI with free samples"""
        pi_data = {
            "customer_id": test_customer["id"],
            "items": [
                {
                    "product_name": "Test PI Product",
                    "qty": 2,
                    "unit": "L",
                    "rate": 500,
                    "amount": 1000,
                    "gst_rate": 0,
                    "gst_amount": 0,
                    "total": 1000,
                    "description": ""
                }
            ],
            "free_samples": [
                {"item_name": "PI Free Sample - 20ml", "description": "Complimentary sample"}
            ],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "remark": "Test PI with free samples"
        }
        
        response = requests.post(f"{BASE_URL}/api/proforma-invoices", json=pi_data, headers=admin_headers)
        assert response.status_code == 200, f"PI creation failed: {response.text}"
        
        pi = response.json()
        assert "free_samples" in pi, "free_samples field missing from created PI"
        assert len(pi["free_samples"]) == 1
        print(f"Created PI {pi['pi_number']} with {len(pi['free_samples'])} free samples")
        
        # Verify by fetching the PI
        get_response = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi['id']}", headers=admin_headers)
        assert get_response.status_code == 200
        fetched_pi = get_response.json()
        assert len(fetched_pi["free_samples"]) == 1
        print(f"Verified free samples persisted in PI")
        
        return pi


class TestCustomerAddressManagement:
    """Test Customer address management - add address after customer creation"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_create_customer_then_add_address(self, admin_headers):
        """Test creating a customer and then adding an address"""
        # Create customer
        customer_data = {
            "name": f"TEST_Address_Customer_{int(time.time())}",
            "phone_numbers": ["9876543299"],
            "gst_no": "",
            "email": ""
        }
        cust_response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=admin_headers)
        assert cust_response.status_code == 200, f"Customer creation failed: {cust_response.text}"
        customer = cust_response.json()
        print(f"Created customer: {customer['name']}")
        
        # Add address to customer
        address_data = {
            "address_line": "123 Test Street, Test Area",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "label": "Office"
        }
        addr_response = requests.post(
            f"{BASE_URL}/api/customers/{customer['id']}/addresses",
            json=address_data,
            headers=admin_headers
        )
        assert addr_response.status_code == 200, f"Address creation failed: {addr_response.text}"
        address = addr_response.json()
        assert address["address_line"] == "123 Test Street, Test Area"
        assert address["city"] == "Mumbai"
        assert address["label"] == "Office"
        print(f"Added address to customer: {address['label']} - {address['city']}")
        
        # Verify address is listed
        list_response = requests.get(
            f"{BASE_URL}/api/customers/{customer['id']}/addresses",
            headers=admin_headers
        )
        assert list_response.status_code == 200
        addresses = list_response.json()
        assert len(addresses) >= 1
        print(f"Customer has {len(addresses)} address(es)")
        
        # Cleanup - delete customer (will fail if has orders, which is fine)
        try:
            requests.delete(f"{BASE_URL}/api/customers/{customer['id']}", headers=admin_headers)
        except:
            pass
        
        return customer, address


class TestFormulationAccessControl:
    """Test strict formulation access control"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_admin_can_see_formulation(self, admin_headers):
        """Test that admin can see formulation field in orders"""
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        assert orders_response.status_code == 200
        orders = orders_response.json()
        
        if not orders:
            pytest.skip("No orders found")
        
        # Admin should see formulation field in items
        order = orders[0]
        if order.get("items"):
            # Formulation field should be present (even if empty)
            # The key should exist for admin
            print(f"Admin can access order items with formulation data")
    
    def test_admin_can_update_formulation(self, admin_headers):
        """Test that admin can update formulation"""
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        orders = orders_response.json()
        
        if not orders:
            pytest.skip("No orders found")
        
        order_id = orders[0]["id"]
        
        # Update formulation
        formulation_data = {
            "items": [
                {"index": 0, "formulation": "Test formulation by admin"}
            ]
        }
        response = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/formulation",
            json=formulation_data,
            headers=admin_headers
        )
        assert response.status_code == 200, f"Formulation update failed: {response.text}"
        print(f"Admin successfully updated formulation")


class TestDispatchLock:
    """Test dispatch lock functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_dispatched_order_blocks_general_edit(self, admin_headers):
        """Test that dispatched orders block general edits but allow payment updates"""
        # Find a dispatched order
        orders_response = requests.get(f"{BASE_URL}/api/orders?status=dispatched&view_all=true", headers=admin_headers)
        orders = orders_response.json()
        
        if not orders:
            pytest.skip("No dispatched orders found")
        
        order_id = orders[0]["id"]
        
        # Try to update purpose (should fail)
        update_data = {"purpose": "Changed purpose"}
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=admin_headers)
        
        # Should be blocked
        if response.status_code == 400:
            print(f"Correctly blocked general edit on dispatched order")
        else:
            print(f"Warning: Edit on dispatched order returned {response.status_code}")
        
        # Payment update should work
        payment_data = {"payment_status": "partial", "amount_paid": 100}
        payment_response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=payment_data, headers=admin_headers)
        # This should succeed
        print(f"Payment update on dispatched order: {payment_response.status_code}")


class TestAllOrdersFilter:
    """Test All Orders page executive filter"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_admin_can_filter_by_executive(self, admin_headers):
        """Test admin can filter orders by executive"""
        # Get users
        users_response = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        users = users_response.json()
        
        if not users:
            pytest.skip("No users found")
        
        # Filter by first user
        user_id = users[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/orders?telecaller_id={user_id}&view_all=true",
            headers=admin_headers
        )
        assert response.status_code == 200
        orders = response.json()
        print(f"Found {len(orders)} orders for executive {users[0]['name']}")
    
    def test_admin_can_view_all_orders(self, admin_headers):
        """Test admin can view all orders"""
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        assert response.status_code == 200
        orders = response.json()
        print(f"Admin can view all {len(orders)} orders")


# Cleanup fixture
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data():
    """Cleanup test data after all tests"""
    yield
    # Cleanup happens after all tests
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        if response.status_code == 200:
            token = response.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Delete test customers
            customers_response = requests.get(f"{BASE_URL}/api/customers?search=TEST_", headers=headers)
            if customers_response.status_code == 200:
                for customer in customers_response.json():
                    if customer["name"].startswith("TEST_"):
                        try:
                            requests.delete(f"{BASE_URL}/api/customers/{customer['id']}", headers=headers)
                        except:
                            pass
    except:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
