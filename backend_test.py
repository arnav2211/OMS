import requests
import sys
import json
import time
from datetime import datetime

class CitSprayAPITester:
    def __init__(self, base_url="https://pi-payment.preview.emergentagent.com/api"):
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

    # NEW FEATURE TESTS FOR CITSPRAY OMS v2
    
    def test_settings_api(self):
        """Test settings GET endpoint"""
        success, response = self.run_test(
            "Get Global Settings",
            "GET",
            "settings",
            200
        )
        if success and 'show_formulation' in response:
            print(f"   Current formulation setting: {response['show_formulation']}")
        return success

    def test_update_settings(self):
        """Test updating global formulation setting (admin only)"""
        success, response = self.run_test(
            "Update Global Formulation Setting",
            "PUT",
            "settings",
            200,
            data={"show_formulation": True}
        )
        return success

    def test_customer_duplicate_prevention(self):
        """Test customer duplicate prevention - phone and GST"""
        # First create a unique customer
        unique_time = int(time.time())
        unique_phone = f"999{unique_time % 10000000}"  # Create unique phone
        unique_gst = f"27AABCU9603R{unique_time % 1000:03d}Z"
        
        success1, response1 = self.run_test(
            "Create Customer for Duplicate Test",
            "POST", 
            "customers",
            200,
            data={
                "name": f"Duplicate Test Customer {unique_time}",
                "gst_no": unique_gst,
                "billing_address": {"address": "Test Address", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
                "shipping_address": {"address": "Test Address", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
                "phone_numbers": [unique_phone],
                "email": f"test{unique_time}@example.com"
            }
        )
        
        if not success1:
            print(f"   Failed to create test customer, trying with different GST")
            # If failed due to GST collision, try a different approach
            unique_gst2 = f"27AABCU9603R{(unique_time + 123) % 1000:03d}Z" 
            success1, response1 = self.run_test(
                "Create Customer for Duplicate Test (Retry)",
                "POST",
                "customers",
                200,
                data={
                    "name": f"Duplicate Test Customer {unique_time}",
                    "gst_no": unique_gst2,
                    "billing_address": {"address": "Test Address", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
                    "shipping_address": {"address": "Test Address", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
                    "phone_numbers": [unique_phone],
                    "email": f"test{unique_time}@example.com"
                }
            )
            unique_gst = unique_gst2
            
        if not success1:
            return False
            
        # Test duplicate phone rejection
        success2, response2 = self.run_test(
            "Test Duplicate Phone Rejection",
            "POST",
            "customers", 
            400,  # Should fail with 400
            data={
                "name": "Another Customer",
                "phone_numbers": [unique_phone],  # Same phone
                "billing_address": {"address": "Different Address", "city": "Delhi", "state": "Delhi", "pincode": "110001"},
                "shipping_address": {"address": "Different Address", "city": "Delhi", "state": "Delhi", "pincode": "110001"},
            }
        )
        
        # Test duplicate GST rejection
        success3, response3 = self.run_test(
            "Test Duplicate GST Rejection", 
            "POST",
            "customers",
            400,  # Should fail with 400
            data={
                "name": "Yet Another Customer",
                "gst_no": unique_gst,  # Same GST
                "phone_numbers": [f"888{(unique_time + 456) % 10000000}"],  # Different phone
                "billing_address": {"address": "Another Address", "city": "Chennai", "state": "Tamil Nadu", "pincode": "600001"},
                "shipping_address": {"address": "Another Address", "city": "Chennai", "state": "Tamil Nadu", "pincode": "600001"},
            }
        )
        
        return success1 and success2 and success3

    def test_customer_orders_endpoint(self):
        """Test GET /api/customers/{id}/orders"""
        # Get first customer from list to test
        list_success, customers = self.run_test("List Customers for Orders Test", "GET", "customers", 200)
        if not list_success or not customers or len(customers) == 0:
            print("❌ No customers found for orders test")
            return False
            
        customer_id = customers[0]['id']
        success, response = self.run_test(
            "Get Customer Orders",
            "GET",
            f"customers/{customer_id}/orders",
            200
        )
        if success:
            print(f"   Found {len(response)} orders for customer")
        return success

    def test_delete_customer_with_orders(self):
        """Test that customers with orders cannot be deleted"""
        # Get customer with orders from previous test
        list_success, customers = self.run_test("List Customers for Delete Test", "GET", "customers", 200)
        if not list_success or not customers:
            return False
            
        # Find a customer with orders (should be the first one as we tested that above)
        customer_with_orders = customers[0]
        
        success, response = self.run_test(
            "Try Delete Customer With Orders (Should Fail)",
            "DELETE",
            f"customers/{customer_with_orders['id']}",
            400  # Should fail with 400
        )
        return success

    def test_cancel_order(self):
        """Test order cancellation with PUT /api/orders/{id}/cancel"""
        # Get an existing order
        list_success, orders = self.run_test("List Orders for Cancel Test", "GET", "orders", 200)
        if not list_success or not orders or len(orders) == 0:
            print("❌ No orders found for cancel test")
            return False
            
        # Find a non-cancelled order
        order_to_cancel = None
        for order in orders:
            if order.get('status') != 'cancelled':
                order_to_cancel = order
                break
                
        if not order_to_cancel:
            print("❌ No non-cancelled orders found")
            return False
            
        success, response = self.run_test(
            "Cancel Order",
            "PUT",
            f"orders/{order_to_cancel['id']}/cancel",
            200
        )
        if success and response.get('status') == 'cancelled':
            print(f"   Successfully cancelled order {response.get('order_number')}")
        return success

    def test_update_payment_status(self):
        """Test updating order payment status and amount"""
        # Get an existing order
        list_success, orders = self.run_test("List Orders for Payment Test", "GET", "orders", 200)
        if not list_success or not orders or len(orders) == 0:
            return False
            
        # Use first available order
        order = orders[0]
        success, response = self.run_test(
            "Update Order Payment Status",
            "PUT", 
            f"orders/{order['id']}",
            200,
            data={
                "payment_status": "partial",
                "amount_paid": 100.0,
                "balance_amount": max(0, order.get('grand_total', 0) - 100.0)
            }
        )
        return success

    def test_proforma_invoice_crud(self):
        """Test Proforma Invoice CRUD operations"""
        # First get a customer
        list_success, customers = self.run_test("List Customers for PI Test", "GET", "customers", 200)
        if not list_success or not customers:
            return False
            
        customer = customers[0]
        
        # Create PI
        success1, pi_response = self.run_test(
            "Create Proforma Invoice",
            "POST",
            "proforma-invoices",
            200,
            data={
                "customer_id": customer['id'],
                "items": [
                    {
                        "product_name": "Test PI Product 1",
                        "qty": 2,
                        "unit": "pcs",
                        "rate": 100.0,
                        "amount": 200.0,
                        "gst_rate": 18,
                        "gst_amount": 36.0,
                        "total": 236.0
                    }
                ],
                "gst_applicable": True,
                "show_rate": True,
                "shipping_charge": 25.0,
                "remark": "Test PI creation"
            }
        )
        
        if not success1 or 'id' not in pi_response:
            return False
            
        pi_id = pi_response['id']
        print(f"   Created PI: {pi_response.get('pi_number')}")
        
        # List PIs
        success2, response2 = self.run_test(
            "List Proforma Invoices", 
            "GET",
            "proforma-invoices",
            200
        )
        
        # Get PI PDF - Note: PDF endpoint returns binary data, not JSON
        success3, response3 = self.run_test(
            "Get PI PDF",
            "GET", 
            f"proforma-invoices/{pi_id}/pdf",
            200
        )
        
        return success1 and success2 and success3

    def test_convert_pi_to_order(self):
        """Test converting PI to order"""
        # Get existing PIs
        list_success, pis = self.run_test("List PIs for Convert Test", "GET", "proforma-invoices", 200)
        if not list_success or not pis or len(pis) == 0:
            print("❌ No PIs found for convert test")
            return False
            
        # Find a non-converted PI
        pi_to_convert = None
        for pi in pis:
            if pi.get('status') != 'converted':
                pi_to_convert = pi
                break
                
        if not pi_to_convert:
            print("❌ No non-converted PIs found")
            return False
            
        success, response = self.run_test(
            "Convert PI to Order",
            "POST",
            f"proforma-invoices/{pi_to_convert['id']}/convert",
            200,
            data={
                "shipping_method": "courier",
                "courier_name": "Test Courier",
                "purpose": "Converted from PI",
                "payment_status": "unpaid",
                "amount_paid": 0
            }
        )
        if success and 'order_number' in response:
            print(f"   Converted to order: {response.get('order_number')}")
        return success

    def test_item_sales_analytics(self):
        """Test item sales analytics API"""
        success, response = self.run_test(
            "Item Sales Analytics",
            "GET",
            "reports/item-sales",
            200
        )
        if success:
            print(f"   Found analytics for {len(response)} products")
        return success

    def test_item_sales_with_date_filter(self):
        """Test item sales analytics with date filters"""
        success, response = self.run_test(
            "Item Sales Analytics with Date Filter",
            "GET",
            "reports/item-sales?date_from=2024-01-01&date_to=2024-12-31",
            200
        )
        return success

    def test_telecaller_sales_reports(self):
        """Test telecaller sales reports with different periods and filters"""
        tests = [
            ("Today Sales", "reports/telecaller-sales?period=today"),
            ("Week Sales", "reports/telecaller-sales?period=week"),
            ("Month Sales", "reports/telecaller-sales?period=month"),
            ("Sales Excluding GST", "reports/telecaller-sales?period=all&exclude_gst=true"),
            ("Sales Excluding Shipping", "reports/telecaller-sales?period=all&exclude_shipping=true"),
            ("Sales Excluding GST & Shipping", "reports/telecaller-sales?period=all&exclude_gst=true&exclude_shipping=true")
        ]
        
        all_passed = True
        for test_name, endpoint in tests:
            success, response = self.run_test(test_name, "GET", endpoint, 200)
            if not success:
                all_passed = False
            elif response:
                print(f"   {test_name}: {response.get('total_orders', 0)} orders, ₹{response.get('product_sales', 0)}")
                
        return all_passed

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
        ("Settings API (NEW)", [
            tester.test_settings_api,
            tester.test_update_settings
        ]),
        ("Customer Management", [
            tester.test_list_customers,
            tester.test_search_customers
        ]),
        ("Customer Duplicate Prevention (NEW)", [
            tester.test_customer_duplicate_prevention
        ]),
        ("Customer Orders & Delete (NEW)", [
            tester.test_customer_orders_endpoint,
            tester.test_delete_customer_with_orders
        ]),
        ("Order Management", [
            tester.test_list_orders,
            tester.test_order_filters
        ]),
        ("Order Cancel & Payment (NEW)", [
            tester.test_cancel_order,
            tester.test_update_payment_status
        ]),
        ("Proforma Invoice (NEW)", [
            tester.test_proforma_invoice_crud,
            tester.test_convert_pi_to_order
        ]),
        ("Item Sales Analytics (NEW)", [
            tester.test_item_sales_analytics,
            tester.test_item_sales_with_date_filter
        ]),
        ("Telecaller Sales (NEW)", [
            tester.test_telecaller_sales_reports
        ]),
        ("Order Operations (Original)", [
            tester.test_update_formulation,
            tester.test_update_packaging,
            tester.test_update_dispatch
        ]),
        ("Utilities & Reports (Original)", [
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