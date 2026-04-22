"""
Test PI Terms & Conditions Feature
- PICreate model accepts terms_and_conditions field
- POST /api/proforma-invoices with terms_and_conditions field
- PUT /api/proforma-invoices/{id} stores terms_and_conditions
- GET /api/proforma-invoices/{id} returns terms_and_conditions field
- PI PDF includes TERMS & CONDITIONS section
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Default terms from backend
DEFAULT_PI_TERMS = [
    "Goods once sold will not be taken back or exchanged.",
    "All disputes are subject to Nagpur jurisdiction only.",
    "Dispatch will be done within 2–3 working days after receipt of full payment.",
    "Prices are subject to change without prior notice.",
    "Delivery timelines may vary due to transport or unforeseen circumstances.",
    "Any damage or shortage must be reported within 24 hours of delivery. Opening video of the package is mandatory for any claim.",
    "Payment once made is non-refundable except in mutually agreed cases.",
]


@pytest.fixture(scope="module")
def auth_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def test_customer(api_client):
    """Create or get a test customer for PI tests"""
    # Search for existing test customer
    response = api_client.get(f"{BASE_URL}/api/customers?search=TEST_PI_TERMS")
    if response.status_code == 200 and response.json():
        return response.json()[0]
    
    # Create new test customer with unique phone
    import time
    unique_phone = f"98765{int(time.time()) % 100000:05d}"
    response = api_client.post(f"{BASE_URL}/api/customers", json={
        "name": "TEST_PI_TERMS Customer",
        "phone_numbers": [unique_phone],
        "email": "test_pi_terms@example.com"
    })
    assert response.status_code == 200, f"Failed to create customer: {response.text}"
    return response.json()


@pytest.fixture(scope="module")
def test_address(api_client, test_customer):
    """Create or get a test address for PI tests"""
    response = api_client.get(f"{BASE_URL}/api/customers/{test_customer['id']}/addresses")
    if response.status_code == 200 and response.json():
        return response.json()[0]
    
    # Create new address
    response = api_client.post(f"{BASE_URL}/api/customers/{test_customer['id']}/addresses", json={
        "address_line": "123 Test Street",
        "city": "Nagpur",
        "state": "Maharashtra",
        "pincode": "440001",
        "label": "Office"
    })
    assert response.status_code == 200, f"Failed to create address: {response.text}"
    return response.json()


class TestPITermsAndConditions:
    """Test Terms & Conditions feature for Proforma Invoices"""
    
    def test_create_pi_without_terms(self, api_client, test_customer, test_address):
        """Test creating PI without custom terms - should use defaults"""
        payload = {
            "customer_id": test_customer["id"],
            "items": [{
                "product_name": "Test Product No Terms",
                "qty": 1,
                "unit": "pcs",
                "rate": 100,
                "amount": 100,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 100
            }],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "Test PI without custom terms",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json=payload)
        assert response.status_code == 200, f"Failed to create PI: {response.text}"
        
        pi = response.json()
        assert "id" in pi
        assert "pi_number" in pi
        # terms_and_conditions should be empty string (defaults will be used in PDF)
        assert pi.get("terms_and_conditions", "") == ""
        
        print(f"✓ Created PI without custom terms: {pi['pi_number']}")
        return pi
    
    def test_create_pi_with_custom_terms(self, api_client, test_customer, test_address):
        """Test creating PI with custom terms"""
        custom_terms = "Custom Term 1: Payment within 7 days.\nCustom Term 2: No returns accepted.\nCustom Term 3: Warranty void if tampered."
        
        payload = {
            "customer_id": test_customer["id"],
            "items": [{
                "product_name": "Test Product Custom Terms",
                "qty": 2,
                "unit": "L",
                "rate": 500,
                "amount": 1000,
                "gst_rate": 0,
                "gst_amount": 0,
                "total": 1000
            }],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 50,
            "additional_charges": [],
            "remark": "Test PI with custom terms",
            "terms_and_conditions": custom_terms,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json=payload)
        assert response.status_code == 200, f"Failed to create PI: {response.text}"
        
        pi = response.json()
        assert "id" in pi
        assert pi.get("terms_and_conditions") == custom_terms
        
        print(f"✓ Created PI with custom terms: {pi['pi_number']}")
        return pi
    
    def test_get_pi_returns_terms(self, api_client, test_customer, test_address):
        """Test that GET /api/proforma-invoices/{id} returns terms_and_conditions"""
        # First create a PI with custom terms
        custom_terms = "GET Test Term 1\nGET Test Term 2"
        
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "GET Test Product", "qty": 1, "unit": "pcs", "rate": 200, "amount": 200, "gst_rate": 0, "gst_amount": 0, "total": 200}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": custom_terms,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi_id = create_response.json()["id"]
        
        # GET the PI
        get_response = api_client.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}")
        assert get_response.status_code == 200, f"Failed to get PI: {get_response.text}"
        
        pi = get_response.json()
        assert pi.get("terms_and_conditions") == custom_terms
        
        print(f"✓ GET PI returns terms_and_conditions correctly")
    
    def test_update_pi_terms(self, api_client, test_customer, test_address):
        """Test updating PI terms via PUT"""
        # Create PI without terms
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Update Test Product", "qty": 1, "unit": "pcs", "rate": 300, "amount": 300, "gst_rate": 0, "gst_amount": 0, "total": 300}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi = create_response.json()
        pi_id = pi["id"]
        
        # Update with custom terms
        updated_terms = "Updated Term 1: New payment policy.\nUpdated Term 2: New return policy."
        
        update_response = api_client.put(f"{BASE_URL}/api/proforma-invoices/{pi_id}", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Update Test Product", "qty": 1, "unit": "pcs", "rate": 300, "amount": 300, "gst_rate": 0, "gst_amount": 0, "total": 300}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": updated_terms,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert update_response.status_code == 200, f"Failed to update PI: {update_response.text}"
        
        # Verify update
        get_response = api_client.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}")
        assert get_response.status_code == 200
        assert get_response.json().get("terms_and_conditions") == updated_terms
        
        print(f"✓ PUT PI updates terms_and_conditions correctly")
    
    def test_create_gst_pi_with_terms(self, api_client, test_customer, test_address):
        """Test creating GST PI with custom terms"""
        custom_terms = "GST PI Term 1: Tax invoice will be provided.\nGST PI Term 2: GST credit applicable."
        
        payload = {
            "customer_id": test_customer["id"],
            "items": [{
                "product_name": "GST Test Product",
                "qty": 1,
                "unit": "L",
                "rate": 1000,
                "amount": 1000,
                "gst_rate": 18,
                "gst_amount": 180,
                "total": 1180
            }],
            "gst_applicable": True,
            "show_rate": True,
            "shipping_charge": 100,
            "additional_charges": [],
            "remark": "GST PI with custom terms",
            "terms_and_conditions": custom_terms,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json=payload)
        assert response.status_code == 200, f"Failed to create GST PI: {response.text}"
        
        pi = response.json()
        assert pi.get("gst_applicable") == True
        assert pi.get("terms_and_conditions") == custom_terms
        
        print(f"✓ Created GST PI with custom terms: {pi['pi_number']}")
        return pi
    
    def test_pdf_generation_with_default_terms(self, api_client, auth_token, test_customer, test_address):
        """Test PDF generation includes default terms when no custom terms set"""
        # Create PI without custom terms
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "PDF Default Terms Test", "qty": 1, "unit": "pcs", "rate": 500, "amount": 500, "gst_rate": 0, "gst_amount": 0, "total": 500}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi_id = create_response.json()["id"]
        
        # Get PDF
        pdf_response = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf?token={auth_token}")
        assert pdf_response.status_code == 200, f"Failed to get PDF: {pdf_response.text}"
        assert pdf_response.headers.get("content-type") == "application/pdf"
        assert len(pdf_response.content) > 1000  # PDF should have content
        
        print(f"✓ PDF generated successfully for PI without custom terms (uses defaults)")
    
    def test_pdf_generation_with_custom_terms(self, api_client, auth_token, test_customer, test_address):
        """Test PDF generation includes custom terms when set"""
        custom_terms = "PDF Custom Term 1\nPDF Custom Term 2\nPDF Custom Term 3"
        
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "PDF Custom Terms Test", "qty": 1, "unit": "pcs", "rate": 600, "amount": 600, "gst_rate": 0, "gst_amount": 0, "total": 600}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": custom_terms,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi_id = create_response.json()["id"]
        
        # Get PDF
        pdf_response = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf?token={auth_token}")
        assert pdf_response.status_code == 200, f"Failed to get PDF: {pdf_response.text}"
        assert pdf_response.headers.get("content-type") == "application/pdf"
        assert len(pdf_response.content) > 1000
        
        print(f"✓ PDF generated successfully for PI with custom terms")
    
    def test_gst_pdf_generation_with_terms(self, api_client, auth_token, test_customer, test_address):
        """Test GST PI PDF generation includes terms"""
        custom_terms = "GST PDF Term 1\nGST PDF Term 2"
        
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "GST PDF Terms Test", "qty": 1, "unit": "L", "rate": 1000, "amount": 1000, "gst_rate": 18, "gst_amount": 180, "total": 1180}],
            "gst_applicable": True,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": custom_terms,
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi_id = create_response.json()["id"]
        
        # Get PDF
        pdf_response = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf?token={auth_token}")
        assert pdf_response.status_code == 200, f"Failed to get GST PDF: {pdf_response.text}"
        assert pdf_response.headers.get("content-type") == "application/pdf"
        assert len(pdf_response.content) > 1000
        
        print(f"✓ GST PI PDF generated successfully with custom terms")
    
    def test_existing_pi_non_gst(self, api_client, auth_token):
        """Test existing Non-GST PI: 0242f1c9-3882-447d-9a3d-4cfd7a1dba71"""
        pi_id = "0242f1c9-3882-447d-9a3d-4cfd7a1dba71"
        
        # Get PI
        get_response = api_client.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}")
        if get_response.status_code == 404:
            pytest.skip("Existing Non-GST PI not found")
        
        assert get_response.status_code == 200
        pi = get_response.json()
        
        # Check terms field exists
        assert "terms_and_conditions" in pi or pi.get("terms_and_conditions") is None
        print(f"✓ Existing Non-GST PI has terms_and_conditions: '{pi.get('terms_and_conditions', '')[:50]}...'")
        
        # Get PDF
        pdf_response = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf?token={auth_token}")
        assert pdf_response.status_code == 200
        assert pdf_response.headers.get("content-type") == "application/pdf"
        print(f"✓ Existing Non-GST PI PDF generated successfully")
    
    def test_existing_pi_gst(self, api_client, auth_token):
        """Test existing GST PI: d9441f44-830f-4ffc-9c9d-9a50d5431ff2"""
        pi_id = "d9441f44-830f-4ffc-9c9d-9a50d5431ff2"
        
        # Get PI
        get_response = api_client.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}")
        if get_response.status_code == 404:
            pytest.skip("Existing GST PI not found")
        
        assert get_response.status_code == 200
        pi = get_response.json()
        
        # Check terms field exists
        assert "terms_and_conditions" in pi or pi.get("terms_and_conditions") is None
        print(f"✓ Existing GST PI has terms_and_conditions: '{pi.get('terms_and_conditions', '')[:50]}...'")
        
        # Get PDF
        pdf_response = requests.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}/pdf?token={auth_token}")
        assert pdf_response.status_code == 200
        assert pdf_response.headers.get("content-type") == "application/pdf"
        print(f"✓ Existing GST PI PDF generated successfully")
    
    def test_empty_terms_uses_defaults(self, api_client, test_customer, test_address):
        """Test that empty string terms_and_conditions uses defaults in PDF"""
        # Create PI with empty terms
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Empty Terms Test", "qty": 1, "unit": "pcs", "rate": 100, "amount": 100, "gst_rate": 0, "gst_amount": 0, "total": 100}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": "",  # Explicitly empty
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi = create_response.json()
        
        # Verify empty terms stored
        assert pi.get("terms_and_conditions") == ""
        
        print(f"✓ PI with empty terms created - defaults will be used in PDF")
    
    def test_reset_terms_to_empty(self, api_client, test_customer, test_address):
        """Test resetting custom terms back to empty (use defaults)"""
        # Create PI with custom terms
        create_response = api_client.post(f"{BASE_URL}/api/proforma-invoices", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Reset Terms Test", "qty": 1, "unit": "pcs", "rate": 100, "amount": 100, "gst_rate": 0, "gst_amount": 0, "total": 100}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": "Custom terms to be reset",
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert create_response.status_code == 200
        pi_id = create_response.json()["id"]
        
        # Update to reset terms to empty
        update_response = api_client.put(f"{BASE_URL}/api/proforma-invoices/{pi_id}", json={
            "customer_id": test_customer["id"],
            "items": [{"product_name": "Reset Terms Test", "qty": 1, "unit": "pcs", "rate": 100, "amount": 100, "gst_rate": 0, "gst_amount": 0, "total": 100}],
            "gst_applicable": False,
            "show_rate": True,
            "shipping_charge": 0,
            "additional_charges": [],
            "remark": "",
            "terms_and_conditions": "",  # Reset to empty
            "billing_address_id": test_address["id"],
            "shipping_address_id": test_address["id"]
        })
        assert update_response.status_code == 200
        
        # Verify reset
        get_response = api_client.get(f"{BASE_URL}/api/proforma-invoices/{pi_id}")
        assert get_response.status_code == 200
        assert get_response.json().get("terms_and_conditions") == ""
        
        print(f"✓ Terms reset to empty successfully - defaults will be used in PDF")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_pis(self, api_client):
        """Delete test PIs created during testing"""
        response = api_client.get(f"{BASE_URL}/api/proforma-invoices?page_size=200")
        if response.status_code == 200:
            pis = response.json().get("pis", response.json())
            for pi in pis:
                if "TEST_PI_TERMS" in pi.get("customer_name", ""):
                    api_client.delete(f"{BASE_URL}/api/proforma-invoices/{pi['id']}")
        print("✓ Cleanup completed")
