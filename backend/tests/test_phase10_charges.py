"""
Phase 10 Tests: Charges UI restructure and image compression verification
Tests the new 3-section charges layout (Shipping, Local, Additional)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestChargesStructure:
    """Test the new charges structure in orders and PIs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get a customer for testing
        customers_response = self.session.get(f"{BASE_URL}/api/customers")
        assert customers_response.status_code == 200
        customers = customers_response.json()
        assert len(customers) > 0, "No customers found for testing"
        self.customer_id = customers[0]["id"]
        
        yield
        
        # Cleanup - no specific cleanup needed
    
    def test_create_order_with_shipping_and_local_charges(self):
        """Test 7: Create order with shipping_charge=100 and local charge as additional_charge entry"""
        # Create order with shipping charge and local charge
        order_payload = {
            "customer_id": self.customer_id,
            "purpose": "TEST_Phase10_Charges",
            "items": [{
                "product_name": "TEST_Product_Charges",
                "qty": 1,
                "unit": "pcs",
                "rate": 500,
                "amount": 500,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 500,
                "description": "Test product for charges verification"
            }],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 100,  # Separate shipping charge
            "additional_charges": [
                {
                    "name": "Local Charges",  # Local charge stored as additional_charge
                    "amount": 50,
                    "gst_percent": 0,
                    "gst_amount": 0
                },
                {
                    "name": "Insurance",  # Additional charge
                    "amount": 25,
                    "gst_percent": 0,
                    "gst_amount": 0
                }
            ],
            "remark": "Test order for Phase 10 charges verification",
            "payment_status": "unpaid",
            "amount_paid": 0,
            "free_samples": [],
            "billing_address_id": "",
            "shipping_address_id": ""
        }
        
        response = self.session.post(f"{BASE_URL}/api/orders", json=order_payload)
        assert response.status_code in [200, 201], f"Order creation failed: {response.text}"
        
        order = response.json()
        order_id = order["id"]
        
        # Verify shipping_charge is stored correctly
        assert order.get("shipping_charge") == 100, f"Shipping charge mismatch: expected 100, got {order.get('shipping_charge')}"
        
        # Verify additional_charges contains Local Charges
        additional_charges = order.get("additional_charges", [])
        local_charge = next((c for c in additional_charges if c.get("name") == "Local Charges"), None)
        assert local_charge is not None, "Local Charges not found in additional_charges"
        assert local_charge.get("amount") == 50, f"Local charge amount mismatch: expected 50, got {local_charge.get('amount')}"
        
        # Verify Insurance charge is also present
        insurance_charge = next((c for c in additional_charges if c.get("name") == "Insurance"), None)
        assert insurance_charge is not None, "Insurance charge not found in additional_charges"
        assert insurance_charge.get("amount") == 25, f"Insurance amount mismatch: expected 25, got {insurance_charge.get('amount')}"
        
        # Verify grand total calculation: 500 (item) + 100 (shipping) + 50 (local) + 25 (insurance) = 675
        expected_total = 675
        assert order.get("grand_total") == expected_total, f"Grand total mismatch: expected {expected_total}, got {order.get('grand_total')}"
        
        print(f"TEST PASS: Order {order.get('order_number')} created with correct charges structure")
        
        # Cleanup - delete the test order
        # Note: Orders typically can't be deleted, so we'll leave it
        
    def test_get_order_returns_correct_charges_structure(self):
        """Verify GET order returns shipping_charge and additional_charges correctly"""
        # First create an order
        order_payload = {
            "customer_id": self.customer_id,
            "purpose": "TEST_Phase10_GET_Charges",
            "items": [{
                "product_name": "TEST_Product_GET",
                "qty": 2,
                "unit": "Kg",
                "rate": 200,
                "amount": 400,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 400,
                "description": ""
            }],
            "gst_applicable": False,
            "shipping_method": "transport",
            "transporter_name": "Test Transport",
            "shipping_charge": 150,
            "additional_charges": [
                {"name": "Local Charges", "amount": 75, "gst_percent": 0, "gst_amount": 0},
                {"name": "Handling", "amount": 30, "gst_percent": 0, "gst_amount": 0}
            ],
            "remark": "",
            "payment_status": "unpaid",
            "amount_paid": 0,
            "free_samples": [],
            "billing_address_id": "",
            "shipping_address_id": ""
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/orders", json=order_payload)
        assert create_response.status_code in [200, 201]
        order_id = create_response.json()["id"]
        
        # GET the order
        get_response = self.session.get(f"{BASE_URL}/api/orders/{order_id}")
        assert get_response.status_code == 200
        
        order = get_response.json()
        
        # Verify structure
        assert "shipping_charge" in order, "shipping_charge field missing from order"
        assert "additional_charges" in order, "additional_charges field missing from order"
        assert order["shipping_charge"] == 150
        
        # Verify Local Charges is in additional_charges
        local = next((c for c in order["additional_charges"] if c["name"] == "Local Charges"), None)
        assert local is not None, "Local Charges not in additional_charges"
        assert local["amount"] == 75
        
        print(f"TEST PASS: GET order returns correct charges structure")
    
    def test_update_order_charges(self):
        """Test updating order charges"""
        # Create order first
        order_payload = {
            "customer_id": self.customer_id,
            "purpose": "TEST_Phase10_Update",
            "items": [{
                "product_name": "TEST_Product_Update",
                "qty": 1,
                "unit": "pcs",
                "rate": 300,
                "amount": 300,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 300,
                "description": ""
            }],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 50,
            "additional_charges": [
                {"name": "Local Charges", "amount": 25, "gst_percent": 0, "gst_amount": 0}
            ],
            "remark": "",
            "payment_status": "unpaid",
            "amount_paid": 0,
            "free_samples": [],
            "billing_address_id": "",
            "shipping_address_id": ""
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/orders", json=order_payload)
        assert create_response.status_code in [200, 201]
        order = create_response.json()
        order_id = order["id"]
        
        # Update the order with new charges
        update_payload = {
            "purpose": "TEST_Phase10_Update_Modified",
            "items": [{
                "product_name": "TEST_Product_Update",
                "qty": 1,
                "unit": "pcs",
                "rate": 300,
                "amount": 300,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 300,
                "description": ""
            }],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 200,  # Updated shipping
            "shipping_gst": 0,
            "additional_charges": [
                {"name": "Local Charges", "amount": 100, "gst_percent": 0, "gst_amount": 0},  # Updated local
                {"name": "Packing", "amount": 50, "gst_percent": 0, "gst_amount": 0}  # New charge
            ],
            "subtotal": 300,
            "total_gst": 0,
            "grand_total": 650,  # 300 + 200 + 100 + 50
            "remark": "",
            "payment_status": "unpaid",
            "amount_paid": 0,
            "balance_amount": 650,
            "free_samples": [],
            "payment_screenshots": [],
            "billing_address_id": "",
            "shipping_address_id": ""
        }
        
        update_response = self.session.put(f"{BASE_URL}/api/orders/{order_id}", json=update_payload)
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify updated values
        get_response = self.session.get(f"{BASE_URL}/api/orders/{order_id}")
        assert get_response.status_code == 200
        updated_order = get_response.json()
        
        assert updated_order["shipping_charge"] == 200, f"Shipping charge not updated: {updated_order['shipping_charge']}"
        
        local = next((c for c in updated_order["additional_charges"] if c["name"] == "Local Charges"), None)
        assert local is not None and local["amount"] == 100, "Local charge not updated correctly"
        
        packing = next((c for c in updated_order["additional_charges"] if c["name"] == "Packing"), None)
        assert packing is not None and packing["amount"] == 50, "Packing charge not added"
        
        print(f"TEST PASS: Order charges updated correctly")


class TestPIChargesStructure:
    """Test PI charges structure"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        customers_response = self.session.get(f"{BASE_URL}/api/customers")
        assert customers_response.status_code == 200
        customers = customers_response.json()
        assert len(customers) > 0
        self.customer_id = customers[0]["id"]
        
        yield
    
    def test_create_pi_with_charges(self):
        """Test creating PI with shipping and local charges"""
        pi_payload = {
            "customer_id": self.customer_id,
            "items": [{
                "product_name": "TEST_PI_Product",
                "qty": 5,
                "unit": "L",
                "rate": 100,
                "amount": 500,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 500,
                "description": ""
            }],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 80,
            "additional_charges": [
                {"name": "Local Charges", "amount": 40, "gst_percent": 0, "gst_amount": 0},
                {"name": "Documentation", "amount": 20, "gst_percent": 0, "gst_amount": 0}
            ],
            "remark": "Test PI for Phase 10",
            "free_samples": [],
            "billing_address_id": "",
            "shipping_address_id": ""
        }
        
        response = self.session.post(f"{BASE_URL}/api/proforma-invoices", json=pi_payload)
        assert response.status_code in [200, 201], f"PI creation failed: {response.text}"
        
        pi = response.json()
        
        # Verify charges
        assert pi.get("shipping_charge") == 80
        
        local = next((c for c in pi.get("additional_charges", []) if c["name"] == "Local Charges"), None)
        assert local is not None and local["amount"] == 40
        
        doc = next((c for c in pi.get("additional_charges", []) if c["name"] == "Documentation"), None)
        assert doc is not None and doc["amount"] == 20
        
        # Grand total: 500 + 80 + 40 + 20 = 640
        assert pi.get("grand_total") == 640, f"Grand total mismatch: expected 640, got {pi.get('grand_total')}"
        
        print(f"TEST PASS: PI {pi.get('pi_number')} created with correct charges")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/proforma-invoices/{pi['id']}")


class TestImageCompressionUtility:
    """Verify image compression utility exists and is properly configured"""
    
    def test_compress_image_file_exists(self):
        """Test 8: Verify compressImage.js exists"""
        import os
        compress_file = "/app/frontend/src/lib/compressImage.js"
        assert os.path.exists(compress_file), f"compressImage.js not found at {compress_file}"
        
        # Read and verify content
        with open(compress_file, 'r') as f:
            content = f.read()
        
        # Verify key parameters
        assert "MAX_WIDTH = 1280" in content, "MAX_WIDTH not set to 1280"
        assert "MAX_HEIGHT = 1280" in content, "MAX_HEIGHT not set to 1280"
        assert '"image/jpeg"' in content, "Output format not set to JPEG"
        assert "0.7" in content, "Quality not set to 0.7"
        
        print("TEST PASS: compressImage.js exists with correct configuration")
    
    def test_compress_image_imported_in_create_order(self):
        """Test 9a: Verify compressImage is imported in CreateOrder.js"""
        import os
        create_order_file = "/app/frontend/src/pages/telecaller/CreateOrder.js"
        assert os.path.exists(create_order_file)
        
        with open(create_order_file, 'r') as f:
            content = f.read()
        
        assert 'import { compressImage }' in content or 'compressImage' in content, "compressImage not imported in CreateOrder.js"
        print("TEST PASS: compressImage imported in CreateOrder.js")
    
    def test_compress_image_imported_in_edit_order(self):
        """Test 9b: Verify compressImage is imported in EditOrder.js"""
        import os
        edit_order_file = "/app/frontend/src/pages/EditOrder.js"
        assert os.path.exists(edit_order_file)
        
        with open(edit_order_file, 'r') as f:
            content = f.read()
        
        assert 'import { compressImage }' in content or 'compressImage' in content, "compressImage not imported in EditOrder.js"
        print("TEST PASS: compressImage imported in EditOrder.js")
    
    def test_compress_image_imported_in_packaging_dashboard(self):
        """Test 9c: Verify compressImage is imported in PackagingDashboard.js"""
        import os
        packaging_file = "/app/frontend/src/pages/packaging/PackagingDashboard.js"
        assert os.path.exists(packaging_file)
        
        with open(packaging_file, 'r') as f:
            content = f.read()
        
        assert 'import { compressImage }' in content or 'compressImage' in content, "compressImage not imported in PackagingDashboard.js"
        print("TEST PASS: compressImage imported in PackagingDashboard.js")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
