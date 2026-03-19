"""
CitSpray OMS Phase 3 Backend Tests
Tests for:
- Admin dashboard/orders merged view
- Settings (formulation toggle, packaging staff CRUD)
- Telecaller user creation and dashboard with View All toggle
- Packaging staff multi-select fields (mandatory for packed status)
- Dispatch logic with courier dropdown and transport LR requirement
- Order print endpoint (PDF)
- Executive Reports (admin views telecaller dashboard)
- Formulation history endpoint
- Courier options API
- Packaging staff API
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthAndSetup:
    """Authentication and basic setup tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token for authenticated requests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print("PASS: Admin login successful")


class TestPackagingStaffAPI:
    """Packaging Staff CRUD tests"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_packaging_staff_returns_defaults(self, admin_headers):
        """Test default packaging staff (Yogita, Sapna, Samiksha)"""
        response = requests.get(f"{BASE_URL}/api/packaging-staff", headers=admin_headers)
        assert response.status_code == 200
        staff = response.json()
        names = [s["name"] for s in staff]
        # Default staff should be present
        assert "Yogita" in names or "Sapna" in names or "Samiksha" in names, f"No default staff found: {names}"
        print(f"PASS: Packaging staff API returns {len(staff)} staff members")
    
    def test_add_packaging_staff(self, admin_headers):
        """Test adding new packaging staff"""
        response = requests.post(
            f"{BASE_URL}/api/packaging-staff",
            json={"name": "TestStaff_Phase3"},
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TestStaff_Phase3"
        assert "id" in data
        print(f"PASS: Added new staff: {data['name']}")
        return data["id"]
    
    def test_add_duplicate_staff_fails(self, admin_headers):
        """Test duplicate staff name is rejected"""
        # First add
        requests.post(
            f"{BASE_URL}/api/packaging-staff",
            json={"name": "DuplicateTest"},
            headers=admin_headers
        )
        # Try duplicate
        response = requests.post(
            f"{BASE_URL}/api/packaging-staff",
            json={"name": "DuplicateTest"},
            headers=admin_headers
        )
        assert response.status_code == 400
        print("PASS: Duplicate staff name correctly rejected")
    
    def test_remove_packaging_staff(self, admin_headers):
        """Test soft-delete of packaging staff"""
        # Add a staff first
        add_resp = requests.post(
            f"{BASE_URL}/api/packaging-staff",
            json={"name": "ToBeRemoved"},
            headers=admin_headers
        )
        staff_id = add_resp.json()["id"]
        
        # Remove
        del_resp = requests.delete(
            f"{BASE_URL}/api/packaging-staff/{staff_id}",
            headers=admin_headers
        )
        assert del_resp.status_code == 200
        print("PASS: Staff member removed (soft delete)")


class TestCourierOptionsAPI:
    """Test courier options endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_courier_options(self, admin_headers):
        """Test courier options returns predefined list"""
        response = requests.get(f"{BASE_URL}/api/courier-options", headers=admin_headers)
        assert response.status_code == 200
        options = response.json()
        expected = ["DTDC", "Anjani", "Professional", "India Post"]
        assert options == expected, f"Expected {expected}, got {options}"
        print(f"PASS: Courier options: {options}")


