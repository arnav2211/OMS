"""
Test Phase 15 Features:
1. Extra shipping details in order creation
2. Free sample formulation support
3. Order detail GST number display
4. Invoice column in All Orders
5. GST column for accounts role
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def test_customer(auth_headers):
    """Create a test customer for order tests"""
    import random
    unique_phone = f"98765{random.randint(10000, 99999)}"
    customer_data = {
        "name": f"TEST_Phase15_Customer_{random.randint(1000, 9999)}",
        "gst_no": "",  # No GST to avoid duplicate GST error
        "phone_numbers": [unique_phone],
        "email": f"test{random.randint(1000, 9999)}@phase15.com"
    }
    
    response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=auth_headers)
    assert response.status_code in [200, 201], f"Customer creation failed: {response.text}"
    return response.json()

@pytest.fixture(scope="module")
def test_address(auth_headers, test_customer):
    """Create a test address for the customer"""
    address_data = {
        "address_line": "123 Test Street",
        "city": "Nagpur",
        "state": "Maharashtra",
        "pincode": "440001",
        "label": "Office"
    }
    # Check existing addresses
    response = requests.get(f"{BASE_URL}/api/customers/{test_customer['id']}/addresses", headers=auth_headers)
    if response.status_code == 200 and response.json():
        return response.json()[0]
    
    response = requests.post(f"{BASE_URL}/api/customers/{test_customer['id']}/addresses", json=address_data, headers=auth_headers)
    assert response.status_code in [200, 201], f"Address creation failed: {response.text}"
    return response.json()


class TestExtraShippingDetails:
    """Test extra_shipping_details field in order creation and retrieval"""
    
    def test_create_order_with_extra_shipping_details(self, auth_headers, test_customer, test_address):
        """Test creating an order with extra_shipping_details"""
        order_data = {
            "customer_id": test_customer["id"],
            "purpose": "Test extra shipping details",
            "items": [{
                "product_name": "Test Product",
                "qty": 1,
                "unit": "pcs",
                "rate": 100,
                "amount": 100,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 100
            }],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 50,
            "extra_shipping_details": "Driver contact: 9876543210, Landmark: Near City Mall",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "unpaid"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert response.status_code in [200, 201], f"Order creation failed: {response.text}"
        
        order = response.json()
        assert "extra_shipping_details" in order, "extra_shipping_details not in response"
        assert order["extra_shipping_details"] == "Driver contact: 9876543210, Landmark: Near City Mall"
        
        # Verify by fetching the order
        get_response = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=auth_headers)
        assert get_response.status_code == 200
        fetched_order = get_response.json()
        assert fetched_order["extra_shipping_details"] == "Driver contact: 9876543210, Landmark: Near City Mall"
        
        return order
    
    def test_update_order_extra_shipping_details(self, auth_headers, test_customer, test_address):
        """Test updating extra_shipping_details on an existing order"""
        # First create an order
        order_data = {
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Update Test", "qty": 1, "unit": "pcs", "rate": 50, "amount": 50, "total": 50}],
            "gst_applicable": False,
            "shipping_method": "transport",
            "extra_shipping_details": "Initial details",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "unpaid"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert create_response.status_code in [200, 201]
        order = create_response.json()
        
        # Update the order
        update_data = {
            "extra_shipping_details": "Updated: Driver name - Ramesh, Contact: 9999999999"
        }
        update_response = requests.put(f"{BASE_URL}/api/orders/{order['id']}", json=update_data, headers=auth_headers)
        assert update_response.status_code == 200
        
        updated_order = update_response.json()
        assert updated_order["extra_shipping_details"] == "Updated: Driver name - Ramesh, Contact: 9999999999"


class TestFreeSampleFormulation:
    """Test formulation support for free samples"""
    
    def test_create_order_with_free_samples(self, auth_headers, test_customer, test_address):
        """Test creating an order with free samples"""
        order_data = {
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Main Product", "qty": 5, "unit": "L", "rate": 500, "amount": 2500, "total": 2500}],
            "free_samples": [
                {"item_name": "Sample A - 10ml", "description": "Citronella Oil Sample"},
                {"item_name": "Sample B - 5ml", "description": "Lemongrass Oil Sample"}
            ],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "unpaid"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert response.status_code in [200, 201], f"Order creation failed: {response.text}"
        
        order = response.json()
        assert "free_samples" in order
        assert len(order["free_samples"]) == 2
        assert order["free_samples"][0]["item_name"] == "Sample A - 10ml"
        
        return order
    
    def test_update_free_sample_formulation(self, auth_headers, test_customer, test_address):
        """Test updating formulation for free samples"""
        # Create order with free samples
        order_data = {
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Product X", "qty": 2, "unit": "Kg", "rate": 1000, "amount": 2000, "total": 2000}],
            "free_samples": [
                {"item_name": "Free Sample 1", "description": "Test sample", "formulation": ""},
                {"item_name": "Free Sample 2", "description": "Another sample", "formulation": ""}
            ],
            "gst_applicable": False,
            "shipping_method": "transport",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "unpaid"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert create_response.status_code in [200, 201]
        order = create_response.json()
        
        # Update formulation for items and free samples
        formulation_data = {
            "items": [
                {"index": 0, "formulation": "Main product formulation: 50% base, 50% active"},
                {"is_free_sample": True, "fs_index": 0, "formulation": "Free sample 1 formulation: Pure extract"},
                {"is_free_sample": True, "fs_index": 1, "formulation": "Free sample 2 formulation: Diluted 10%"}
            ]
        }
        
        update_response = requests.put(f"{BASE_URL}/api/orders/{order['id']}/formulation", json=formulation_data, headers=auth_headers)
        assert update_response.status_code == 200, f"Formulation update failed: {update_response.text}"
        
        updated_order = update_response.json()
        
        # Verify item formulation
        assert updated_order["items"][0]["formulation"] == "Main product formulation: 50% base, 50% active"
        
        # Verify free sample formulations
        assert len(updated_order["free_samples"]) == 2
        assert updated_order["free_samples"][0]["formulation"] == "Free sample 1 formulation: Pure extract"
        assert updated_order["free_samples"][1]["formulation"] == "Free sample 2 formulation: Diluted 10%"


class TestOrderGSTFields:
    """Test GST-related fields in orders"""
    
    def test_gst_applicable_order(self, auth_headers, test_customer, test_address):
        """Test creating a GST applicable order"""
        order_data = {
            "customer_id": test_customer["id"],
            "items": [{
                "product_name": "GST Product",
                "qty": 10,
                "unit": "L",
                "rate": 100,
                "amount": 1000,
                "gst_rate": 18,
                "gst_amount": 180,
                "total": 1180
            }],
            "gst_applicable": True,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 100,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "full"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert response.status_code in [200, 201]
        
        order = response.json()
        assert order["gst_applicable"] == True
        assert order["items"][0]["gst_rate"] == 18
        assert order["items"][0]["gst_amount"] == 180
        
        return order
    
    def test_non_gst_order(self, auth_headers, test_customer, test_address):
        """Test creating a non-GST order"""
        order_data = {
            "customer_id": test_customer["id"],
            "items": [{
                "product_name": "Non-GST Product",
                "qty": 5,
                "unit": "Kg",
                "rate": 200,
                "amount": 1000,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 1000
            }],
            "gst_applicable": False,
            "shipping_method": "transport",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "unpaid"
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert response.status_code in [200, 201]
        
        order = response.json()
        assert order["gst_applicable"] == False
        
        return order


class TestCustomerGSTNumber:
    """Test customer GST number retrieval"""
    
    def test_customer_gst_field_exists(self, auth_headers, test_customer):
        """Verify customer has gst_no field"""
        response = requests.get(f"{BASE_URL}/api/customers/{test_customer['id']}", headers=auth_headers)
        assert response.status_code == 200
        
        customer = response.json()
        assert "gst_no" in customer, "gst_no field missing from customer"
    
    def test_update_customer_gst(self, auth_headers, test_customer):
        """Test updating customer GST number"""
        import random
        # Generate a unique GST number for testing
        test_gst = f"27AABCU{random.randint(1000, 9999)}R1ZM"
        
        update_data = {
            "name": test_customer["name"],
            "gst_no": test_gst,
            "phone_numbers": test_customer["phone_numbers"],
            "email": test_customer.get("email", "")
        }
        
        response = requests.put(f"{BASE_URL}/api/customers/{test_customer['id']}", json=update_data, headers=auth_headers)
        assert response.status_code == 200
        
        updated = response.json()
        assert updated["gst_no"] == test_gst


class TestOrderListFields:
    """Test order list returns required fields for All Orders page"""
    
    def test_orders_list_has_gst_applicable(self, auth_headers):
        """Verify orders list includes gst_applicable field"""
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=auth_headers)
        assert response.status_code == 200
        
        orders = response.json()
        if orders:
            order = orders[0]
            assert "gst_applicable" in order, "gst_applicable field missing from order list"
    
    def test_orders_list_has_tax_invoice_url(self, auth_headers):
        """Verify orders list includes tax_invoice_url field"""
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=auth_headers)
        assert response.status_code == 200
        
        orders = response.json()
        if orders:
            order = orders[0]
            assert "tax_invoice_url" in order, "tax_invoice_url field missing from order list"


class TestInvoiceUpload:
    """Test invoice upload functionality"""
    
    def test_invoice_upload_requires_gst_order(self, auth_headers, test_customer, test_address):
        """Test that invoice upload only works for GST orders"""
        # Create non-GST order
        order_data = {
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Non-GST Item", "qty": 1, "unit": "pcs", "rate": 100, "amount": 100, "total": 100}],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"],
            "payment_status": "unpaid"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=auth_headers)
        assert create_response.status_code in [200, 201]
        order = create_response.json()
        
        # Try to set invoice URL on non-GST order
        invoice_response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/invoice",
            json={"invoice_url": "/api/uploads/test.pdf"},
            headers=auth_headers
        )
        assert invoice_response.status_code == 400
        assert "GST" in invoice_response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
