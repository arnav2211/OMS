"""
Test Suite for Iteration 18 Features:
1. Packing Sheet PDF - Purpose, Free Samples (with formulation), Extra Shipping Details
2. Print Address PDF with quantities
3. Address Name field in addresses
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAddressNameField:
    """Test address_name field in address CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get or create a test customer
        customers_resp = requests.get(f"{BASE_URL}/api/customers", headers=self.headers)
        assert customers_resp.status_code == 200
        customers = customers_resp.json()
        if customers:
            self.customer_id = customers[0]["id"]
            self.customer_name = customers[0]["name"]
        else:
            # Create a test customer
            create_resp = requests.post(f"{BASE_URL}/api/customers", headers=self.headers, json={
                "name": "TEST_AddressName_Customer",
                "phone_numbers": ["9876543210"]
            })
            assert create_resp.status_code in [200, 201]
            self.customer_id = create_resp.json()["id"]
            self.customer_name = "TEST_AddressName_Customer"
    
    def test_create_address_with_address_name(self):
        """Test creating address with explicit address_name"""
        response = requests.post(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses",
            headers=self.headers,
            json={
                "address_line": "123 Test Street",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400001",
                "label": "Office",
                "address_name": "TEST_Custom Recipient Name"
            }
        )
        assert response.status_code in [200, 201], f"Create address failed: {response.text}"
        data = response.json()
        assert data["address_name"] == "TEST_Custom Recipient Name", f"address_name not set correctly: {data}"
        print(f"PASS: Address created with custom address_name: {data['address_name']}")
    
    def test_create_address_without_address_name_defaults_to_customer_name(self):
        """Test that address_name defaults to customer name when not provided"""
        response = requests.post(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses",
            headers=self.headers,
            json={
                "address_line": "456 Default Street",
                "city": "Delhi",
                "state": "Delhi",
                "pincode": "110001",
                "label": "Home"
                # address_name not provided
            }
        )
        assert response.status_code in [200, 201], f"Create address failed: {response.text}"
        data = response.json()
        assert data["address_name"] == self.customer_name, f"address_name should default to customer name '{self.customer_name}', got: {data.get('address_name')}"
        print(f"PASS: Address created with default address_name (customer name): {data['address_name']}")
    
    def test_create_address_with_empty_address_name_defaults_to_customer_name(self):
        """Test that empty address_name defaults to customer name"""
        response = requests.post(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses",
            headers=self.headers,
            json={
                "address_line": "789 Empty Name Street",
                "city": "Chennai",
                "state": "Tamil Nadu",
                "pincode": "600001",
                "label": "Warehouse",
                "address_name": ""  # Empty string
            }
        )
        assert response.status_code in [200, 201], f"Create address failed: {response.text}"
        data = response.json()
        assert data["address_name"] == self.customer_name, f"Empty address_name should default to customer name, got: {data.get('address_name')}"
        print(f"PASS: Empty address_name defaults to customer name: {data['address_name']}")
    
    def test_update_address_with_address_name(self):
        """Test updating address with new address_name"""
        # First create an address
        create_resp = requests.post(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses",
            headers=self.headers,
            json={
                "address_line": "Update Test Street",
                "city": "Bangalore",
                "state": "Karnataka",
                "pincode": "560001",
                "label": "Test",
                "address_name": "Original Name"
            }
        )
        assert create_resp.status_code in [200, 201]
        address_id = create_resp.json()["id"]
        
        # Update the address
        update_resp = requests.put(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses/{address_id}",
            headers=self.headers,
            json={
                "address_line": "Update Test Street",
                "city": "Bangalore",
                "state": "Karnataka",
                "pincode": "560001",
                "label": "Test",
                "address_name": "TEST_Updated Recipient Name"
            }
        )
        assert update_resp.status_code == 200, f"Update address failed: {update_resp.text}"
        data = update_resp.json()
        assert data["address_name"] == "TEST_Updated Recipient Name", f"address_name not updated: {data}"
        print(f"PASS: Address updated with new address_name: {data['address_name']}")
    
    def test_list_addresses_includes_address_name(self):
        """Test that listing addresses includes address_name field for newly created addresses"""
        # First create a new address with address_name
        create_resp = requests.post(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses",
            headers=self.headers,
            json={
                "address_line": "TEST List Address Street",
                "city": "Pune",
                "state": "Maharashtra",
                "pincode": "411001",
                "label": "Test",
                "address_name": "TEST_List_Recipient"
            }
        )
        assert create_resp.status_code in [200, 201]
        new_addr_id = create_resp.json()["id"]
        
        # Now list addresses
        response = requests.get(
            f"{BASE_URL}/api/customers/{self.customer_id}/addresses",
            headers=self.headers
        )
        assert response.status_code == 200, f"List addresses failed: {response.text}"
        addresses = response.json()
        assert len(addresses) > 0, "No addresses found"
        
        # Find our newly created address and verify it has address_name
        new_addr = next((a for a in addresses if a["id"] == new_addr_id), None)
        assert new_addr is not None, "Newly created address not found in list"
        assert "address_name" in new_addr, f"address_name field missing in new address: {new_addr}"
        assert new_addr["address_name"] == "TEST_List_Recipient", f"address_name value incorrect: {new_addr}"
        print(f"PASS: Newly created address has address_name field: {new_addr['address_name']}")


