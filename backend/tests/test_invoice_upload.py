"""
Test Invoice Upload Feature - Tax Invoice + E-Way Bill PDF Merge
Tests the POST /api/orders/{order_id}/invoice-upload endpoint
"""
import pytest
import requests
import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

def create_test_pdf(text_content, num_pages=1):
    """Create a test PDF with specified number of pages"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for i in range(num_pages):
        c.drawString(100, 750, f"{text_content} - Page {i+1}")
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture(scope="module")
def gst_order(auth_headers):
    """Find or create a GST-applicable order for testing"""
    # First try to find an existing GST order
    response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=auth_headers)
    assert response.status_code == 200
    orders = response.json()
    gst_orders = [o for o in orders if o.get("gst_applicable")]
    
    if gst_orders:
        # Return the first GST order without invoice for testing
        for order in gst_orders:
            if not order.get("tax_invoice_url"):
                return order
        # If all have invoices, return the first one (we'll replace it)
        return gst_orders[0]
    
    # If no GST orders exist, create one
    # First get or create a customer
    cust_response = requests.get(f"{BASE_URL}/api/customers", headers=auth_headers)
    customers = cust_response.json()
    
    if customers:
        customer_id = customers[0]["id"]
    else:
        # Create a test customer
        cust_create = requests.post(f"{BASE_URL}/api/customers", headers=auth_headers, json={
            "name": "TEST_Invoice_Customer",
            "phone_numbers": ["+919999888877"],
            "gst_no": "27AABCU9603R1ZM"
        })
        assert cust_create.status_code == 200
        customer_id = cust_create.json()["id"]
    
    # Create a GST order
    order_data = {
        "customer_id": customer_id,
        "purpose": "Test Invoice Upload",
        "items": [{
            "product_name": "Test Product",
            "qty": 1,
            "unit": "pc",
            "rate": 1000,
            "amount": 1000,
            "gst_rate": 18,
            "gst_amount": 180,
            "total": 1180
        }],
        "gst_applicable": True,
        "shipping_method": "courier",
        "payment_status": "unpaid"
    }
    
    order_response = requests.post(f"{BASE_URL}/api/orders", headers=auth_headers, json=order_data)
    assert order_response.status_code == 200, f"Failed to create order: {order_response.text}"
    return order_response.json()


class TestInvoiceUploadEndpoint:
    """Tests for POST /api/orders/{order_id}/invoice-upload"""
    
    def test_upload_tax_invoice_only(self, auth_headers, gst_order):
        """Test uploading only tax invoice (no e-way bill)"""
        order_id = gst_order["id"]
        
        # Create a 2-page test PDF for tax invoice
        tax_pdf = create_test_pdf("Tax Invoice", num_pages=2)
        
        files = {
            "tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert "tax_invoice_url" in data
        assert data["tax_invoice_url"].startswith("/api/uploads/")
        assert data["tax_invoice_url"].endswith(".pdf")
        print(f"PASS: Tax invoice only upload - URL: {data['tax_invoice_url']}")
    
    def test_upload_tax_invoice_with_eway_bill(self, auth_headers, gst_order):
        """Test uploading both tax invoice and e-way bill (should merge)"""
        order_id = gst_order["id"]
        
        # Create test PDFs - 2 pages for tax invoice, 1 page for e-way bill
        tax_pdf = create_test_pdf("Tax Invoice Content", num_pages=2)
        eway_pdf = create_test_pdf("E-Way Bill Content", num_pages=1)
        
        files = {
            "tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf"),
            "eway_bill": ("eway_bill.pdf", eway_pdf, "application/pdf")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        
        assert response.status_code == 200, f"Upload with merge failed: {response.text}"
        data = response.json()
        assert "tax_invoice_url" in data
        assert data["tax_invoice_url"].startswith("/api/uploads/")
        print(f"PASS: Tax invoice + E-Way bill merged upload - URL: {data['tax_invoice_url']}")
        
        # Verify the merged PDF is accessible
        pdf_url = f"{BASE_URL}{data['tax_invoice_url']}"
        pdf_response = requests.get(pdf_url, headers=auth_headers)
        assert pdf_response.status_code == 200, f"Cannot access merged PDF: {pdf_response.status_code}"
        assert pdf_response.headers.get("content-type", "").startswith("application/pdf") or \
               "pdf" in pdf_response.headers.get("content-type", "").lower() or \
               pdf_response.content[:4] == b'%PDF', "Response is not a PDF"
        print(f"PASS: Merged PDF is accessible and valid")
    
    def test_upload_without_tax_invoice_fails(self, auth_headers, gst_order):
        """Test that upload fails when tax invoice is missing"""
        order_id = gst_order["id"]
        
        # Try to upload only e-way bill (should fail)
        eway_pdf = create_test_pdf("E-Way Bill Only", num_pages=1)
        
        files = {
            "eway_bill": ("eway_bill.pdf", eway_pdf, "application/pdf")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        
        # Should fail because tax_invoice is required
        assert response.status_code == 422, f"Expected 422 for missing tax_invoice, got {response.status_code}"
        print("PASS: Upload without tax invoice correctly rejected")
    
    def test_upload_empty_tax_invoice_fails(self, auth_headers, gst_order):
        """Test that upload fails with empty tax invoice file"""
        order_id = gst_order["id"]
        
        # Create empty file
        empty_file = io.BytesIO(b"")
        
        files = {
            "tax_invoice": ("empty.pdf", empty_file, "application/pdf")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        
        assert response.status_code == 400, f"Expected 400 for empty file, got {response.status_code}"
        print("PASS: Empty tax invoice correctly rejected")
    
    def test_upload_to_non_gst_order_fails(self, auth_headers):
        """Test that upload fails for non-GST orders"""
        # Find a non-GST order
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=auth_headers)
        orders = response.json()
        non_gst_orders = [o for o in orders if not o.get("gst_applicable")]
        
        if not non_gst_orders:
            pytest.skip("No non-GST orders available for testing")
        
        order_id = non_gst_orders[0]["id"]
        tax_pdf = create_test_pdf("Tax Invoice", num_pages=1)
        
        files = {
            "tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        
        assert response.status_code == 400, f"Expected 400 for non-GST order, got {response.status_code}"
        assert "GST" in response.json().get("detail", "")
        print("PASS: Upload to non-GST order correctly rejected")
    
    def test_upload_to_nonexistent_order_fails(self, auth_headers):
        """Test that upload fails for non-existent order"""
        fake_order_id = "nonexistent-order-id-12345"
        tax_pdf = create_test_pdf("Tax Invoice", num_pages=1)
        
        files = {
            "tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders/{fake_order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        
        assert response.status_code == 404, f"Expected 404 for non-existent order, got {response.status_code}"
        print("PASS: Upload to non-existent order correctly rejected")


class TestInvoiceDelete:
    """Tests for DELETE /api/orders/{order_id}/invoice"""
    
    def test_delete_invoice(self, auth_headers, gst_order):
        """Test deleting an invoice"""
        order_id = gst_order["id"]
        
        # First ensure there's an invoice to delete
        tax_pdf = create_test_pdf("Tax Invoice to Delete", num_pages=1)
        files = {"tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")}
        upload_response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        assert upload_response.status_code == 200
        
        # Now delete it
        delete_response = requests.delete(
            f"{BASE_URL}/api/orders/{order_id}/invoice",
            headers=auth_headers
        )
        
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        assert "removed" in delete_response.json().get("message", "").lower()
        print("PASS: Invoice deleted successfully")
        
        # Verify it's actually deleted
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}", headers=auth_headers)
        assert order_response.status_code == 200
        assert order_response.json().get("tax_invoice_url") == ""
        print("PASS: Invoice URL cleared after delete")


class TestInvoiceViewAccess:
    """Tests for viewing uploaded invoices"""
    
    def test_view_invoice_after_upload(self, auth_headers, gst_order):
        """Test that uploaded invoice can be viewed"""
        order_id = gst_order["id"]
        
        # Upload an invoice
        tax_pdf = create_test_pdf("Viewable Tax Invoice", num_pages=1)
        files = {"tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")}
        upload_response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=auth_headers,
            files=files
        )
        assert upload_response.status_code == 200
        invoice_url = upload_response.json()["tax_invoice_url"]
        
        # Try to view it
        view_response = requests.get(f"{BASE_URL}{invoice_url}", headers=auth_headers)
        assert view_response.status_code == 200, f"Cannot view invoice: {view_response.status_code}"
        
        # Verify it's a PDF
        content = view_response.content
        assert content[:4] == b'%PDF', "Response is not a valid PDF"
        print(f"PASS: Invoice viewable at {invoice_url}")


class TestInvoiceFilter:
    """Tests for invoice filter functionality"""
    
    def test_filter_gst_orders(self, auth_headers):
        """Test filtering orders by GST applicable"""
        response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=auth_headers)
        assert response.status_code == 200
        
        orders = response.json()
        gst_orders = [o for o in orders if o.get("gst_applicable")]
        non_gst_orders = [o for o in orders if not o.get("gst_applicable")]
        
        print(f"PASS: Found {len(gst_orders)} GST orders and {len(non_gst_orders)} non-GST orders")
        
        # Verify GST orders have the gst_applicable flag
        for order in gst_orders:
            assert order.get("gst_applicable") == True
        
        print("PASS: All GST orders have gst_applicable=True")


class TestRoleBasedAccess:
    """Tests for role-based access to invoice upload"""
    
    def test_accounts_user_can_upload(self, auth_headers):
        """Test that accounts role can upload invoices"""
        # First check if accounts user exists, if not skip
        users_response = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
        if users_response.status_code != 200:
            pytest.skip("Cannot list users")
        
        users = users_response.json()
        accounts_users = [u for u in users if u.get("role") == "accounts"]
        
        if not accounts_users:
            # Create an accounts user for testing
            create_response = requests.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
                "username": "test_accounts_invoice",
                "password": "test123",
                "name": "Test Accounts User",
                "role": "accounts"
            })
            if create_response.status_code != 200:
                pytest.skip("Cannot create accounts user")
        
        # Login as accounts user
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_accounts_invoice",
            "password": "test123"
        })
        
        if login_response.status_code != 200:
            pytest.skip("Cannot login as accounts user")
        
        accounts_token = login_response.json()["token"]
        accounts_headers = {"Authorization": f"Bearer {accounts_token}"}
        
        # Get a GST order
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=accounts_headers)
        assert orders_response.status_code == 200
        
        gst_orders = [o for o in orders_response.json() if o.get("gst_applicable")]
        if not gst_orders:
            pytest.skip("No GST orders available")
        
        order_id = gst_orders[0]["id"]
        
        # Try to upload
        tax_pdf = create_test_pdf("Accounts User Upload", num_pages=1)
        files = {"tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")}
        
        upload_response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=accounts_headers,
            files=files
        )
        
        assert upload_response.status_code == 200, f"Accounts user upload failed: {upload_response.text}"
        print("PASS: Accounts user can upload invoices")
    
    def test_telecaller_cannot_upload(self, auth_headers):
        """Test that telecaller role cannot upload invoices"""
        # Check if telecaller user exists
        users_response = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
        users = users_response.json()
        telecaller_users = [u for u in users if u.get("role") == "telecaller"]
        
        if not telecaller_users:
            # Create a telecaller user
            create_response = requests.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
                "username": "test_telecaller_invoice",
                "password": "test123",
                "name": "Test Telecaller",
                "role": "telecaller"
            })
            if create_response.status_code != 200:
                pytest.skip("Cannot create telecaller user")
        
        # Login as telecaller
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "test_telecaller_invoice",
            "password": "test123"
        })
        
        if login_response.status_code != 200:
            pytest.skip("Cannot login as telecaller")
        
        telecaller_token = login_response.json()["token"]
        telecaller_headers = {"Authorization": f"Bearer {telecaller_token}"}
        
        # Get a GST order
        orders_response = requests.get(f"{BASE_URL}/api/orders?view_all=true", headers=telecaller_headers)
        if orders_response.status_code != 200:
            pytest.skip("Telecaller cannot view orders")
        
        gst_orders = [o for o in orders_response.json() if o.get("gst_applicable")]
        if not gst_orders:
            pytest.skip("No GST orders available")
        
        order_id = gst_orders[0]["id"]
        
        # Try to upload (should fail)
        tax_pdf = create_test_pdf("Telecaller Upload Attempt", num_pages=1)
        files = {"tax_invoice": ("tax_invoice.pdf", tax_pdf, "application/pdf")}
        
        upload_response = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/invoice-upload",
            headers=telecaller_headers,
            files=files
        )
        
        assert upload_response.status_code == 403, f"Expected 403 for telecaller, got {upload_response.status_code}"
        print("PASS: Telecaller correctly denied invoice upload access")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
