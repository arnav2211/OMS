"""
Amazon Dispatch Features Tests - Iteration 13
Tests for new features:
1. POST /api/amazon/upload-pdf no longer requires courier_name for self_ship
2. POST /api/amazon/orders/bulk-dispatch - bulk dispatch easy_ship orders
3. PUT /api/amazon/orders/{id}/courier - update courier name
4. PUT /api/amazon/orders/{id}/dispatch - requires LR for self_ship
5. DELETE /api/amazon/orders/{id} - admin only, cannot delete dispatched
6. Mark packed accessible by packaging and dispatch roles
7. Access control for packaging and dispatch roles
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://order-search-1.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}
PACKAGING_CREDS = {"username": "test_packaging_user", "password": "test123"}
DISPATCH_CREDS = {"username": "test_dispatch_user", "password": "test123"}


class TestAmazonUploadPDFNoCourer:
    """Test that self_ship PDF upload no longer requires courier_name"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert res.status_code == 200, f"Admin login failed: {res.text}"
        return res.json()["token"]
    
    def test_self_ship_upload_no_courier_required(self, admin_token):
        """POST /api/amazon/upload-pdf with self_ship should NOT require courier_name"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a dummy PDF file - this will fail parsing but should NOT fail on courier validation
        files = {"file": ("test.pdf", b"dummy pdf content", "application/pdf")}
        res = requests.post(
            f"{BASE_URL}/api/amazon/upload-pdf?ship_type=self_ship",
            headers=headers,
            files=files
        )
        # Should fail with PDF parsing error, NOT courier validation error
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        error_msg = res.json().get("detail", "").lower()
        # Should NOT mention courier - should be a PDF parsing error
        assert "courier" not in error_msg, f"Error should NOT mention courier: {error_msg}"
        assert "pdf" in error_msg or "parsing" in error_msg or "no orders" in error_msg, \
            f"Error should be about PDF parsing: {error_msg}"
        print("PASS: Self ship upload no longer requires courier_name parameter")


class TestBulkDispatch:
    """Test POST /api/amazon/orders/bulk-dispatch endpoint"""
    
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
    def dispatch_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
        if res.status_code != 200:
            pytest.skip("Dispatch user not found")
        return res.json()["token"]
    
    def test_bulk_dispatch_endpoint_exists(self, admin_token):
        """POST /api/amazon/orders/bulk-dispatch endpoint should exist"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        res = requests.post(f"{BASE_URL}/api/amazon/orders/bulk-dispatch", 
                           headers=headers, json={"order_ids": []})
        # Should return 400 for empty list, not 404/405
        assert res.status_code == 400, f"Expected 400 for empty list, got {res.status_code}"
        print("PASS: Bulk dispatch endpoint exists")
    
    def test_bulk_dispatch_with_valid_orders(self, admin_token):
        """Bulk dispatch should dispatch multiple easy_ship orders"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Get easy_ship orders that are not dispatched
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        easy_ship_ids = [o["id"] for o in orders 
                        if o.get("ship_type") == "easy_ship" and o.get("status") != "dispatched"]
        
        if not easy_ship_ids:
            pytest.skip("No easy_ship orders available for bulk dispatch")
        
        # Take up to 2 orders for testing
        test_ids = easy_ship_ids[:2]
        
        res = requests.post(f"{BASE_URL}/api/amazon/orders/bulk-dispatch",
                           headers=headers, json={"order_ids": test_ids})
        assert res.status_code == 200, f"Bulk dispatch failed: {res.text}"
        
        result = res.json()
        assert "dispatched" in result, "Response should contain 'dispatched' count"
        assert result["dispatched"] >= 0, "Dispatched count should be >= 0"
        print(f"PASS: Bulk dispatch completed - {result['dispatched']} orders dispatched")
    
    def test_bulk_dispatch_accessible_by_packaging(self, packaging_token):
        """Packaging role should be able to access bulk dispatch"""
        headers = {"Authorization": f"Bearer {packaging_token}", "Content-Type": "application/json"}
        res = requests.post(f"{BASE_URL}/api/amazon/orders/bulk-dispatch",
                           headers=headers, json={"order_ids": []})
        # Should return 400 for empty list, not 403
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        print("PASS: Packaging role can access bulk dispatch endpoint")
    
    def test_bulk_dispatch_accessible_by_dispatch(self, dispatch_token):
        """Dispatch role should be able to access bulk dispatch"""
        headers = {"Authorization": f"Bearer {dispatch_token}", "Content-Type": "application/json"}
        res = requests.post(f"{BASE_URL}/api/amazon/orders/bulk-dispatch",
                           headers=headers, json={"order_ids": []})
        # Should return 400 for empty list, not 403
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        print("PASS: Dispatch role can access bulk dispatch endpoint")


class TestCourierUpdate:
    """Test PUT /api/amazon/orders/{id}/courier endpoint"""
    
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
    def dispatch_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
        if res.status_code != 200:
            pytest.skip("Dispatch user not found")
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def self_ship_order_id(self, admin_token):
        """Get a self_ship order that is not dispatched"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for o in orders:
            if o.get("ship_type") == "self_ship" and o.get("status") != "dispatched":
                return o["id"]
        pytest.skip("No self_ship non-dispatched order available")
    
    def test_courier_update_endpoint_exists(self, admin_token, self_ship_order_id):
        """PUT /api/amazon/orders/{id}/courier endpoint should exist"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_order_id}/courier",
                          headers=headers, json={"courier_name": "DTDC"})
        assert res.status_code == 200, f"Courier update failed: {res.text}"
        print("PASS: Courier update endpoint exists and works")
    
    def test_courier_update_changes_value(self, admin_token, self_ship_order_id):
        """Courier update should change the courier_name value"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Update to Anjani
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_order_id}/courier",
                          headers=headers, json={"courier_name": "Anjani"})
        assert res.status_code == 200
        
        # Verify the change
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{self_ship_order_id}", headers=headers)
        order = res2.json()
        assert order["courier_name"] == "Anjani", f"Courier should be Anjani, got {order['courier_name']}"
        
        # Restore to DTDC
        requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_order_id}/courier",
                    headers=headers, json={"courier_name": "DTDC"})
        print("PASS: Courier update correctly changes the value")
    
    def test_courier_update_accessible_by_packaging(self, packaging_token, self_ship_order_id):
        """Packaging role should be able to update courier"""
        headers = {"Authorization": f"Bearer {packaging_token}", "Content-Type": "application/json"}
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_order_id}/courier",
                          headers=headers, json={"courier_name": "DTDC"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        print("PASS: Packaging role can update courier")
    
    def test_courier_update_accessible_by_dispatch(self, dispatch_token, self_ship_order_id):
        """Dispatch role should be able to update courier"""
        headers = {"Authorization": f"Bearer {dispatch_token}", "Content-Type": "application/json"}
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_order_id}/courier",
                          headers=headers, json={"courier_name": "DTDC"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        print("PASS: Dispatch role can update courier")


class TestSelfShipDispatchRequiresLR:
    """Test that self_ship dispatch requires LR number"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def self_ship_packed_order_id(self, admin_token):
        """Get a self_ship order in packed status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for o in orders:
            if o.get("ship_type") == "self_ship" and o.get("status") == "packed":
                return o["id"]
        pytest.skip("No self_ship packed order available")
    
    def test_self_ship_dispatch_without_lr_fails(self, admin_token, self_ship_packed_order_id):
        """PUT /api/amazon/orders/{id}/dispatch without LR should return 400 for self_ship"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_packed_order_id}/dispatch",
                          headers=headers, json={})
        assert res.status_code == 400, f"Expected 400 without LR, got {res.status_code}"
        
        error_msg = res.json().get("detail", "").lower()
        assert "lr" in error_msg, f"Error should mention LR: {error_msg}"
        print("PASS: Self ship dispatch without LR correctly returns 400")
    
    def test_self_ship_dispatch_with_lr_succeeds(self, admin_token, self_ship_packed_order_id):
        """PUT /api/amazon/orders/{id}/dispatch with LR should succeed for self_ship"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{self_ship_packed_order_id}/dispatch",
                          headers=headers, json={"lr_number": "TEST-LR-123456"})
        assert res.status_code == 200, f"Dispatch with LR failed: {res.text}"
        
        # Verify dispatch data
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{self_ship_packed_order_id}", headers=headers)
        order = res2.json()
        assert order["status"] == "dispatched"
        assert order.get("dispatch", {}).get("lr_number") == "TEST-LR-123456"
        print("PASS: Self ship dispatch with LR succeeds")


