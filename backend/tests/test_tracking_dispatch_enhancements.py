"""
Test suite for Tracking and Dispatch Enhancements
Features tested:
1. LR No./Tracking No. mandatory for Courier and Transport shipping methods
2. Regex validations for Courier LR formats (DTDC, Anjani, Professional, India Post)
3. Porter link extraction and storage
4. Backend DispatchUpdate model includes porter_link field
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}
DISPATCH_CREDS = {"username": "test_dispatch_user", "password": "test123"}
PACKAGING_CREDS = {"username": "test_packaging_user", "password": "test123"}

# Courier LR Regex Patterns (matching frontend courierTracking.js)
COURIER_LR_PATTERNS = {
    "DTDC": r"^[A-Za-z][0-9]{10}$",  # 1 letter + 10 digits (e.g., D1234567890)
    "Anjani": r"^[0-9]{10}$",  # 10 digits (e.g., 1234567890)
    "Professional": r"^[A-Za-z]{3}[0-9]{9}$",  # 3 letters + 9 digits (e.g., PAT500068734)
    "India Post": r"^[A-Za-z]{2}[0-9]{9}[A-Za-z]{2}$",  # 2 letters + 9 digits + 2 letters (e.g., EE123456789IN)
}


class TestAuth:
    """Authentication tests"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print(f"PASS: Admin login successful")
        return data["token"]
    
    def test_dispatch_login(self):
        """Test dispatch user login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
        assert response.status_code == 200, f"Dispatch login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "dispatch"
        print(f"PASS: Dispatch user login successful")
        return data["token"]


class TestCourierLRPatterns:
    """Test courier LR regex patterns"""
    
    def test_dtdc_valid_lr(self):
        """DTDC: 1 letter + 10 digits"""
        pattern = COURIER_LR_PATTERNS["DTDC"]
        valid_examples = ["D1234567890", "A0000000000", "Z9999999999", "d1234567890"]
        for lr in valid_examples:
            assert re.match(pattern, lr), f"DTDC pattern should match: {lr}"
        print(f"PASS: DTDC valid LR patterns match correctly")
    
    def test_dtdc_invalid_lr(self):
        """DTDC: Invalid formats should not match"""
        pattern = COURIER_LR_PATTERNS["DTDC"]
        invalid_examples = ["12345678901", "DD1234567890", "D123456789", "D12345678901", "1234567890"]
        for lr in invalid_examples:
            assert not re.match(pattern, lr), f"DTDC pattern should NOT match: {lr}"
        print(f"PASS: DTDC invalid LR patterns correctly rejected")
    
    def test_anjani_valid_lr(self):
        """Anjani: 10 digits"""
        pattern = COURIER_LR_PATTERNS["Anjani"]
        valid_examples = ["1234567890", "0000000000", "9999999999"]
        for lr in valid_examples:
            assert re.match(pattern, lr), f"Anjani pattern should match: {lr}"
        print(f"PASS: Anjani valid LR patterns match correctly")
    
    def test_anjani_invalid_lr(self):
        """Anjani: Invalid formats should not match"""
        pattern = COURIER_LR_PATTERNS["Anjani"]
        invalid_examples = ["123456789", "12345678901", "A1234567890", "123456789A"]
        for lr in invalid_examples:
            assert not re.match(pattern, lr), f"Anjani pattern should NOT match: {lr}"
        print(f"PASS: Anjani invalid LR patterns correctly rejected")
    
    def test_professional_valid_lr(self):
        """Professional: 3 letters + 9 digits"""
        pattern = COURIER_LR_PATTERNS["Professional"]
        valid_examples = ["PAT500068734", "ABC123456789", "XYZ000000000"]
        for lr in valid_examples:
            assert re.match(pattern, lr), f"Professional pattern should match: {lr}"
        print(f"PASS: Professional valid LR patterns match correctly")
    
    def test_professional_invalid_lr(self):
        """Professional: Invalid formats should not match"""
        pattern = COURIER_LR_PATTERNS["Professional"]
        invalid_examples = ["PA500068734", "PATT500068734", "PAT50006873", "PAT5000687341", "123456789012"]
        for lr in invalid_examples:
            assert not re.match(pattern, lr), f"Professional pattern should NOT match: {lr}"
        print(f"PASS: Professional invalid LR patterns correctly rejected")
    
    def test_india_post_valid_lr(self):
        """India Post: 2 letters + 9 digits + 2 letters"""
        pattern = COURIER_LR_PATTERNS["India Post"]
        valid_examples = ["EE123456789IN", "AB000000000CD", "XY999999999ZZ"]
        for lr in valid_examples:
            assert re.match(pattern, lr), f"India Post pattern should match: {lr}"
        print(f"PASS: India Post valid LR patterns match correctly")
    
    def test_india_post_invalid_lr(self):
        """India Post: Invalid formats should not match"""
        pattern = COURIER_LR_PATTERNS["India Post"]
        invalid_examples = ["E123456789IN", "EEE123456789IN", "EE12345678IN", "EE1234567890IN", "EE123456789I"]
        for lr in invalid_examples:
            assert not re.match(pattern, lr), f"India Post pattern should NOT match: {lr}"
        print(f"PASS: India Post invalid LR patterns correctly rejected")


class TestDispatchEndpoint:
    """Test dispatch endpoint with mandatory LR validation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and find a packed order"""
        # Login as admin
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
        assert response.status_code == 200
        self.admin_token = response.json()["token"]
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        
        # Login as dispatch
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DISPATCH_CREDS)
        if response.status_code == 200:
            self.dispatch_token = response.json()["token"]
            self.dispatch_headers = {"Authorization": f"Bearer {self.dispatch_token}"}
        else:
            self.dispatch_token = None
            self.dispatch_headers = self.admin_headers
    
    def get_or_create_packed_order(self):
        """Get an existing packed order or create one for testing"""
        # First try to find an existing packed order
        response = requests.get(f"{BASE_URL}/api/orders?status=packed&page_size=10", headers=self.admin_headers)
        if response.status_code == 200:
            orders = response.json().get("orders", [])
            if orders:
                return orders[0]
        
        # If no packed order, try to find a new/packaging order and mark it packed
        response = requests.get(f"{BASE_URL}/api/orders?status=new&page_size=10", headers=self.admin_headers)
        if response.status_code == 200:
            orders = response.json().get("orders", [])
            if orders:
                order = orders[0]
                # Mark as packed
                pack_response = requests.put(
                    f"{BASE_URL}/api/orders/{order['id']}/mark-packed",
                    headers=self.admin_headers
                )
                if pack_response.status_code == 200:
                    return pack_response.json()
        
        return None
    
    def test_dispatch_model_accepts_porter_link(self):
        """Test that DispatchUpdate model accepts porter_link field"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Try to dispatch with porter_link
        dispatch_data = {
            "dispatch_type": "porter",
            "shipping_method": "porter",
            "porter_link": "https://porter.in/track/test123",
            "lr_no": "",
            "courier_name": "",
            "transporter_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        assert response.status_code == 200, f"Dispatch with porter_link failed: {response.text}"
        data = response.json()
        assert data.get("dispatch", {}).get("porter_link") == "https://porter.in/track/test123"
        print(f"PASS: DispatchUpdate model accepts porter_link field")
    
    def test_dispatch_courier_requires_lr(self):
        """Test that courier dispatch requires LR number"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Try to dispatch with courier but no LR
        dispatch_data = {
            "dispatch_type": "courier",
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "lr_no": "",  # Empty LR
            "transporter_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        # Should fail with 400 error
        assert response.status_code == 400, f"Expected 400 for courier without LR, got {response.status_code}"
        assert "mandatory" in response.text.lower() or "lr" in response.text.lower()
        print(f"PASS: Courier dispatch correctly requires LR number")
    
    def test_dispatch_transport_requires_lr(self):
        """Test that transport dispatch requires LR number"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Try to dispatch with transport but no LR
        dispatch_data = {
            "dispatch_type": "transport",
            "shipping_method": "transport",
            "transporter_name": "Test Transporter",
            "lr_no": "",  # Empty LR
            "courier_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        # Should fail with 400 error
        assert response.status_code == 400, f"Expected 400 for transport without LR, got {response.status_code}"
        assert "mandatory" in response.text.lower() or "lr" in response.text.lower()
        print(f"PASS: Transport dispatch correctly requires LR number")
    
    def test_dispatch_self_arranged_no_lr_required(self):
        """Test that self-arranged dispatch does NOT require LR"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Dispatch with self_arranged - no LR required
        dispatch_data = {
            "dispatch_type": "self_arranged",
            "shipping_method": "self_arranged",
            "lr_no": "",
            "courier_name": "",
            "transporter_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        assert response.status_code == 200, f"Self-arranged dispatch should succeed without LR: {response.text}"
        print(f"PASS: Self-arranged dispatch works without LR number")
    
    def test_dispatch_office_collection_no_lr_required(self):
        """Test that office_collection dispatch does NOT require LR"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Dispatch with office_collection - no LR required
        dispatch_data = {
            "dispatch_type": "office_collection",
            "shipping_method": "office_collection",
            "lr_no": "",
            "courier_name": "",
            "transporter_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        assert response.status_code == 200, f"Office collection dispatch should succeed without LR: {response.text}"
        print(f"PASS: Office collection dispatch works without LR number")
    
    def test_dispatch_courier_with_valid_lr(self):
        """Test courier dispatch with valid LR succeeds"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Dispatch with courier and valid DTDC LR
        dispatch_data = {
            "dispatch_type": "courier",
            "shipping_method": "courier",
            "courier_name": "DTDC",
            "lr_no": "D1234567890",  # Valid DTDC format
            "transporter_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        assert response.status_code == 200, f"Courier dispatch with valid LR should succeed: {response.text}"
        data = response.json()
        assert data.get("dispatch", {}).get("lr_no") == "D1234567890"
        assert data.get("dispatch", {}).get("courier_name") == "DTDC"
        print(f"PASS: Courier dispatch with valid LR succeeds")
    
    def test_dispatch_transport_with_valid_lr(self):
        """Test transport dispatch with valid LR succeeds"""
        order = self.get_or_create_packed_order()
        if not order:
            pytest.skip("No packed order available for testing")
        
        # Dispatch with transport and LR
        dispatch_data = {
            "dispatch_type": "transport",
            "shipping_method": "transport",
            "transporter_name": "Test Transporter",
            "lr_no": "LR123456",
            "courier_name": "",
            "dispatch_slip_images": []
        }
        
        response = requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/dispatch",
            json=dispatch_data,
            headers=self.admin_headers
        )
        
        assert response.status_code == 200, f"Transport dispatch with LR should succeed: {response.text}"
        data = response.json()
        assert data.get("dispatch", {}).get("lr_no") == "LR123456"
        print(f"PASS: Transport dispatch with valid LR succeeds")


class TestPorterLinkExtraction:
    """Test Porter link extraction functionality"""
    
    def test_porter_link_regex(self):
        """Test Porter link extraction regex pattern"""
        # Pattern from courierTracking.js
        pattern = r"https?://(?:www\.)?porter\.in/[^\s)\"\]]+"
        
        test_cases = [
            ("Check out https://porter.in/track/abc123 for tracking", "https://porter.in/track/abc123"),
            ("Porter link: https://www.porter.in/track/xyz789", "https://www.porter.in/track/xyz789"),
            ("http://porter.in/delivery/test", "http://porter.in/delivery/test"),
            ("No link here", None),
            ("https://google.com/porter", None),
        ]
        
        for text, expected in test_cases:
            match = re.search(pattern, text, re.IGNORECASE)
            result = match.group(0) if match else None
            if expected:
                assert result == expected, f"Expected '{expected}' but got '{result}' for text: {text}"
            else:
                assert result is None, f"Expected no match but got '{result}' for text: {text}"
        
        print(f"PASS: Porter link extraction regex works correctly")


class TestCourierTrackingUtility:
    """Test that courierTracking.js utility file exists and has correct exports"""
    
    def test_courier_tracking_file_exists(self):
        """Verify courierTracking.js file exists"""
        import os
        file_path = "/app/frontend/src/lib/courierTracking.js"
        assert os.path.exists(file_path), f"courierTracking.js not found at {file_path}"
        print(f"PASS: courierTracking.js file exists")
    
    def test_courier_tracking_exports(self):
        """Verify courierTracking.js has required exports"""
        file_path = "/app/frontend/src/lib/courierTracking.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        required_exports = [
            "COURIER_LR_PATTERNS",
            "validateLrNumber",
            "getTrackingUrl",
            "extractPorterLink",
            "isLrMandatory"
        ]
        
        for export in required_exports:
            assert export in content, f"Missing export: {export}"
        
        print(f"PASS: courierTracking.js has all required exports")
    
    def test_courier_tracking_patterns(self):
        """Verify courierTracking.js has correct courier patterns"""
        file_path = "/app/frontend/src/lib/courierTracking.js"
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for courier names
        couriers = ["DTDC", "Anjani", "Professional", "India Post"]
        for courier in couriers:
            assert courier in content, f"Missing courier: {courier}"
        
        print(f"PASS: courierTracking.js has all courier patterns")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
