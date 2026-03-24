"""
Amazon PDF Orders Module Tests
Tests for: PDF upload, order CRUD, packaging, dispatch, access control, AM-XXXX numbering
"""
import pytest
import requests
import os
import tempfile

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://packaging-workflow-2.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}
TELECALLER_CREDS = {"username": "test_tc_payment", "password": "test123"}
PACKAGING_CREDS = {"username": "test_packaging_user", "password": "test123"}


class TestAmazonAuth:
    """Test authentication and access control for Amazon endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert res.status_code == 200, f"Admin login failed: {res.text}"
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        """Get telecaller token"""
        res = requests.post(f"{BASE_URL}/api/auth/login", json=TELECALLER_CREDS)
        if res.status_code != 200:
            pytest.skip("Telecaller user not found")
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_token(self):
        """Get packaging token"""
        res = requests.post(f"{BASE_URL}/api/auth/login", json=PACKAGING_CREDS)
        if res.status_code != 200:
            pytest.skip("Packaging user not found")
        return res.json()["token"]
    
    def test_telecaller_cannot_access_amazon_orders(self, telecaller_token):
        """Telecaller role should NOT have access to Amazon endpoints"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        assert res.status_code == 403, f"Expected 403 for telecaller, got {res.status_code}"
        print("PASS: Telecaller correctly denied access to Amazon orders")
    
    def test_admin_can_access_amazon_orders(self, admin_token):
        """Admin should have access to Amazon endpoints"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        assert res.status_code == 200, f"Admin should access Amazon orders: {res.text}"
        print(f"PASS: Admin can access Amazon orders, found {len(res.json())} orders")
    
    def test_packaging_can_access_amazon_orders(self, packaging_token):
        """Packaging role should have access to Amazon endpoints"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        assert res.status_code == 200, f"Packaging should access Amazon orders: {res.text}"
        print(f"PASS: Packaging can access Amazon orders, found {len(res.json())} orders")


