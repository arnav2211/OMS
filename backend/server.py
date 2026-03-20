from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import re
import uuid
import jwt
import io
import math
import aiofiles
import requests
import phonenumbers
import qrcode
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Auth
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.environ.get("JWT_SECRET", "fallback_secret")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()

UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Company Details
COMPANY = {
    "name": "MANGALAM AGRO",
    "brand": "CitSpray Aroma Sciences",
    "address": "B Wing, Poonam Heights, Pandey Layout, Khamla, Nagpur, Maharashtra, 440025",
    "mobile": "9371177870",
    "gstin": "27AGIPA3784B1ZO",
    "email": "aroma@citspray.com",
    "website": "www.citspray.com",
    "state_code": "27",
}
LOGO_PATH = ROOT_DIR / "logo.png"

COURIER_OPTIONS = ["DTDC", "Anjani", "Professional", "India Post"]

# Bank details for PI PDFs
BANK_GST = {
    "account_name": "Mangalam Agro",
    "account_no": "1472002100029992",
    "ifsc": "PUNB0147200",
    "bank": "Punjab National Bank",
    "branch": "Khamla, Nagpur",
    "upi_string": "upi://pay?pa=archanaagrawal80-1@okicici&mam=1&am={amount}&cu=INR",
}
BANK_NON_GST = {
    "account_name": "Arnav Mukul Agrawal",
    "account_no": "1472000100369074",
    "ifsc": "PUNB0147200",
    "bank": "Punjab National Bank",
    "branch": "Khamla, Nagpur",
    "upi_string": "upi://pay?pa=citronellaoilnagpur-2@okaxis&mam=1&am={amount}&cu=INR",
}

PAYMENT_MODES = ["Cash", "Online", "Other"]

GST_STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "25": "Daman & Diu", "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra", "28": "Andhra Pradesh (Old)", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar", "36": "Telangana", "37": "Andhra Pradesh",
}

# Pydantic Models
class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    active: Optional[bool] = None

class AddressCreate(BaseModel):
    address_line: str
    city: str
    state: str
    pincode: str
    label: str = ""

class CustomerCreate(BaseModel):
    name: str
    gst_no: Optional[str] = ""
    phone_numbers: List[str] = []
    email: Optional[str] = ""

class OrderItemModel(BaseModel):
    product_name: str
    qty: float = 0
    unit: str = ""
    rate: float = 0
    amount: float = 0
    gst_rate: float = 0
    gst_amount: float = 0
    total: float = 0
    formulation: str = ""
    description: str = ""

class OrderCreate(BaseModel):
    customer_id: str
    purpose: str = ""
    items: List[OrderItemModel]
    gst_applicable: bool = False
    shipping_method: str = ""
    courier_name: str = ""
    transporter_name: str = ""
    shipping_charge: float = 0
    shipping_gst: float = 0
    remark: str = ""
    payment_status: str = "unpaid"
    amount_paid: float = 0
    payment_screenshots: List[str] = []
    mode_of_payment: str = ""
    payment_mode_details: str = ""
    billing_address_id: str = ""
    shipping_address_id: str = ""

class FormulationUpdate(BaseModel):
    items: List[Dict[str, Any]]

class DispatchUpdate(BaseModel):
    courier_name: str = ""
    transporter_name: str = ""
    lr_no: str = ""
    dispatch_type: str = ""

class PICreate(BaseModel):
    customer_id: str
    items: List[OrderItemModel]
    gst_applicable: bool = False
    show_rate: bool = True
    shipping_charge: float = 0
    remark: str = ""
    billing_address_id: str = ""
    shipping_address_id: str = ""