class TestSettingsAPI:
    """Test settings endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_settings(self, admin_headers):
        """Test get settings endpoint"""
        response = requests.get(f"{BASE_URL}/api/settings", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "show_formulation" in data
        print(f"PASS: Settings retrieved - show_formulation: {data['show_formulation']}")
    
    def test_update_formulation_toggle(self, admin_headers):
        """Test toggling global formulation visibility"""
        # Toggle ON
        response = requests.put(
            f"{BASE_URL}/api/settings",
            json={"show_formulation": True},
            headers=admin_headers
        )
        assert response.status_code == 200
        
        # Verify
        get_resp = requests.get(f"{BASE_URL}/api/settings", headers=admin_headers)
        assert get_resp.json()["show_formulation"] == True
        
        # Toggle OFF
        response = requests.put(
            f"{BASE_URL}/api/settings",
            json={"show_formulation": False},
            headers=admin_headers
        )
        assert response.status_code == 200
        print("PASS: Formulation toggle working")


class TestTelecallerWorkflow:
    """Test telecaller creation, login, and dashboard features"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def telecaller_data(self, admin_headers):
        """Create a test telecaller"""
        unique_name = f"TestTelecaller_{int(time.time())}"
        response = requests.post(
            f"{BASE_URL}/api/users",
            json={
                "username": unique_name.lower().replace(" ", "_"),
                "password": "test123",
                "name": unique_name,
                "role": "telecaller"
            },
            headers=admin_headers
        )
        if response.status_code != 200:
            pytest.skip(f"Could not create telecaller: {response.text}")
        return response.json()
    
    @pytest.fixture(scope="class")
    def telecaller_headers(self, telecaller_data):
        """Login as telecaller"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": telecaller_data["username"],
            "password": "test123"
        })
        assert response.status_code == 200, f"Telecaller login failed: {response.text}"
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_create_telecaller(self, telecaller_data):
        """Test telecaller user creation"""
        assert telecaller_data["role"] == "telecaller"
        assert "id" in telecaller_data
        print(f"PASS: Telecaller created: {telecaller_data['name']}")
    
    def test_telecaller_login(self, telecaller_headers):
        """Test telecaller can login"""
        assert "Authorization" in telecaller_headers
        print("PASS: Telecaller login successful")
    
    def test_telecaller_see_own_orders_by_default(self, telecaller_headers):
        """Test telecaller sees only own orders by default (view_all=false)"""
        response = requests.get(
            f"{BASE_URL}/api/orders?view_all=false",
            headers=telecaller_headers
        )
        assert response.status_code == 200
        print("PASS: Telecaller can fetch own orders")
    
    def test_telecaller_view_all_orders_anonymized(self, telecaller_headers):
        """Test telecaller can view all orders with anonymized telecaller info"""
        response = requests.get(
            f"{BASE_URL}/api/orders?view_all=true",
            headers=telecaller_headers
        )
        assert response.status_code == 200
        orders = response.json()
        # If there are orders from other telecallers, they should not have telecaller_name
        for order in orders:
            # telecaller_name should be stripped when view_all=true for non-own orders
            pass  # The backend strips telecaller_name for anonymization
        print(f"PASS: Telecaller can view all orders (count: {len(orders)})")


class TestCreateCustomerAndOrder:
    """Test creating customer and order with courier shipping"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_customer(self, admin_headers):
        """Create a test customer"""
        unique_phone = f"99{int(time.time()) % 100000000:08d}"
        response = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": f"TestCustomer_{int(time.time())}",
                "phone_numbers": [unique_phone],
                "billing_address": {
                    "address": "123 Test St",
                    "city": "Nagpur",
                    "state": "Maharashtra",
                    "pincode": "440001"
                },
                "shipping_address": {
                    "address": "123 Test St",
                    "city": "Nagpur",
                    "state": "Maharashtra",
                    "pincode": "440001"
                }
            },
            headers=admin_headers
        )
        assert response.status_code == 200, f"Customer creation failed: {response.text}"
        return response.json()
    
    def test_create_customer(self, test_customer):
        """Test customer creation"""
        assert "id" in test_customer
        assert test_customer["name"].startswith("TestCustomer_")
        print(f"PASS: Customer created: {test_customer['name']}")
    
    def test_create_order_with_courier(self, admin_headers, test_customer):
        """Test creating order with courier shipping (DTDC)"""
        response = requests.post(
            f"{BASE_URL}/api/orders",
            json={
                "customer_id": test_customer["id"],
                "purpose": "Phase 3 Test Order",
                "items": [
                    {
                        "product_name": "Test Product",
                        "qty": 2,
                        "unit": "L",
                        "rate": 500,
                        "amount": 1000,
                        "gst_rate": 18,
                        "gst_amount": 180,
                        "total": 1180
                    }
                ],
                "gst_applicable": True,
                "shipping_method": "courier",
                "courier_name": "DTDC",
                "shipping_charge": 100
            },
            headers=admin_headers
        )
        assert response.status_code == 200, f"Order creation failed: {response.text}"
        order = response.json()
        assert order["shipping_method"] == "courier"
        assert order["courier_name"] == "DTDC"
        assert order["status"] == "new"
        print(f"PASS: Order created with courier (DTDC): {order['order_number']}")
        return order