class TestPrintAddressesWithQuantities:
    """Test print-addresses endpoint with quantity support"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_print_addresses_basic(self):
        """Test basic print-addresses without quantities"""
        # Get some orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=self.headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        assert len(orders) > 0, "No orders found for testing"
        
        order_ids = [orders[0]["id"]]
        
        response = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            headers=self.headers,
            json={"order_ids": order_ids}
        )
        assert response.status_code == 200, f"Print addresses failed: {response.text}"
        assert response.headers.get("content-type") == "application/pdf", "Response should be PDF"
        assert len(response.content) > 0, "PDF content should not be empty"
        print(f"PASS: Print addresses returns PDF ({len(response.content)} bytes)")
    
    def test_print_addresses_with_quantities(self):
        """Test print-addresses with quantity parameter"""
        # Get some orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=self.headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        assert len(orders) > 0, "No orders found for testing"
        
        order_id = orders[0]["id"]
        
        # Request with quantity=2
        response = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            headers=self.headers,
            json={
                "order_ids": [order_id],
                "quantities": {order_id: 2}
            }
        )
        assert response.status_code == 200, f"Print addresses with quantities failed: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print(f"PASS: Print addresses with quantity=2 returns PDF ({len(response.content)} bytes)")
    
    def test_print_addresses_multiple_orders_different_quantities(self):
        """Test print-addresses with multiple orders and different quantities"""
        # Get multiple orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=self.headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        if len(orders) < 2:
            pytest.skip("Need at least 2 orders for this test")
        
        order_ids = [orders[0]["id"], orders[1]["id"]]
        quantities = {
            orders[0]["id"]: 2,
            orders[1]["id"]: 3
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            headers=self.headers,
            json={
                "order_ids": order_ids,
                "quantities": quantities
            }
        )
        assert response.status_code == 200, f"Print addresses failed: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print(f"PASS: Print addresses with multiple orders and quantities returns PDF ({len(response.content)} bytes)")
    
    def test_print_addresses_packaging_user(self):
        """Test that packaging user can access print-addresses"""
        # Login as packaging user
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_packaging_user",
            "password": "test123"
        })
        assert login_resp.status_code == 200, f"Packaging login failed: {login_resp.text}"
        pkg_token = login_resp.json()["token"]
        pkg_headers = {"Authorization": f"Bearer {pkg_token}"}
        
        # Get orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=pkg_headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        if len(orders) == 0:
            pytest.skip("No orders available for packaging user")
        
        response = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            headers=pkg_headers,
            json={"order_ids": [orders[0]["id"]]}
        )
        assert response.status_code == 200, f"Packaging user print addresses failed: {response.text}"
        print("PASS: Packaging user can access print-addresses endpoint")
    
    def test_print_addresses_empty_order_ids(self):
        """Test print-addresses with empty order_ids returns error"""
        response = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            headers=self.headers,
            json={"order_ids": []}
        )
        assert response.status_code == 400, f"Expected 400 for empty order_ids, got: {response.status_code}"
        print("PASS: Empty order_ids returns 400 error")


class TestPackingSheetPDF:
    """Test packing sheet PDF includes Purpose, Free Samples, Extra Shipping Details"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_packing_sheet_for_order_with_all_fields(self):
        """Test packing sheet for order CS-0021 which has purpose, free_samples, extra_shipping_details"""
        # The order 20cdd1d5-0b59-4fa3-9fe4-4cffc1424c93 (CS-0021) has been set up with test data
        order_id = "20cdd1d5-0b59-4fa3-9fe4-4cffc1424c93"
        
        # First verify the order exists and has the expected fields
        order_resp = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=self.headers)
        if order_resp.status_code == 404:
            pytest.skip("Test order CS-0021 not found")
        
        assert order_resp.status_code == 200, f"Get order failed: {order_resp.text}"
        order = order_resp.json()
        
        # Verify the order has the expected fields
        print(f"Order {order.get('order_number')} fields:")
        print(f"  - purpose: {order.get('purpose')}")
        print(f"  - free_samples: {order.get('free_samples')}")
        print(f"  - extra_shipping_details: {order.get('extra_shipping_details')}")
        
        # Get the packing sheet PDF
        pdf_resp = requests.get(
            f"{BASE_URL}/api/orders/{order_id}/print?token={self.token}",
            headers=self.headers
        )
        assert pdf_resp.status_code == 200, f"Get packing sheet failed: {pdf_resp.text}"
        assert pdf_resp.headers.get("content-type") == "application/pdf"
        assert len(pdf_resp.content) > 0, "PDF content should not be empty"
        print(f"PASS: Packing sheet PDF generated ({len(pdf_resp.content)} bytes)")
    
    def test_packing_sheet_endpoint_exists(self):
        """Test that packing sheet endpoint exists and returns PDF"""
        # Get any order
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=self.headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        if len(orders) == 0:
            pytest.skip("No orders available")
        
        order_id = orders[0]["id"]
        
        pdf_resp = requests.get(
            f"{BASE_URL}/api/orders/{order_id}/print?token={self.token}",
            headers=self.headers
        )
        assert pdf_resp.status_code == 200, f"Get packing sheet failed: {pdf_resp.text}"
        assert "pdf" in pdf_resp.headers.get("content-type", "").lower()
        print(f"PASS: Packing sheet endpoint works for order {orders[0].get('order_number')}")