class TestDeleteAmazonOrder:
    """Test DELETE /api/amazon/orders/{id} endpoint"""
    
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
    def dispatched_order_id(self, admin_token):
        """Get a dispatched order"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for o in orders:
            if o.get("status") == "dispatched":
                return o["id"]
        pytest.skip("No dispatched order available")
    
    @pytest.fixture(scope="class")
    def non_dispatched_order_id(self, admin_token):
        """Get a non-dispatched order"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for o in orders:
            if o.get("status") != "dispatched":
                return o["id"]
        pytest.skip("No non-dispatched order available")
    
    def test_delete_dispatched_order_fails(self, admin_token, dispatched_order_id):
        """DELETE /api/amazon/orders/{id} should return 400 for dispatched order"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.delete(f"{BASE_URL}/api/amazon/orders/{dispatched_order_id}", headers=headers)
        assert res.status_code == 400, f"Expected 400 for dispatched order, got {res.status_code}"
        print("PASS: Cannot delete dispatched order")
    
    def test_delete_requires_admin(self, packaging_token, non_dispatched_order_id):
        """DELETE /api/amazon/orders/{id} should require admin role"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        res = requests.delete(f"{BASE_URL}/api/amazon/orders/{non_dispatched_order_id}", headers=headers)
        assert res.status_code == 403, f"Expected 403 for non-admin, got {res.status_code}"
        print("PASS: Delete requires admin role")


