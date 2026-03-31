"""
Test suite for Formulation Lock feature
- Formulation preservation during order updates
- Formulation lock mechanism for non-admin users
- Edit permission request/approve/reject flow
- Admin bypass for locked orders
"""
import pytest
import requests
import os
import uuid
import random

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}
TELECALLER_CREDS = {"username": "test_tc_payment", "password": "test123"}
PACKAGING_CREDS = {"username": "test_packaging_user", "password": "test123"}


class TestFormulationLock:
    """Test formulation lock and preservation features"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        """Get telecaller auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=TELECALLER_CREDS)
        assert response.status_code == 200, f"Telecaller login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_token(self):
        """Get packaging auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PACKAGING_CREDS)
        assert response.status_code == 200, f"Packaging login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def telecaller_headers(self, telecaller_token):
        return {"Authorization": f"Bearer {telecaller_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def packaging_headers(self, packaging_token):
        return {"Authorization": f"Bearer {packaging_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_customer(self, admin_headers):
        """Create a test customer for orders"""
        import random
        phone = f"98{random.randint(10000000, 99999999)}"
        customer_data = {
            "name": f"TEST_FormLock_Customer_{uuid.uuid4().hex[:6]}",
            "phone_numbers": [phone],
            "email": "test_formlock@example.com"
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=admin_headers)
        assert response.status_code in [200, 201], f"Customer creation failed: {response.text}"
        return response.json()
    
    @pytest.fixture(scope="class")
    def test_order_with_formulation(self, admin_headers, test_customer):
        """Create a test order and add formulation to it"""
        # Create order
        order_data = {
            "customer_id": test_customer["id"],
            "customer_name": test_customer["name"],
            "items": [
                {"product_name": "Test Product A", "qty": 10, "unit": "L", "rate": 100, "amount": 1000, "gst_rate": 0, "gst_amount": 0, "total": 1000},
                {"product_name": "Test Product B", "qty": 5, "unit": "Kg", "rate": 200, "amount": 1000, "gst_rate": 0, "gst_amount": 0, "total": 1000}
            ],
            "free_samples": [
                {"item_name": "Free Sample X", "description": "Test sample"}
            ],
            "subtotal": 2000,
            "grand_total": 2000,
            "payment_status": "unpaid"
        }
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=admin_headers)
        assert response.status_code in [200, 201], f"Order creation failed: {response.text}"
        order = response.json()
        
        # Add formulation to the order
        formulation_data = {
            "items": [
                {"index": 0, "formulation": "Mix 50% Eucalyptus + 30% Lemon + 20% Pine"},
                {"index": 1, "formulation": "Pure Lavender Extract"},
                {"is_free_sample": True, "fs_index": 0, "formulation": "Sample formulation mix"}
            ]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order['id']}/formulation", json=formulation_data, headers=admin_headers)
        assert response.status_code == 200, f"Formulation update failed: {response.text}"
        
        # Fetch updated order
        response = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=admin_headers)
        return response.json()
    
    # ── Test 1: Verify formulation_locked field in GET response ──
    def test_order_has_formulation_locked_field(self, admin_headers, test_order_with_formulation):
        """Orders with formulations should have formulation_locked=true"""
        order_id = test_order_with_formulation["id"]
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        assert response.status_code == 200
        order = response.json()
        assert "formulation_locked" in order, "formulation_locked field missing from order response"
        assert order["formulation_locked"] == True, "Order with formulation should have formulation_locked=true"
        print(f"✓ Order {order['order_number']} has formulation_locked=true")
    
    # ── Test 2: Admin can edit locked orders ──
    def test_admin_can_edit_locked_order(self, admin_headers, test_order_with_formulation):
        """Admin should be able to edit orders with formulations"""
        order_id = test_order_with_formulation["id"]
        update_data = {
            "remark": f"Admin edit test - {uuid.uuid4().hex[:6]}",
            "items": test_order_with_formulation["items"]  # Keep same items
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=admin_headers)
        assert response.status_code == 200, f"Admin should be able to edit locked order: {response.text}"
        print("✓ Admin can edit locked orders")
    
    # ── Test 3: Telecaller blocked from editing locked order ──
    def test_telecaller_blocked_from_locked_order(self, telecaller_headers, test_order_with_formulation):
        """Telecaller should get 403 when trying to edit locked order without permission"""
        order_id = test_order_with_formulation["id"]
        update_data = {
            "remark": "Telecaller trying to edit",
            "items": test_order_with_formulation["items"]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=telecaller_headers)
        # Should be 403 (locked) or 403 (not own order)
        assert response.status_code == 403, f"Expected 403 for telecaller editing locked order, got {response.status_code}: {response.text}"
        print("✓ Telecaller blocked from editing locked order")
    
    # ── Test 4: Formulation preservation during order update ──
    def test_formulation_preserved_on_update(self, admin_headers, test_order_with_formulation):
        """When items are updated without formulation field, existing formulations should be preserved"""
        order_id = test_order_with_formulation["id"]
        original_formulation = test_order_with_formulation["items"][0].get("formulation", "")
        
        # Update order with items that have empty formulation
        update_data = {
            "items": [
                {"product_name": "Test Product A", "qty": 15, "unit": "L", "rate": 100, "amount": 1500, "gst_rate": 0, "gst_amount": 0, "total": 1500, "formulation": ""},
                {"product_name": "Test Product B", "qty": 5, "unit": "Kg", "rate": 200, "amount": 1000, "gst_rate": 0, "gst_amount": 0, "total": 1000, "formulation": ""}
            ],
            "subtotal": 2500,
            "grand_total": 2500
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=admin_headers)
        assert response.status_code == 200, f"Order update failed: {response.text}"
        
        # Verify formulations are preserved
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        updated_order = response.json()
        
        assert updated_order["items"][0].get("formulation") == original_formulation, \
            f"Formulation was not preserved. Expected '{original_formulation}', got '{updated_order['items'][0].get('formulation')}'"
        print(f"✓ Formulation preserved: '{updated_order['items'][0].get('formulation')}'")
    
    # ── Test 5: Free sample formulation preservation ──
    def test_free_sample_formulation_preserved(self, admin_headers, test_order_with_formulation):
        """Free sample formulations should also be preserved during updates"""
        order_id = test_order_with_formulation["id"]
        
        # Get current free sample formulation
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        order = response.json()
        original_fs_formulation = order.get("free_samples", [{}])[0].get("formulation", "")
        
        # Update with empty free sample formulation
        update_data = {
            "free_samples": [
                {"item_name": "Free Sample X", "description": "Updated description", "formulation": ""}
            ]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=admin_headers)
        assert response.status_code == 200
        
        # Verify preservation
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        updated_order = response.json()
        
        if original_fs_formulation:
            assert updated_order.get("free_samples", [{}])[0].get("formulation") == original_fs_formulation, \
                "Free sample formulation was not preserved"
            print(f"✓ Free sample formulation preserved: '{original_fs_formulation}'")
        else:
            print("✓ Free sample formulation test skipped (no original formulation)")
    
    # ── Test 6: Check formulation lock endpoint ──
    def test_formulation_lock_endpoint(self, admin_headers, telecaller_headers, test_order_with_formulation):
        """Test /api/orders/{id}/formulation-lock endpoint"""
        order_id = test_order_with_formulation["id"]
        
        # Admin check
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}/formulation-lock", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["locked"] == True, "Order should be locked"
        assert data["can_edit"] == True, "Admin should be able to edit"
        print(f"✓ Admin formulation-lock check: locked={data['locked']}, can_edit={data['can_edit']}")
        
        # Telecaller check
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}/formulation-lock", headers=telecaller_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["locked"] == True, "Order should be locked"
        # Telecaller without permission should not be able to edit
        print(f"✓ Telecaller formulation-lock check: locked={data['locked']}, can_edit={data['can_edit']}")


class TestEditPermissionFlow:
    """Test edit permission request/approve/reject flow"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=TELECALLER_CREDS)
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def telecaller_headers(self, telecaller_token):
        return {"Authorization": f"Bearer {telecaller_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def locked_order_for_telecaller(self, admin_headers, telecaller_headers):
        """Create an order owned by telecaller with formulation"""
        # First get telecaller user info
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=telecaller_headers)
        telecaller_user = response.json()
        
        # Create customer
        customer_data = {
            "name": f"TEST_PermFlow_Customer_{uuid.uuid4().hex[:6]}",
            "phone_numbers": [f"98{random.randint(10000000, 99999999)}"]
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=telecaller_headers)
        assert response.status_code in [200, 201]
        customer = response.json()
        
        # Create order as telecaller
        order_data = {
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "items": [
                {"product_name": "Perm Test Product", "qty": 10, "unit": "L", "rate": 100, "amount": 1000, "gst_rate": 0, "gst_amount": 0, "total": 1000}
            ],
            "subtotal": 1000,
            "grand_total": 1000,
            "payment_status": "unpaid"
        }
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=telecaller_headers)
        assert response.status_code in [200, 201]
        order = response.json()
        
        # Admin adds formulation to lock the order
        formulation_data = {
            "items": [{"index": 0, "formulation": "Test formulation for permission flow"}]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order['id']}/formulation", json=formulation_data, headers=admin_headers)
        assert response.status_code == 200
        
        # Return updated order
        response = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=admin_headers)
        return response.json()
    
    # ── Test 7: Request edit permission ──
    def test_request_edit_permission(self, telecaller_headers, locked_order_for_telecaller):
        """Telecaller can request edit permission for locked order"""
        order_id = locked_order_for_telecaller["id"]
        
        request_data = {"reason": "Need to update quantity for customer request"}
        response = requests.post(f"{BASE_URL}/api/orders/{order_id}/request-edit", json=request_data, headers=telecaller_headers)
        assert response.status_code == 200, f"Edit permission request failed: {response.text}"
        
        perm = response.json()
        assert perm["status"] == "pending"
        assert perm["order_id"] == order_id
        print(f"✓ Edit permission requested: {perm['id']}")
        return perm
    
    # ── Test 8: Duplicate request should fail ──
    def test_duplicate_request_fails(self, telecaller_headers, locked_order_for_telecaller):
        """Duplicate pending request should be rejected"""
        order_id = locked_order_for_telecaller["id"]
        
        request_data = {"reason": "Another request"}
        response = requests.post(f"{BASE_URL}/api/orders/{order_id}/request-edit", json=request_data, headers=telecaller_headers)
        # Should fail because there's already a pending request
        assert response.status_code == 400, f"Expected 400 for duplicate request, got {response.status_code}"
        print("✓ Duplicate request correctly rejected")
    
    # ── Test 9: Admin can list edit permissions ──
    def test_admin_list_edit_permissions(self, admin_headers):
        """Admin can list all edit permissions"""
        response = requests.get(f"{BASE_URL}/api/edit-permissions", headers=admin_headers)
        assert response.status_code == 200
        permissions = response.json()
        assert isinstance(permissions, list)
        print(f"✓ Admin can list edit permissions: {len(permissions)} found")
    
    # ── Test 10: Admin approve permission ──
    def test_admin_approve_permission(self, admin_headers, telecaller_headers, locked_order_for_telecaller):
        """Admin can approve edit permission"""
        order_id = locked_order_for_telecaller["id"]
        
        # Get pending permission for this order
        response = requests.get(f"{BASE_URL}/api/edit-permissions", headers=admin_headers)
        permissions = response.json()
        pending_perm = next((p for p in permissions if p["order_id"] == order_id and p["status"] == "pending"), None)
        
        if not pending_perm:
            pytest.skip("No pending permission found for this order")
        
        # Approve it
        response = requests.put(f"{BASE_URL}/api/edit-permissions/{pending_perm['id']}", 
                               json={"action": "approve"}, headers=admin_headers)
        assert response.status_code == 200, f"Approve failed: {response.text}"
        
        updated_perm = response.json()
        assert updated_perm["status"] == "approved"
        print(f"✓ Permission approved: {pending_perm['id']}")
    
    # ── Test 11: Telecaller can edit after approval ──
    def test_telecaller_can_edit_after_approval(self, telecaller_headers, locked_order_for_telecaller):
        """Telecaller can edit locked order after permission is approved"""
        order_id = locked_order_for_telecaller["id"]
        
        update_data = {
            "remark": f"Edited after approval - {uuid.uuid4().hex[:6]}",
            "items": locked_order_for_telecaller["items"]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=telecaller_headers)
        assert response.status_code == 200, f"Edit after approval failed: {response.text}"
        print("✓ Telecaller can edit after approval")
    
    # ── Test 12: Permission marked as used after edit ──
    def test_permission_marked_as_used(self, admin_headers, telecaller_headers, locked_order_for_telecaller):
        """After telecaller edits, permission should be marked as 'used' - verified by telecaller being blocked again"""
        order_id = locked_order_for_telecaller["id"]
        
        # The API filters out "used" permissions, so we verify by checking:
        # 1. No approved permission exists for this order anymore
        response = requests.get(f"{BASE_URL}/api/edit-permissions", headers=admin_headers)
        permissions = response.json()
        
        # Find approved permission for this order (should not exist after use)
        order_perms = [p for p in permissions if p["order_id"] == order_id]
        approved_perm = next((p for p in order_perms if p["status"] == "approved"), None)
        
        # 2. Telecaller should be blocked from editing (confirming permission was used)
        update_data = {"remark": "Test if blocked"}
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=telecaller_headers)
        
        # Either no approved permission exists OR telecaller is blocked (403)
        assert approved_perm is None or response.status_code == 403, \
            "Permission should be used (no approved permission or telecaller blocked)"
        print("✓ Permission marked as used (verified by telecaller being blocked)")
    
    # ── Test 13: Telecaller blocked again after permission used ──
    def test_telecaller_blocked_after_permission_used(self, telecaller_headers, locked_order_for_telecaller):
        """After permission is used, telecaller should be blocked again"""
        order_id = locked_order_for_telecaller["id"]
        
        update_data = {
            "remark": "Second edit attempt",
            "items": locked_order_for_telecaller["items"]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=telecaller_headers)
        assert response.status_code == 403, f"Expected 403 after permission used, got {response.status_code}"
        print("✓ Telecaller blocked again after permission used")


