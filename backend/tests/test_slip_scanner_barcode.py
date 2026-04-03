"""
Test suite for Courier/Transport Slip Image Upload with Barcode Scanning feature
Tests:
1. POST /api/scan-barcode endpoint
2. PUT /api/orders/{id}/dispatch with dispatch_slip_images
3. Dispatch workflow with slip images
"""
import pytest
import requests
import os
import io
from PIL import Image

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}
PACKAGING_CREDS = {"username": "test_packaging_user", "password": "test123"}
DISPATCH_CREDS = {"username": "test_dispatch_user", "password": "test123"}

# Test order IDs from context
TEST_PACKED_ORDER_ID_1 = "94b4789e-fe4b-4587-afbc-80e31fdc28b8"  # CS-0014
TEST_PACKED_ORDER_ID_2 = "d252442d-009f-4659-8cd2-29da8e391760"  # CS-0013


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def packaging_token():
    """Get packaging user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=PACKAGING_CREDS)
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Packaging authentication failed")


@pytest.fixture(scope="module")
def dispatch_token():
    """Get dispatch user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Dispatch authentication failed")


def create_test_image():
    """Create a simple test image for upload"""
    img = Image.new('RGB', (100, 100), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    return img_bytes


class TestScanBarcodeEndpoint:
    """Tests for POST /api/scan-barcode endpoint"""
    
    def test_scan_barcode_returns_correct_structure(self, admin_token):
        """Test that scan-barcode endpoint returns {found, code, type}"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        img_bytes = create_test_image()
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        
        response = requests.post(f"{BASE_URL}/api/scan-barcode", headers=headers, files=files)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "found" in data, "Response should contain 'found' field"
        assert "code" in data, "Response should contain 'code' field"
        assert "type" in data, "Response should contain 'type' field"
        print(f"PASS: scan-barcode returns correct structure: {data}")
    
    def test_scan_barcode_blank_image_returns_not_found(self, admin_token):
        """Test that blank image returns found=false"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        img_bytes = create_test_image()
        files = {"file": ("blank.jpg", img_bytes, "image/jpeg")}
        
        response = requests.post(f"{BASE_URL}/api/scan-barcode", headers=headers, files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["found"] == False, "Blank image should return found=false"
        print(f"PASS: Blank image returns found=false: {data}")
    
    def test_scan_barcode_packaging_role_allowed(self, packaging_token):
        """Test that packaging role can access scan-barcode"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        img_bytes = create_test_image()
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        
        response = requests.post(f"{BASE_URL}/api/scan-barcode", headers=headers, files=files)
        
        assert response.status_code == 200, f"Packaging should be able to scan: {response.text}"
        print("PASS: Packaging role can access scan-barcode endpoint")
    
    def test_scan_barcode_dispatch_role_allowed(self, dispatch_token):
        """Test that dispatch role can access scan-barcode"""
        headers = {"Authorization": f"Bearer {dispatch_token}"}
        img_bytes = create_test_image()
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        
        response = requests.post(f"{BASE_URL}/api/scan-barcode", headers=headers, files=files)
        
        assert response.status_code == 200, f"Dispatch should be able to scan: {response.text}"
        print("PASS: Dispatch role can access scan-barcode endpoint")


class TestDispatchWithSlipImages:
    """Tests for dispatch endpoint with dispatch_slip_images"""
    
    def test_dispatch_accepts_slip_images_array(self, admin_token):
        """Test that PUT /api/orders/{id}/dispatch accepts dispatch_slip_images array"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # First get a packed order
        response = requests.get(f"{BASE_URL}/api/orders?status=packed&page_size=1", headers=headers)
        if response.status_code != 200 or not response.json().get("orders"):
            pytest.skip("No packed orders available for testing")
        
        order = response.json()["orders"][0]
        order_id = order["id"]
        
        # Dispatch with slip images
        dispatch_data = {
            "courier_name": "DTDC",
            "transporter_name": "",
            "lr_no": "TEST-LR-12345",
            "dispatch_type": "courier",
            "shipping_method": "courier",
            "dispatch_slip_images": ["/api/uploads/test_slip_1.jpg", "/api/uploads/test_slip_2.jpg"]
        }
        
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/dispatch", headers=headers, json=dispatch_data)
        
        assert response.status_code == 200, f"Dispatch should succeed: {response.text}"
        data = response.json()
        assert data.get("dispatch", {}).get("dispatch_slip_images") == dispatch_data["dispatch_slip_images"], \
            "Dispatch slip images should be stored"
        print(f"PASS: Dispatch accepts slip_images array for order {order.get('order_number')}")
    
    def test_dispatch_slip_images_persisted_in_order(self, admin_token):
        """Test that dispatch_slip_images are persisted and returned in GET order"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Get a dispatched order
        response = requests.get(f"{BASE_URL}/api/orders?status=dispatched&page_size=5", headers=headers)
        if response.status_code != 200 or not response.json().get("orders"):
            pytest.skip("No dispatched orders available")
        
        # Find one with slip images
        orders = response.json()["orders"]
        for order in orders:
            order_detail = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=headers).json()
            if order_detail.get("dispatch", {}).get("dispatch_slip_images"):
                assert isinstance(order_detail["dispatch"]["dispatch_slip_images"], list), \
                    "dispatch_slip_images should be a list"
                print(f"PASS: dispatch_slip_images persisted for order {order_detail.get('order_number')}: {order_detail['dispatch']['dispatch_slip_images']}")
                return
        
        print("INFO: No orders with dispatch_slip_images found (may need to dispatch with images first)")


class TestDispatchWorkflow:
    """Tests for complete dispatch workflow"""
    
    def test_dispatch_transport_with_lr_and_slip(self, admin_token):
        """Test transport dispatch with LR number and slip image"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Get a packed order
        response = requests.get(f"{BASE_URL}/api/orders?status=packed&page_size=1", headers=headers)
        if response.status_code != 200 or not response.json().get("orders"):
            pytest.skip("No packed orders available")
        
        order = response.json()["orders"][0]
        order_id = order["id"]
        
        dispatch_data = {
            "courier_name": "",
            "transporter_name": "Test Transporter",
            "lr_no": "LR-TRANSPORT-001",
            "dispatch_type": "transport",
            "shipping_method": "transport",
            "dispatch_slip_images": ["/api/uploads/transport_slip.jpg"]
        }
        
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/dispatch", headers=headers, json=dispatch_data)
        
        assert response.status_code == 200, f"Transport dispatch should succeed: {response.text}"
        data = response.json()
        assert data["status"] == "dispatched"
        assert data["dispatch"]["lr_no"] == "LR-TRANSPORT-001"
        assert data["dispatch"]["transporter_name"] == "Test Transporter"
        print(f"PASS: Transport dispatch with LR and slip works for {order.get('order_number')}")
    
    def test_dispatch_courier_with_tracking_and_slip(self, admin_token):
        """Test courier dispatch with tracking number and slip image"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Get a packed order
        response = requests.get(f"{BASE_URL}/api/orders?status=packed&page_size=1", headers=headers)
        if response.status_code != 200 or not response.json().get("orders"):
            pytest.skip("No packed orders available")
        
        order = response.json()["orders"][0]
        order_id = order["id"]
        
        dispatch_data = {
            "courier_name": "DTDC",
            "transporter_name": "",
            "lr_no": "DTDC-TRACK-12345",
            "dispatch_type": "courier",
            "shipping_method": "courier",
            "dispatch_slip_images": ["/api/uploads/courier_slip.jpg"]
        }
        
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/dispatch", headers=headers, json=dispatch_data)
        
        assert response.status_code == 200, f"Courier dispatch should succeed: {response.text}"
        data = response.json()
        assert data["status"] == "dispatched"
        assert data["dispatch"]["courier_name"] == "DTDC"
        assert data["dispatch"]["lr_no"] == "DTDC-TRACK-12345"
        print(f"PASS: Courier dispatch with tracking and slip works for {order.get('order_number')}")
    
    def test_packaging_role_can_dispatch(self, packaging_token):
        """Test that packaging role can dispatch orders"""
        headers = {"Authorization": f"Bearer {packaging_token}", "Content-Type": "application/json"}
        
        # Get a packed order
        response = requests.get(f"{BASE_URL}/api/orders?status=packed&page_size=1", headers=headers)
        if response.status_code != 200 or not response.json().get("orders"):
            pytest.skip("No packed orders available for packaging user")
        
        order = response.json()["orders"][0]
        order_id = order["id"]
        
        dispatch_data = {
            "courier_name": "Anjani",
            "transporter_name": "",
            "lr_no": "PKG-DISPATCH-001",
            "dispatch_type": "courier",
            "shipping_method": "courier",
            "dispatch_slip_images": []
        }
        
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/dispatch", headers=headers, json=dispatch_data)
        
        assert response.status_code == 200, f"Packaging role should be able to dispatch: {response.text}"
        print(f"PASS: Packaging role can dispatch orders")


class TestUploadEndpoint:
    """Tests for file upload endpoint used by SlipScanner"""
    
    def test_upload_image_returns_url(self, admin_token):
        """Test that upload endpoint returns URL for slip images"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        img_bytes = create_test_image()
        files = {"file": ("slip_test.jpg", img_bytes, "image/jpeg")}
        
        response = requests.post(f"{BASE_URL}/api/upload", headers=headers, files=files)
        
        assert response.status_code == 200, f"Upload should succeed: {response.text}"
        data = response.json()
        assert "url" in data, "Response should contain 'url' field"
        assert data["url"].startswith("/api/uploads/"), "URL should be in uploads path"
        print(f"PASS: Upload returns URL: {data['url']}")


class TestLRFieldManualEntry:
    """Tests to verify LR field remains manually editable"""
    
    def test_lr_field_accepts_manual_entry(self, admin_token):
        """Test that LR/Tracking field accepts manual entry"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Get a packed order
        response = requests.get(f"{BASE_URL}/api/orders?status=packed&page_size=1", headers=headers)
        if response.status_code != 200 or not response.json().get("orders"):
            pytest.skip("No packed orders available")
        
        order = response.json()["orders"][0]
        order_id = order["id"]
        
        # Dispatch with manually entered LR
        manual_lr = "MANUAL-LR-ENTRY-TEST-123"
        dispatch_data = {
            "courier_name": "Professional",
            "transporter_name": "",
            "lr_no": manual_lr,
            "dispatch_type": "courier",
            "shipping_method": "courier",
            "dispatch_slip_images": []
        }
        
        response = requests.put(f"{BASE_URL}/api/orders/{order_id}/dispatch", headers=headers, json=dispatch_data)
        
        assert response.status_code == 200, f"Manual LR entry should work: {response.text}"
        data = response.json()
        assert data["dispatch"]["lr_no"] == manual_lr, "Manual LR should be saved"
        print(f"PASS: Manual LR entry works: {manual_lr}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
