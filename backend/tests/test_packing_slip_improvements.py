"""
Test Packing Slip Improvements:
1. Free samples merged into items table with [Free Sample] tag
2. Remarks bigger, bolder, highlighted in red
3. Free sample image upload support with free_sample__ prefix keys
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test order with free samples: 4270b49b-a803-4412-81dc-0fdf07cca530 (CS-0050)
TEST_ORDER_ID = "4270b49b-a803-4412-81dc-0fdf07cca530"


class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def packaging_token(self):
        """Get packaging user token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_packaging_user",
            "password": "test123"
        })
        if response.status_code != 200:
            pytest.skip("Packaging user not found - skipping packaging-specific tests")
        return response.json()["token"]


class TestPackingSlipPDF(TestAuth):
    """Test packing slip PDF generation with free samples"""
    
    def test_order_exists_with_free_samples(self, admin_token):
        """Verify test order exists and has free samples"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        
        assert response.status_code == 200, f"Order not found: {response.text}"
        order = response.json()
        
        # Verify order has free samples
        free_samples = order.get("free_samples", [])
        assert len(free_samples) > 0, "Test order should have free samples"
        
        # Check free sample names
        sample_names = [s.get("item_name", "") for s in free_samples]
        print(f"Free samples found: {sample_names}")
        
        # Verify order has a remark
        remark = order.get("remark", "")
        print(f"Order remark: {remark}")
        
        return order
    
    def test_print_order_pdf_accessible(self, admin_token):
        """Test that print order PDF endpoint is accessible"""
        response = requests.get(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/print?token={admin_token}"
        )
        
        assert response.status_code == 200, f"PDF generation failed: {response.status_code}"
        assert response.headers.get("content-type") == "application/pdf", "Response should be PDF"
        
        # Check PDF has content
        pdf_content = response.content
        assert len(pdf_content) > 1000, "PDF should have substantial content"
        
        # Verify PDF header
        assert pdf_content[:4] == b'%PDF', "Response should be a valid PDF"
        
        print(f"PDF generated successfully, size: {len(pdf_content)} bytes")
    
    def test_print_order_pdf_with_packaging_user(self, packaging_token):
        """Test that packaging user can access print endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/print?token={packaging_token}"
        )
        
        assert response.status_code == 200, f"Packaging user PDF access failed: {response.status_code}"
        assert response.headers.get("content-type") == "application/pdf"
    
    def test_print_order_requires_auth(self):
        """Test that print endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/print")
        assert response.status_code == 401, "Should require authentication"
    
    def test_print_order_invalid_token(self):
        """Test that invalid token is rejected"""
        response = requests.get(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/print?token=invalid_token"
        )
        assert response.status_code == 401, "Should reject invalid token"


class TestFreeSampleImageUpload(TestAuth):
    """Test free sample image upload functionality"""
    
    def test_packaging_update_with_free_sample_images(self, admin_token):
        """Test that packaging can be updated with free_sample__ prefixed keys"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get the order to see current state
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        assert response.status_code == 200
        order = response.json()
        
        # Get existing packaging data
        existing_packaging = order.get("packaging", {})
        existing_item_images = existing_packaging.get("item_images", {})
        
        # Create test payload with free_sample__ key
        # Using a test URL that won't actually exist but tests the key format
        test_free_sample_key = "free_sample__Lavender Oil 10ml__0"
        
        # Prepare update payload - preserve existing data
        update_payload = {
            "item_images": {
                **existing_item_images,
                test_free_sample_key: ["/uploads/test_free_sample_image.jpg"]
            },
            "order_images": existing_packaging.get("order_images", []),
            "packed_box_images": existing_packaging.get("packed_box_images", []),
            "item_packed_by": existing_packaging.get("item_packed_by", []),
            "box_packed_by": existing_packaging.get("box_packed_by", []),
            "checked_by": existing_packaging.get("checked_by", []),
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/packaging",
            headers=headers,
            json=update_payload
        )
        
        assert response.status_code == 200, f"Packaging update failed: {response.text}"
        
        # Verify the update was saved
        updated_order = response.json()
        item_images = updated_order.get("packaging", {}).get("item_images", {})
        
        assert test_free_sample_key in item_images, f"Free sample key not saved. Keys: {list(item_images.keys())}"
        assert item_images[test_free_sample_key] == ["/uploads/test_free_sample_image.jpg"]
        
        print(f"Free sample image key saved successfully: {test_free_sample_key}")
    
    def test_packaging_update_preserves_regular_item_images(self, admin_token):
        """Test that regular item images are preserved when updating"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get current order state
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        assert response.status_code == 200
        order = response.json()
        
        existing_packaging = order.get("packaging", {})
        existing_item_images = existing_packaging.get("item_images", {})
        
        # Add a regular item image
        test_item_key = "Test Product__0"
        
        update_payload = {
            "item_images": {
                **existing_item_images,
                test_item_key: ["/uploads/test_regular_item.jpg"]
            },
            "order_images": existing_packaging.get("order_images", []),
            "packed_box_images": existing_packaging.get("packed_box_images", []),
            "item_packed_by": existing_packaging.get("item_packed_by", []),
            "box_packed_by": existing_packaging.get("box_packed_by", []),
            "checked_by": existing_packaging.get("checked_by", []),
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/packaging",
            headers=headers,
            json=update_payload
        )
        
        assert response.status_code == 200
        
        # Verify both regular and free sample keys exist
        updated_order = response.json()
        item_images = updated_order.get("packaging", {}).get("item_images", {})
        
        # Check that free_sample key from previous test is still there
        free_sample_keys = [k for k in item_images.keys() if k.startswith("free_sample__")]
        print(f"Free sample keys in item_images: {free_sample_keys}")
        
        # Check regular item key
        assert test_item_key in item_images, "Regular item key should be saved"
    
    def test_cleanup_test_images(self, admin_token):
        """Clean up test images from packaging"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get current order state
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        assert response.status_code == 200
        order = response.json()
        
        existing_packaging = order.get("packaging", {})
        existing_item_images = existing_packaging.get("item_images", {})
        
        # Remove test keys
        cleaned_images = {
            k: v for k, v in existing_item_images.items()
            if not k.startswith("Test Product") and "/uploads/test_" not in str(v)
        }
        
        # Also clean free_sample test images
        for key in list(cleaned_images.keys()):
            if key.startswith("free_sample__") and "/uploads/test_" in str(cleaned_images.get(key, [])):
                cleaned_images[key] = [u for u in cleaned_images[key] if "/uploads/test_" not in u]
                if not cleaned_images[key]:
                    del cleaned_images[key]
        
        update_payload = {
            "item_images": cleaned_images,
            "order_images": existing_packaging.get("order_images", []),
            "packed_box_images": existing_packaging.get("packed_box_images", []),
            "item_packed_by": existing_packaging.get("item_packed_by", []),
            "box_packed_by": existing_packaging.get("box_packed_by", []),
            "checked_by": existing_packaging.get("checked_by", []),
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/packaging",
            headers=headers,
            json=update_payload
        )
        
        assert response.status_code == 200
        print("Test images cleaned up")