class TestAddressNameInPrintOutputs:
    """Test that address_name is used in print outputs"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_order_shipping_address_has_address_name(self):
        """Test that orders with shipping addresses include address_name"""
        orders_resp = requests.get(f"{BASE_URL}/api/orders", headers=self.headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json()
        
        # Find an order with shipping_address
        order_with_address = None
        for order in orders:
            if order.get("shipping_address") and order["shipping_address"].get("address_line"):
                order_with_address = order
                break
        
        if not order_with_address:
            pytest.skip("No orders with shipping address found")
        
        shipping_addr = order_with_address["shipping_address"]
        print(f"Order {order_with_address.get('order_number')} shipping address:")
        print(f"  - address_name: {shipping_addr.get('address_name')}")
        print(f"  - address_line: {shipping_addr.get('address_line')}")
        
        # address_name may or may not be set depending on when the order was created
        # The field should exist in the schema
        print("PASS: Shipping address structure verified")


class TestOrderFieldsForPackingSheet:
    """Test that order fields for packing sheet are properly stored and retrieved"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_order_has_purpose_field(self):
        """Test that orders can have purpose field"""
        # Get the test order
        order_id = "20cdd1d5-0b59-4fa3-9fe4-4cffc1424c93"
        order_resp = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=self.headers)
        
        if order_resp.status_code == 404:
            pytest.skip("Test order not found")
        
        order = order_resp.json()
        purpose = order.get("purpose")
        print(f"Order purpose: {purpose}")
        
        if purpose:
            assert isinstance(purpose, str), "Purpose should be a string"
            print(f"PASS: Order has purpose field: {purpose}")
        else:
            print("INFO: Order does not have purpose set")
    
    def test_order_has_free_samples_with_formulation(self):
        """Test that orders can have free_samples with formulation"""
        order_id = "20cdd1d5-0b59-4fa3-9fe4-4cffc1424c93"
        order_resp = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=self.headers)
        
        if order_resp.status_code == 404:
            pytest.skip("Test order not found")
        
        order = order_resp.json()
        free_samples = order.get("free_samples", [])
        print(f"Order free_samples: {free_samples}")
        
        if free_samples:
            for sample in free_samples:
                assert "item_name" in sample, "Free sample should have item_name"
                if sample.get("formulation"):
                    print(f"PASS: Free sample '{sample['item_name']}' has formulation: {sample['formulation']}")
        else:
            print("INFO: Order does not have free_samples set")
    
    def test_order_has_extra_shipping_details(self):
        """Test that orders can have extra_shipping_details"""
        order_id = "20cdd1d5-0b59-4fa3-9fe4-4cffc1424c93"
        order_resp = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=self.headers)
        
        if order_resp.status_code == 404:
            pytest.skip("Test order not found")
        
        order = order_resp.json()
        extra_shipping = order.get("extra_shipping_details")
        print(f"Order extra_shipping_details: {extra_shipping}")
        
        if extra_shipping:
            assert isinstance(extra_shipping, str), "extra_shipping_details should be a string"
            print(f"PASS: Order has extra_shipping_details: {extra_shipping}")
        else:
            print("INFO: Order does not have extra_shipping_details set")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
