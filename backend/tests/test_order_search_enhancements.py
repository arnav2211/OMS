import pytest
import os
import requests
import uuid

# Base URL pointing to the running backend server
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://127.0.0.1:8000').rstrip('/')

# Test credentials
ADMIN_CREDS = {"username": "admin", "password": "admin123"}


class APIClientWrapper:
    """Helper to wrap calls to requests (live URL)"""
    def post(self, endpoint, json=None, headers=None):
        response = requests.post(f"{BASE_URL}{endpoint}", json=json, headers=headers)
        return response.status_code, response.json()

    def get(self, endpoint, headers=None):
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
        return response.status_code, response.json()

    def put(self, endpoint, json=None, headers=None):
        response = requests.put(f"{BASE_URL}{endpoint}", json=json, headers=headers)
        return response.status_code, response.json()


@pytest.fixture(scope="module")
def api_client():
    return APIClientWrapper()


@pytest.fixture(scope="module")
def auth_headers(api_client):
    # Log in as admin
    status_code, data = api_client.post("/api/auth/login", json=ADMIN_CREDS)
    assert status_code == 200, f"Login failed: {data}"
    token = data["token"]
    return {"Authorization": f"Bearer {token}"}


def test_order_search_by_city_state_lr(api_client, auth_headers):
    # 1. Create a unique customer
    unique_suffix = uuid.uuid4().hex[:8]
    cust_name = f"Search Test Cust {unique_suffix}"
    cust_phone = f"9911{uuid.uuid4().hex[:6]}" # Generate valid-like phone number format
    
    customer_payload = {
        "name": cust_name,
        "gst_no": "",
        "phone_numbers": [cust_phone],
        "email": f"search_test_{unique_suffix}@example.com",
        "alias": f"alias_{unique_suffix}"
    }
    
    status, customer = api_client.post("/api/customers", json=customer_payload, headers=auth_headers)
    assert status == 200, f"Failed to create customer: {customer}"
    customer_id = customer["id"]
    
    # 2. Create address for search testing (unique city and state)
    city_name = f"CityXYZ_{unique_suffix}"
    state_name = f"StateABC_{unique_suffix}"
    
    address_payload = {
        "address_line": "123 Search St",
        "city": city_name,
        "state": state_name,
        "pincode": "400001",
        "label": "Office",
        "address_name": cust_name
    }
    
    status, address = api_client.post(f"/api/customers/{customer_id}/addresses", json=address_payload, headers=auth_headers)
    assert status == 200, f"Failed to create address: {address}"
    address_id = address["id"]
    
    # 3. Create an order with this shipping/billing address
    order_payload = {
        "customer_id": customer_id,
        "purpose": "Search test order",
        "items": [
            {
                "product_name": "Test Essential Oil 10ml",
                "qty": 5,
                "unit": "pcs",
                "rate": 100,
                "amount": 500,
                "gst_rate": 18,
                "gst_amount": 90,
                "total": 590
            }
        ],
        "gst_applicable": True,
        "shipping_method": "courier",
        "courier_name": "DTDC",
        "shipping_charge": 100,
        "billing_address_id": address_id,
        "shipping_address_id": address_id,
        "payment_status": "unpaid",
        "amount_paid": 0
    }
    
    status, order = api_client.post("/api/orders", json=order_payload, headers=auth_headers)
    assert status == 200, f"Failed to create order: {order}"
    order_id = order["id"]
    order_number = order["order_number"]
    
    # 4. Search by city name and verify the order is found
    status, search_results = api_client.get(f"/api/orders?search={city_name}", headers=auth_headers)
    assert status == 200
    orders_list = search_results.get("orders", [])
    found_order_ids = [o["id"] for o in orders_list]
    assert order_id in found_order_ids, f"Order {order_number} not found when searching by city '{city_name}'"
    
    # 5. Search by state name and verify the order is found
    status, search_results = api_client.get(f"/api/orders?search={state_name}", headers=auth_headers)
    assert status == 200
    orders_list = search_results.get("orders", [])
    found_order_ids = [o["id"] for o in orders_list]
    assert order_id in found_order_ids, f"Order {order_number} not found when searching by state '{state_name}'"
    
    # 6. Mark the order packed so it can be dispatched
    status, packed_order = api_client.put(f"/api/orders/{order_id}/mark-packed", headers=auth_headers)
    assert status == 200, f"Failed to mark order packed: {packed_order}"
    
    # 7. Dispatch order with a unique LR Number
    lr_number = f"D{unique_suffix[:6]}1234" # Must fit DTDC format check (1 letter + 10 digits) if DTDC is used
    dispatch_payload = {
        "courier_name": "DTDC",
        "transporter_name": "",
        "lr_no": lr_number,
        "dispatch_type": "courier",
        "shipping_method": "courier",
        "dispatch_slip_images": [],
        "porter_link": ""
    }
    
    status, dispatched_order = api_client.put(f"/api/orders/{order_id}/dispatch", json=dispatch_payload, headers=auth_headers)
    assert status == 200, f"Failed to dispatch order: {dispatched_order}"
    
    # 8. Search by LR number and verify the order is found
    status, search_results = api_client.get(f"/api/orders?search={lr_number}", headers=auth_headers)
    assert status == 200
    orders_list = search_results.get("orders", [])
    found_order_ids = [o["id"] for o in orders_list]
    assert order_id in found_order_ids, f"Order {order_number} not found when searching by LR No '{lr_number}'"
    print(f"\n密 PASS: Successfully verified search by city, state, and LR number.")