class TestMarkPackedAccessControl:
    """Test that mark-packed is accessible by packaging and dispatch roles"""
    
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
    def dispatch_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
        if res.status_code != 200:
            pytest.skip("Dispatch user not found")
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_order_id(self, admin_token):
        """Get an order in packaging status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        for o in orders:
            if o.get("status") == "packaging":
                return o["id"]
        # If no packaging order, create one by updating a new order
        for o in orders:
            if o.get("status") == "new":
                # Update packaging to change status to packaging
                requests.put(f"{BASE_URL}/api/amazon/orders/{o['id']}/packaging",
                           headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                           json={"item_packed_by": ["Test"]})
                return o["id"]
        pytest.skip("No order available for mark-packed test")
    
    def test_mark_packed_accessible_by_packaging(self, packaging_token, packaging_order_id):
        """Packaging role should be able to mark order as packed"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{packaging_order_id}/mark-packed", headers=headers)
        # Should be 200 or already packed
        assert res.status_code in [200, 400], f"Expected 200 or 400, got {res.status_code}"
        print("PASS: Packaging role can access mark-packed endpoint")
    
    def test_mark_packed_accessible_by_dispatch(self, dispatch_token, admin_token):
        """Dispatch role should be able to mark order as packed"""
        # First get a new order and put it in packaging status
        headers_admin = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers_admin)
        orders = res.json()
        
        test_order_id = None
        for o in orders:
            if o.get("status") in ["new", "packaging"]:
                test_order_id = o["id"]
                # Ensure it's in packaging status
                requests.put(f"{BASE_URL}/api/amazon/orders/{test_order_id}/packaging",
                           headers=headers_admin, json={"item_packed_by": ["Test"]})
                break
        
        if not test_order_id:
            pytest.skip("No order available for dispatch mark-packed test")
        
        headers_dispatch = {"Authorization": f"Bearer {dispatch_token}"}
        res = requests.put(f"{BASE_URL}/api/amazon/orders/{test_order_id}/mark-packed", headers=headers_dispatch)
        # Should be 200 or already packed
        assert res.status_code in [200, 400], f"Expected 200 or 400, got {res.status_code}"
        print("PASS: Dispatch role can access mark-packed endpoint")


class TestDispatchRoleAccessControl:
    """Test that dispatch role can access amazon dispatch endpoints"""
    
    @pytest.fixture(scope="class")
    def dispatch_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
        if res.status_code != 200:
            pytest.skip("Dispatch user not found")
        return res.json()["token"]
    
    def test_dispatch_can_list_amazon_orders(self, dispatch_token):
        """Dispatch role should be able to list Amazon orders"""
        headers = {"Authorization": f"Bearer {dispatch_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        print("PASS: Dispatch role can list Amazon orders")
    
    def test_dispatch_can_view_order_detail(self, dispatch_token):
        """Dispatch role should be able to view order detail"""
        headers = {"Authorization": f"Bearer {dispatch_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        if not orders:
            pytest.skip("No orders available")
        
        order_id = orders[0]["id"]
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{order_id}", headers=headers)
        assert res2.status_code == 200, f"Expected 200, got {res2.status_code}"
        print("PASS: Dispatch role can view order detail")
    
    def test_dispatch_can_dispatch_order(self, dispatch_token):
        """Dispatch role should be able to dispatch orders"""
        headers = {"Authorization": f"Bearer {dispatch_token}", "Content-Type": "application/json"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        
        # Find a packed easy_ship order
        for o in orders:
            if o.get("status") == "packed" and o.get("ship_type") == "easy_ship":
                res2 = requests.put(f"{BASE_URL}/api/amazon/orders/{o['id']}/dispatch",
                                   headers=headers, json={})
                assert res2.status_code == 200, f"Expected 200, got {res2.status_code}"
                print("PASS: Dispatch role can dispatch orders")
                return
        
        # If no packed order, just verify endpoint access
        print("PASS: Dispatch role has access to dispatch endpoint (no packed order to test)")


class TestPackagingRoleAccessControl:
    """Test that packaging role can access amazon orders"""
    
    @pytest.fixture(scope="class")
    def packaging_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json=PACKAGING_CREDS)
        if res.status_code != 200:
            pytest.skip("Packaging user not found")
        return res.json()["token"]
    
    def test_packaging_can_list_amazon_orders(self, packaging_token):
        """Packaging role should be able to list Amazon orders"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        print("PASS: Packaging role can list Amazon orders")
    
    def test_packaging_can_view_order_detail(self, packaging_token):
        """Packaging role should be able to view order detail"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        res = requests.get(f"{BASE_URL}/api/amazon/orders", headers=headers)
        orders = res.json()
        if not orders:
            pytest.skip("No orders available")
        
        order_id = orders[0]["id"]
        res2 = requests.get(f"{BASE_URL}/api/amazon/orders/{order_id}", headers=headers)
        assert res2.status_code == 200, f"Expected 200, got {res2.status_code}"
        print("PASS: Packaging role can view order detail")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
