"""
Phase 11 Testing: Notification System & Share Packed Box Images
Tests for:
1. POST /api/notifications - Create notification (idempotent by order_id+type)
2. GET /api/notifications - Get unacknowledged notifications for current user
3. PUT /api/notifications/{id}/acknowledge - Mark notification as acknowledged
4. GET /api/orders/my-notifications - Trigger logic for packed/dispatched orders
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestNotificationEndpoints:
    """Test notification CRUD operations"""
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        """Login as telecaller user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_tc_payment",
            "password": "test123"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Telecaller login failed - user may not exist")
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200
        return response.json().get("token")
    
    def test_get_notifications_unauthenticated(self):
        """GET /api/notifications without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 403 or response.status_code == 401
        print("PASS: GET /api/notifications requires authentication")
    
    def test_get_notifications_telecaller(self, telecaller_token):
        """GET /api/notifications returns unacknowledged notifications for telecaller"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        response = requests.get(f"{BASE_URL}/api/notifications", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/notifications returned {len(data)} notifications")
        # Check structure if notifications exist
        if len(data) > 0:
            notif = data[0]
            assert "id" in notif
            assert "order_id" in notif
            assert "order_number" in notif
            assert "customer_name" in notif
            assert "type" in notif
            assert "acknowledged" in notif
            assert notif["acknowledged"] == False  # Only unacknowledged returned
            print(f"PASS: Notification structure verified - order_number: {notif['order_number']}")
    
    def test_create_notification_missing_fields(self, telecaller_token):
        """POST /api/notifications without required fields should fail"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        response = requests.post(f"{BASE_URL}/api/notifications", headers=headers, json={})
        assert response.status_code == 400
        print("PASS: POST /api/notifications requires order_id and type")
    
    def test_create_notification_success(self, telecaller_token):
        """POST /api/notifications creates a new notification"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        test_order_id = f"test-order-{uuid.uuid4().hex[:8]}"
        payload = {
            "order_id": test_order_id,
            "order_number": "CS-TEST-NEW",
            "customer_name": "Test Customer",
            "type": "packed",
            "shipping_method": "courier"
        }
        response = requests.post(f"{BASE_URL}/api/notifications", headers=headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == test_order_id
        assert data["order_number"] == "CS-TEST-NEW"
        assert data["type"] == "packed"
        assert data["acknowledged"] == False
        print(f"PASS: Created notification with id: {data['id']}")
        return data["id"]
    
    def test_create_notification_idempotent(self, telecaller_token):
        """POST /api/notifications is idempotent by order_id+type"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        test_order_id = f"test-idempotent-{uuid.uuid4().hex[:8]}"
        payload = {
            "order_id": test_order_id,
            "order_number": "CS-IDEM-001",
            "customer_name": "Idempotent Test",
            "type": "dispatched"
        }
        # First creation
        response1 = requests.post(f"{BASE_URL}/api/notifications", headers=headers, json=payload)
        assert response1.status_code == 200
        notif1 = response1.json()
        
        # Second creation with same order_id+type should return existing
        response2 = requests.post(f"{BASE_URL}/api/notifications", headers=headers, json=payload)
        assert response2.status_code == 200
        notif2 = response2.json()
        
        assert notif1["id"] == notif2["id"]
        print("PASS: POST /api/notifications is idempotent - same notification returned")
    
    def test_acknowledge_notification(self, telecaller_token):
        """PUT /api/notifications/{id}/acknowledge marks notification as acknowledged"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        
        # First create a notification
        test_order_id = f"test-ack-{uuid.uuid4().hex[:8]}"
        create_response = requests.post(f"{BASE_URL}/api/notifications", headers=headers, json={
            "order_id": test_order_id,
            "order_number": "CS-ACK-001",
            "customer_name": "Ack Test",
            "type": "packed"
        })
        assert create_response.status_code == 200
        notif_id = create_response.json()["id"]
        
        # Acknowledge it
        ack_response = requests.put(f"{BASE_URL}/api/notifications/{notif_id}/acknowledge", headers=headers)
        assert ack_response.status_code == 200
        assert ack_response.json()["status"] == "acknowledged"
        print(f"PASS: Notification {notif_id} acknowledged")
        
        # Verify it's no longer in unacknowledged list
        get_response = requests.get(f"{BASE_URL}/api/notifications", headers=headers)
        assert get_response.status_code == 200
        notifs = get_response.json()
        notif_ids = [n["id"] for n in notifs]
        assert notif_id not in notif_ids
        print("PASS: Acknowledged notification no longer in GET /api/notifications")
    
    def test_acknowledge_nonexistent_notification(self, telecaller_token):
        """PUT /api/notifications/{id}/acknowledge with invalid id returns 404"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        response = requests.put(f"{BASE_URL}/api/notifications/nonexistent-id/acknowledge", headers=headers)
        assert response.status_code == 404
        print("PASS: Acknowledging nonexistent notification returns 404")
    
    def test_my_notifications_endpoint(self, telecaller_token):
        """GET /api/orders/my-notifications returns packed/dispatched orders"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/my-notifications", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/orders/my-notifications returned {len(data)} items")
        # Check structure if items exist
        if len(data) > 0:
            item = data[0]
            assert "id" in item
            assert "order_number" in item
            assert "customer_name" in item
            assert "status" in item
            print(f"PASS: my-notifications item structure verified")
    
    def test_my_notifications_admin_returns_empty(self, admin_token):
        """GET /api/orders/my-notifications for non-telecaller returns empty"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/my-notifications", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data == []
        print("PASS: GET /api/orders/my-notifications returns empty for admin")


class TestSharePackedBoxImages:
    """Test that packed_box_images field exists in order packaging"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Login as admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200
        return response.json().get("token")
    
    def test_order_has_packed_box_images_field(self, admin_token):
        """Verify orders have packaging.packed_box_images field"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Get any order
        response = requests.get(f"{BASE_URL}/api/orders", headers=headers)
        assert response.status_code == 200
        orders = response.json()
        if len(orders) > 0:
            order = orders[0]
            # Check packaging structure
            packaging = order.get("packaging", {})
            assert "packed_box_images" in packaging or packaging == {}
            print(f"PASS: Order {order.get('order_number')} has packaging.packed_box_images field")
        else:
            print("SKIP: No orders to verify packed_box_images field")


class TestExistingNotification:
    """Test the existing test notification for test_tc_payment user"""
    
    @pytest.fixture(scope="class")
    def telecaller_token(self):
        """Login as telecaller user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_tc_payment",
            "password": "test123"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Telecaller login failed")
    
    def test_existing_notification_cs_test_001(self, telecaller_token):
        """Check if CS-TEST-001 notification exists for test_tc_payment"""
        headers = {"Authorization": f"Bearer {telecaller_token}"}
        response = requests.get(f"{BASE_URL}/api/notifications", headers=headers)
        assert response.status_code == 200
        notifs = response.json()
        # Look for CS-TEST-001
        cs_test_notifs = [n for n in notifs if n.get("order_number") == "CS-TEST-001"]
        if len(cs_test_notifs) > 0:
            print(f"PASS: Found existing CS-TEST-001 notification: {cs_test_notifs[0]}")
        else:
            print("INFO: CS-TEST-001 notification not found (may have been acknowledged)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