# Auth Helpers
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(user_id: str, role: str, name: str, username: str) -> str:
    return jwt.encode(
        {"user_id": user_id, "role": role, "name": name, "username": username},
        JWT_SECRET, algorithm=JWT_ALGORITHM
    )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_user_from_token_param(token: str):
    """Authenticate user from a query parameter token (for endpoints opened in new tabs like PDF print)."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="User not found or inactive")
        return user
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Validation Helpers
def normalize_phone(phone: str) -> str:
    """Normalize phone number to +91XXXXXXXXXX format."""
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    if not cleaned:
        return ""
    try:
        parsed = phonenumbers.parse(cleaned, "IN")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    digits = re.sub(r'[^\d]', '', cleaned)
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) == 13 and digits.startswith("091"):
        return f"+91{digits[3:]}"
    return cleaned

def validate_pincode(pincode: str) -> bool:
    return bool(re.match(r'^\d{6}$', pincode))

def validate_gst(gst_no: str) -> bool:
    if not gst_no:
        return True
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$'
    return bool(re.match(pattern, gst_no.upper()))

def validate_email(email: str) -> bool:
    if not email:
        return True
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_alpha_only(text: str) -> bool:
    if not text:
        return True
    return bool(re.match(r'^[a-zA-Z\s]+$', text))

# Startup
@app.on_event("startup")
async def startup():
    await db.users.create_index("username", unique=True)
    await db.customers.create_index("name")
    await db.customers.create_index("phone_numbers")
    await db.customers.create_index("gst_no")
    await db.orders.create_index("order_number")
    await db.orders.create_index("customer_id")
    await db.orders.create_index("status")
    await db.orders.create_index("created_at")
    await db.orders.create_index("telecaller_id")
    await db.addresses.create_index("customer_id")

    existing = await db.users.find_one({"username": "admin"})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "name": "Administrator",
            "role": "admin",
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    existing_counter = await db.counters.find_one({"_id": "order_number"})
    if not existing_counter:
        await db.counters.insert_one({"_id": "order_number", "seq": 0})
    pi_counter = await db.counters.find_one({"_id": "pi_number"})
    if not pi_counter:
        await db.counters.insert_one({"_id": "pi_number", "seq": 0})

    settings = await db.settings.find_one({"_id": "global"})
    if not settings:
        await db.settings.insert_one({"_id": "global", "show_formulation": False})

    # Seed packaging staff
    staff_count = await db.packaging_staff.count_documents({})
    if staff_count == 0:
        for name in ["Yogita", "Sapna", "Samiksha"]:
            await db.packaging_staff.insert_one({
                "id": str(uuid.uuid4()),
                "name": name,
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

# Auth Routes
@api_router.post("/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"username": req.username}, {"_id": 0})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("active", True):
        raise HTTPException(status_code=401, detail="Account is deactivated")
    token = create_token(user["id"], user["role"], user["name"], user["username"])
    return {
        "token": token,
        "user": {
            "id": user["id"], "username": user["username"],
            "name": user["name"], "role": user["role"]
        }
    }

@api_router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "name": user["name"], "role": user["role"]}

# User Management (Admin)
@api_router.post("/users")
async def create_user(req: UserCreate, admin=Depends(require_admin)):
    if req.role not in ["admin", "telecaller", "packaging", "dispatch"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = await db.users.find_one({"username": req.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    user_doc = {
        "id": str(uuid.uuid4()),
        "username": req.username,
        "password_hash": hash_password(req.password),
        "name": req.name,
        "role": req.role,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    return {"id": user_doc["id"], "username": req.username, "name": req.name, "role": req.role, "active": True}

@api_router.get("/users")
async def list_users(admin=Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, req: UserUpdate, admin=Depends(require_admin)):
    update = {}
    if req.name is not None:
        update["name"] = req.name
    if req.role is not None:
        update["role"] = req.role
    if req.password is not None:
        update["password_hash"] = hash_password(req.password)
    if req.active is not None:
        update["active"] = req.active
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db.users.update_one({"id": user_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User updated"}

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}

# Customer Routes
@api_router.post("/customers")
async def create_customer(req: CustomerCreate, user=Depends(get_current_user)):
    # Validate phone numbers
    raw_phones = [p for p in req.phone_numbers if p.strip()]
    if not raw_phones:
        raise HTTPException(status_code=400, detail="At least one phone number is required")
    phones = []
    for p in raw_phones:
        normalized = normalize_phone(p)
        digits = re.sub(r'[^\d]', '', normalized)
        if len(digits) < 10 or len(digits) > 13:
            raise HTTPException(status_code=400, detail=f"Invalid phone number: {p}. Must be a valid 10-digit Indian mobile number.")
        phones.append(normalized)
    # Validate GST
    if req.gst_no and not validate_gst(req.gst_no):
        raise HTTPException(status_code=400, detail="Invalid GST number format")
    # Validate email
    if req.email and not validate_email(req.email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    # Check duplicate phone
    if phones:
        existing_phone = await db.customers.find_one({"phone_numbers": {"$in": phones}}, {"_id": 0})
        if existing_phone:
            raise HTTPException(status_code=400, detail=f"Phone number already exists for customer: {existing_phone['name']}")
    # Check duplicate GST
    if req.gst_no:
        existing_gst = await db.customers.find_one({"$and": [{"gst_no": req.gst_no.upper()}, {"gst_no": {"$ne": ""}}]}, {"_id": 0})
        if existing_gst:
            raise HTTPException(status_code=400, detail=f"GST number already exists for customer: {existing_gst['name']}")
    doc = {
        "id": str(uuid.uuid4()),
        "name": req.name.strip(),
        "gst_no": req.gst_no.upper().strip() if req.gst_no else "",
        "phone_numbers": phones,
        "email": req.email.strip() if req.email else "",
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.customers.insert_one(doc)
    created = await db.customers.find_one({"id": doc["id"]}, {"_id": 0})
    return created

@api_router.get("/customers")
async def list_customers(search: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if search:
        query = {"$or": [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone_numbers": {"$regex": search, "$options": "i"}},
            {"gst_no": {"$regex": search, "$options": "i"}},
        ]}
    customers = await db.customers.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return customers

@api_router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, user=Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@api_router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, req: CustomerCreate, user=Depends(get_current_user)):
    raw_phones = [p for p in req.phone_numbers if p.strip()]
    if not raw_phones:
        raise HTTPException(status_code=400, detail="At least one phone number is required")
    phones = []
    for p in raw_phones:
        normalized = normalize_phone(p)
        digits = re.sub(r'[^\d]', '', normalized)
        if len(digits) < 10 or len(digits) > 13:
            raise HTTPException(status_code=400, detail=f"Invalid phone number: {p}")
        phones.append(normalized)
    if req.gst_no and not validate_gst(req.gst_no):
        raise HTTPException(status_code=400, detail="Invalid GST number format")
    if req.email and not validate_email(req.email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    if phones:
        existing_phone = await db.customers.find_one(
            {"phone_numbers": {"$in": phones}, "id": {"$ne": customer_id}}, {"_id": 0}
        )
        if existing_phone:
            raise HTTPException(status_code=400, detail=f"Phone number already exists for customer: {existing_phone['name']}")
    if req.gst_no:
        existing_gst = await db.customers.find_one(
            {"$and": [{"gst_no": req.gst_no.upper()}, {"gst_no": {"$ne": ""}}, {"id": {"$ne": customer_id}}]}, {"_id": 0}
        )
        if existing_gst:
            raise HTTPException(status_code=400, detail=f"GST number already exists for customer: {existing_gst['name']}")
    update_data = {
        "name": req.name.strip(),
        "gst_no": req.gst_no.upper().strip() if req.gst_no else "",
        "phone_numbers": phones,
        "email": req.email.strip() if req.email else "",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    updated = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    return updated

@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Only admin or telecaller can delete customers")
    order_count = await db.orders.count_documents({"customer_id": customer_id})
    if order_count > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete: customer has {order_count} order(s)")
    result = await db.customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"message": "Customer deleted"}

@api_router.get("/customers/{customer_id}/orders")
async def get_customer_orders(customer_id: str, user=Depends(get_current_user)):
    orders = await db.orders.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    if user["role"] != "admin":
        for o in orders:
            o.pop("telecaller_name", None)
            o.pop("telecaller_id", None)
    return orders

# Address Directory
@api_router.get("/customers/{customer_id}/addresses")
async def list_addresses(customer_id: str, user=Depends(get_current_user)):
    addresses = await db.addresses.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return addresses

@api_router.post("/customers/{customer_id}/addresses")
async def create_address(customer_id: str, req: AddressCreate, user=Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not validate_pincode(req.pincode):
        raise HTTPException(status_code=400, detail="Pincode must be exactly 6 digits")
    doc = {
        "id": str(uuid.uuid4()),
        "customer_id": customer_id,
        "address_line": req.address_line.strip(),
        "city": req.city.strip(),
        "state": req.state.strip(),
        "pincode": req.pincode.strip(),
        "label": req.label.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.addresses.insert_one(doc)
    created = await db.addresses.find_one({"id": doc["id"]}, {"_id": 0})
    return created

@api_router.put("/customers/{customer_id}/addresses/{address_id}")
async def update_address(customer_id: str, address_id: str, req: AddressCreate, user=Depends(get_current_user)):
    if not validate_pincode(req.pincode):
        raise HTTPException(status_code=400, detail="Pincode must be exactly 6 digits")
    update_data = {
        "address_line": req.address_line.strip(),
        "city": req.city.strip(),
        "state": req.state.strip(),
        "pincode": req.pincode.strip(),
        "label": req.label.strip(),
    }
    result = await db.addresses.update_one({"id": address_id, "customer_id": customer_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    updated = await db.addresses.find_one({"id": address_id}, {"_id": 0})
    return updated

@api_router.delete("/customers/{customer_id}/addresses/{address_id}")
async def delete_address(customer_id: str, address_id: str, user=Depends(get_current_user)):
    result = await db.addresses.delete_one({"id": address_id, "customer_id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"message": "Address deleted"}

# Pincode Lookup
@api_router.get("/pincode/{pincode}")
async def lookup_pincode(pincode: str, user=Depends(get_current_user)):
    if not validate_pincode(pincode):
        raise HTTPException(status_code=400, detail="Pincode must be exactly 6 digits")
    try:
        resp = requests.get(f"https://api.postalpincode.in/pincode/{pincode}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data and data[0].get("Status") == "Success" and data[0].get("PostOffice"):
                po = data[0]["PostOffice"][0]
                return {
                    "pincode": pincode,
                    "city": po.get("District", ""),
                    "state": po.get("State", ""),
                    "country": po.get("Country", "India"),
                    "post_offices": [{"name": p.get("Name", ""), "district": p.get("District", ""), "state": p.get("State", "")} for p in data[0]["PostOffice"][:5]]
                }
        raise HTTPException(status_code=404, detail="Pincode not found")
    except requests.RequestException:
        # Fallback: common Indian state/city mapping by pincode prefix
        prefix_map = {
            "11": ("New Delhi", "Delhi"), "12": ("Gurugram", "Haryana"), "13": ("Chandigarh", "Chandigarh"),
            "14": ("Ludhiana", "Punjab"), "15": ("Amritsar", "Punjab"), "16": ("Jammu", "Jammu & Kashmir"),
            "17": ("Shimla", "Himachal Pradesh"), "20": ("Lucknow", "Uttar Pradesh"), "21": ("Varanasi", "Uttar Pradesh"),
            "22": ("Lucknow", "Uttar Pradesh"), "23": ("Allahabad", "Uttar Pradesh"), "24": ("Bareilly", "Uttar Pradesh"),
            "25": ("Agra", "Uttar Pradesh"), "26": ("Dehradun", "Uttarakhand"),
            "30": ("Jaipur", "Rajasthan"), "31": ("Jaipur", "Rajasthan"), "32": ("Jodhpur", "Rajasthan"),
            "33": ("Bikaner", "Rajasthan"), "34": ("Udaipur", "Rajasthan"),
            "36": ("Ahmedabad", "Gujarat"), "37": ("Rajkot", "Gujarat"), "38": ("Surat", "Gujarat"),
            "39": ("Vadodara", "Gujarat"),
            "40": ("Mumbai", "Maharashtra"), "41": ("Mumbai", "Maharashtra"), "42": ("Pune", "Maharashtra"),
            "43": ("Nashik", "Maharashtra"), "44": ("Nagpur", "Maharashtra"), "45": ("Amravati", "Maharashtra"),
            "46": ("Aurangabad", "Maharashtra"),
            "48": ("Bhopal", "Madhya Pradesh"), "49": ("Raipur", "Chhattisgarh"),
            "50": ("Hyderabad", "Telangana"), "51": ("Hyderabad", "Telangana"), "52": ("Visakhapatnam", "Andhra Pradesh"),
            "53": ("Vijayawada", "Andhra Pradesh"),
            "56": ("Bengaluru", "Karnataka"), "57": ("Mysuru", "Karnataka"), "58": ("Hubli", "Karnataka"),
            "59": ("Belgaum", "Karnataka"),
            "60": ("Chennai", "Tamil Nadu"), "61": ("Tiruchirappalli", "Tamil Nadu"), "62": ("Coimbatore", "Tamil Nadu"),
            "63": ("Madurai", "Tamil Nadu"), "64": ("Tirunelveli", "Tamil Nadu"),
            "67": ("Kozhikode", "Kerala"), "68": ("Kochi", "Kerala"), "69": ("Thiruvananthapuram", "Kerala"),
            "70": ("Kolkata", "West Bengal"), "71": ("Kolkata", "West Bengal"), "72": ("Howrah", "West Bengal"),
            "73": ("Siliguri", "West Bengal"),
            "75": ("Bhubaneswar", "Odisha"), "76": ("Cuttack", "Odisha"),
            "78": ("Guwahati", "Assam"),
            "80": ("Patna", "Bihar"), "81": ("Patna", "Bihar"), "82": ("Ranchi", "Jharkhand"),
            "83": ("Ranchi", "Jharkhand"),
            "40": ("Goa", "Goa"),
        }
        prefix2 = pincode[:2]
        if prefix2 in prefix_map:
            city, state = prefix_map[prefix2]
            return {"pincode": pincode, "city": city, "state": state, "country": "India", "post_offices": []}
        return {"pincode": pincode, "city": "", "state": "", "country": "India", "post_offices": []}

# Order Routes
@api_router.post("/orders")
async def create_order(req: OrderCreate, user=Depends(get_current_user)):
    counter = await db.counters.find_one_and_update(
        {"_id": "order_number"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    order_number = f"CS-{counter['seq']:04d}"
    customer = await db.customers.find_one({"id": req.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Fetch addresses
    billing_addr = None
    shipping_addr = None
    if req.billing_address_id:
        billing_addr = await db.addresses.find_one({"id": req.billing_address_id}, {"_id": 0})
    if req.shipping_address_id:
        shipping_addr = await db.addresses.find_one({"id": req.shipping_address_id}, {"_id": 0})

    items = []
    subtotal = 0
    total_gst = 0
    for item in req.items:
        item_dict = item.model_dump()
        if item_dict["rate"] > 0 and item_dict["amount"] == 0:
            item_dict["amount"] = item_dict["rate"] * item_dict["qty"]
        elif item_dict["amount"] > 0 and item_dict["rate"] == 0 and item_dict["qty"] > 0:
            item_dict["rate"] = item_dict["amount"] / item_dict["qty"]
        if req.gst_applicable and item_dict["gst_rate"] > 0:
            item_dict["gst_amount"] = round(item_dict["amount"] * item_dict["gst_rate"] / 100, 2)
        else:
            item_dict["gst_amount"] = 0
        item_dict["total"] = round(item_dict["amount"] + item_dict["gst_amount"], 2)
        subtotal += item_dict["amount"]
        total_gst += item_dict["gst_amount"]
        items.append(item_dict)

    shipping_gst = 0
    if req.gst_applicable and req.shipping_charge > 0:
        shipping_gst = round(req.shipping_charge * 0.18, 2)

    raw_total = subtotal + total_gst + req.shipping_charge + shipping_gst
    grand_total = math.ceil(raw_total)

    order_doc = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "customer_id": req.customer_id,
        "customer_name": customer["name"],
        "purpose": req.purpose,
        "items": items,
        "gst_applicable": req.gst_applicable,
        "shipping_method": req.shipping_method,
        "courier_name": req.courier_name,
        "transporter_name": req.transporter_name,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "status": "new",
        "payment_status": req.payment_status,
        "amount_paid": req.amount_paid if req.payment_status != "unpaid" else 0,
        "balance_amount": round(grand_total - (req.amount_paid if req.payment_status == "partial" else (grand_total if req.payment_status == "full" else 0)), 2),
        "payment_screenshots": req.payment_screenshots,
        "mode_of_payment": req.mode_of_payment,
        "payment_mode_details": req.payment_mode_details,
        "billing_address_id": req.billing_address_id,
        "shipping_address_id": req.shipping_address_id,
        "billing_address": billing_addr,
        "shipping_address": shipping_addr,
        "telecaller_id": user["id"],
        "telecaller_name": user["name"],
        "packaging": {
            "item_images": {},
            "order_images": [],
            "packed_box_images": [],
            "item_packed_by": [],
            "box_packed_by": [],
            "checked_by": [],
            "packed_at": ""
        },
        "dispatch": {
            "courier_name": "",
            "transporter_name": "",
            "lr_no": "",
            "dispatched_by": "",
            "dispatched_at": ""
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.insert_one(order_doc)
    created = await db.orders.find_one({"id": order_doc["id"]}, {"_id": 0})
    return created

@api_router.get("/orders")
async def list_orders(
    status: Optional[str] = None,
    telecaller_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    view_all: Optional[bool] = False,
    user=Depends(get_current_user)
):
    query = {}
    # Role-based filtering
    if not view_all:
        if user["role"] == "telecaller":
            query["telecaller_id"] = user["id"]
        elif user["role"] == "packaging":
            query["status"] = {"$in": ["new", "packaging", "packed", "dispatched"]}
        elif user["role"] == "dispatch":
            query["status"] = {"$in": ["packed", "dispatched"]}
    else:
        # Telecaller viewing all: default to own, but if view_all=true, show all
        if user["role"] == "telecaller" and telecaller_id:
            query["telecaller_id"] = telecaller_id

    if status:
        query["status"] = status
    if telecaller_id and user["role"] == "admin":
        query["telecaller_id"] = telecaller_id
    if customer_id:
        query["customer_id"] = customer_id
    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    if search:
        query["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
        ]

    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)

    # Get settings for formulation visibility
    settings = await db.settings.find_one({"_id": "global"})
    show_formulation_global = settings.get("show_formulation", False) if settings else False

    for o in orders:
        # Hide telecaller info for non-admin
        if user["role"] != "admin":
            if view_all:
                o.pop("telecaller_name", None)
                o.pop("telecaller_id", None)
            elif o.get("telecaller_id") != user.get("id"):
                o.pop("telecaller_name", None)
                o.pop("telecaller_id", None)

        # Strict formulation visibility rules
        if user["role"] == "telecaller":
            # Telecallers NEVER see formulations
            for item in o.get("items", []):
                item.pop("formulation", None)
        elif user["role"] == "packaging":
            # Packaging: only see if global toggle is ON
            if not show_formulation_global:
                for item in o.get("items", []):
                    item.pop("formulation", None)
        elif user["role"] == "dispatch":
            # Dispatch: never see formulations
            for item in o.get("items", []):
                item.pop("formulation", None)
        # Admin: always sees formulations (no stripping)

    return orders

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Hide telecaller info for non-admin
    if user["role"] != "admin":
        order.pop("telecaller_name", None)
        order.pop("telecaller_id", None)
    # Strict formulation visibility
    settings = await db.settings.find_one({"_id": "global"})
    show_formulation_global = settings.get("show_formulation", False) if settings else False
    if user["role"] == "telecaller":
        for item in order.get("items", []):
            item.pop("formulation", None)
    elif user["role"] == "packaging" and not show_formulation_global:
        for item in order.get("items", []):
            item.pop("formulation", None)
    elif user["role"] == "dispatch":
        for item in order.get("items", []):
            item.pop("formulation", None)
    return order

@api_router.put("/orders/{order_id}")
async def update_order(order_id: str, updates: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Only admin or telecaller can edit orders")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Dispatch lock: once dispatched, only formulation can be edited
    if order.get("status") == "dispatched":
        allowed_dispatched = {"payment_status", "amount_paid", "balance_amount"}
        non_allowed = set(updates.keys()) - allowed_dispatched - {"id", "order_number", "updated_at"}
        if non_allowed:
            raise HTTPException(status_code=400, detail="Order is dispatched. Only payment details can be updated. Use formulation endpoint for formulation changes.")
    # Telecaller can only edit their own orders
    if user["role"] == "telecaller" and order.get("telecaller_id") != user["id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own orders")
    updates.pop("id", None)
    updates.pop("order_number", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.orders.update_one({"id": order_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# Formulation (Admin + Packaging when toggle is ON)
@api_router.put("/orders/{order_id}/formulation")
async def update_formulation(order_id: str, req: FormulationUpdate, user=Depends(get_current_user)):
    if user["role"] == "admin":
        pass  # Admin always allowed
    elif user["role"] == "packaging":
        settings = await db.settings.find_one({"_id": "global"})
        if not settings or not settings.get("show_formulation", False):
            raise HTTPException(status_code=403, detail="Formulation editing is currently disabled")
    else:
        raise HTTPException(status_code=403, detail="Only admin or packaging can edit formulations")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    items = order["items"]
    for update_item in req.items:
        idx = update_item.get("index")
        if idx is not None and 0 <= idx < len(items):
            if "formulation" in update_item:
                items[idx]["formulation"] = update_item["formulation"]
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"items": items, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# Packaging
@api_router.put("/orders/{order_id}/packaging")
async def update_packaging(order_id: str, updates: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Packaging or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    packaging = order.get("packaging", {})
    if "item_images" in updates:
        packaging["item_images"] = updates["item_images"]
    if "order_images" in updates:
        packaging["order_images"] = updates["order_images"]
    if "packed_box_images" in updates:
        packaging["packed_box_images"] = updates["packed_box_images"]
    if "item_packed_by" in updates:
        packaging["item_packed_by"] = updates["item_packed_by"]
    if "box_packed_by" in updates:
        packaging["box_packed_by"] = updates["box_packed_by"]
    if "checked_by" in updates:
        packaging["checked_by"] = updates["checked_by"]

    new_status = updates.get("status", order["status"])
    if new_status == "packed":
        # Validate mandatory fields
        if not packaging.get("item_packed_by"):
            raise HTTPException(status_code=400, detail="Item Packed By is required")
        if not packaging.get("box_packed_by"):
            raise HTTPException(status_code=400, detail="Box Packed By is required")
        if not packaging.get("checked_by"):
            raise HTTPException(status_code=400, detail="Checked By is required")
        packaging["packed_at"] = datetime.now(timezone.utc).isoformat()

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"packaging": packaging, "status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# Dispatch
@api_router.put("/orders/{order_id}/dispatch")
async def update_dispatch(order_id: str, req: DispatchUpdate, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Dispatch, packaging or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shipping_method = order.get("shipping_method", "")
    # For transport: dispatch team must provide LR number
    if shipping_method == "transport" and user["role"] in ["dispatch", "packaging"]:
        if not req.lr_no:
            raise HTTPException(status_code=400, detail="LR Number is mandatory for transport dispatch")

    dispatch = {
        "courier_name": req.courier_name,
        "transporter_name": req.transporter_name or order.get("transporter_name", ""),
        "lr_no": req.lr_no,
        "dispatched_by": user["name"],
        "dispatched_at": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"dispatch": dispatch, "status": "dispatched", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# Order Delete (permanent)
@api_router.delete("/orders/{order_id}")
async def delete_order(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Only admin or telecaller can delete")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    result = await db.orders.delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": f"Order {order.get('order_number', '')} permanently deleted"}

# Packaging Staff Management
@api_router.get("/packaging-staff")
async def list_packaging_staff(user=Depends(get_current_user)):
    staff = await db.packaging_staff.find({"active": True}, {"_id": 0}).sort("name", 1).to_list(100)
    return staff

@api_router.post("/packaging-staff")
async def add_packaging_staff(body: dict, admin=Depends(require_admin)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    existing = await db.packaging_staff.find_one({"name": name, "active": True})
    if existing:
        raise HTTPException(status_code=400, detail="Name already exists")
    # Check if soft-deleted, reactivate
    deleted = await db.packaging_staff.find_one({"name": name, "active": False})
    if deleted:
        await db.packaging_staff.update_one({"name": name}, {"$set": {"active": True}})
        updated = await db.packaging_staff.find_one({"name": name}, {"_id": 0})
        return updated
    doc = {"id": str(uuid.uuid4()), "name": name, "active": True, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.packaging_staff.insert_one(doc)
    created = await db.packaging_staff.find_one({"id": doc["id"]}, {"_id": 0})
    return created

@api_router.delete("/packaging-staff/{staff_id}")
async def remove_packaging_staff(staff_id: str, admin=Depends(require_admin)):
    # Soft delete - historical data preserved
    result = await db.packaging_staff.update_one({"id": staff_id}, {"$set": {"active": False}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Staff not found")
    return {"message": "Staff member removed"}

# Courier Options
@api_router.get("/courier-options")
async def get_courier_options(user=Depends(get_current_user)):
    return COURIER_OPTIONS

# Settings
@api_router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    settings = await db.settings.find_one({"_id": "global"})
    return {"show_formulation": settings.get("show_formulation", False) if settings else False}

@api_router.put("/settings")
async def update_settings(updates: dict, admin=Depends(require_admin)):
    allowed = {"show_formulation"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        raise HTTPException(status_code=400, detail="No valid settings to update")
    await db.settings.update_one({"_id": "global"}, {"$set": filtered}, upsert=True)
    return {"message": "Settings updated", **filtered}

# GST Verification
@api_router.get("/gst-verify/{gst_no}")
async def verify_gst(gst_no: str, user=Depends(get_current_user)):
    gst_no = gst_no.upper().strip()
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$'
    if not re.match(pattern, gst_no):
        raise HTTPException(status_code=400, detail="Invalid GSTIN format")
    state_code = gst_no[:2]
    state_name = GST_STATES.get(state_code, "Unknown")
    result = {"gstin": gst_no, "valid_format": True, "state_code": state_code, "state_name": state_name, "pan": gst_no[2:12]}
    gst_api_key = os.environ.get("GST_API_KEY")
    if gst_api_key:
        try:
            resp = requests.get(f"https://sheet.gstincheck.co.in/check/{gst_api_key}/{gst_no}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("flag"):
                    info = data.get("data", {})
                    result["trade_name"] = info.get("tradeNam", "")
                    result["legal_name"] = info.get("lgnm", "")
                    result["address"] = info.get("pradr", {}).get("adr", "")
                    result["status"] = info.get("sts", "")
                    result["api_verified"] = True
        except Exception:
            pass
    return result

# File Upload
@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    filename = f"{uuid.uuid4()}{ext}"
    filepath = UPLOAD_DIR / filename
    async with aiofiles.open(filepath, 'wb') as f:
        content = await file.read()
        await f.write(content)
    return {"url": f"/api/uploads/{filename}", "filename": filename}

# Reports
@api_router.get("/reports/sales")
async def sales_report(date_from: Optional[str] = None, date_to: Optional[str] = None, admin=Depends(require_admin)):
    query = {}
    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    orders = await db.orders.find(query, {"_id": 0}).to_list(5000)
    telecaller_stats = {}
    status_counts = {"new": 0, "packaging": 0, "packed": 0, "dispatched": 0, "cancelled": 0}
    total_revenue = 0
    for order in orders:
        tid = order.get("telecaller_id", "unknown")
        tname = order.get("telecaller_name", "Unknown")
        if tid not in telecaller_stats:
            telecaller_stats[tid] = {"id": tid, "name": tname, "order_count": 0, "total_amount": 0}
        telecaller_stats[tid]["order_count"] += 1
        telecaller_stats[tid]["total_amount"] += order.get("grand_total", 0)
        s = order.get("status", "new")
        if s in status_counts:
            status_counts[s] += 1
        total_revenue += order.get("grand_total", 0)
    return {
        "total_orders": len(orders),
        "total_revenue": round(total_revenue, 2),
        "status_counts": status_counts,
        "telecaller_stats": list(telecaller_stats.values()),
    }

@api_router.get("/reports/dashboard")
async def dashboard_stats(user=Depends(get_current_user)):
    query = {}
    if user["role"] == "telecaller":
        query["telecaller_id"] = user["id"]
    total = await db.orders.count_documents(query)
    new_q = {**query, "status": "new"}
    packaging_q = {**query, "status": {"$in": ["packaging", "new"]}}
    packed_q = {**query, "status": "packed"}
    dispatched_q = {**query, "status": "dispatched"}
    if user["role"] == "packaging":
        packaging_q = {"status": {"$in": ["new", "packaging"]}}
    if user["role"] == "dispatch":
        packed_q = {"status": "packed"}
        dispatched_q = {"status": "dispatched"}
    new_count = await db.orders.count_documents(new_q)
    packaging_count = await db.orders.count_documents(packaging_q)
    packed_count = await db.orders.count_documents(packed_q)
    dispatched_count = await db.orders.count_documents(dispatched_q)
    total_customers = await db.customers.count_documents({})
    return {
        "total_orders": total,
        "new_orders": new_count,
        "packaging_orders": packaging_count,
        "packed_orders": packed_count,
        "dispatched_orders": dispatched_count,
        "total_customers": total_customers
    }

# Telecaller Sales Report
@api_router.get("/reports/telecaller-sales")
async def telecaller_sales(
    period: Optional[str] = "all",
    exclude_gst: Optional[bool] = False,
    exclude_shipping: Optional[bool] = False,
    telecaller_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user=Depends(get_current_user)
):
    # If admin provides telecaller_id, use that; otherwise use own id
    target_id = telecaller_id if (telecaller_id and user["role"] == "admin") else user["id"]
    query = {"telecaller_id": target_id, "status": {"$ne": "cancelled"}}
    now = datetime.now(timezone.utc)

    # Custom date range takes priority over period
    if date_from or date_to:
        if date_from:
            query.setdefault("created_at", {})["$gte"] = date_from
        if date_to:
            query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    elif period == "today":
        query["created_at"] = {"$gte": now.replace(hour=0, minute=0, second=0).isoformat()}
    elif period == "week":
        week_start = now - timedelta(days=now.weekday())
        query["created_at"] = {"$gte": week_start.replace(hour=0, minute=0, second=0).isoformat()}
    elif period == "month":
        query["created_at"] = {"$gte": now.replace(day=1, hour=0, minute=0, second=0).isoformat()}

    orders = await db.orders.find(query, {"_id": 0}).to_list(5000)
    total_orders = len(orders)
    total_amount = 0
    product_only_amount = 0
    for order in orders:
        total_amount += order.get("grand_total", 0)
        if exclude_gst and exclude_shipping:
            product_only_amount += order.get("subtotal", 0)
        elif exclude_gst:
            product_only_amount += order.get("subtotal", 0) + order.get("shipping_charge", 0)
        elif exclude_shipping:
            product_only_amount += order.get("subtotal", 0) + order.get("total_gst", 0)
        else:
            product_only_amount += order.get("grand_total", 0)

    return {
        "period": period,
        "total_orders": total_orders,
        "total_amount": round(total_amount, 2),
        "product_sales": round(product_only_amount, 2),
        "orders": orders
    }

# Admin view telecaller dashboard
@api_router.get("/reports/telecaller-dashboard/{target_telecaller_id}")
async def telecaller_dashboard_for_admin(
    target_telecaller_id: str,
    admin=Depends(require_admin)
):
    # Return same stats the telecaller would see
    query = {"telecaller_id": target_telecaller_id}
    total = await db.orders.count_documents(query)
    new_count = await db.orders.count_documents({**query, "status": "new"})
    packaging_count = await db.orders.count_documents({**query, "status": {"$in": ["packaging", "new"]}})
    packed_count = await db.orders.count_documents({**query, "status": "packed"})
    dispatched_count = await db.orders.count_documents({**query, "status": "dispatched"})
    return {
        "total_orders": total,
        "new_orders": new_count,
        "packaging_orders": packaging_count,
        "packed_orders": packed_count,
        "dispatched_orders": dispatched_count,
    }

# Item Sales Analytics
@api_router.get("/reports/item-sales")
async def item_sales_report(date_from: Optional[str] = None, date_to: Optional[str] = None, admin=Depends(require_admin)):
    query = {"status": {"$ne": "cancelled"}}
    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    orders = await db.orders.find(query, {"_id": 0}).to_list(5000)
    item_stats = {}
    for order in orders:
        for item in order.get("items", []):
            name_key = item.get("product_name", "").strip().lower()
            display_name = item.get("product_name", "").strip()
            if name_key not in item_stats:
                item_stats[name_key] = {"product_name": display_name, "total_qty": 0, "total_amount": 0, "order_count": 0, "orders": []}
            item_stats[name_key]["total_qty"] += item.get("qty", 0)
            item_stats[name_key]["total_amount"] += item.get("amount", 0)
            item_stats[name_key]["order_count"] += 1
            item_stats[name_key]["orders"].append({
                "order_number": order.get("order_number"),
                "order_id": order.get("id"),
                "customer_name": order.get("customer_name"),
                "qty": item.get("qty", 0),
                "amount": item.get("amount", 0),
                "date": order.get("created_at"),
            })
    result = sorted(item_stats.values(), key=lambda x: x["total_amount"], reverse=True)
    for r in result:
        r["total_amount"] = round(r["total_amount"], 2)
    return result

# Admin Company-Wide Analytics
@api_router.get("/reports/admin-analytics")
async def admin_analytics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exclude_gst: Optional[bool] = False,
    exclude_shipping: Optional[bool] = False,
    period: Optional[str] = "month",
    admin=Depends(require_admin)
):
    query = {"status": {"$ne": "cancelled"}}
    now = datetime.now(timezone.utc)
    if date_from or date_to:
        if date_from:
            query.setdefault("created_at", {})["$gte"] = date_from
        if date_to:
            query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    elif period == "today":
        query["created_at"] = {"$gte": now.replace(hour=0, minute=0, second=0).isoformat()}
    elif period == "week":
        week_start = now - timedelta(days=now.weekday())
        query["created_at"] = {"$gte": week_start.replace(hour=0, minute=0, second=0).isoformat()}
    elif period == "month":
        query["created_at"] = {"$gte": now.replace(day=1, hour=0, minute=0, second=0).isoformat()}

    orders = await db.orders.find(query, {"_id": 0}).to_list(5000)
    total_orders = len(orders)
    total_revenue = 0
    product_sales = 0
    status_counts = {"new": 0, "packaging": 0, "packed": 0, "dispatched": 0}
    telecaller_stats = {}

    for order in orders:
        total_revenue += order.get("grand_total", 0)
        s = order.get("status", "new")
        if s in status_counts:
            status_counts[s] += 1
        # Calculate product-only sales based on exclusions
        if exclude_gst and exclude_shipping:
            product_sales += order.get("subtotal", 0)
        elif exclude_gst:
            product_sales += order.get("subtotal", 0) + order.get("shipping_charge", 0)
        elif exclude_shipping:
            product_sales += order.get("subtotal", 0) + order.get("total_gst", 0)
        else:
            product_sales += order.get("grand_total", 0)
        # Per-executive breakdown
        tid = order.get("telecaller_id", "unknown")
        tname = order.get("telecaller_name", "Unknown")
        if tid not in telecaller_stats:
            telecaller_stats[tid] = {"id": tid, "name": tname, "order_count": 0, "total_amount": 0}
        telecaller_stats[tid]["order_count"] += 1
        telecaller_stats[tid]["total_amount"] += order.get("grand_total", 0)

    return {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "product_sales": round(product_sales, 2),
        "status_counts": status_counts,
        "telecaller_stats": sorted(telecaller_stats.values(), key=lambda x: x["total_amount"], reverse=True),
    }

# Formulation History
@api_router.get("/orders/formulation-history/{customer_id}")
async def formulation_history(customer_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Admin or packaging only")
    orders = await db.orders.find(
        {"customer_id": customer_id, "status": {"$ne": "cancelled"}},
        {"_id": 0, "order_number": 1, "id": 1, "items": 1, "created_at": 1, "customer_name": 1}
    ).sort("created_at", -1).to_list(50)
    history = []
    for order in orders:
        items_with_formulation = [
            {"product_name": item["product_name"], "formulation": item.get("formulation", ""), "qty": item.get("qty", 0), "unit": item.get("unit", "")}
            for item in order.get("items", []) if item.get("formulation")
        ]
        if items_with_formulation:
            history.append({
                "order_number": order["order_number"],
                "order_id": order["id"],
                "customer_name": order.get("customer_name", ""),
                "created_at": order["created_at"],
                "items": items_with_formulation
            })
    return history

# Data Reset
@api_router.post("/admin/reset-data")
async def reset_data(admin=Depends(require_admin)):
    await db.orders.delete_many({})
    await db.customers.delete_many({})
    await db.proforma_invoices.delete_many({})
    await db.addresses.delete_many({})
    await db.counters.update_one({"_id": "order_number"}, {"$set": {"seq": 0}})
    await db.counters.update_one({"_id": "pi_number"}, {"$set": {"seq": 0}})
    return {"message": "All orders, customers, and proforma invoices have been cleared"}

# Order Print (Packaging Print) - accepts token via query param for new-tab access
@api_router.get("/orders/{order_id}/print")
async def print_order(order_id: str, size: str = "A4", token: str = ""):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await get_user_from_token_param(token)
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Admin or packaging only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = await db.customers.find_one({"id": order["customer_id"]}, {"_id": 0})

    page_size = A5 if size == "A5" else A4
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=14, spaceAfter=4, alignment=TA_CENTER)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=9, leading=12)
    bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=10, leading=14)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.grey)
    form_style = ParagraphStyle('Formulation', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.HexColor('#B45309'), backColor=colors.HexColor('#FEF3C7'))

    # Company Header
    if LOGO_PATH.exists():
        try:
            logo = Image(str(LOGO_PATH), width=40*mm, height=20*mm)
            logo.hAlign = 'LEFT'
            elements.append(logo)
        except Exception:
            pass

    elements.append(Paragraph(f"<b>{COMPANY['name']}</b>", ParagraphStyle('CoName', parent=styles['Normal'], fontSize=12, leading=16)))
    elements.append(Paragraph(f"<i>{COMPANY['brand']}</i>", ParagraphStyle('CoBrand', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#16A34A'))))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f"<b>ORDER: {order['order_number']}</b>", title_style))
    elements.append(Spacer(1, 3*mm))

    # Order info
    created_date = datetime.fromisoformat(order['created_at']).strftime('%d/%m/%Y %I:%M %p')
    info_data = [
        [Paragraph(f"<b>Date:</b> {created_date}", header_style),
         Paragraph(f"<b>Executive:</b> {order.get('telecaller_name', 'N/A')}", header_style)],
        [Paragraph(f"<b>Status:</b> {order.get('status', '').upper()}", header_style),
         Paragraph(f"<b>Shipping:</b> {order.get('shipping_method', '').replace('_', ' ').title()}", header_style)],
    ]
    pw = page_size[0] - 24*mm
    info_t = Table(info_data, colWidths=[pw/2, pw/2])
    info_t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    elements.append(info_t)
    elements.append(Spacer(1, 3*mm))

    # Customer info
    if customer:
        elements.append(Paragraph("<b>Customer:</b>", bold_style))
        cust_info = f"{customer.get('name', '')}"
        if customer.get('phone_numbers'):
            cust_info += f" | Ph: {', '.join(customer['phone_numbers'])}"
        elements.append(Paragraph(cust_info, header_style))
        sa = order.get("shipping_address")
        if sa and sa.get("address_line"):
            elements.append(Paragraph(f"Ship To: {sa['address_line']}, {sa.get('city','')}, {sa.get('state','')} - {sa.get('pincode','')}", small_style))
        if customer.get("gst_no"):
            elements.append(Paragraph(f"GSTIN: {customer['gst_no']}", small_style))
    elements.append(Spacer(1, 4*mm))

    # Items table with formulations beside each item
    headers = ['#', 'Item', 'Qty', 'Unit', 'Amount', 'Formulation']
    col_widths = [8*mm, pw*0.22, 14*mm, 14*mm, 20*mm, pw*0.35]
    table_data = [headers]
    for i, item in enumerate(order.get("items", [])):
        desc_text = item.get("product_name", "")
        if item.get("description"):
            desc_text += f"\n{item['description']}"
        formulation_text = item.get("formulation", "") or ""
        row = [
            str(i + 1),
            Paragraph(desc_text.replace("\n", "<br/>"), ParagraphStyle('ItemP', parent=styles['Normal'], fontSize=8, leading=10)),
            str(item.get("qty", 0)),
            item.get("unit", ""),
            f"{item.get('amount', 0):.2f}",
            Paragraph(formulation_text, form_style) if formulation_text else "",
        ]
        table_data.append(row)
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16A34A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (2, 1), (4, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0FDF4')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 3*mm))

    # Totals
    total_style = ParagraphStyle('TotalRight', parent=styles['Normal'], fontSize=9, alignment=TA_RIGHT)
    totals = []
    totals.append([Paragraph("Subtotal:", total_style), Paragraph(f"{order.get('subtotal', 0):.2f}", total_style)])
    if order.get("total_gst", 0) > 0:
        totals.append([Paragraph("GST:", total_style), Paragraph(f"{order['total_gst']:.2f}", total_style)])
    if order.get("shipping_charge", 0) > 0:
        totals.append([Paragraph("Shipping:", total_style), Paragraph(f"{order['shipping_charge']:.2f}", total_style)])
    total_bold = ParagraphStyle('TotalBold', parent=styles['Normal'], fontSize=10, alignment=TA_RIGHT)
    totals.append([Paragraph("<b>Grand Total:</b>", total_bold), Paragraph(f"<b>INR {order.get('grand_total', 0):.2f}</b>", total_bold)])
    tt = Table(totals, colWidths=[pw - 50*mm, 50*mm])
    tt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black)]))
    elements.append(tt)
    elements.append(Spacer(1, 5*mm))

    # Mode of Payment
    if order.get("mode_of_payment"):
        mop_text = f"<b>Mode of Payment:</b> {order['mode_of_payment']}"
        if order.get("payment_mode_details"):
            mop_text += f" ({order['payment_mode_details']})"
        elements.append(Paragraph(mop_text, header_style))
        elements.append(Spacer(1, 2*mm))

    # Dispatch info
    if order.get("shipping_method"):
        elements.append(Spacer(1, 3*mm))
        elements.append(Paragraph(f"<b>Dispatch Type:</b> {order['shipping_method'].replace('_', ' ').title()}", header_style))
        if order.get("courier_name"):
            elements.append(Paragraph(f"<b>Courier:</b> {order['courier_name']}", header_style))
        if order.get("transporter_name"):
            elements.append(Paragraph(f"<b>Transporter:</b> {order['transporter_name']}", header_style))

    if order.get("remark"):
        elements.append(Spacer(1, 3*mm))
        elements.append(Paragraph(f"<b>Remarks:</b> {order['remark']}", header_style))

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={order['order_number']}_packing.pdf"}
    )

# Proforma Invoice
@api_router.post("/proforma-invoices")
async def create_pi(req: PICreate, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    counter = await db.counters.find_one_and_update(
        {"_id": "pi_number"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    pi_number = f"PI-{counter['seq']:04d}"
    customer = await db.customers.find_one({"id": req.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    items = []
    subtotal = 0
    total_gst = 0
    for item in req.items:
        d = item.model_dump()
        if d["rate"] > 0 and d["amount"] == 0:
            d["amount"] = round(d["rate"] * d["qty"], 2)
        elif d["amount"] > 0 and d["rate"] == 0 and d["qty"] > 0:
            d["rate"] = round(d["amount"] / d["qty"], 2)
        if req.gst_applicable and d["gst_rate"] > 0:
            d["gst_amount"] = round(d["amount"] * d["gst_rate"] / 100, 2)
        else:
            d["gst_amount"] = 0
        d["total"] = round(d["amount"] + d["gst_amount"], 2)
        subtotal += d["amount"]
        total_gst += d["gst_amount"]
        items.append(d)
    shipping_gst = round(req.shipping_charge * 0.18, 2) if req.gst_applicable and req.shipping_charge > 0 else 0
    grand_total = math.ceil(subtotal + total_gst + req.shipping_charge + shipping_gst)

    # Fetch addresses
    billing_addr = None
    shipping_addr = None
    if req.billing_address_id:
        billing_addr = await db.addresses.find_one({"id": req.billing_address_id}, {"_id": 0})
    if req.shipping_address_id:
        shipping_addr = await db.addresses.find_one({"id": req.shipping_address_id}, {"_id": 0})

    pi_doc = {
        "id": str(uuid.uuid4()),
        "pi_number": pi_number,
        "customer_id": req.customer_id,
        "customer_name": customer["name"],
        "items": items,
        "gst_applicable": req.gst_applicable,
        "show_rate": req.show_rate,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "status": "draft",
        "converted_order_id": "",
        "billing_address_id": req.billing_address_id,
        "shipping_address_id": req.shipping_address_id,
        "billing_address": billing_addr,
        "shipping_address": shipping_addr,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.proforma_invoices.insert_one(pi_doc)
    created = await db.proforma_invoices.find_one({"id": pi_doc["id"]}, {"_id": 0})
    return created

@api_router.get("/proforma-invoices")
async def list_pis(user=Depends(get_current_user)):
    query = {}
    if user["role"] == "telecaller":
        query["created_by"] = user["id"]
    pis = await db.proforma_invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return pis

@api_router.get("/proforma-invoices/{pi_id}")
async def get_pi(pi_id: str, user=Depends(get_current_user)):
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    return pi

@api_router.put("/proforma-invoices/{pi_id}")
async def update_pi(pi_id: str, req: PICreate, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    customer = await db.customers.find_one({"id": req.customer_id}, {"_id": 0})
    items = []
    subtotal = 0
    total_gst = 0
    for item in req.items:
        d = item.model_dump()
        if d["rate"] > 0 and d["amount"] == 0:
            d["amount"] = round(d["rate"] * d["qty"], 2)
        elif d["amount"] > 0 and d["rate"] == 0 and d["qty"] > 0:
            d["rate"] = round(d["amount"] / d["qty"], 2)
        if req.gst_applicable and d["gst_rate"] > 0:
            d["gst_amount"] = round(d["amount"] * d["gst_rate"] / 100, 2)
        else:
            d["gst_amount"] = 0
        d["total"] = round(d["amount"] + d["gst_amount"], 2)
        subtotal += d["amount"]
        total_gst += d["gst_amount"]
        items.append(d)
    shipping_gst = round(req.shipping_charge * 0.18, 2) if req.gst_applicable and req.shipping_charge > 0 else 0
    grand_total = math.ceil(subtotal + total_gst + req.shipping_charge + shipping_gst)

    billing_addr = None
    shipping_addr = None
    if req.billing_address_id:
        billing_addr = await db.addresses.find_one({"id": req.billing_address_id}, {"_id": 0})
    if req.shipping_address_id:
        shipping_addr = await db.addresses.find_one({"id": req.shipping_address_id}, {"_id": 0})

    update_data = {
        "customer_id": req.customer_id,
        "customer_name": customer["name"] if customer else pi["customer_name"],
        "items": items,
        "gst_applicable": req.gst_applicable,
        "show_rate": req.show_rate,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "billing_address_id": req.billing_address_id,
        "shipping_address_id": req.shipping_address_id,
        "billing_address": billing_addr,
        "shipping_address": shipping_addr,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.proforma_invoices.update_one({"id": pi_id}, {"$set": update_data})
    updated = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    return updated

@api_router.post("/proforma-invoices/{pi_id}/convert")
async def convert_pi_to_order(pi_id: str, body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    if pi.get("converted_order_id"):
        raise HTTPException(status_code=400, detail="PI already converted")
    counter = await db.counters.find_one_and_update(
        {"_id": "order_number"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    order_number = f"CS-{counter['seq']:04d}"
    await db.customers.find_one({"id": pi["customer_id"]}, {"_id": 0})
    order_doc = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "customer_id": pi["customer_id"],
        "customer_name": pi["customer_name"],
        "purpose": body.get("purpose", ""),
        "items": pi["items"],
        "gst_applicable": pi["gst_applicable"],
        "shipping_method": body.get("shipping_method", ""),
        "courier_name": body.get("courier_name", ""),
        "transporter_name": body.get("transporter_name", ""),
        "shipping_charge": pi["shipping_charge"],
        "shipping_gst": pi["shipping_gst"],
        "subtotal": pi["subtotal"],
        "total_gst": pi["total_gst"],
        "grand_total": pi["grand_total"],
        "remark": body.get("remark", pi.get("remark", "")),
        "status": "new",
        "payment_status": body.get("payment_status", "unpaid"),
        "amount_paid": body.get("amount_paid", 0),
        "balance_amount": round(pi["grand_total"] - body.get("amount_paid", 0), 2),
        "payment_screenshots": [],
        "mode_of_payment": body.get("mode_of_payment", ""),
        "payment_mode_details": body.get("payment_mode_details", ""),
        "billing_address_id": pi.get("billing_address_id", ""),
        "shipping_address_id": pi.get("shipping_address_id", ""),
        "billing_address": pi.get("billing_address"),
        "shipping_address": pi.get("shipping_address"),
        "telecaller_id": user["id"],
        "telecaller_name": user["name"],
        "packaging": {"item_images": {}, "order_images": [], "packed_box_images": [], "item_packed_by": [], "box_packed_by": [], "checked_by": [], "packed_at": ""},
        "dispatch": {"courier_name": "", "transporter_name": "", "lr_no": "", "dispatched_by": "", "dispatched_at": ""},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.insert_one(order_doc)
    await db.proforma_invoices.update_one(
        {"id": pi_id},
        {"$set": {"converted_order_id": order_doc["id"], "status": "converted", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    created = await db.orders.find_one({"id": order_doc["id"]}, {"_id": 0})
    return created

# PI PDF Generation - accepts token via query param for new-tab access
@api_router.get("/proforma-invoices/{pi_id}/pdf")
async def generate_pi_pdf(pi_id: str, token: str = ""):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await get_user_from_token_param(token)
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    customer = await db.customers.find_one({"id": pi["customer_id"]}, {"_id": 0})
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []
    pw = A4[0] - 30*mm

    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6, alignment=TA_CENTER)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=9, leading=12)
    bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=10, leading=14)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.grey)
    bank_style = ParagraphStyle('Bank', parent=styles['Normal'], fontSize=8, leading=11)

    # Company header with logo
    if pi.get("gst_applicable"):
        logo_cell = Paragraph("", header_style)
        if LOGO_PATH.exists():
            try:
                logo_cell = Image(str(LOGO_PATH), width=40*mm, height=20*mm)
            except Exception:
                pass
        company_info = Paragraph(
            f"<b>{COMPANY['name']}</b><br/>"
            f"<i>{COMPANY['brand']}</i><br/>"
            f"<font size=7>{COMPANY['address']}</font><br/>"
            f"<font size=7>Mobile: {COMPANY['mobile']} | Email: {COMPANY['email']} | Web: {COMPANY['website']}</font><br/>"
            f"<font size=7>GSTIN: {COMPANY['gstin']}</font>",
            ParagraphStyle('CoInfo', parent=styles['Normal'], fontSize=10, leading=13)
        )
        header_t = Table([[logo_cell, company_info]], colWidths=[45*mm, pw - 45*mm])
        header_t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (0, 0), 0)]))
        elements.append(header_t)
        elements.append(Spacer(1, 6*mm))
    else:
        elements.append(Paragraph(f"<b>{COMPANY['brand']}</b>", ParagraphStyle('BrandOnly', parent=styles['Normal'], fontSize=12, leading=16)))
        elements.append(Spacer(1, 4*mm))

    elements.append(Paragraph("PROFORMA INVOICE", title_style))
    elements.append(Spacer(1, 3*mm))

    pi_info = [[
        Paragraph(f"<b>PI No:</b> {pi['pi_number']}", header_style),
        Paragraph(f"<b>Date:</b> {datetime.fromisoformat(pi['created_at']).strftime('%d/%m/%Y')}", header_style),
    ]]
    t = Table(pi_info, colWidths=[pw/2, pw/2])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(t)
    elements.append(Spacer(1, 4*mm))

    if customer:
        elements.append(Paragraph("<b>Bill To:</b>", bold_style))
        cust_line = customer.get("name", "")
        if customer.get("phone_numbers"):
            cust_line += f" | Ph: {', '.join(customer['phone_numbers'])}"
        elements.append(Paragraph(cust_line, header_style))
        # Use billing address from PI or customer addresses
        ba = pi.get("billing_address")
        if ba and ba.get("address_line"):
            elements.append(Paragraph(f"{ba['address_line']}, {ba.get('city','')}, {ba.get('state','')} - {ba.get('pincode','')}", small_style))
        if customer.get("gst_no"):
            elements.append(Paragraph(f"GSTIN: {customer['gst_no']}", small_style))
        if customer.get("email"):
            elements.append(Paragraph(f"Email: {customer['email']}", small_style))
    elements.append(Spacer(1, 5*mm))

    # Items table
    if pi.get("gst_applicable"):
        if pi.get("show_rate"):
            headers = ['#', 'Item Name', 'Qty', 'Rate', 'Amount', 'GST%', 'GST Amt', 'Total']
            col_widths = [8*mm, 48*mm, 18*mm, 22*mm, 25*mm, 15*mm, 22*mm, 25*mm]
        else:
            headers = ['#', 'Item Name', 'Qty', 'Amount', 'GST%', 'GST Amt', 'Total']
            col_widths = [8*mm, 60*mm, 20*mm, 28*mm, 18*mm, 25*mm, 28*mm]
    else:
        if pi.get("show_rate"):
            headers = ['#', 'Item Name', 'Qty', 'Rate', 'Amount']
            col_widths = [10*mm, 70*mm, 25*mm, 35*mm, 40*mm]
        else:
            headers = ['#', 'Item Name', 'Qty', 'Amount']
            col_widths = [10*mm, 85*mm, 30*mm, 55*mm]
    table_data = [headers]
    for i, item in enumerate(pi.get("items", [])):
        item_name = item.get("product_name", "")
        if item.get("description"):
            item_name += f"\n{item['description']}"
        row = [str(i + 1), Paragraph(item_name.replace("\n", "<br/>"), ParagraphStyle('ItemP', parent=styles['Normal'], fontSize=8, leading=10)), str(item.get("qty", 0))]
        if pi.get("show_rate"):
            row.append(f"{item.get('rate', 0):.2f}")
        row.append(f"{item.get('amount', 0):.2f}")
        if pi.get("gst_applicable"):
            row.append(f"{item.get('gst_rate', 0)}%")
            row.append(f"{item.get('gst_amount', 0):.2f}")
            row.append(f"{item.get('total', 0):.2f}")
        table_data.append(row)
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16A34A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0FDF4')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))

    # Totals
    total_style = ParagraphStyle('TotalRight', parent=styles['Normal'], fontSize=9, alignment=TA_RIGHT)
    total_bold = ParagraphStyle('TotalBold', parent=styles['Normal'], fontSize=11, alignment=TA_RIGHT)
    totals = []
    totals.append([Paragraph("Subtotal:", total_style), Paragraph(f"{pi.get('subtotal', 0):.2f}", total_style)])
    if pi.get("gst_applicable"):
        cust_state = ""
        if pi.get("billing_address"):
            cust_state = pi["billing_address"].get("state", "")
        if not cust_state and customer:
            # Fallback: check customer addresses
            cust_state = ""
        if cust_state.lower() in ["maharashtra"]:
            cgst = round(pi.get("total_gst", 0) / 2, 2)
            totals.append([Paragraph("CGST:", total_style), Paragraph(f"{cgst:.2f}", total_style)])
            totals.append([Paragraph("SGST:", total_style), Paragraph(f"{cgst:.2f}", total_style)])
        else:
            totals.append([Paragraph("IGST:", total_style), Paragraph(f"{pi.get('total_gst', 0):.2f}", total_style)])
    if pi.get("shipping_charge", 0) > 0:
        totals.append([Paragraph("Shipping:", total_style), Paragraph(f"{pi['shipping_charge']:.2f}", total_style)])
        if pi.get("shipping_gst", 0) > 0:
            totals.append([Paragraph("Shipping GST (18%):", total_style), Paragraph(f"{pi['shipping_gst']:.2f}", total_style)])
    totals.append([Paragraph("<b>Grand Total:</b>", total_bold), Paragraph(f"<b>INR {pi.get('grand_total', 0):.0f}</b>", total_bold)])
    tt = Table(totals, colWidths=[pw - 60*mm, 60*mm])
    tt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT'), ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black)]))
    elements.append(tt)

    if pi.get("remark"):
        elements.append(Spacer(1, 5*mm))
        elements.append(Paragraph(f"<b>Remarks:</b> {pi['remark']}", header_style))

    # Bank Details & UPI QR Code
    elements.append(Spacer(1, 8*mm))
    bank = BANK_GST if pi.get("gst_applicable") else BANK_NON_GST
    upi_string = bank["upi_string"].format(amount=int(pi.get("grand_total", 0)))

    # Generate QR code
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=6, border=2)
    qr.add_data(upi_string)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    qr_image = Image(qr_buffer, width=30*mm, height=30*mm)

    bank_text = Paragraph(
        f"<b>Bank Details:</b><br/>"
        f"A/c Name: {bank['account_name']}<br/>"
        f"A/c No.: {bank['account_no']}<br/>"
        f"IFSC: {bank['ifsc']}<br/>"
        f"Bank: {bank['bank']}<br/>"
        f"Branch: {bank['branch']}",
        bank_style
    )

    payment_table = Table(
        [[bank_text, qr_image]],
        colWidths=[pw - 40*mm, 40*mm]
    )
    payment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(Paragraph("<b>Payment Information</b>", bold_style))
    elements.append(Spacer(1, 2*mm))
    elements.append(payment_table)

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={pi['pi_number']}.pdf"}
    )

# Static + Mount
app.include_router(api_router)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