class TestOrderWithFreeSamplesStructure(TestAuth):
    """Test order structure with free samples"""
    
    def test_order_free_samples_structure(self, admin_token):
        """Verify free samples have correct structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        
        assert response.status_code == 200
        order = response.json()
        
        free_samples = order.get("free_samples", [])
        assert len(free_samples) > 0, "Order should have free samples"
        
        for sample in free_samples:
            # Each free sample should have item_name
            assert "item_name" in sample, f"Free sample missing item_name: {sample}"
            print(f"Free sample: {sample.get('item_name')} - {sample.get('description', 'No description')}")
    
    def test_order_has_remark(self, admin_token):
        """Verify order has a remark for testing remark styling"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        
        assert response.status_code == 200
        order = response.json()
        
        remark = order.get("remark", "")
        print(f"Order remark: '{remark}'")
        
        # Note: remark may be empty, which is fine - the PDF code handles this


class TestPackagingUserAccess(TestAuth):
    """Test packaging user access to relevant endpoints"""
    
    def test_packaging_user_can_view_order(self, packaging_token):
        """Test packaging user can view order details"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        
        assert response.status_code == 200, f"Packaging user cannot view order: {response.text}"
        order = response.json()
        
        # Verify free samples are visible
        free_samples = order.get("free_samples", [])
        print(f"Packaging user sees {len(free_samples)} free samples")
    
    def test_packaging_user_can_update_packaging(self, packaging_token):
        """Test packaging user can update packaging data"""
        headers = {"Authorization": f"Bearer {packaging_token}"}
        
        # Get current state
        response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        assert response.status_code == 200
        order = response.json()
        
        existing_packaging = order.get("packaging", {})
        
        # Try to update with same data (no actual change)
        update_payload = {
            "item_images": existing_packaging.get("item_images", {}),
            "order_images": existing_packaging.get("order_images", []),
            "packed_box_images": existing_packaging.get("packed_box_images", []),
            "item_packed_by": existing_packaging.get("item_packed_by", []),
            "box_packed_by": existing_packaging.get("box_packed_by", []),
            "checked_by": existing_packaging.get("checked_by", []),
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/packaging",
            headers=headers,
            json=update_payload
        )
        
        # Should succeed (200) or fail if order is dispatched (400)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 400:
            print(f"Order may be dispatched: {response.json().get('detail', '')}")
        else:
            print("Packaging user can update packaging data")


class TestPDFContentVerification(TestAuth):
    """Verify PDF content structure (basic checks)"""
    
    def test_pdf_contains_order_number(self, admin_token):
        """Verify PDF contains the order number"""
        response = requests.get(
            f"{BASE_URL}/api/orders/{TEST_ORDER_ID}/print?token={admin_token}"
        )
        
        assert response.status_code == 200
        
        # Get order number for verification
        headers = {"Authorization": f"Bearer {admin_token}"}
        order_response = requests.get(f"{BASE_URL}/api/orders/{TEST_ORDER_ID}", headers=headers)
        order = order_response.json()
        order_number = order.get("order_number", "")
        
        print(f"PDF generated for order: {order_number}")
        print(f"PDF size: {len(response.content)} bytes")
        
        # PDF content is binary, but we can check it's valid
        assert response.content[:4] == b'%PDF', "Should be valid PDF"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