class TestAmazonOrdersList:
    """Test GET /api/amazon/orders endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    def test_list_amazon_orders_returns_array(self, admin_token):
        """GET /api/amazon/orders should return array sorted by created_at desc"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        assert res.status_code == 200
        orders = res.json()
        assert isinstance(orders, list), "Response should be a list"
        print(f"PASS: Amazon orders list returned {len(orders)} orders")
        
        # Verify order structure if orders exist
        if orders:
            order = orders[0]
            required_fields = ["id", "am_order_number", "amazon_order_id", "customer_name", 
                             "address", "items", "grand_total", "status", "ship_type"]
            for field in required_fields:
                assert field in order, f"Missing field: {field}"
            print(f"PASS: Order structure verified with all required fields")
    
    def test_orders_have_am_numbering(self, admin_token):
        """Orders should have AM-XXXX format numbering"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        
        for order in orders[:5]:  # Check first 5
            am_num = order.get("am_order_number", "")
            assert am_num.startswith("AM-"), f"Order number should start with AM-: {am_num}"
            # Verify format AM-XXXX
            parts = am_num.split("-")
            assert len(parts) == 2, f"Invalid AM number format: {am_num}"
            assert parts[1].isdigit(), f"AM number should have numeric suffix: {am_num}"
        print("PASS: All orders have correct AM-XXXX numbering format")


class TestAmazonOrderDetail:
    """Test GET /api/amazon/orders/{id} endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def sample_order_id(self, admin_token):
        """Get a sample order ID for testing"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        if not orders:
            pytest.skip("No Amazon orders available for testing")
        return orders[0]["id"]
    
    def test_get_single_order(self, admin_token, sample_order_id):
        """GET /api/amazon/orders/{id} should return single order with all fields"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders/{sample_order_id}", headers=headers)
        assert res.status_code == 200, f"Failed to get order: {res.text}"
        
        order = res.json()
        assert order["id"] == sample_order_id
        
        # Verify all expected fields
        expected_fields = ["id", "am_order_number", "amazon_order_id", "customer_name", 
                         "address", "phone", "items", "grand_total", "status", 
                         "ship_type", "shipping_method", "packaging", "dispatch"]
        for field in expected_fields:
            assert field in order, f"Missing field: {field}"
        
        # Verify items structure
        assert isinstance(order["items"], list), "Items should be a list"
        if order["items"]:
            item = order["items"][0]
            item_fields = ["product_name", "quantity", "unit_price", "amount"]
            for field in item_fields:
                assert field in item, f"Item missing field: {field}"
        
        print(f"PASS: Order detail returned with all fields - {order['am_order_number']}")
    
    def test_get_nonexistent_order(self, admin_token):
        """GET /api/amazon/orders/{id} should return 404 for non-existent order"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders/nonexistent-id-12345", headers=headers)
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"
        print("PASS: Non-existent order returns 404")


class TestAmazonPackaging:
    """Test PUT /api/amazon/orders/{id}/packaging endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=PACKAGING_CREDS)
        if res.status_code != 200:
            pytest.skip("Packaging user not found")
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def test_order_id(self, admin_token):
        """Get a non-dispatched order for testing"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        # Find a non-dispatched order
        for order in orders:
            if order.get("status") != "dispatched":
                return order["id"]
        pytest.skip("No non-dispatched Amazon orders available")
    
    def test_update_packaging_data(self, admin_token, test_order_id):
        """PUT /api/amazon/orders/{id}/packaging should update packaging data"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        packaging_data = {
            "item_packed_by": ["Yogita"],
            "box_packed_by": ["Sapna"],
            "checked_by": ["Samiksha"],
            "item_images": {},
            "order_images": [],
            "packed_box_images": []
        }
        
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{test_order_id}/packaging", 
                          headers=headers, json=packaging_data)
        assert res.status_code == 200, f"Failed to update packaging: {res.text}"
        
        # Verify the update
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{test_order_id}", headers=headers)
        order = res2.json()
        assert order["packaging"]["item_packed_by"] == ["Yogita"]
        assert order["packaging"]["box_packed_by"] == ["Sapna"]
        assert order["packaging"]["checked_by"] == ["Samiksha"]
        
        print("PASS: Packaging data updated successfully")
    
    def test_packaging_changes_status_to_packaging(self, admin_token, test_order_id):
        """Updating packaging on 'new' order should change status to 'packaging'"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders/{test_order_id}", headers=headers)
        order = res.json()
        
        # Status should be 'packaging' after update (or already was)
        assert order["status"] in ["packaging", "packed", "dispatched"], \
            f"Status should be packaging or later, got: {order['status']}"
        print(f"PASS: Order status is '{order['status']}' after packaging update")


class TestAmazonMarkPacked:
    """Test PUT /api/amazon/orders/{id}/mark-packed endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_order_id(self, admin_token):
        """Get an order in 'packaging' status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for order in orders:
            if order.get("status") == "packaging":
                return order["id"]
        pytest.skip("No order in 'packaging' status available")
    
    def test_mark_packed(self, admin_token, packaging_order_id):
        """PUT /api/amazon/orders/{id}/mark-packed should change status to packed"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{packaging_order_id}/mark-packed", headers=headers)
        assert res.status_code == 200, f"Failed to mark packed: {res.text}"
        
        # Verify status changed
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{packaging_order_id}", headers=headers)
        order = res2.json()
        assert order["status"] == "packed", f"Status should be 'packed', got: {order['status']}"
        assert "packed_at" in order.get("packaging", {}), "packed_at timestamp should be set"
        
        print("PASS: Order marked as packed successfully")


class TestAmazonDispatch:
    """Test PUT /api/amazon/orders/{id}/dispatch endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def packed_order_id(self, admin_token):
        """Get an order in 'packed' status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for order in orders:
            if order.get("status") == "packed":
                return order["id"], order.get("ship_type", "easy_ship")
        pytest.skip("No order in 'packed' status available")
    
    def test_dispatch_order(self, admin_token, packed_order_id):
        """PUT /api/amazon/orders/{id}/dispatch should dispatch the order"""
        order_id, ship_type = packed_order_id
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # For self_ship, we can optionally provide LR number
        data = {}
        if ship_type == "self_ship":
            data["lr_number"] = "TEST-LR-12345"
        
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{order_id}/dispatch", 
                          headers=headers, json=data)
        assert res.status_code == 200, f"Failed to dispatch: {res.text}"
        
        # Verify status changed
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{order_id}", headers=headers)
        order = res2.json()
        assert order["status"] == "dispatched", f"Status should be 'dispatched', got: {order['status']}"
        assert "dispatched_at" in order.get("dispatch", {}), "dispatched_at should be set"
        
        print(f"PASS: Order dispatched successfully (ship_type: {ship_type})")


