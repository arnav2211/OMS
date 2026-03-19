import requests
import sys
import json
import time
from datetime import datetime

class CitSprayAPITester:
    def __init__(self, base_url="https://logistics-pro-76.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user_data = None
        self.tests_run = 0
        self.tests_passed = 0
        self.customer_id = None
        self.order_id = None
        self.telecaller_user_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}" if not endpoint.startswith('http') else endpoint
        test_headers = {'Content-Type': 'application/json'}
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if response_data:
                        print(f"   Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Array with ' + str(len(response_data)) + ' items'}")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error text: {response.text[:200]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin123"}
        )
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            self.user_data = response['user']
            print(f"   Logged in as: {self.user_data['name']} ({self.user_data['role']})")
            return True
        return False

    def test_auth_me(self):
        """Test auth me endpoint"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_create_telecaller_user(self):
        """Test creating a telecaller user"""
        success, response = self.run_test(
            "Create Telecaller User",
            "POST",
            "users",
            200,
            data={
                "username": f"testuser_{int(time.time())}",
                "password": "test123",
                "name": "Test Telecaller",
                "role": "telecaller"
            }
        )
        if success and 'id' in response:
            self.telecaller_user_id = response['id']
        return success

    def test_list_users(self):
        """Test listing users"""
        success, response = self.run_test(
            "List Users",
            "GET",
            "users",
            200
        )
        return success

    def test_create_customer(self):
        """Test creating a customer"""
        success, response = self.run_test(
            "Create Customer",
            "POST",
            "customers",
            200,
            data={
                "name": "Test Customer Corp",
                "gst_no": "27AABCU9603R1ZM",
                "billing_address": {
                    "address": "123 Test Street",
                    "city": "Mumbai", 
                    "state": "Maharashtra",
                    "pincode": "400001"
                },
                "shipping_address": {
                    "address": "123 Test Street",
                    "city": "Mumbai",
                    "state": "Maharashtra", 
                    "pincode": "400001"
                },
                "phone_numbers": ["9876543210", "8765432109"],
                "email": "test@testcorp.com"
            }
        )
        if success and 'id' in response:
            self.customer_id = response['id']
        return success

    def test_list_customers(self):
        """Test listing customers"""
        success, response = self.run_test(
            "List Customers",
            "GET",
            "customers",
            200
        )
        return success

    def test_search_customers(self):
        """Test customer search"""
        success, response = self.run_test(
            "Search Customers",
            "GET",
            "customers?search=Test",
            200
        )
        return success

    def test_create_order(self):
        """Test creating an order"""
        if not self.customer_id:
            print("❌ Cannot create order - no customer ID")
            return False
            
        success, response = self.run_test(
            "Create Order",
            "POST", 
            "orders",
            200,
            data={
                "customer_id": self.customer_id,
                "purpose": "Testing order creation via API",
                "items": [
                    {
                        "product_name": "Test Citrus Spray 500ml",
                        "qty": 2,
                        "unit": "pcs",
                        "rate": 150.0,
                        "amount": 300.0,
                        "gst_rate": 18,
                        "gst_amount": 54.0,
                        "total": 354.0
                    },
                    {
                        "product_name": "Test Cleaning Solution 1L", 
                        "qty": 1,
                        "unit": "L",
                        "rate": 200.0,
                        "amount": 200.0,
                        "gst_rate": 18,
                        "gst_amount": 36.0,
                        "total": 236.0
                    }
                ],
                "gst_applicable": True,
                "shipping_method": "courier",
                "courier_name": "Test Courier",
                "shipping_charge": 50.0,
                "shipping_gst": 9.0,
                "remark": "Test order for API validation"
            }
        )
        if success and 'id' in response:
            self.order_id = response['id']
            print(f"   Created order: {response.get('order_number')}")
        return success

    def test_list_orders(self):
        """Test listing orders"""
        success, response = self.run_test(
            "List Orders",
            "GET",
            "orders",
            200
        )
        return success

    def test_get_order_detail(self):
        """Test getting order details"""
        if not self.order_id:
            print("❌ Cannot get order detail - no order ID")
            return False
            
        success, response = self.run_test(
            "Get Order Detail",
            "GET", 
            f"orders/{self.order_id}",
            200
        )
        return success

    def test_order_filters(self):
        """Test order filtering"""
        tests = [
            ("Filter by Status", "orders?status=new"),
            ("Filter by Date", "orders?date_from=2024-01-01&date_to=2024-12-31"), 
            ("Search Orders", "orders?search=CS-")
        ]
        
        all_passed = True
        for test_name, endpoint in tests:
            success, _ = self.run_test(test_name, "GET", endpoint, 200)
            if not success:
                all_passed = False
        return all_passed

    def test_update_formulation(self):
        """Test updating order formulation (admin only)"""
        if not self.order_id:
            print("❌ Cannot update formulation - no order ID")
            return False
            
        success, response = self.run_test(
            "Update Formulation",
            "PUT",
            f"orders/{self.order_id}/formulation",
            200,
            data={
                "items": [
                    {
                        "index": 0,
                        "formulation": "Mix 10ml base with 5ml active ingredient. pH should be 6.5-7.0",
                        "show_formulation": True
                    },
                    {
                        "index": 1, 
                        "formulation": "Dilute 1:10 with distilled water. Add stabilizer 0.1%",
                        "show_formulation": False
                    }
                ]
            }
        )
        return success

    def test_update_packaging(self):
        """Test updating packaging details"""
        if not self.order_id:
            print("❌ Cannot update packaging - no order ID")
            return False
            
        success, response = self.run_test(
            "Update Packaging",
            "PUT",
            f"orders/{self.order_id}/packaging", 
            200,
            data={
                "item_images": {
                    "0": ["/api/uploads/test1.jpg"],
                    "1": ["/api/uploads/test2.jpg"]
                },
                "order_images": ["/api/uploads/order1.jpg"],
                "packed_box_images": ["/api/uploads/box1.jpg"],
                "packed_by": "Test Packer",
                "status": "packed"
            }
        )
        return success

    def test_update_dispatch(self):
        """Test updating dispatch details"""
        if not self.order_id:
            print("❌ Cannot update dispatch - no order ID")
            return False
            
        success, response = self.run_test(
            "Update Dispatch",
            "PUT",
            f"orders/{self.order_id}/dispatch",
            200,
            data={
                "courier_name": "DTDC Express",
                "transporter_name": "Test Transport Co",
                "lr_no": "LR123456789"
            }
        )
        return success

    def test_gst_verification(self):
        """Test GST number verification"""
        success, response = self.run_test(
            "GST Verification",
            "GET",
            "gst-verify/27AABCU9603R1ZM",
            200
        )
        return success

    def test_dashboard_stats(self):
        """Test dashboard statistics"""
        success, response = self.run_test(
            "Dashboard Stats",
            "GET",
            "reports/dashboard",
            200
        )
        return success

    def test_sales_report(self):
        """Test sales report"""
        success, response = self.run_test(
            "Sales Report",
            "GET",
            "reports/sales",
            200
        )
        return success

    def test_sales_report_with_filters(self):
        """Test sales report with date filters"""
        success, response = self.run_test(
            "Sales Report with Date Filter",
            "GET",
            "reports/sales?date_from=2024-01-01&date_to=2024-12-31",
            200
        )
        return success

def main():
    print("🚀 Starting CitSpray Order Management System API Tests")
    print("=" * 60)
    
    tester = CitSprayAPITester()
    
    # Test sequence
    test_sequence = [
        ("Authentication", [
            tester.test_login,
            tester.test_auth_me
        ]),
        ("User Management", [
            tester.test_create_telecaller_user,
            tester.test_list_users
        ]),
        ("Customer Management", [
            tester.test_create_customer,
            tester.test_list_customers,
            tester.test_search_customers
        ]),
        ("Order Management", [
            tester.test_create_order,
            tester.test_list_orders,
            tester.test_get_order_detail,
            tester.test_order_filters
        ]),
        ("Order Operations", [
            tester.test_update_formulation,
            tester.test_update_packaging,
            tester.test_update_dispatch
        ]),
        ("Utilities & Reports", [
            tester.test_gst_verification,
            tester.test_dashboard_stats,
            tester.test_sales_report,
            tester.test_sales_report_with_filters
        ])
    ]
    
    # Run test categories
    for category, tests in test_sequence:
        print(f"\n📋 {category}")
        print("-" * 40)
        category_passed = 0
        category_total = len(tests)
        
        for test_func in tests:
            if test_func():
                category_passed += 1
                
        print(f"\n📊 {category} Results: {category_passed}/{category_total} passed")
    
    # Final results
    print(f"\n🏁 Final Results")
    print("=" * 40)
    print(f"Total Tests: {tester.tests_run}")
    print(f"Passed: {tester.tests_passed}")
    print(f"Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run*100):.1f}%")
    
    # Test data for reference
    if tester.customer_id:
        print(f"\nCreated Customer ID: {tester.customer_id}")
    if tester.order_id:
        print(f"Created Order ID: {tester.order_id}")
    if tester.telecaller_user_id:
        print(f"Created User ID: {tester.telecaller_user_id}")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())