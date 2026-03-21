"""
Phase 7 Backend Tests - CitSpray Order Management System
Tests: Edit Order, PI Conversion, Image Delete, Notifications, Print Addresses
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]

@pytest.fixture(scope="module")
def admin_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}

@pytest.fixture(scope="module")
def test_customer_id(admin_headers):
    """Get or create a test customer"""
    resp = requests.get(f"{BASE_URL}/api/customers", headers=admin_headers)
    customers = resp.json()
    if customers:
        return customers[0]["id"]
    # Create one
    resp = requests.post(f"{BASE_URL}/api/customers", json={
        "name": "TEST_Phase7_Customer",
        "phone_numbers": ["+919876543210"],
        "gst_no": "",
        "email": ""
    }, headers=admin_headers)
    assert resp.status_code == 200
    return resp.json()["id"]

@pytest.fixture(scope="module")
def test_order(admin_headers, test_customer_id):
    """Create a test order for testing"""
    payload = {
        "customer_id": test_customer_id,
        "purpose": "TEST Phase7 Purpose",
        "items": [{"product_name": "TEST Product A", "qty": 5, "unit": "L", "rate": 100, "amount": 500, "gst_rate": 0, "gst_amount": 0, "total": 500, "description": "Test item"}],
        "gst_applicable": False,
        "shipping_method": "courier",
        "courier_name": "DTDC",
        "shipping_charge": 50,
        "shipping_gst": 0,
        "remark": "TEST Phase7 remark",
        "payment_status": "unpaid",
        "amount_paid": 0,
        "payment_screenshots": [],
        "mode_of_payment": "Cash",
        "payment_mode_details": "",
        "free_samples": [],
        "billing_address_id": "",
        "shipping_address_id": ""
    }
    resp = requests.post(f"{BASE_URL}/api/orders", json=payload, headers=admin_headers)
    assert resp.status_code == 200, f"Order creation failed: {resp.text}"
    return resp.json()

# ─── AUTH TESTS ───────────────────────────────────────────────────────────────
class TestAuth:
    """Authentication tests"""

    def test_admin_login_success(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "wrongpass"})
        assert resp.status_code in [401, 400]

# ─── MY-NOTIFICATIONS ENDPOINT ────────────────────────────────────────────────
class TestMyNotifications:
    """Tests for /orders/my-notifications endpoint"""

    def test_admin_gets_empty_notifications(self, admin_headers):
        """Admin should get empty list (only for telecallers)"""
        resp = requests.get(f"{BASE_URL}/api/orders/my-notifications", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data == [], f"Expected empty list for admin, got: {data}"

    def test_notifications_with_since_param(self, admin_headers):
        """Endpoint works with since parameter"""
        import urllib.parse
        since = "2024-01-01T00:00:00.000Z"
        resp = requests.get(
            f"{BASE_URL}/api/orders/my-notifications?since={urllib.parse.quote(since)}",
            headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_notifications_unauthenticated(self):
        """Without auth token should fail"""
        resp = requests.get(f"{BASE_URL}/api/orders/my-notifications")
        assert resp.status_code in [401, 403]

# ─── EDIT ORDER TESTS ─────────────────────────────────────────────────────────
class TestEditOrder:
    """Tests for order editing (PUT /orders/{id})"""

    def test_get_order_for_edit(self, admin_headers, test_order):
        """Admin can fetch order by ID"""
        oid = test_order["id"]
        resp = requests.get(f"{BASE_URL}/api/orders/{oid}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == oid
        assert "items" in data
        assert "payment_status" in data

    def test_admin_can_update_order(self, admin_headers, test_order):
        """Admin can update order fields"""
        oid = test_order["id"]
        update_payload = {
            "purpose": "TEST Phase7 Updated Purpose",
            "remark": "Updated remark for phase7",
            "payment_status": "partial",
            "amount_paid": 200,
            "balance_amount": 351
        }
        resp = requests.put(f"{BASE_URL}/api/orders/{oid}", json=update_payload, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["purpose"] == "TEST Phase7 Updated Purpose"
        assert data["payment_status"] == "partial"

    def test_update_order_persists(self, admin_headers, test_order):
        """Updated order values persist (GET after PUT)"""
        oid = test_order["id"]
        # First update
        resp = requests.put(f"{BASE_URL}/api/orders/{oid}", json={"remark": "Persist check remark"}, headers=admin_headers)
        assert resp.status_code == 200
        # Verify with GET
        get_resp = requests.get(f"{BASE_URL}/api/orders/{oid}", headers=admin_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["remark"] == "Persist check remark"

    def test_update_order_items(self, admin_headers, test_order):
        """Admin can update order items"""
        oid = test_order["id"]
        new_items = [
            {"product_name": "TEST Product Updated", "qty": 10, "unit": "Kg", "rate": 200,
             "amount": 2000, "gst_rate": 0, "gst_amount": 0, "total": 2000, "description": "Updated"}
        ]
        resp = requests.put(f"{BASE_URL}/api/orders/{oid}", json={"items": new_items}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["product_name"] == "TEST Product Updated"

# ─── FORMULATION TESTS ────────────────────────────────────────────────────────
class TestFormulation:
    """Tests for formulation saving"""

    def test_save_formulation(self, admin_headers, test_order):
        """Admin can save formulations for order items"""
        oid = test_order["id"]
        formulation_payload = {
            "items": [{"product_name": "TEST Product Updated", "formulation": "Test formulation - citronella 10ml, lemon 5ml"}]
        }
        resp = requests.put(f"{BASE_URL}/api/orders/{oid}/formulation", json=formulation_payload, headers=admin_headers)
        assert resp.status_code == 200

    def test_formulation_persists(self, admin_headers, test_order):
        """Formulation data persists after save"""
        oid = test_order["id"]
        # Save formulation
        formulation_payload = {
            "items": [{"product_name": "TEST Product Updated", "formulation": "Persistent formulation test"}]
        }
        requests.put(f"{BASE_URL}/api/orders/{oid}/formulation", json=formulation_payload, headers=admin_headers)
        # Verify with GET
        get_resp = requests.get(f"{BASE_URL}/api/orders/{oid}", headers=admin_headers)
        assert get_resp.status_code == 200
        items = get_resp.json().get("items", [])
        assert len(items) > 0
        assert items[0].get("formulation") == "Persistent formulation test"

# ─── IMAGE DELETE TESTS ───────────────────────────────────────────────────────
class TestImageDelete:
    """Tests for image deletion endpoint"""

    def test_image_delete_endpoint_exists(self, admin_headers, test_order):
        """DELETE /orders/{id}/images endpoint responds"""
        oid = test_order["id"]
        import urllib.parse
        # Try to delete a non-existent image (should still return 200 or remove it gracefully)
        fake_url = "/uploads/test_nonexistent.jpg"
        resp = requests.delete(
            f"{BASE_URL}/api/orders/{oid}/images",
            params={"image_type": "payment", "image_url": fake_url},
            headers=admin_headers
        )
        # Should return 200 (graceful - just remove if exists, no-op if not)
        assert resp.status_code == 200

    def test_image_delete_invalid_type(self, admin_headers, test_order):
        """DELETE with invalid image_type should fail"""
        oid = test_order["id"]
        resp = requests.delete(
            f"{BASE_URL}/api/orders/{oid}/images",
            params={"image_type": "invalid_type", "image_url": "/uploads/test.jpg"},
            headers=admin_headers
        )
        assert resp.status_code == 400

    def test_image_delete_unauthorized(self, test_order):
        """Without auth, image delete should fail"""
        oid = test_order["id"]
        resp = requests.delete(
            f"{BASE_URL}/api/orders/{oid}/images",
            params={"image_type": "payment", "image_url": "/uploads/test.jpg"}
        )
        assert resp.status_code in [401, 403]

# ─── PRINT ADDRESSES TESTS ────────────────────────────────────────────────────
class TestPrintAddresses:
    """Tests for bulk address printing"""

    def test_print_addresses_generates_pdf(self, admin_headers, test_order):
        """POST /orders/print-addresses returns PDF binary"""
        oid = test_order["id"]
        resp = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            json={"order_ids": [oid]},
            headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/pdf"
        assert len(resp.content) > 100  # Non-empty PDF

    def test_print_addresses_empty_list_fails(self, admin_headers):
        """Empty order_ids should return 400"""
        resp = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            json={"order_ids": []},
            headers=admin_headers
        )
        assert resp.status_code == 400

    def test_print_addresses_invalid_ids(self, admin_headers):
        """Invalid order IDs should return 404"""
        resp = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            json={"order_ids": ["nonexistent_order_id_xyz"]},
            headers=admin_headers
        )
        assert resp.status_code == 404

    def test_print_addresses_unauthorized(self, test_order):
        """Without auth, should fail"""
        resp = requests.post(
            f"{BASE_URL}/api/orders/print-addresses",
            json={"order_ids": [test_order["id"]]}
        )
        assert resp.status_code in [401, 403]

# ─── PI CONVERSION TESTS ──────────────────────────────────────────────────────
class TestPIConversion:
    """Tests for PI to Order conversion (backend side)"""

    def test_get_proforma_invoices(self, admin_headers):
        """Can list proforma invoices"""
        resp = requests.get(f"{BASE_URL}/api/proforma-invoices", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_pi_and_fetch(self, admin_headers, test_customer_id):
        """Create PI, fetch it to verify it exists"""
        payload = {
            "customer_id": test_customer_id,
            "purpose": "TEST Phase7 PI",
            "items": [{"product_name": "TEST PI Item", "qty": 3, "unit": "L", "rate": 150, "amount": 450,
                       "gst_rate": 0, "gst_amount": 0, "total": 450, "description": ""}],
            "gst_applicable": False,
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "shipping_charge": 0,
            "remark": "",
            "free_samples": [],
            "billing_address_id": "",
            "shipping_address_id": ""
        }
        create_resp = requests.post(f"{BASE_URL}/api/proforma-invoices", json=payload, headers=admin_headers)
        assert create_resp.status_code == 200
        pi_data = create_resp.json()
        pi_id = pi_data["id"]

        # Fetch the PI
        get_resp = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}", headers=admin_headers)
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        assert fetched["id"] == pi_id
        assert fetched["remark"] == "" or fetched.get("remark") is not None
        # Verify PI items are persisted
        assert len(fetched.get("items", [])) == 1
        assert fetched["items"][0]["product_name"] == "TEST PI Item"

# ─── USER MANAGEMENT TESTS ────────────────────────────────────────────────────
class TestUserManagement:
    """Tests for user management - delete button removed"""

    def test_list_users(self, admin_headers):
        """Admin can list users"""
        resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_update_user(self, admin_headers):
        """Create user and update (edit flow)"""
        create_resp = requests.post(f"{BASE_URL}/api/users", json={
            "username": "TEST_phase7_user",
            "password": "testpass123",
            "name": "TEST Phase7 User",
            "role": "telecaller"
        }, headers=admin_headers)
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]

        # Update user
        update_resp = requests.put(f"{BASE_URL}/api/users/{user_id}", json={
            "name": "TEST Phase7 User Updated",
            "role": "packaging"
        }, headers=admin_headers)
        assert update_resp.status_code == 200

        # Verify update
        get_resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        users = get_resp.json()
        updated = next((u for u in users if u["id"] == user_id), None)
        assert updated is not None
        assert updated["name"] == "TEST Phase7 User Updated"
        assert updated["role"] == "packaging"

        # Cleanup
        requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=admin_headers)

    def test_admin_user_exists(self, admin_headers):
        """Admin user is in user list"""
        resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        users = resp.json()
        admin_users = [u for u in users if u["role"] == "admin"]
        assert len(admin_users) > 0

# ─── ORDERS LIST TESTS ────────────────────────────────────────────────────────
class TestAllOrders:
    """Tests for orders listing"""

    def test_admin_gets_all_orders(self, admin_headers):
        """Admin can get all orders with view_all=true"""
        resp = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_orders_have_required_fields(self, admin_headers):
        """Orders contain required fields"""
        resp = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=admin_headers)
        orders = resp.json()
        if orders:
            order = orders[0]
            required_fields = ["id", "order_number", "customer_name", "status", "grand_total"]
            for field in required_fields:
                assert field in order, f"Missing field: {field}"