class TestAmazonDeleteImages:
    """Test DELETE /api/amazon/orders/{id}/images endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    def test_delete_image_endpoint_exists(self, admin_token):
        """DELETE /api/amazon/orders/{id}/images endpoint should exist"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Test with a fake order ID - should return 404 (not 405 method not allowed)
        res = requests.delete(
            f"{BASE_URL}/api/amazon/orders/fake-id/images",
            headers=headers,
            params={"image_type": "order_image", "image_url": "/api/uploads/test.jpg"}
        )
        assert res.status_code in [404, 200], f"Unexpected status: {res.status_code}"
        print("PASS: Delete images endpoint exists and responds correctly")


class TestAmazonUploadPDF:
    """Test POST /api/amazon/upload-pdf endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=TELECALLER_CREDS)
        if res.status_code != 200:
            pytest.skip("Telecaller user not found")
        return res.json()["token"]
    
    def test_upload_requires_admin(self, telecaller_token):
        """Only admin should be able to upload PDFs"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        
        # Create a dummy PDF file
        files = {"file": ("test.pdf", b"dummy pdf content", "application/pdf")}
        res = requests.post(
            f"{BASE_URL}/api/amazon/upload-pdf?ship_type=easy_ship",
            headers=headers,
            files=files
        )
        assert res.status_code == 403, f"Expected 403 for non-admin, got {res.status_code}"
        print("PASS: Non-admin correctly denied PDF upload")
    
    def test_upload_validates_ship_type(self, admin_token):
        """Upload should validate ship_type parameter"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        files = {"file": ("test.pdf", b"dummy pdf content", "application/pdf")}
        res = requests.post(
            f"{BASE_URL}/api/amazon/upload-pdf?ship_type=invalid_type",
            headers=headers,
            files=files
        )
        assert res.status_code == 400, f"Expected 400 for invalid ship_type, got {res.status_code}"
        print("PASS: Invalid ship_type correctly rejected")
    
    def test_self_ship_requires_courier(self, admin_token):
        """Self ship should require courier_name"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        files = {"file": ("test.pdf", b"dummy pdf content", "application/pdf")}
        res = requests.post(
            f"{BASE_URL}/api/amazon/upload-pdf?ship_type=self_ship",
            headers=headers,
            files=files
        )
        assert res.status_code == 400, f"Expected 400 for self_ship without courier, got {res.status_code}"
        assert "courier" in res.text.lower(), "Error should mention courier"
        print("PASS: Self ship without courier correctly rejected")


class TestAmazonOrdersExisting:
    """Test existing Amazon orders in database"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    def test_existing_orders_have_correct_structure(self, admin_token):
        """Verify existing orders (AM-0001 to AM-0007) have correct structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        
        assert len(orders) >= 7, f"Expected at least 7 orders, found {len(orders)}"
        
        # Check for AM-0001 to AM-0007
        am_numbers = [o.get("am_order_number") for o in orders]
        for i in range(1, 8):
            expected = f"AM-{i:04d}"
            assert expected in am_numbers, f"Missing order {expected}"
        
        print(f"PASS: Found all expected orders AM-0001 to AM-0007")
    
    def test_orders_have_ship_type(self, admin_token):
        """All orders should have ship_type field"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        
        for order in orders:
            assert "ship_type" in order, f"Order {order.get('am_order_number')} missing ship_type"
            assert order["ship_type"] in ["easy_ship", "self_ship"], \
                f"Invalid ship_type: {order['ship_type']}"
        
        print("PASS: All orders have valid ship_type")
    
    def test_orders_have_amazon_order_id(self, admin_token):
        """All orders should have unique amazon_order_id"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        
        amazon_ids = set()
        for order in orders:
            aid = order.get("amazon_order_id")
            assert aid, f"Order {order.get('am_order_number')} missing amazon_order_id"
            assert aid not in amazon_ids, f"Duplicate amazon_order_id: {aid}"
            amazon_ids.add(aid)
        
        print(f"PASS: All {len(orders)} orders have unique amazon_order_id")


class TestAmazonStatusFlow:
    """Test the status flow: new -> packaging -> packed -> dispatched"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    def test_valid_statuses(self, admin_token):
        """All orders should have valid status values"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        
        valid_statuses = ["new", "packaging", "packed", "dispatched"]
        status_counts = {s: 0 for s in valid_statuses}
        
        for order in orders:
            status = order.get("status")
            assert status in valid_statuses, f"Invalid status: {status}"
            status_counts[status] += 1
        
        print(f"PASS: Status distribution: {status_counts}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