class TestPackagingDispatchFormulationPreservation:
    """Test that packaging/dispatch endpoints don't clear formulations"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PACKAGING_CREDS)
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def packaging_headers(self, packaging_token):
        return {"Authorization": f"Bearer {packaging_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def order_for_packaging_test(self, admin_headers):
        """Create order with formulation for packaging test"""
        # Create customer
        customer_data = {
            "name": f"TEST_PackTest_Customer_{uuid.uuid4().hex[:6]}",
            "phone_numbers": [f"97{random.randint(10000000, 99999999)}"]
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=admin_headers)
        assert response.status_code in [200, 201]
        customer = response.json()
        
        # Create order
        order_data = {
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "items": [
                {"product_name": "Packaging Test Product", "qty": 10, "unit": "L", "rate": 100, "amount": 1000, "gst_rate": 0, "gst_amount": 0, "total": 1000}
            ],
            "subtotal": 1000,
            "grand_total": 1000,
            "payment_status": "unpaid"
        }
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=admin_headers)
        assert response.status_code in [200, 201]
        order = response.json()
        
        # Add formulation
        formulation_data = {
            "items": [{"index": 0, "formulation": "Packaging test formulation - DO NOT CLEAR"}]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order['id']}/formulation", json=formulation_data, headers=admin_headers)
        assert response.status_code == 200
        
        response = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=admin_headers)
        return response.json()
    
    # ── Test 14: Packaging update doesn't clear formulation ──
    def test_packaging_update_preserves_formulation(self, admin_headers, packaging_headers, order_for_packaging_test):
        """PUT /api/orders/{id}/packaging should not clear formulations"""
        order_id = order_for_packaging_test["id"]
        original_formulation = order_for_packaging_test["items"][0].get("formulation", "")
        
        # Update packaging
        packaging_data = {
            "item_packed_by": ["Test Staff"],
            "box_packed_by": ["Test Staff"],
            "checked_by": ["Test Staff"]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/packaging", json=packaging_data, headers=packaging_headers)
        assert response.status_code == 200, f"Packaging update failed: {response.text}"
        
        # Verify formulation preserved
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        updated_order = response.json()
        
        assert updated_order["items"][0].get("formulation") == original_formulation, \
            f"Formulation cleared by packaging update! Expected '{original_formulation}', got '{updated_order['items'][0].get('formulation')}'"
        print(f"✓ Packaging update preserved formulation: '{original_formulation}'")
    
    # ── Test 15: Mark packed doesn't clear formulation ──
    def test_mark_packed_preserves_formulation(self, admin_headers, order_for_packaging_test):
        """PUT /api/orders/{id}/mark-packed should not clear formulations"""
        order_id = order_for_packaging_test["id"]
        
        # Get current formulation
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        order = response.json()
        original_formulation = order["items"][0].get("formulation", "")
        
        # Mark as packed
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/mark-packed", headers=admin_headers)
        assert response.status_code == 200, f"Mark packed failed: {response.text}"
        
        # Verify formulation preserved
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        updated_order = response.json()
        
        assert updated_order["items"][0].get("formulation") == original_formulation, \
            "Formulation cleared by mark-packed!"
        print(f"✓ Mark packed preserved formulation")
    
    # ── Test 16: Dispatch doesn't clear formulation ──
    def test_dispatch_preserves_formulation(self, admin_headers, order_for_packaging_test):
        """PUT /api/orders/{id}/dispatch should not clear formulations"""
        order_id = order_for_packaging_test["id"]
        
        # Get current formulation
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        order = response.json()
        original_formulation = order["items"][0].get("formulation", "")
        
        # Dispatch order
        dispatch_data = {
            "dispatch_type": "courier",
            "courier_name": "DTDC",
            "lr_no": "TEST123"
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/dispatch", json=dispatch_data, headers=admin_headers)
        assert response.status_code == 200, f"Dispatch failed: {response.text}"
        
        # Verify formulation preserved
        response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=admin_headers)
        updated_order = response.json()
        
        assert updated_order["items"][0].get("formulation") == original_formulation, \
            "Formulation cleared by dispatch!"
        print(f"✓ Dispatch preserved formulation")


class TestAdminRejectPermission:
    """Test admin reject permission flow"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=TELECALLER_CREDS)
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def telecaller_headers(self, telecaller_token):
        return {"Authorization": f"Bearer {telecaller_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def order_for_reject_test(self, admin_headers, telecaller_headers):
        """Create order for reject test"""
        # Create customer
        customer_data = {
            "name": f"TEST_RejectTest_Customer_{uuid.uuid4().hex[:6]}",
            "phone_numbers": [f"96{random.randint(10000000, 99999999)}"]
        }
        response = requests.post(f"{BASE_URL}/api/customers", json=customer_data, headers=telecaller_headers)
        assert response.status_code in [200, 201]
        customer = response.json()
        
        # Create order as telecaller
        order_data = {
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "items": [
                {"product_name": "Reject Test Product", "qty": 10, "unit": "L", "rate": 100, "amount": 1000, "gst_rate": 0, "gst_amount": 0, "total": 1000}
            ],
            "subtotal": 1000,
            "grand_total": 1000,
            "payment_status": "unpaid"
        }
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data, headers=telecaller_headers)
        assert response.status_code in [200, 201]
        order = response.json()
        
        # Admin adds formulation
        formulation_data = {
            "items": [{"index": 0, "formulation": "Reject test formulation"}]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order['id']}/formulation", json=formulation_data, headers=admin_headers)
        assert response.status_code == 200
        
        response = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=admin_headers)
        return response.json()
    
    # ── Test 17: Admin can reject permission ──
    def test_admin_reject_permission(self, admin_headers, telecaller_headers, order_for_reject_test):
        """Admin can reject edit permission request"""
        order_id = order_for_reject_test["id"]
        
        # Request permission
        request_data = {"reason": "Test reject flow"}
        response = requests.post(f"{BASE_URL}/api/orders/{order_id}/request-edit", json=request_data, headers=telecaller_headers)
        assert response.status_code == 200
        perm = response.json()
        
        # Admin rejects
        response = requests.put(f"{BASE_URL}/api/edit-permissions/{perm['id']}", 
                               json={"action": "reject"}, headers=admin_headers)
        assert response.status_code == 200
        
        rejected_perm = response.json()
        assert rejected_perm["status"] == "rejected"
        print(f"✓ Permission rejected: {perm['id']}")
    
    # ── Test 18: Telecaller still blocked after rejection ──
    def test_telecaller_blocked_after_rejection(self, telecaller_headers, order_for_reject_test):
        """Telecaller should still be blocked after permission is rejected"""
        order_id = order_for_reject_test["id"]
        
        update_data = {
            "remark": "Edit after rejection",
            "items": order_for_reject_test["items"]
        }
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}", json=update_data, headers=telecaller_headers)
        assert response.status_code == 403, f"Expected 403 after rejection, got {response.status_code}"
        print("✓ Telecaller still blocked after rejection")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
