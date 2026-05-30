"""
Test Suite for Bulk Packaging Sheet Printing Feature:
1. Access control: Admin, Packaging, Accounts roles are allowed.
2. Requesting bulk packing sheets returns a valid PDF binary.
3. Error handling: returns 400 for empty selection.
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://127.0.0.1:8000').rstrip('/')

ADMIN_CREDS = {"username": "admin", "password": "admin123"}


class TestBulkPackingSheets:
    """Test /orders/print-packing-sheets endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin and dynamically create packaging and telecaller users"""
        # Login as Admin
        admin_resp = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert admin_resp.status_code == 200, f"Admin login failed: {admin_resp.text}"
        self.admin_token = admin_resp.json()["token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # Create packaging user dynamically
        pkg_username = f"pkg_{int(time.time() * 1000)}"
        pkg_payload = {
            "username": pkg_username,
            "password": "testpassword123",
            "name": "Test Packaging User",
            "role": "packaging"
        }
        create_pkg_resp = requests.post(f"{BASE_URL}/api/users", headers=self.admin_headers, json=pkg_payload)
        assert create_pkg_resp.status_code == 200, f"Failed to create packaging user: {create_pkg_resp.text}"

        # Login as Packaging User
        pkg_resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": pkg_username, "password": "testpassword123"})
        assert pkg_resp.status_code == 200, f"Packaging login failed: {pkg_resp.text}"
        self.pkg_token = pkg_resp.json()["token"]
        self.pkg_headers = {"Authorization": f"Bearer {self.pkg_token}"}

        # Create telecaller user dynamically
        tc_username = f"tc_{int(time.time() * 1000)}"
        tc_payload = {
            "username": tc_username,
            "password": "testpassword123",
            "name": "Test Telecaller User",
            "role": "telecaller"
        }
        create_tc_resp = requests.post(f"{BASE_URL}/api/users", headers=self.admin_headers, json=tc_payload)
        assert create_tc_resp.status_code == 200, f"Failed to create telecaller user: {create_tc_resp.text}"

        # Login as Telecaller User
        tc_resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": tc_username, "password": "testpassword123"})
        assert tc_resp.status_code == 200, f"Telecaller login failed: {tc_resp.text}"
        self.tc_token = tc_resp.json()["token"]
        self.tc_headers = {"Authorization": f"Bearer {self.tc_token}"}

    def test_print_bulk_packing_sheets_admin(self):
        """Test printing multiple packing sheets as admin"""
        # Fetch some orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders?page_size=5", headers=self.admin_headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json().get("orders", [])
        assert len(orders) > 0, "No orders available for testing"

        order_ids = [o["id"] for o in orders[:2]]  # select up to 2 orders

        # Request bulk print PDF
        response = requests.post(
            f"{BASE_URL}/api/orders/print-packing-sheets",
            headers=self.admin_headers,
            json={"order_ids": order_ids}
        )
        assert response.status_code == 200, f"Bulk print failed: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 0
        print(f"PASS: Admin successfully printed packaging sheets for {len(order_ids)} orders")

    def test_print_bulk_packing_sheets_packaging(self):
        """Test printing multiple packing sheets as packaging staff"""
        # Fetch some orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders?page_size=5", headers=self.pkg_headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json().get("orders", [])
        assert len(orders) > 0, "No orders available for testing"

        order_ids = [orders[0]["id"]]

        # Request bulk print PDF
        response = requests.post(
            f"{BASE_URL}/api/orders/print-packing-sheets",
            headers=self.pkg_headers,
            json={"order_ids": order_ids}
        )
        assert response.status_code == 200, f"Bulk print failed: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        print("PASS: Packaging staff successfully printed packaging sheets")

    def test_print_bulk_packing_sheets_telecaller_forbidden(self):
        """Test that a telecaller is forbidden from printing packaging sheets"""
        # Fetch some orders
        orders_resp = requests.get(f"{BASE_URL}/api/orders?page_size=5", headers=self.admin_headers)
        assert orders_resp.status_code == 200
        orders = orders_resp.json().get("orders", [])
        assert len(orders) > 0

        order_ids = [orders[0]["id"]]

        # Request bulk print PDF (should return 403 Forbidden)
        response = requests.post(
            f"{BASE_URL}/api/orders/print-packing-sheets",
            headers=self.tc_headers,
            json={"order_ids": order_ids}
        )
        assert response.status_code == 403, f"Expected 403 Forbidden, got {response.status_code}"
        print("PASS: Telecaller is correctly forbidden from printing bulk packaging sheets")

    def test_print_bulk_packing_sheets_empty_ids(self):
        """Test requesting bulk print with an empty selection returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/orders/print-packing-sheets",
            headers=self.admin_headers,
            json={"order_ids": []}
        )
        assert response.status_code == 400, f"Expected 400 Bad Request, got {response.status_code}"
        print("PASS: Empty order list correctly returns 400 Bad Request")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
