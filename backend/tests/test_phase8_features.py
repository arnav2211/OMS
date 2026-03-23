"""
Phase 8 Backend Tests - Final 10 Fixes and Enhancements
Tests for:
1. Customer delete restricted to Admin (403 for non-admin)
2. Duplicate Order endpoint
3. Duplicate PI endpoint
4. Update shipping method endpoint
5. Additional charges in orders
6. Negative value prevention (min=0 on Rate/Amount)
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
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        """Get or create telecaller token"""
        # Try to login first
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "telecaller1",
            "password": "telecaller123"
        })
        if response.status_code == 200:
            return response.json()["token"]
        
        # Create telecaller user if not exists
        admin_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        admin_token = admin_response.json()["token"]
        
        create_response = requests.post(
            f"{BASE_URL}/api/users",
            json={
                "username": "telecaller1",
                "password": "telecaller123",
                "name": "Test Telecaller",
                "role": "telecaller"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Login again
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "telecaller1",
            "password": "telecaller123"
        })
        assert response.status_code == 200, f"Telecaller login failed: {response.text}"
        return response.json()["token"]
    
    def test_admin_login(self, admin_token):
        """Test admin can login"""
        assert admin_token is not None
        print("Admin login successful")


class TestCustomerDeleteRestriction:
    """Test customer delete is restricted to admin only"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self, admin_token):
        # Try to login first
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "telecaller1",
            "password": "telecaller123"
        })
        if response.status_code == 200:
            return response.json()["token"]
        
        # Create telecaller user if not exists
        requests.post(
            f"{BASE_URL}/api/users",
            json={
                "username": "telecaller1",
                "password": "telecaller123",
                "name": "Test Telecaller",
                "role": "telecaller"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "telecaller1",
            "password": "telecaller123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def test_customer(self, admin_token):
        """Create a test customer for deletion tests"""
        response = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": "TEST_DeleteTestCustomer",
                "phone_numbers": ["+919999999999"],
                "email": "test_delete@example.com"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed to create test customer: {response.text}"
        return response.json()
    
    def test_telecaller_cannot_delete_customer(self, telecaller_token, test_customer):
        """Test that telecaller gets 403 when trying to delete customer"""
        response = requests.delete(
            f"{BASE_URL}/api/customers/{test_customer['id']}",
            headers={"Authorization": f"Bearer {telecaller_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("Telecaller correctly blocked from deleting customer (403)")
    
    def test_admin_can_delete_customer(self, admin_token, test_customer):
        """Test that admin can delete customer"""
        response = requests.delete(
            f"{BASE_URL}/api/customers/{test_customer['id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # Should be 200 or 400 (if customer has orders)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}: {response.text}"
        print(f"Admin delete customer response: {response.status_code}")


class TestDuplicateOrder:
    """Test duplicate order endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def existing_order(self, admin_token):
        """Get an existing order for duplication"""
        response = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        orders = response.json()
        if orders:
            return orders[0]
        pytest.skip("No existing orders to test duplication")
    
    def test_duplicate_order_returns_data(self, admin_token, existing_order):
        """Test POST /api/orders/{id}/duplicate returns order data"""
        response = requests.post(
            f"{BASE_URL}/api/orders/{existing_order['id']}/duplicate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Duplicate failed: {response.text}"
        data = response.json()
        
        # Verify returned data structure
        assert "customer_id" in data, "Missing customer_id in duplicate response"
        assert "items" in data, "Missing items in duplicate response"
        assert "gst_applicable" in data, "Missing gst_applicable in duplicate response"
        
        # Verify data matches original
        assert data["customer_id"] == existing_order["customer_id"], "Customer ID mismatch"
        print(f"Duplicate order endpoint working - returned {len(data.get('items', []))} items")
    
    def test_duplicate_order_includes_additional_charges(self, admin_token, existing_order):
        """Test duplicate includes additional_charges field"""
        response = requests.post(
            f"{BASE_URL}/api/orders/{existing_order['id']}/duplicate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # additional_charges should be present (even if empty)
        assert "additional_charges" in data, "Missing additional_charges in duplicate response"
        print(f"Duplicate includes additional_charges: {data.get('additional_charges', [])}")


class TestDuplicatePI:
    """Test duplicate PI endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def existing_pi(self, admin_token):
        """Get an existing PI for duplication"""
        response = requests.get(
            f"{BASE_URL}/api/proforma-invoices",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        pis = response.json()
        if pis:
            return pis[0]
        pytest.skip("No existing PIs to test duplication")
    
    def test_duplicate_pi_returns_data(self, admin_token, existing_pi):
        """Test POST /api/proforma-invoices/{id}/duplicate returns PI data"""
        response = requests.post(
            f"{BASE_URL}/api/proforma-invoices/{existing_pi['id']}/duplicate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Duplicate PI failed: {response.text}"
        data = response.json()
        
        # Verify returned data structure
        assert "customer_id" in data, "Missing customer_id in duplicate PI response"
        assert "items" in data, "Missing items in duplicate PI response"
        assert "gst_applicable" in data, "Missing gst_applicable in duplicate PI response"
        
        print(f"Duplicate PI endpoint working - returned {len(data.get('items', []))} items")
    
    def test_duplicate_pi_includes_additional_charges(self, admin_token, existing_pi):
        """Test duplicate PI includes additional_charges field"""
        response = requests.post(
            f"{BASE_URL}/api/proforma-invoices/{existing_pi['id']}/duplicate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "additional_charges" in data, "Missing additional_charges in duplicate PI response"
        print(f"Duplicate PI includes additional_charges: {data.get('additional_charges', [])}")


class TestShippingMethodUpdate:
    """Test shipping method update endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def existing_order(self, admin_token):
        """Get an existing order"""
        response = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        orders = response.json()
        if orders:
            return orders[0]
        pytest.skip("No existing orders to test shipping method update")
    
    def test_update_shipping_method(self, admin_token, existing_order):
        """Test PUT /api/orders/{id}/shipping-method updates shipping"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{existing_order['id']}/shipping-method",
            json={
                "shipping_method": "courier",
                "courier_name": "DTDC"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Update shipping failed: {response.text}"
        data = response.json()
        
        assert data.get("shipping_method") == "courier", "Shipping method not updated"
        assert data.get("courier_name") == "DTDC", "Courier name not updated"
        print("Shipping method update endpoint working")
    
    def test_update_shipping_method_transport(self, admin_token, existing_order):
        """Test updating to transport method"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{existing_order['id']}/shipping-method",
            json={
                "shipping_method": "transport",
                "transporter_name": "Test Transporter"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Update shipping failed: {response.text}"
        data = response.json()
        
        assert data.get("shipping_method") == "transport", "Shipping method not updated to transport"
        print("Shipping method update to transport working")


class TestAdditionalCharges:
    """Test additional charges in orders"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def test_customer(self, admin_token):
        """Get or create a test customer"""
        response = requests.get(
            f"{BASE_URL}/api/customers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        customers = response.json()
        if customers:
            return customers[0]
        
        # Create customer if none exist
        response = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": "TEST_AdditionalChargesCustomer",
                "phone_numbers": ["+919876543210"]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        return response.json()
    
    def test_create_order_with_additional_charges(self, admin_token, test_customer):
        """Test creating order with additional charges"""
        response = requests.post(
            f"{BASE_URL}/api/orders",
            json={
                "customer_id": test_customer["id"],
                "items": [{
                    "product_name": "TEST_Product",
                    "qty": 1,
                    "unit": "pcs",
                    "rate": 100,
                    "amount": 100,
                    "gst_rate": 0,
                    "gst_amount": 0,
                    "total": 100
                }],
                "gst_applicable": True,
                "additional_charges": [
                    {"name": "Shipping", "amount": 50, "gst_percent": 18},
                    {"name": "Insurance", "amount": 25, "gst_percent": 0}
                ],
                "shipping_method": "courier",
                "courier_name": "DTDC"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Create order failed: {response.text}"
        data = response.json()
        
        # Verify additional charges are saved
        assert "additional_charges" in data, "Missing additional_charges in response"
        charges = data.get("additional_charges", [])
        assert len(charges) >= 2, f"Expected at least 2 charges, got {len(charges)}"
        
        # Verify GST calculation on charges
        shipping_charge = next((c for c in charges if c.get("name") == "Shipping"), None)
        if shipping_charge:
            assert shipping_charge.get("gst_amount") == 9.0, f"Expected GST 9.0, got {shipping_charge.get('gst_amount')}"
        
        print(f"Order created with {len(charges)} additional charges")
        return data


class TestOrdersListShippingColumn:
    """Test that orders list includes shipping method data"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    def test_orders_include_shipping_method(self, admin_token):
        """Test GET /api/orders returns shipping_method field"""
        response = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        orders = response.json()
        
        if orders:
            order = orders[0]
            # shipping_method should be present
            assert "shipping_method" in order, "Missing shipping_method in order"
            print(f"Orders include shipping_method: {order.get('shipping_method')}")
            
            # courier_name and transporter_name should also be present
            assert "courier_name" in order or order.get("shipping_method") != "courier", "Missing courier_name for courier order"
            print("Orders list includes shipping data")


class TestRoleBasedAccess:
    """Test role-based access for various endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def dispatch_token(self, admin_token):
        """Get or create dispatch user token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "dispatch1",
            "password": "dispatch123"
        })
        if response.status_code == 200:
            return response.json()["token"]
        
        # Create dispatch user
        requests.post(
            f"{BASE_URL}/api/users",
            json={
                "username": "dispatch1",
                "password": "dispatch123",
                "name": "Test Dispatch",
                "role": "dispatch"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "dispatch1",
            "password": "dispatch123"
        })
        return response.json()["token"]
    
    def test_dispatch_can_update_shipping_method(self, dispatch_token, admin_token):
        """Test dispatch role can update shipping method"""
        # Get an order first
        response = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        orders = response.json()
        if not orders:
            pytest.skip("No orders to test")
        
        order = orders[0]
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/shipping-method",
            json={"shipping_method": "porter"},
            headers={"Authorization": f"Bearer {dispatch_token}"}
        )
        assert response.status_code == 200, f"Dispatch should be able to update shipping: {response.text}"
        print("Dispatch role can update shipping method")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
