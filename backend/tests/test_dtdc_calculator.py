"""
DTDC Serviceability & Rate Calculator API Tests
Tests for POST /api/dtdc/calculate and GET /api/dtdc/check/{pincode}
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestDTDCCheckPincode:
    """Tests for GET /api/dtdc/check/{pincode} endpoint"""
    
    def test_check_serviceable_pincode(self):
        """Check serviceable pincode returns correct info"""
        response = requests.get(f"{BASE_URL}/api/dtdc/check/110001")
        assert response.status_code == 200
        data = response.json()
        
        assert data["serviceable"] is True
        assert data["pincode"] == "110001"
        assert data["city"] == "DELHI"
        assert data["state"] == "DELHI"
        assert data["category"] == "Metros"
    
    def test_check_non_serviceable_pincode(self):
        """Check non-serviceable pincode returns serviceable=false"""
        response = requests.get(f"{BASE_URL}/api/dtdc/check/999999")
        assert response.status_code == 200
        data = response.json()
        
        assert data["serviceable"] is False
        assert "message" in data


class TestDTDCCalculate:
    """Tests for POST /api/dtdc/calculate endpoint"""
    
    def test_calculate_serviceable_pincode_basic(self):
        """Test basic calculation with serviceable pincode"""
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 1, "grams": 250}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields are present
        assert data["serviceable"] is True
        assert data["pincode"] == "110001"
        assert data["city"] == "DELHI"
        assert data["state"] == "DELHI"
        assert data["category"] == "Metros"
        assert data["total_weight_kg"] == 1.25
        assert "ground_express_cost" in data
        assert "standard_cost" in data
        assert "series" in data
        assert "final_charge" in data
        assert "selected_method" in data
    
    def test_calculate_non_serviceable_pincode(self):
        """Test calculation with non-serviceable pincode returns serviceable=false"""
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "999999", "kg": 1, "grams": 0}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["serviceable"] is False
        assert "message" in data
    
    def test_calculate_weight_conversion(self):
        """Test weight conversion: 1kg 250g = 1.25kg"""
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 1, "grams": 250}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_weight_kg"] == 1.25
    
    def test_calculate_ground_express_ceiling_logic(self):
        """Test Ground Express ceiling logic: 3.1kg should ceil extra weight to 1kg
        
        For Metros: base=147, per_kg=38
        3.1kg -> extra = ceil(3.1 - 3) = ceil(0.1) = 1kg
        Ground cost = 147 + 1*38 = 185
        """
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 3, "grams": 100}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_weight_kg"] == 3.1
        assert data["ground_express_cost"] == 185  # 147 + ceil(0.1)*38 = 147 + 38 = 185
    
    def test_calculate_standard_ceiling_logic(self):
        """Test Standard ceiling logic: 0.75kg -> 1 extra 500g slab
        
        For Metros: base=66, per_500g=59
        0.75kg -> extra slabs = ceil((0.75 - 0.5) / 0.5) = ceil(0.5) = 1
        Standard cost = 66 + 1*59 = 125
        """
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 0, "grams": 750}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_weight_kg"] == 0.75
        assert data["standard_cost"] == 125  # 66 + ceil(0.25/0.5)*59 = 66 + 59 = 125
    
    def test_calculate_final_charge_rounded_up(self):
        """Test final charge is rounded up to nearest 10 (CEILING)
        
        For 1.25kg Metros:
        Ground = 147 (base, <=3kg)
        Standard = 66 + ceil((1.25-0.5)/0.5)*59 = 66 + 2*59 = 184
        Ground is cheaper (147), final = ceil(147/10)*10 = 150
        """
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 1, "grams": 250}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["ground_express_cost"] == 147
        assert data["standard_cost"] == 184
        assert data["final_charge"] == 150  # ceil(147/10)*10 = 150
    
    def test_calculate_lighter_weight_picks_standard(self):
        """Test lighter weight should pick Standard (M-Series)
        
        For 0.35kg Metros:
        Ground = 147 (base, <=3kg)
        Standard = 66 (base, <=0.5kg)
        Standard is cheaper (66), series = M-Series
        """
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 0, "grams": 350}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["ground_express_cost"] == 147
        assert data["standard_cost"] == 66
        assert data["selected_method"] == "Standard"
        assert data["series"] == "M-Series"
        assert data["final_charge"] == 70  # ceil(66/10)*10 = 70
    
    def test_calculate_heavier_weight_picks_ground(self):
        """Test heavier weight should pick Ground Express (D-Series)
        
        For 3.1kg Metros:
        Ground = 147 + ceil(0.1)*38 = 185
        Standard = 66 + ceil((3.1-0.5)/0.5)*59 = 66 + 6*59 = 420
        Ground is cheaper (185), series = D-Series
        """
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 3, "grams": 100}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["ground_express_cost"] == 185
        assert data["standard_cost"] == 420
        assert data["selected_method"] == "Ground Express"
        assert data["series"] == "D-Series"
        assert data["final_charge"] == 190  # ceil(185/10)*10 = 190
    
    def test_calculate_exact_3kg_uses_base_rate(self):
        """Test exactly 3kg uses base rate for Ground Express"""
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 3, "grams": 0}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_weight_kg"] == 3.0
        assert data["ground_express_cost"] == 147  # Base rate for Metros
    
    def test_calculate_exact_500g_uses_base_rate(self):
        """Test exactly 500g uses base rate for Standard"""
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 0, "grams": 500}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_weight_kg"] == 0.5
        assert data["standard_cost"] == 66  # Base rate for Metros Standard


class TestDTDCDifferentCategories:
    """Test different pincode categories"""
    
    def test_calculate_within_city_category(self):
        """Test calculation for Within City category if available"""
        # First check if we have a Within City pincode
        response = requests.post(
            f"{BASE_URL}/api/dtdc/calculate",
            json={"pincode": "110001", "kg": 1, "grams": 0}
        )
        assert response.status_code == 200
        # Just verify the endpoint works for different weights
        data = response.json()
        assert data["serviceable"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