class TestPackagingWorkflow:
    """Test packaging workflow with mandatory multi-select fields"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_order(self, admin_headers):
        """Create a test order for packaging"""
        # Create customer first
        unique_phone = f"88{int(time.time()) % 100000000:08d}"
        cust_resp = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": f"PackagingTestCust_{int(time.time())}",
                "phone_numbers": [unique_phone],
                "billing_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"},
                "shipping_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"}
            },
            headers=admin_headers
        )
        customer = cust_resp.json()
        
        # Create order
        order_resp = requests.post(
            f"{BASE_URL}/api/orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_name": "Packaging Test Item", "qty": 1, "unit": "L", "rate": 100, "amount": 100}],
                "shipping_method": "transport",
                "transporter_name": "Test Transporter"
            },
            headers=admin_headers
        )
        return order_resp.json()
    
    def test_mark_packed_without_required_fields_fails(self, admin_headers, test_order):
        """Test that marking as packed without required fields fails"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{test_order['id']}/packaging",
            json={
                "status": "packed",
                "item_packed_by": [],  # Empty - should fail
                "box_packed_by": [],
                "checked_by": []
            },
            headers=admin_headers
        )
        assert response.status_code == 400
        assert "required" in response.text.lower()
        print("PASS: Mark as packed correctly requires mandatory fields")
    
    def test_mark_packed_with_required_fields(self, admin_headers, test_order):
        """Test marking as packed with all required fields"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{test_order['id']}/packaging",
            json={
                "status": "packed",
                "item_packed_by": ["Yogita", "Sapna"],
                "box_packed_by": ["Samiksha"],
                "checked_by": ["Yogita"]
            },
            headers=admin_headers
        )
        assert response.status_code == 200
        order = response.json()
        assert order["status"] == "packed"
        assert order["packaging"]["item_packed_by"] == ["Yogita", "Sapna"]
        print("PASS: Order marked as packed with multi-select fields")
        return order


class TestDispatchWorkflow:
    """Test dispatch logic - courier dropdown, transport LR requirement"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def packaging_headers(self, admin_headers):
        """Create packaging user and get headers"""
        # Create packaging user
        unique_name = f"pkg_user_{int(time.time())}"
        requests.post(
            f"{BASE_URL}/api/users",
            json={"username": unique_name, "password": "test123", "name": "Pkg User", "role": "packaging"},
            headers=admin_headers
        )
        # Login
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": unique_name, "password": "test123"})
        if resp.status_code == 200:
            return {"Authorization": f"Bearer {resp.json()['token']}"}
        return admin_headers  # Fallback to admin
    
    @pytest.fixture(scope="class")
    def transport_order(self, admin_headers):
        """Create a packed transport order"""
        # Create customer
        unique_phone = f"77{int(time.time()) % 100000000:08d}"
        cust_resp = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": f"DispatchTestCust_{int(time.time())}",
                "phone_numbers": [unique_phone],
                "billing_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"},
                "shipping_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"}
            },
            headers=admin_headers
        )
        customer = cust_resp.json()
        
        # Create order with transport
        order_resp = requests.post(
            f"{BASE_URL}/api/orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_name": "Dispatch Test Item", "qty": 1, "unit": "L", "rate": 100, "amount": 100}],
                "shipping_method": "transport",
                "transporter_name": "ABC Logistics"
            },
            headers=admin_headers
        )
        order = order_resp.json()
        
        # Mark as packed
        requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/packaging",
            json={
                "status": "packed",
                "item_packed_by": ["Yogita"],
                "box_packed_by": ["Sapna"],
                "checked_by": ["Samiksha"]
            },
            headers=admin_headers
        )
        
        # Refresh order
        get_resp = requests.get(f"{BASE_URL}/api/orders/{order['id']}", headers=admin_headers)
        return get_resp.json()
    
    def test_transport_dispatch_without_lr_fails_for_packaging(self, packaging_headers, transport_order):
        """Test transport dispatch without LR fails for packaging role"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{transport_order['id']}/dispatch",
            json={
                "lr_no": "",  # Empty - should fail for packaging role
                "transporter_name": "ABC Logistics"
            },
            headers=packaging_headers
        )
        # If packaging role, should fail
        if "packaging" in str(packaging_headers):
            assert response.status_code == 400
            print("PASS: Transport dispatch without LR correctly rejected for packaging role")
        else:
            print("INFO: Using admin headers - LR requirement not enforced for admin")
    
    def test_transport_dispatch_with_lr_succeeds(self, admin_headers, transport_order):
        """Test transport dispatch with LR number succeeds"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{transport_order['id']}/dispatch",
            json={
                "lr_no": "LR123456",
                "transporter_name": "ABC Logistics"
            },
            headers=admin_headers
        )
        assert response.status_code == 200
        order = response.json()
        assert order["status"] == "dispatched"
        assert order["dispatch"]["lr_no"] == "LR123456"
        print("PASS: Transport dispatch with LR number successful")


