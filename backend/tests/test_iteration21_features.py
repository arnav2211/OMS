"""
Test iteration 21 features:
1. Backend: Packaging status auto-transition (new -> packaging when packaging data saved without explicit status)
2. Backend: Verify packaging endpoint still works correctly with explicit status='packed'
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPackagingStatusAutoTransition:
    """Test the packaging status auto-transition bug fix"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as admin and create test order"""
        # Login as admin
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.admin_token = login_resp.json()["token"]
        self.admin_headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json"
        }
        
        # Login as packaging user
        pkg_login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_packaging_user",
            "password": "test123"
        })
        assert pkg_login.status_code == 200, f"Packaging login failed: {pkg_login.text}"
        self.pkg_token = pkg_login.json()["token"]
        self.pkg_headers = {
            "Authorization": f"Bearer {self.pkg_token}",
            "Content-Type": "application/json"
        }
        
        # Get or create a test customer
        customers_resp = requests.get(f"{BASE_URL}/api/customers?search=TEST_ITER21", headers=self.admin_headers)
        customers = customers_resp.json()
        
        if customers:
            self.customer_id = customers[0]["id"]
        else:
            # Create test customer
            cust_resp = requests.post(f"{BASE_URL}/api/customers", headers=self.admin_headers, json={
                "name": "TEST_ITER21_Customer",
                "phone_numbers": [f"+91{9000000000 + uuid.uuid4().int % 1000000}"],
                "email": "test_iter21@example.com"
            })
            assert cust_resp.status_code == 200, f"Customer creation failed: {cust_resp.text}"
            self.customer_id = cust_resp.json()["id"]
        
        yield
        
        # Cleanup: Delete test orders created during tests
        # (Orders will be cleaned up by individual tests or left for inspection)
    
    def create_test_order(self, suffix=""):
        """Helper to create a test order with status 'new'"""
        order_resp = requests.post(f"{BASE_URL}/api/orders", headers=self.admin_headers, json={
            "customer_id": self.customer_id,
            "purpose": f"TEST_ITER21_Order_{suffix}",
            "items": [{
                "product_name": f"Test Product {suffix}",
                "qty": 1,
                "unit": "pc",
                "rate": 100,
                "amount": 100,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 100
            }],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC"
        })
        assert order_resp.status_code == 200, f"Order creation failed: {order_resp.text}"
        order = order_resp.json()
        assert order["status"] == "new", f"Expected status 'new', got '{order['status']}'"
        return order
    
    def test_packaging_auto_transition_new_to_packaging(self):
        """
        Test: When packaging data is saved on a 'new' order WITHOUT explicit status field,
        the order status should auto-transition from 'new' to 'packaging'
        """
        # Create a new order
        order = self.create_test_order("auto_transition")
        order_id = order["id"]
        
        # Verify initial status is 'new'
        assert order["status"] == "new"
        
        # Update packaging WITHOUT status field (simulating Order Details page save)
        pkg_update = {
            "item_images": {"Test Product auto_transition": ["http://example.com/img1.jpg"]},
            "order_images": ["http://example.com/order1.jpg"]
        }
        
        pkg_resp = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json=pkg_update
        )
        assert pkg_resp.status_code == 200, f"Packaging update failed: {pkg_resp.text}"
        
        updated_order = pkg_resp.json()
        
        # CRITICAL: Status should auto-transition to 'packaging'
        assert updated_order["status"] == "packaging", \
            f"Expected status 'packaging' after auto-transition, got '{updated_order['status']}'"
        
        # Verify packaging data was saved
        assert updated_order["packaging"]["item_images"] == pkg_update["item_images"]
        assert updated_order["packaging"]["order_images"] == pkg_update["order_images"]
        
        print(f"✓ Order {order['order_number']} auto-transitioned from 'new' to 'packaging'")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{order_id}", headers=self.admin_headers)
    
    def test_packaging_explicit_status_packed(self):
        """
        Test: When packaging data is saved WITH explicit status='packed',
        it should work as before (require mandatory fields)
        """
        # Create a new order
        order = self.create_test_order("explicit_packed")
        order_id = order["id"]
        
        # First transition to packaging
        requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json={"order_images": ["http://example.com/img.jpg"]}
        )
        
        # Try to mark as packed WITHOUT mandatory fields - should fail
        pkg_update_fail = {
            "status": "packed"
        }
        
        fail_resp = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json=pkg_update_fail
        )
        assert fail_resp.status_code == 400, \
            f"Expected 400 for missing mandatory fields, got {fail_resp.status_code}"
        
        # Now provide all mandatory fields
        pkg_update_success = {
            "status": "packed",
            "item_packed_by": ["Yogita"],
            "box_packed_by": ["Sapna"],
            "checked_by": ["Samiksha"]
        }
        
        success_resp = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json=pkg_update_success
        )
        assert success_resp.status_code == 200, f"Packed update failed: {success_resp.text}"
        
        packed_order = success_resp.json()
        assert packed_order["status"] == "packed", \
            f"Expected status 'packed', got '{packed_order['status']}'"
        
        print(f"✓ Order {order['order_number']} correctly marked as 'packed' with mandatory fields")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{order_id}", headers=self.admin_headers)
    
    def test_packaging_already_packaging_stays_packaging(self):
        """
        Test: When packaging data is saved on an order already in 'packaging' status,
        it should stay 'packaging' (not revert to 'new')
        """
        # Create a new order
        order = self.create_test_order("stay_packaging")
        order_id = order["id"]
        
        # First update to transition to 'packaging'
        first_update = {"order_images": ["http://example.com/first.jpg"]}
        resp1 = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json=first_update
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "packaging"
        
        # Second update - should stay 'packaging'
        second_update = {"packed_box_images": ["http://example.com/box.jpg"]}
        resp2 = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json=second_update
        )
        assert resp2.status_code == 200
        
        final_order = resp2.json()
        assert final_order["status"] == "packaging", \
            f"Expected status to stay 'packaging', got '{final_order['status']}'"
        
        print(f"✓ Order {order['order_number']} correctly stayed in 'packaging' status")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{order_id}", headers=self.admin_headers)
    
    def test_packaging_with_explicit_status_new(self):
        """
        Test: If someone explicitly passes status='new' in the update,
        the auto-transition should NOT happen (respect explicit status)
        """
        # Create a new order
        order = self.create_test_order("explicit_new")
        order_id = order["id"]
        
        # Update with explicit status='new' - should NOT auto-transition
        # Note: The backend logic is: if new_status == "new" and "status" not in updates
        # So if status IS in updates, it won't auto-transition
        pkg_update = {
            "status": "new",  # Explicitly keeping it new
            "order_images": ["http://example.com/img.jpg"]
        }
        
        resp = requests.put(
            f"{BASE_URL}/api/orders/{order_id}/packaging",
            headers=self.pkg_headers,
            json=pkg_update
        )
        assert resp.status_code == 200
        
        # Status should remain 'new' because it was explicitly set
        updated_order = resp.json()
        assert updated_order["status"] == "new", \
            f"Expected status 'new' (explicit), got '{updated_order['status']}'"
        
        print(f"✓ Order {order['order_number']} correctly stayed 'new' with explicit status")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/orders/{order_id}", headers=self.admin_headers)


class TestAuthEndpoints:
    """Test authentication for different roles"""
    
    def test_admin_login(self):
        """Test admin login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "admin"
        print("✓ Admin login successful")
    
    def test_packaging_user_login(self):
        """Test packaging user login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_packaging_user",
            "password": "test123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "packaging"
        print("✓ Packaging user login successful")
    
    def test_telecaller_login(self):
        """Test telecaller login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_tc_payment",
            "password": "test123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "telecaller"
        print("✓ Telecaller login successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
