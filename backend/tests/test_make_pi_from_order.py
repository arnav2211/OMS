import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8000').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    return response.json()["token"]

@pytest.fixture(scope="module")
def api_client(auth_token):
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session

def test_make_pi_from_order(api_client):
    # Get an existing order
    response = api_client.get(f"{BASE_URL}/api/orders?page_size=1")
    assert response.status_code == 200
    orders = response.json().get("orders", [])
    if not orders:
        pytest.skip("No orders found to test make-pi")
    order = orders[0]
    
    # Make PI from order
    payload = {
        "gst_applicable": True,
        "show_rate": True,
        "pi_date": "2026-06-25"
    }
    response = api_client.post(f"{BASE_URL}/api/orders/{order['id']}/make-pi", json=payload)
    assert response.status_code == 200
    pi = response.json()
    assert pi["gst_applicable"] == True
    assert pi["show_rate"] == True
    assert pi["created_at"].startswith("2026-06-25")
    assert pi["converted_order_id"] == order["id"]
    
    # Verify formulations are cleared
    for item in pi["items"]:
        assert item.get("formulation", "") == ""
    for sample in pi.get("free_samples", []):
        assert sample.get("formulation", "") == ""
        
    # Verify order formulation is unchanged
    order_after = api_client.get(f"{BASE_URL}/api/orders/{order['id']}").json()
    assert order_after["id"] == order["id"]