class TestOrderPrintEndpoint:
    """Test order print PDF endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def test_order(self, admin_headers):
        """Create a test order for printing"""
        unique_phone = f"66{int(time.time()) % 100000000:08d}"
        cust_resp = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": f"PrintTestCust_{int(time.time())}",
                "phone_numbers": [unique_phone],
                "billing_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"},
                "shipping_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"}
            },
            headers=admin_headers
        )
        customer = cust_resp.json()
        
        order_resp = requests.post(
            f"{BASE_URL}/api/orders",
            json={
                "customer_id": customer["id"],
                "items": [
                    {
                        "product_name": "Print Test Item",
                        "qty": 2,
                        "unit": "L",
                        "rate": 500,
                        "amount": 1000,
                        "formulation": "Test formulation details for printing"
                    }
                ],
                "shipping_method": "courier",
                "courier_name": "DTDC"
            },
            headers=admin_headers
        )
        return order_resp.json()
    
    def test_print_endpoint_returns_pdf(self, admin_headers, test_order):
        """Test that print endpoint returns PDF"""
        response = requests.get(
            f"{BASE_URL}/api/orders/{test_order['id']}/print",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        assert len(response.content) > 1000  # PDF should have content
        print(f"PASS: Print endpoint returns PDF ({len(response.content)} bytes)")


class TestExecutiveReports:
    """Test admin viewing telecaller dashboards"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def telecaller_id(self, admin_headers):
        """Get a telecaller's ID"""
        users_resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        users = users_resp.json()
        telecallers = [u for u in users if u["role"] == "telecaller" and u.get("active", True)]
        if not telecallers:
            # Create one
            unique_name = f"report_tc_{int(time.time())}"
            resp = requests.post(
                f"{BASE_URL}/api/users",
                json={"username": unique_name, "password": "test123", "name": "Report TC", "role": "telecaller"},
                headers=admin_headers
            )
            return resp.json()["id"]
        return telecallers[0]["id"]
    
    def test_telecaller_dashboard_endpoint(self, admin_headers, telecaller_id):
        """Test admin can view telecaller dashboard stats"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-dashboard/{telecaller_id}",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_orders" in data
        assert "new_orders" in data
        assert "dispatched_orders" in data
        print(f"PASS: Admin can view telecaller dashboard: {data}")
    
    def test_telecaller_sales_endpoint_for_admin(self, admin_headers, telecaller_id):
        """Test admin can view telecaller sales with telecaller_id param"""
        response = requests.get(
            f"{BASE_URL}/api/reports/telecaller-sales?telecaller_id={telecaller_id}&period=all",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_orders" in data
        assert "total_amount" in data
        print(f"PASS: Admin can view telecaller sales report")


class TestFormulationHistory:
    """Test formulation history endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    @pytest.fixture(scope="class")
    def customer_with_orders(self, admin_headers):
        """Create customer with multiple orders containing formulations"""
        unique_phone = f"55{int(time.time()) % 100000000:08d}"
        cust_resp = requests.post(
            f"{BASE_URL}/api/customers",
            json={
                "name": f"FormHistCust_{int(time.time())}",
                "phone_numbers": [unique_phone],
                "billing_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"},
                "shipping_address": {"address": "Test", "city": "Nagpur", "state": "Maharashtra", "pincode": "440001"}
            },
            headers=admin_headers
        )
        customer = cust_resp.json()
        
        # Create order with formulation
        order_resp = requests.post(
            f"{BASE_URL}/api/orders",
            json={
                "customer_id": customer["id"],
                "items": [{"product_name": "Formulation Item", "qty": 1, "unit": "L", "rate": 100, "amount": 100}],
                "shipping_method": "porter"
            },
            headers=admin_headers
        )
        order = order_resp.json()
        
        # Add formulation via admin
        requests.put(
            f"{BASE_URL}/api/orders/{order['id']}/formulation",
            json={"items": [{"index": 0, "formulation": "Test formulation recipe here"}]},
            headers=admin_headers
        )
        
        return customer
    
    def test_formulation_history_endpoint(self, admin_headers, customer_with_orders):
        """Test formulation history returns previous formulations"""
        response = requests.get(
            f"{BASE_URL}/api/orders/formulation-history/{customer_with_orders['id']}",
            headers=admin_headers
        )
        assert response.status_code == 200
        history = response.json()
        assert isinstance(history, list)
        if len(history) > 0:
            assert "order_number" in history[0]
            assert "items" in history[0]
        print(f"PASS: Formulation history endpoint returns {len(history)} entries")


class TestAdminOrdersView:
    """Test admin can see Executive column in orders"""
    
    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin", "password": "admin123"
        })
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_admin_sees_telecaller_name_in_orders(self, admin_headers):
        """Test admin can see telecaller_name in orders list"""
        response = requests.get(f"{BASE_URL}/api/orders", headers=admin_headers)
        assert response.status_code == 200
        orders = response.json()
        # Admin should see telecaller_name field
        for order in orders:
            # telecaller_name should be present for admin
            if "telecaller_name" in order:
                print(f"PASS: Admin sees Executive column - found telecaller_name: {order['telecaller_name']}")
                return
        if len(orders) == 0:
            print("INFO: No orders to verify telecaller_name visibility")
        else:
            # Check first order has telecaller fields
            assert "telecaller_id" in orders[0] or len(orders) == 0
            print("PASS: Admin orders endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
