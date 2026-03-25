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
    alias: Optional[str] = ""

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

class FreeSampleModel(BaseModel):
    item_name: str = ""
    description: str = ""
    formulation: str = ""

class AdditionalChargeModel(BaseModel):
    name: str = ""
    amount: float = 0
    gst_percent: int = 0
    gst_amount: float = 0

class OrderCreate(BaseModel):
    customer_id: str
    purpose: str = ""
    items: List[OrderItemModel]
    free_samples: List[FreeSampleModel] = []
    gst_applicable: bool = False
    shipping_method: str = ""
    courier_name: str = ""
    transporter_name: str = ""
    shipping_charge: float = 0
    shipping_gst: float = 0
    additional_charges: List[AdditionalChargeModel] = []
    remark: str = ""
    payment_status: str = "unpaid"
    amount_paid: float = 0
    payment_screenshots: List[str] = []
    mode_of_payment: str = ""
    payment_mode_details: str = ""
    billing_address_id: str = ""
    shipping_address_id: str = ""
    extra_shipping_details: str = ""

class FormulationUpdate(BaseModel):
    items: List[Dict[str, Any]]

class DispatchUpdate(BaseModel):
    courier_name: str = ""
    transporter_name: str = ""
    lr_no: str = ""
    dispatch_type: str = ""
    shipping_method: str = ""

class PICreate(BaseModel):
    customer_id: str
    items: List[OrderItemModel]
    free_samples: List[FreeSampleModel] = []
    gst_applicable: bool = False
    show_rate: bool = True
    shipping_charge: float = 0
    additional_charges: List[AdditionalChargeModel] = []
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
    if req.role not in ["admin", "telecaller", "packaging", "dispatch", "accounts"]:
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
    # Protect the admin account from being deactivated
    if req.active is not None and req.active is False:
        target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if target_user and target_user.get("username") == "admin":
            raise HTTPException(status_code=400, detail="The primary admin account cannot be deactivated")
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
        "alias": req.alias.strip() if req.alias else "",
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
            {"alias": {"$regex": search, "$options": "i"}},
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
        "alias": req.alias.strip() if req.alias else "",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    updated = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    return updated

@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete customers")
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

    # Process additional charges
    additional_charges = []
    total_additional = 0
    total_additional_gst = 0
    for charge in req.additional_charges:
        c = charge.model_dump()
        c["amount"] = max(0, c["amount"])
        if req.gst_applicable and c["gst_percent"] > 0:
            c["gst_amount"] = round(c["amount"] * c["gst_percent"] / 100, 2)
        else:
            c["gst_amount"] = 0
        total_additional += c["amount"]
        total_additional_gst += c["gst_amount"]
        additional_charges.append(c)

    shipping_gst = 0
    if req.gst_applicable and req.shipping_charge > 0:
        shipping_gst = round(req.shipping_charge * 0.18, 2)

    raw_total = subtotal + total_gst + req.shipping_charge + shipping_gst + total_additional + total_additional_gst
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
        "additional_charges": additional_charges,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst + total_additional_gst, 2),
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
        "free_samples": [s.model_dump() for s in req.free_samples],
        "extra_shipping_details": req.extra_shipping_details,
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
        "tax_invoice_url": "",
        "payment_check_status": "pending",
        "payment_checked_by": "",
        "payment_checked_at": "",
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
        elif user["role"] == "accounts":
            pass  # Accounts can see all orders (filtered per tab on frontend)
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
        elif user["role"] in ["dispatch", "accounts"]:
            # Dispatch/Accounts: never see formulations
            for item in o.get("items", []):
                item.pop("formulation", None)
        # Admin: always sees formulations (no stripping)

    return orders

@api_router.get("/orders/my-notifications")
async def get_my_notifications(since: str = "", user=Depends(get_current_user)):
    """Return packed/dispatched orders for the current telecaller since the given timestamp."""
    if user["role"] != "telecaller":
        return []
    since_dt = since if since else (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    fields = {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "status": 1, "shipping_method": 1}
    # Packed: only for porter, office_collection, self_arranged
    packed = await db.orders.find({
        "telecaller_id": user["id"],
        "status": "packed",
        "shipping_method": {"$in": ["porter", "office_collection", "self_arranged"]},
        "packaging.packed_at": {"$gt": since_dt}
    }, fields).to_list(50)
    # Dispatched: all shipping methods
    dispatched = await db.orders.find({
        "telecaller_id": user["id"],
        "status": "dispatched",
        "dispatch.dispatched_at": {"$gt": since_dt}
    }, fields).to_list(50)
    return packed + dispatched

# ── Persistent Notifications ──
@api_router.get("/notifications")
async def get_notifications(user=Depends(get_current_user)):
    """Get all unacknowledged notifications for the current user."""
    notifs = await db.notifications.find(
        {"user_id": user["id"], "acknowledged": False},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return notifs

@api_router.post("/notifications")
async def create_notification(data: dict, user=Depends(get_current_user)):
    """Create a persistent notification. Idempotent by order_id + type."""
    order_id = data.get("order_id")
    ntype = data.get("type")
    if not order_id or not ntype:
        raise HTTPException(status_code=400, detail="order_id and type required")
    existing = await db.notifications.find_one(
        {"user_id": user["id"], "order_id": order_id, "type": ntype}, {"_id": 0}
    )
    if existing:
        return existing
    notif = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "order_id": order_id,
        "order_number": data.get("order_number", ""),
        "customer_name": data.get("customer_name", ""),
        "type": ntype,
        "shipping_method": data.get("shipping_method", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "acknowledged": False,
    }
    await db.notifications.insert_one(notif)
    notif.pop("_id", None)
    return notif

@api_router.put("/notifications/{notif_id}/acknowledge")
async def acknowledge_notification(notif_id: str, user=Depends(get_current_user)):
    result = await db.notifications.update_one(
        {"id": notif_id, "user_id": user["id"]},
        {"$set": {"acknowledged": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "acknowledged"}

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Hide telecaller info for non-admin (keep telecaller_id for telecaller's own-order check)
    if user["role"] == "telecaller":
        order.pop("telecaller_name", None)
    elif user["role"] != "admin":
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
    elif user["role"] in ["dispatch", "accounts"]:
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
    # Dispatch lock: admins can edit everything; telecallers can edit payment fields on own orders
    if order.get("status") == "dispatched" and user["role"] != "admin":
        allowed_dispatched = {"payment_status", "amount_paid", "balance_amount", "mode_of_payment", "payment_mode_details", "payment_screenshots"}
        non_allowed = set(updates.keys()) - allowed_dispatched - {"id", "order_number", "updated_at"}
        if non_allowed:
            raise HTTPException(status_code=400, detail="Order is dispatched. Only payment details can be updated.")
    # Telecaller can only edit their own orders
    if user["role"] == "telecaller" and order.get("telecaller_id") != user["id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own orders")
    updates.pop("id", None)
    updates.pop("order_number", None)
    # Auto-recheck: if payment details change on an already-checked order
    if order.get("payment_check_status") == "received":
        payment_changed = (
            ("payment_status" in updates and updates["payment_status"] != order.get("payment_status")) or
            ("amount_paid" in updates and float(updates.get("amount_paid", 0)) != float(order.get("amount_paid", 0)))
        )
        if payment_changed:
            updates["payment_check_status"] = "pending_recheck"
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.orders.update_one({"id": order_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# Forward to Packaging (Admin reference flag)
@api_router.post("/orders/{order_id}/forward-to-packaging")
async def forward_to_packaging(order_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    current = order.get("forwarded_to_packaging", False)
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"forwarded_to_packaging": not current, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"forwarded_to_packaging": not current}

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
    for i, update_item in enumerate(req.items):
        idx = update_item.get("index")
        if idx is not None and 0 <= idx < len(items):
            if "formulation" in update_item:
                items[idx]["formulation"] = update_item["formulation"]
        elif i < len(items):
            # Match by position if no index provided
            if "formulation" in update_item:
                items[i]["formulation"] = update_item["formulation"]
    # Also handle free_samples formulations if provided
    update_set = {"items": items, "updated_at": datetime.now(timezone.utc).isoformat()}
    free_samples_update = [it for it in req.items if it.get("is_free_sample")]
    if free_samples_update:
        free_samples = order.get("free_samples", [])
        for fs_update in free_samples_update:
            fs_idx = fs_update.get("fs_index")
            if fs_idx is not None and 0 <= fs_idx < len(free_samples):
                free_samples[fs_idx]["formulation"] = fs_update.get("formulation", "")
        update_set["free_samples"] = free_samples
    await db.orders.update_one(
        {"id": order_id},
        {"$set": update_set}
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
    # Packaging team cannot edit after dispatch; admin can edit anytime
    if order.get("status") == "dispatched" and user["role"] != "admin":
        raise HTTPException(status_code=400, detail="Cannot modify packaging for a dispatched order")

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

@api_router.put("/orders/{order_id}/mark-packed")
async def mark_order_packed(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Admin or packaging only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] not in ["new", "packaging"]:
        raise HTTPException(status_code=400, detail="Can only mark new/packaging orders as packed")
    packaging = order.get("packaging", {})
    packaging["packed_at"] = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one({"id": order_id}, {"$set": {"status": "packed", "packaging": packaging, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return await db.orders.find_one({"id": order_id}, {"_id": 0})

@api_router.put("/orders/{order_id}/undo-packed")
async def undo_packed(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Admin or packaging only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] != "packed":
        raise HTTPException(status_code=400, detail="Only packed orders can be reverted")
    packaging = order.get("packaging", {})
    packaging["packed_at"] = ""
    await db.orders.update_one({"id": order_id}, {"$set": {"status": "packaging", "packaging": packaging, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


# Dispatch
@api_router.put("/orders/{order_id}/dispatch")
async def update_dispatch(order_id: str, req: DispatchUpdate, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Dispatch, packaging or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shipping_method = req.shipping_method or order.get("shipping_method", "")
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
    update_fields = {
        "dispatch": dispatch,
        "status": "dispatched",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    # Allow updating shipping method from dispatch
    if req.shipping_method:
        update_fields["shipping_method"] = req.shipping_method
    if req.courier_name:
        update_fields["courier_name"] = req.courier_name
    if req.transporter_name:
        update_fields["transporter_name"] = req.transporter_name
    await db.orders.update_one({"id": order_id}, {"$set": update_fields})
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated


# Update shipping method (without dispatching) - for Dispatch/Packaging/Admin
@api_router.put("/orders/{order_id}/shipping-method")
async def update_shipping_method(order_id: str, body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Dispatch, packaging or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "shipping_method" in body:
        update_fields["shipping_method"] = body["shipping_method"]
    if "courier_name" in body:
        update_fields["courier_name"] = body["courier_name"]
    if "transporter_name" in body:
        update_fields["transporter_name"] = body["transporter_name"]
    await db.orders.update_one({"id": order_id}, {"$set": update_fields})
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
    if user["role"] == "telecaller":
        if order.get("telecaller_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Can only delete your own orders")
        if order.get("status") == "dispatched":
            raise HTTPException(status_code=400, detail="Cannot delete dispatched orders")
    result = await db.orders.delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": f"Order {order.get('order_number', '')} permanently deleted"}

# Delete a single image from an order
@api_router.delete("/orders/{order_id}/images")
async def delete_order_image(
    order_id: str,
    image_type: str = Query(..., description="payment | order_image | packed_box_image | item_image"),
    image_url: str = Query(...),
    item_name: str = Query(""),
    user=Depends(get_current_user)
):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched" and user["role"] != "admin":
        raise HTTPException(status_code=400, detail="Cannot modify a dispatched order")

    if image_type == "payment":
        if user["role"] not in ["admin", "telecaller"]:
            raise HTTPException(status_code=403, detail="Not authorized")
        if user["role"] == "telecaller" and order.get("telecaller_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Not your order")
        screenshots = [s for s in order.get("payment_screenshots", []) if s != image_url]
        await db.orders.update_one({"id": order_id}, {"$set": {"payment_screenshots": screenshots, "updated_at": datetime.now(timezone.utc).isoformat()}})
    elif image_type in ["order_image", "packed_box_image", "item_image"]:
        if user["role"] not in ["admin", "packaging"]:
            raise HTTPException(status_code=403, detail="Not authorized")
        packaging = order.get("packaging", {})
        if image_type == "order_image":
            packaging["order_images"] = [u for u in packaging.get("order_images", []) if u != image_url]
        elif image_type == "packed_box_image":
            packaging["packed_box_images"] = [u for u in packaging.get("packed_box_images", []) if u != image_url]
        elif image_type == "item_image":
            item_imgs = packaging.get("item_images", {})
            if item_name in item_imgs:
                item_imgs[item_name] = [u for u in item_imgs[item_name] if u != image_url]
            packaging["item_images"] = item_imgs
        await db.orders.update_one({"id": order_id}, {"$set": {"packaging": packaging, "updated_at": datetime.now(timezone.utc).isoformat()}})
    else:
        raise HTTPException(status_code=400, detail="Invalid image_type")

    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# ── Tax Invoice (Accounts role) ──────────────────────────────────────────────
@api_router.put("/orders/{order_id}/invoice")
async def set_order_invoice(order_id: str, body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "accounts"]:
        raise HTTPException(status_code=403, detail="Accounts or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.get("gst_applicable"):
        raise HTTPException(status_code=400, detail="Tax invoice only for GST-applicable orders")
    invoice_url = body.get("invoice_url", "")
    await db.orders.update_one({"id": order_id}, {"$set": {"tax_invoice_url": invoice_url, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return await db.orders.find_one({"id": order_id}, {"_id": 0})

@api_router.post("/orders/{order_id}/invoice-upload")
async def upload_invoice_with_eway(
    order_id: str,
    tax_invoice: UploadFile = File(...),
    eway_bill: Optional[UploadFile] = File(None),
    user=Depends(get_current_user),
):
    from PyPDF2 import PdfReader, PdfWriter
    if user["role"] not in ["admin", "accounts"]:
        raise HTTPException(status_code=403, detail="Accounts or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.get("gst_applicable"):
        raise HTTPException(status_code=400, detail="Tax invoice only for GST-applicable orders")

    tax_bytes = await tax_invoice.read()
    if not tax_bytes:
        raise HTTPException(status_code=400, detail="Tax invoice file is empty")

    has_eway = eway_bill is not None and eway_bill.filename
    eway_bytes = None
    if has_eway:
        eway_bytes = await eway_bill.read()
        if not eway_bytes:
            has_eway = False

    if has_eway and eway_bytes:
        # Merge: Tax Invoice first, then E-Way Bill
        writer = PdfWriter()
        tax_reader = PdfReader(io.BytesIO(tax_bytes))
        for page in tax_reader.pages:
            writer.add_page(page)
        eway_reader = PdfReader(io.BytesIO(eway_bytes))
        for page in eway_reader.pages:
            writer.add_page(page)
        merged_buf = io.BytesIO()
        writer.write(merged_buf)
        final_bytes = merged_buf.getvalue()
    else:
        final_bytes = tax_bytes

    filename = f"{uuid.uuid4()}.pdf"
    filepath = UPLOAD_DIR / filename
    async with aiofiles.open(filepath, 'wb') as f:
        await f.write(final_bytes)

    invoice_url = f"/api/uploads/{filename}"
    await db.orders.update_one({"id": order_id}, {"$set": {
        "tax_invoice_url": invoice_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return await db.orders.find_one({"id": order_id}, {"_id": 0})

@api_router.delete("/orders/{order_id}/invoice")
async def delete_order_invoice(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "accounts"]:
        raise HTTPException(status_code=403, detail="Accounts or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.orders.update_one({"id": order_id}, {"$set": {"tax_invoice_url": "", "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Invoice removed"}

# ── Payment Check ─────────────────────────────────────────────────────────────
@api_router.put("/orders/{order_id}/payment-check")
async def update_payment_check(order_id: str, body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "accounts"]:
        raise HTTPException(status_code=403, detail="Only accounts or admin can update payment check status")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status = body.get("payment_check_status")
    if status not in ["pending", "received", "pending_recheck"]:
        raise HTTPException(status_code=400, detail="Invalid payment_check_status")
    await db.orders.update_one({"id": order_id}, {"$set": {
        "payment_check_status": status,
        "payment_checked_by": user["name"],
        "payment_checked_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return await db.orders.find_one({"id": order_id}, {"_id": 0})

# Bulk Shipping Address Print
@api_router.post("/orders/print-addresses")
async def print_order_addresses(body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Admin or packaging only")
    order_ids = body.get("order_ids", [])
    if not order_ids:
        raise HTTPException(status_code=400, detail="No orders selected")

    orders = []
    for oid in order_ids:
        o = await db.orders.find_one({"id": oid}, {"_id": 0})
        if o:
            orders.append(o)
    if not orders:
        raise HTTPException(status_code=404, detail="No valid orders found")

    customer_ids = list(set(o.get("customer_id", "") for o in orders))
    customers_list = await db.customers.find({"id": {"$in": customer_ids}}, {"_id": 0}).to_list(500)
    customers = {c["id"]: c for c in customers_list}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()

    addr_normal = ParagraphStyle('AddrN', parent=styles['Normal'], fontSize=10, leading=15, fontName='Helvetica')
    addr_bold = ParagraphStyle('AddrB', parent=styles['Normal'], fontSize=11, leading=16, fontName='Helvetica-Bold')
    addr_to = ParagraphStyle('AddrTo', parent=styles['Normal'], fontSize=10, leading=14, fontName='Helvetica', textColor=colors.HexColor('#666666'))
    addr_mob = ParagraphStyle('AddrMob', parent=styles['Normal'], fontSize=10, leading=14, fontName='Helvetica-Bold')

    def make_address_cell(order, customer):
        name = order.get("customer_name", "Unknown")
        sa = order.get("shipping_address") or {}
        phones = customer.get("phone_numbers", []) if customer else []

        lines = [f"<b>To</b>", f"<b>{name}</b>", ""]
        if sa.get("address_line"):
            lines.append(sa["address_line"])
        city_line = ""
        if sa.get("city") and sa.get("pincode"):
            city_line = f"{sa['city']} - {sa['pincode']}"
        elif sa.get("city"):
            city_line = sa["city"]
        if city_line:
            lines.append(city_line)
        if sa.get("state"):
            lines.append(sa["state"])
        if phones:
            clean_phones = [p.replace("+91", "").replace("+", "").strip() for p in phones]
            mob_str = ", ".join(clean_phones)
            lines.append("")
            lines.append(f"<b>Mob no.-{mob_str}</b>")

        return Paragraph("<br/>".join(lines), addr_normal)

    pw = A4[0] - 24*mm
    col_w = (pw - 8*mm) / 2

    row_data = []
    for i in range(0, len(orders), 2):
        left = make_address_cell(orders[i], customers.get(orders[i].get("customer_id", "")))
        right = make_address_cell(orders[i + 1], customers.get(orders[i + 1].get("customer_id", ""))) if i + 1 < len(orders) else Paragraph("", addr_normal)
        row_data.append([left, right])

    table = Table(row_data, colWidths=[col_w, col_w], spaceBefore=2*mm, spaceAfter=2*mm)
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (0, -1), 1, colors.black),
        ('BOX', (1, 0), (1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#DDDDDD')),
    ]))

    doc.build([table])
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=shipping_addresses.pdf"}
    )

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
    # Handle mobile camera uploads which may have empty/wrong extensions
    ext = Path(file.filename or "photo.jpg").suffix.lower() if file.filename else ""
    # Map content types to extensions for camera uploads that lack proper extensions
    content_type_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/heic": ".jpg",
        "image/heif": ".jpg",
        "application/pdf": ".pdf",
        "application/octet-stream": ".jpg",
    }
    if not ext or ext == ".":
        ext = content_type_map.get(file.content_type, ".jpg")
    # Normalize HEIC/HEIF to jpg
    if ext in [".heic", ".heif"]:
        ext = ".jpg"
    allowed = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"]
    if ext not in allowed:
        ext = ".jpg"  # Fallback for unknown camera formats
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
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)

    # Custom date range takes priority over period
    if date_from or date_to:
        if date_from:
            query.setdefault("created_at", {})["$gte"] = date_from
        if date_to:
            query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    elif period == "today":
        today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": today_start.astimezone(timezone.utc).isoformat()}
    elif period == "week":
        week_start = now_ist - timedelta(days=now_ist.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": week_start.astimezone(timezone.utc).isoformat()}
    elif period == "month":
        month_start = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": month_start.astimezone(timezone.utc).isoformat()}

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

# Payment-Received Sales Report (Admin + Telecaller — SEPARATE section, no existing logic touched)
@api_router.get("/reports/payment-sales")
async def payment_received_sales(
    period: Optional[str] = "today",
    exclude_gst: Optional[bool] = False,
    exclude_shipping: Optional[bool] = False,
    telecaller_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user=Depends(get_current_user)
):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    target_id = telecaller_id if (telecaller_id and user["role"] == "admin") else user["id"]
    query = {"telecaller_id": target_id, "payment_check_status": "received"}
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    if date_from or date_to:
        date_filter = {}
        if date_from: date_filter["$gte"] = date_from
        if date_to:   date_filter["$lte"] = date_to + "T23:59:59"
        query["payment_checked_at"] = date_filter
    elif period == "today":
        today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        query["payment_checked_at"] = {"$gte": today_start.astimezone(timezone.utc).isoformat()}
    elif period == "yesterday":
        y_ist = now_ist - timedelta(days=1)
        yday_start = y_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        yday_end = y_ist.replace(hour=23, minute=59, second=59, microsecond=0)
        query["payment_checked_at"] = {"$gte": yday_start.astimezone(timezone.utc).isoformat(), "$lte": yday_end.astimezone(timezone.utc).isoformat()}
    elif period == "week":
        ws = now_ist - timedelta(days=now_ist.weekday())
        ws = ws.replace(hour=0, minute=0, second=0, microsecond=0)
        query["payment_checked_at"] = {"$gte": ws.astimezone(timezone.utc).isoformat()}
    elif period == "month":
        ms = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query["payment_checked_at"] = {"$gte": ms.astimezone(timezone.utc).isoformat()}
    orders = await db.orders.find(query, {"_id": 0}).to_list(5000)
    total_amount, product_sales = 0, 0
    for o in orders:
        total_amount += o.get("grand_total", 0)
        if exclude_gst and exclude_shipping:
            product_sales += o.get("subtotal", 0)
        elif exclude_gst:
            product_sales += o.get("subtotal", 0) + o.get("shipping_charge", 0)
        elif exclude_shipping:
            product_sales += o.get("subtotal", 0) + o.get("total_gst", 0)
        else:
            product_sales += o.get("grand_total", 0)
    return {"total_orders": len(orders), "total_amount": round(total_amount, 2), "product_sales": round(product_sales, 2)}

# Accounts Dashboard Stats
@api_router.get("/reports/accounts-dashboard")
async def accounts_dashboard(
    period: Optional[str] = "today",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user=Depends(get_current_user)
):
    if user["role"] not in ["admin", "accounts"]:
        raise HTTPException(status_code=403, detail="Accounts or admin only")
    now = datetime.now(timezone.utc)
    date_filter = {}
    if date_from or date_to:
        if date_from: date_filter["$gte"] = date_from
        if date_to:   date_filter["$lte"] = date_to + "T23:59:59"
    elif period == "today":
        date_filter = {"$gte": now.replace(hour=0, minute=0, second=0).isoformat()}
    elif period == "week":
        ws = now - timedelta(days=now.weekday())
        date_filter = {"$gte": ws.replace(hour=0, minute=0, second=0).isoformat()}
    elif period == "month":
        date_filter = {"$gte": now.replace(day=1, hour=0, minute=0, second=0).isoformat()}

    invoice_query = {"gst_applicable": True, "tax_invoice_url": {"$exists": True, "$ne": ""}}
    payment_query = {"payment_check_status": "received"}
    if date_filter:
        invoice_query["updated_at"] = date_filter
        payment_query["payment_checked_at"] = date_filter

    total_invoices = await db.orders.count_documents(invoice_query)
    gst_total = await db.orders.count_documents({"gst_applicable": True})
    gst_without_invoice = await db.orders.count_documents({"gst_applicable": True, "$or": [{"tax_invoice_url": {"$exists": False}}, {"tax_invoice_url": ""}]})
    payments_received = await db.orders.count_documents(payment_query)
    payments_pending = await db.orders.count_documents({"payment_check_status": {"$in": ["pending", "pending_recheck"]}})
    unpaid_orders = await db.orders.count_documents({"payment_status": "unpaid"})

    return {
        "total_invoices": total_invoices,
        "gst_total": gst_total,
        "gst_without_invoice": gst_without_invoice,
        "payments_received": payments_received,
        "payments_pending": payments_pending,
        "unpaid_orders": unpaid_orders,
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
    # Use IST for period calculations (UTC+5:30)
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    if date_from or date_to:
        if date_from:
            query.setdefault("created_at", {})["$gte"] = date_from
        if date_to:
            query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"
    elif period == "today":
        today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": today_start.astimezone(timezone.utc).isoformat()}
    elif period == "yesterday":
        yesterday_ist = now_ist - timedelta(days=1)
        yday_start = yesterday_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        yday_end = yesterday_ist.replace(hour=23, minute=59, second=59, microsecond=0)
        query["created_at"] = {
            "$gte": yday_start.astimezone(timezone.utc).isoformat(),
            "$lte": yday_end.astimezone(timezone.utc).isoformat()
        }
    elif period == "week":
        week_start = now_ist - timedelta(days=now_ist.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": week_start.astimezone(timezone.utc).isoformat()}
    elif period == "month":
        month_start = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": month_start.astimezone(timezone.utc).isoformat()}

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
    doc = SimpleDocTemplate(buffer, pagesize=page_size,
                            leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=10*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    elements = []
    pw = page_size[0] - 24*mm

    # ── Shared Styles ──
    GREEN  = colors.HexColor('#15803D')
    LGREEN = colors.HexColor('#F0FDF4')
    DGREEN = colors.HexColor('#14532D')
    BGRAY  = colors.HexColor('#F8FAFC')
    SGRAY  = colors.HexColor('#E5E7EB')
    AMBER  = colors.HexColor('#B45309')
    LAMBER = colors.HexColor('#FFFBEB')

    def sep(thickness=0.5, col=SGRAY):
        t = Table([['']], colWidths=[pw])
        t.setStyle(TableStyle([('LINEBELOW', (0,0),(0,0), thickness, col)]))
        return t

    lbl  = ParagraphStyle('Lbl',  parent=styles['Normal'], fontSize=8,  leading=11, textColor=colors.HexColor('#6B7280'))
    val  = ParagraphStyle('Val',  parent=styles['Normal'], fontSize=9,  leading=12)
    valb = ParagraphStyle('ValB', parent=styles['Normal'], fontSize=9,  leading=12, fontName='Helvetica-Bold')
    sm   = ParagraphStyle('Sm',   parent=styles['Normal'], fontSize=7.5,leading=10, textColor=colors.HexColor('#374151'))
    itm  = ParagraphStyle('Itm',  parent=styles['Normal'], fontSize=8,  leading=10)
    form_sty = ParagraphStyle('Form', parent=styles['Normal'], fontSize=7.5, leading=10,
                              textColor=AMBER, backColor=LAMBER)
    tot_sty  = ParagraphStyle('Tot',  parent=styles['Normal'], fontSize=9, leading=12, alignment=TA_RIGHT)
    totb_sty = ParagraphStyle('TotB', parent=styles['Normal'], fontSize=10, leading=13,
                              fontName='Helvetica-Bold', alignment=TA_RIGHT)

    # ── 1. HEADER ──
    logo_cell = ''
    if LOGO_PATH.exists():
        try:
            tmp = Image(str(LOGO_PATH))
            aspect = tmp.imageHeight / tmp.imageWidth
            logo_h = 28*mm * aspect
            logo_cell = Image(str(LOGO_PATH), width=28*mm, height=logo_h)
        except Exception:
            pass

    co_info = Paragraph(
        f"<b><font size=11>{COMPANY['name']}</font></b><br/>"
        f"<font size=8 color='#15803D'><i>{COMPANY['brand']}</i></font><br/>"
        f"<font size=7 color='#6B7280'>{COMPANY['address']}</font><br/>"
        f"<font size=7 color='#6B7280'>Ph: {COMPANY['mobile']} | {COMPANY['email']}</font>",
        ParagraphStyle('CoInfo', parent=styles['Normal'], fontSize=9, leading=12)
    )
    header_tbl = Table([[logo_cell, co_info]], colWidths=[32*mm, pw - 32*mm])
    header_tbl.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
        ('LEFTPADDING',  (0,0),(0,0),   0),
        ('RIGHTPADDING', (1,0),(1,0),   0),
        ('TOPPADDING',   (0,0),(-1,-1), 2),
        ('BOTTOMPADDING',(0,0),(-1,-1), 2),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 3*mm))
    elements.append(sep(1.2, GREEN))
    elements.append(Spacer(1, 3*mm))

    # ── 2. DOCUMENT TITLE ──
    title_box_data = [[
        Paragraph(f"<b><font size=13>ORDER PACKING SHEET</font></b>", ParagraphStyle('T', parent=styles['Normal'], alignment=TA_CENTER)),
        Paragraph(f"<b><font size=11>{order['order_number']}</font></b>", ParagraphStyle('N', parent=styles['Normal'], alignment=TA_RIGHT, textColor=GREEN)),
    ]]
    title_box = Table(title_box_data, colWidths=[pw*0.6, pw*0.4])
    title_box.setStyle(TableStyle([
        ('VALIGN',       (0,0),(-1,-1), 'MIDDLE'),
        ('BACKGROUND',   (0,0),(-1,-1), LGREEN),
        ('TOPPADDING',   (0,0),(-1,-1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (0,0),(-1,-1), 8),
        ('LINEBELOW',    (0,0),(-1,-1), 1, GREEN),
    ]))
    elements.append(title_box)
    elements.append(Spacer(1, 4*mm))

    # ── 3. ORDER INFO (2×2 grid) ──
    created_date = datetime.fromisoformat(order['created_at']).strftime('%d %b %Y, %I:%M %p')
    info_data = [
        [Paragraph(f"<font color='#6B7280'>Date</font><br/><b>{created_date}</b>", itm),
         Paragraph(f"<font color='#6B7280'>Executive</font><br/><b>{order.get('telecaller_name','N/A')}</b>", itm)],
        [Paragraph(f"<font color='#6B7280'>Status</font><br/><b>{order.get('status','').upper()}</b>", itm),
         Paragraph(f"<font color='#6B7280'>Shipping</font><br/><b>{order.get('shipping_method','').replace('_',' ').title()}</b>", itm)],
    ]
    info_tbl = Table(info_data, colWidths=[pw/2, pw/2])
    info_tbl.setStyle(TableStyle([
        ('BOX',          (0,0),(-1,-1), 0.5, SGRAY),
        ('INNERGRID',    (0,0),(-1,-1), 0.3, SGRAY),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING',   (0,0),(-1,-1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1), 5),
        ('LEFTPADDING',  (0,0),(-1,-1), 7),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 4*mm))

    # ── 4. CUSTOMER ──
    if customer:
        cust_lines = [f"<b>{customer.get('name','')}</b>"]
        if customer.get('phone_numbers'):
            cust_lines.append(f"<font color='#6B7280'>Ph:</font> {', '.join(customer['phone_numbers'])}")
        sa = order.get("shipping_address")
        if sa and sa.get("address_line"):
            cust_lines.append(f"<font color='#6B7280'>Ship To:</font> {sa['address_line']}, {sa.get('city','')}, {sa.get('state','')} – {sa.get('pincode','')}")
        if customer.get("gst_no"):
            cust_lines.append(f"<font color='#6B7280'>GSTIN:</font> {customer['gst_no']}")
        cust_p = Paragraph("<br/>".join(cust_lines), ParagraphStyle('Cust', parent=styles['Normal'], fontSize=8.5, leading=12))
        cust_tbl = Table([[Paragraph("<b>CUSTOMER DETAILS</b>", ParagraphStyle('CustHdr', parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold'))],
                          [cust_p]], colWidths=[pw])
        cust_tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0,0),(0,0), GREEN),
            ('TEXTCOLOR',    (0,0),(0,0), colors.white),
            ('TOPPADDING',   (0,0),(0,0), 4), ('BOTTOMPADDING',(0,0),(0,0), 4),
            ('LEFTPADDING',  (0,0),(-1,-1), 7),
            ('TOPPADDING',   (0,1),(0,1), 5), ('BOTTOMPADDING',(0,1),(0,1), 5),
            ('BOX',          (0,0),(-1,-1), 0.5, SGRAY),
        ]))
        elements.append(cust_tbl)
        elements.append(Spacer(1, 5*mm))

    # ── 5. ITEMS TABLE ──
    headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Amount', 'Formulation']
    col_widths = [7*mm, pw*0.22, 12*mm, 12*mm, 20*mm, pw - 7*mm - pw*0.22 - 12*mm - 12*mm - 20*mm]
    hdr_style = ParagraphStyle('IH', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)
    table_data = [[Paragraph(h, hdr_style) for h in headers]]
    for i, item in enumerate(order.get("items", [])):
        desc_text = item.get("product_name", "")
        if item.get("description"):
            desc_text += f"<br/><font color='#6B7280' size=7>{item['description']}</font>"
        formulation_text = item.get("formulation", "") or ""
        row = [
            Paragraph(str(i + 1), ParagraphStyle('Num', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
            Paragraph(desc_text, itm),
            Paragraph(str(item.get("qty", 0)), ParagraphStyle('Qty', parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT)),
            Paragraph(item.get("unit", ""), ParagraphStyle('Unit', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
            Paragraph(f"{item.get('amount', 0):.2f}", ParagraphStyle('Amt', parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT, fontName='Helvetica-Bold')),
            Paragraph(formulation_text, form_sty) if formulation_text else Paragraph("", sm),
        ]
        table_data.append(row)
    items_t = Table(table_data, colWidths=col_widths, repeatRows=1)
    items_t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,0),  GREEN),
        ('TEXTCOLOR',    (0,0),(-1,0),  colors.white),
        ('FONTSIZE',     (0,0),(-1,-1), 8),
        ('GRID',         (0,0),(-1,-1), 0.4, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, LGREEN]),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING',   (0,0),(-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('LEFTPADDING',  (0,0),(-1,-1), 5),
        ('RIGHTPADDING', (0,0),(-1,-1), 5),
    ]))
    elements.append(items_t)
    elements.append(Spacer(1, 5*mm))

    # ── 6. TOTALS ──
    totals = []
    totals.append([Paragraph("Subtotal:", tot_sty), Paragraph(f"₹ {order.get('subtotal', 0):.2f}", tot_sty)])
    if order.get("total_gst", 0) > 0:
        totals.append([Paragraph("GST:", tot_sty), Paragraph(f"₹ {order['total_gst']:.2f}", tot_sty)])
    if order.get("shipping_charge", 0) > 0:
        totals.append([Paragraph("Shipping:", tot_sty), Paragraph(f"₹ {order['shipping_charge']:.2f}", tot_sty)])
    # Additional charges
    for charge in order.get("additional_charges", []):
        charge_label = charge.get("name", "Charge")
        charge_amt = charge.get("amount", 0)
        charge_gst = charge.get("gst_amount", 0)
        if charge_amt > 0:
            totals.append([Paragraph(f"{charge_label}:", tot_sty), Paragraph(f"₹ {charge_amt:.2f}", tot_sty)])
        if charge_gst > 0:
            totals.append([Paragraph(f"{charge_label} GST ({charge.get('gst_percent', 0)}%):", tot_sty), Paragraph(f"₹ {charge_gst:.2f}", tot_sty)])
    totals.append([Paragraph("Grand Total:", totb_sty), Paragraph(f"<b>₹ {order.get('grand_total', 0):.0f}</b>", totb_sty)])
    tt = Table(totals, colWidths=[pw - 55*mm, 55*mm])
    tt.setStyle(TableStyle([
        ('ALIGN',        (0,0),(-1,-1), 'RIGHT'),
        ('LINEABOVE',    (0,-1),(-1,-1), 1.2, GREEN),
        ('BACKGROUND',   (0,-1),(-1,-1), LGREEN),
        ('TOPPADDING',   (0,-1),(-1,-1), 5),
        ('BOTTOMPADDING',(0,-1),(-1,-1), 5),
        ('TOPPADDING',   (0,0),(-1,-2), 3),
        ('BOTTOMPADDING',(0,0),(-1,-2), 3),
    ]))
    elements.append(tt)

    # ── 7. PAYMENT / SAMPLES / DISPATCH / REMARKS ──
    extras = []
    if order.get("mode_of_payment"):
        mop = f"<b>Mode of Payment:</b> {order['mode_of_payment']}"
        if order.get("payment_mode_details"):
            mop += f" ({order['payment_mode_details']})"
        extras.append(mop)
    if order.get("free_samples"):
        extras.append("<b>Free Samples:</b>")
        for s in order["free_samples"]:
            t = s.get("item_name", "")
            if s.get("description"): t += f" – {s['description']}"
            extras.append(f"  · {t}")
    if order.get("shipping_method"):
        dispatch_parts = [f"<b>Dispatch:</b> {order['shipping_method'].replace('_',' ').title()}"]
        if order.get("courier_name"):    dispatch_parts.append(f"Courier: {order['courier_name']}")
        if order.get("transporter_name"): dispatch_parts.append(f"Transporter: {order['transporter_name']}")
        extras.append("  |  ".join(dispatch_parts))
    if order.get("remark"):
        extras.append(f"<b>Remarks:</b> {order['remark']}")

    if extras:
        elements.append(Spacer(1, 4*mm))
        elements.append(sep())
        elements.append(Spacer(1, 3*mm))
        for line in extras:
            elements.append(Paragraph(line, ParagraphStyle('Ex', parent=styles['Normal'], fontSize=8, leading=12)))
            elements.append(Spacer(1, 1.5*mm))

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

    # Process additional charges for PI
    additional_charges = []
    total_additional = 0
    total_additional_gst = 0
    for charge in req.additional_charges:
        c = charge.model_dump()
        c["amount"] = max(0, c["amount"])
        if req.gst_applicable and c["gst_percent"] > 0:
            c["gst_amount"] = round(c["amount"] * c["gst_percent"] / 100, 2)
        else:
            c["gst_amount"] = 0
        total_additional += c["amount"]
        total_additional_gst += c["gst_amount"]
        additional_charges.append(c)

    grand_total = math.ceil(subtotal + total_gst + req.shipping_charge + shipping_gst + total_additional + total_additional_gst)

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
        "additional_charges": additional_charges,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst + total_additional_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "status": "draft",
        "converted_order_id": "",
        "billing_address_id": req.billing_address_id,
        "shipping_address_id": req.shipping_address_id,
        "billing_address": billing_addr,
        "shipping_address": shipping_addr,
        "free_samples": [s.model_dump() for s in req.free_samples],
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

    # Process additional charges for PI update
    additional_charges = []
    total_additional = 0
    total_additional_gst = 0
    for charge in req.additional_charges:
        c = charge.model_dump()
        c["amount"] = max(0, c["amount"])
        if req.gst_applicable and c["gst_percent"] > 0:
            c["gst_amount"] = round(c["amount"] * c["gst_percent"] / 100, 2)
        else:
            c["gst_amount"] = 0
        total_additional += c["amount"]
        total_additional_gst += c["gst_amount"]
        additional_charges.append(c)

    grand_total = math.ceil(subtotal + total_gst + req.shipping_charge + shipping_gst + total_additional + total_additional_gst)

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
        "additional_charges": additional_charges,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst + total_additional_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "billing_address_id": req.billing_address_id,
        "shipping_address_id": req.shipping_address_id,
        "billing_address": billing_addr,
        "shipping_address": shipping_addr,
        "free_samples": [s.model_dump() for s in req.free_samples],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.proforma_invoices.update_one({"id": pi_id}, {"$set": update_data})
    updated = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    return updated

@api_router.patch("/proforma-invoices/{pi_id}/mark-converted")
async def mark_pi_converted(pi_id: str, body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    order_id = body.get("order_id", "")
    await db.proforma_invoices.update_one(
        {"id": pi_id},
        {"$set": {"status": "converted", "converted_order_id": order_id, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "PI marked as converted"}

# Duplicate Order
@api_router.post("/orders/{order_id}/duplicate")
async def duplicate_order(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Return the order data needed for pre-filling a new form
    return {
        "customer_id": order.get("customer_id", ""),
        "customer_name": order.get("customer_name", ""),
        "purpose": order.get("purpose", ""),
        "items": order.get("items", []),
        "gst_applicable": order.get("gst_applicable", False),
        "shipping_method": order.get("shipping_method", ""),
        "courier_name": order.get("courier_name", ""),
        "transporter_name": order.get("transporter_name", ""),
        "shipping_charge": order.get("shipping_charge", 0),
        "additional_charges": order.get("additional_charges", []),
        "remark": order.get("remark", ""),
        "free_samples": order.get("free_samples", []),
        "billing_address_id": order.get("billing_address_id", ""),
        "shipping_address_id": order.get("shipping_address_id", ""),
        "billing_address": order.get("billing_address"),
        "shipping_address": order.get("shipping_address"),
        "mode_of_payment": order.get("mode_of_payment", ""),
        "payment_mode_details": order.get("payment_mode_details", ""),
    }

# Duplicate PI
@api_router.post("/proforma-invoices/{pi_id}/duplicate")
async def duplicate_pi(pi_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    return {
        "customer_id": pi.get("customer_id", ""),
        "customer_name": pi.get("customer_name", ""),
        "items": pi.get("items", []),
        "gst_applicable": pi.get("gst_applicable", False),
        "show_rate": pi.get("show_rate", True),
        "shipping_charge": pi.get("shipping_charge", 0),
        "additional_charges": pi.get("additional_charges", []),
        "remark": pi.get("remark", ""),
        "free_samples": pi.get("free_samples", []),
        "billing_address_id": pi.get("billing_address_id", ""),
        "shipping_address_id": pi.get("shipping_address_id", ""),
        "billing_address": pi.get("billing_address"),
        "shipping_address": pi.get("shipping_address"),
    }




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
        "additional_charges": pi.get("additional_charges", []),
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
        "free_samples": pi.get("free_samples", []),
        "telecaller_id": user["id"],
        "telecaller_name": user["name"],
        "packaging": {"item_images": {}, "order_images": [], "packed_box_images": [], "item_packed_by": [], "box_packed_by": [], "checked_by": [], "packed_at": ""},
        "dispatch": {"courier_name": "", "transporter_name": "", "lr_no": "", "dispatched_by": "", "dispatched_at": ""},
        "tax_invoice_url": "",
        "payment_check_status": "pending",
        "payment_checked_by": "",
        "payment_checked_at": "",
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
    await get_user_from_token_param(token)
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    customer = await db.customers.find_one({"id": pi["customer_id"]}, {"_id": 0})

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []
    pw = A4[0] - 30*mm
    is_gst = pi.get("gst_applicable", False)

    # ── Colours & shared styles ──
    GREEN   = colors.HexColor('#15803D')
    LGREEN  = colors.HexColor('#F0FDF4')
    SGRAY   = colors.HexColor('#E5E7EB')
    DGRAY   = colors.HexColor('#374151')
    MGRAY   = colors.HexColor('#6B7280')
    BGRAY   = colors.HexColor('#F9FAFB')

    def sep(thickness=0.5, col=SGRAY, width=None):
        t = Table([['']], colWidths=[width or pw])
        t.setStyle(TableStyle([('LINEBELOW',(0,0),(0,0), thickness, col)]))
        return t

    def sty(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    body    = sty('B',  fontSize=9,  leading=13)
    small   = sty('S',  fontSize=8,  leading=11, textColor=MGRAY)
    bold9   = sty('B9', fontSize=9,  leading=13, fontName='Helvetica-Bold')
    label   = sty('L',  fontSize=7.5,leading=10, textColor=MGRAY)
    tr      = sty('TR', fontSize=9,  leading=12, alignment=TA_RIGHT)
    trb     = sty('TRB',fontSize=11, leading=14, fontName='Helvetica-Bold', alignment=TA_RIGHT)
    hdr_tbl = sty('HT', fontSize=8,  leading=11, fontName='Helvetica-Bold',
                  textColor=colors.white)

    # ─────────────────────────────────────────────────────────────
    # ── A. GST PROFORMA INVOICE ──────────────────────────────────
    # ─────────────────────────────────────────────────────────────
    if is_gst:
        # 1. HEADER: logo (aspect-ratio corrected) + company info
        logo_cell = Paragraph('', body)
        if LOGO_PATH.exists():
            try:
                tmp = Image(str(LOGO_PATH))
                aspect = tmp.imageHeight / tmp.imageWidth
                logo_cell = Image(str(LOGO_PATH), width=30*mm, height=30*mm * aspect)
            except Exception:
                pass

        co_para = Paragraph(
            f"<b><font size=13>{COMPANY['name']}</font></b><br/>"
            f"<font size=8 color='#15803D'><i>{COMPANY['brand']}</i></font><br/>"
            f"<font size=7.5 color='#374151'>{COMPANY['address']}</font><br/>"
            f"<font size=7.5 color='#6B7280'>"
            f"Ph: {COMPANY['mobile']}  |  {COMPANY['email']}  |  {COMPANY['website']}</font><br/>"
            f"<font size=7.5 color='#374151'><b>GSTIN:</b> {COMPANY['gstin']}</font>",
            sty('CoP', fontSize=9, leading=13)
        )
        head = Table([[logo_cell, co_para]], colWidths=[34*mm, pw - 34*mm])
        head.setStyle(TableStyle([
            ('VALIGN',      (0,0),(-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0),(0,0),   0),
            ('RIGHTPADDING',(1,0),(1,0),   0),
            ('TOPPADDING',  (0,0),(-1,-1), 0),
            ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ]))
        elements.append(head)
        elements.append(Spacer(1, 4*mm))
        elements.append(sep(1.5, GREEN))
        elements.append(Spacer(1, 3*mm))

        # 2. TITLE + PI META
        pi_date = datetime.fromisoformat(pi['created_at']).strftime('%d %b %Y')
        title_row = Table([[
            Paragraph('<b><font size=15>PROFORMA INVOICE</font></b>',
                      sty('PT', fontSize=15, fontName='Helvetica-Bold')),
            Paragraph(
                f"<font color='#6B7280' size=8>PI No.</font><br/>"
                f"<b><font size=11>{pi['pi_number']}</font></b><br/>"
                f"<font color='#6B7280' size=8>Date: {pi_date}</font>",
                sty('PN', fontSize=9, leading=13, alignment=TA_RIGHT)
            ),
        ]], colWidths=[pw*0.55, pw*0.45])
        title_row.setStyle(TableStyle([
            ('VALIGN',      (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',  (0,0),(-1,-1), 0),
            ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ]))
        elements.append(title_row)
        elements.append(Spacer(1, 5*mm))

        # 3. BILL TO / SHIP TO
        if customer:
            def addr_block(title_text, name, phones, addr, gst_no, email):
                lines = [
                    Paragraph(title_text, sty('AHdr', fontSize=7.5, fontName='Helvetica-Bold',
                                              textColor=colors.white)),
                ]
                name_p = Paragraph(f"<b>{name}</b>", sty('AN', fontSize=9.5, leading=13))
                details = []
                if phones:
                    details.append(f"<b>Ph:</b> {', '.join(phones)}")
                if addr and addr.get('address_line'):
                    details.append(addr['address_line'])
                    city_st = f"{addr.get('city','')}, {addr.get('state','')} – {addr.get('pincode','')}"
                    if city_st.strip(', –'):
                        details.append(city_st)
                if gst_no:
                    details.append(f"<b>GSTIN:</b> {gst_no}")
                if email:
                    details.append(f"<b>Email:</b> {email}")
                details_p = Paragraph("<br/>".join(details), sty('AD', fontSize=8, leading=12))
                inner = Table([[name_p], [details_p]], colWidths=[None])
                inner.setStyle(TableStyle([
                    ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
                    ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                ]))
                outer = Table([
                    [Paragraph(title_text, sty('ATH', fontSize=7.5, fontName='Helvetica-Bold', textColor=colors.white))],
                    [inner],
                ], colWidths=[None])
                outer.setStyle(TableStyle([
                    ('BACKGROUND',  (0,0),(0,0), GREEN),
                    ('TOPPADDING',  (0,0),(0,0), 4), ('BOTTOMPADDING',(0,0),(0,0), 4),
                    ('LEFTPADDING', (0,0),(-1,-1),7),
                    ('TOPPADDING',  (0,1),(0,1), 5), ('BOTTOMPADDING',(0,1),(0,1), 7),
                    ('BOX',         (0,0),(-1,-1), 0.5, SGRAY),
                    ('RIGHTPADDING',(0,0),(-1,-1),7),
                ]))
                return outer

            ba = pi.get('billing_address') or {}
            sa = pi.get('shipping_address') or {}
            bill_blk = addr_block("BILL TO", customer.get('name',''),
                                  customer.get('phone_numbers',[]),
                                  ba, customer.get('gst_no',''), customer.get('email',''))
            ship_blk = addr_block("SHIP TO", customer.get('name',''),
                                  customer.get('phone_numbers',[]),
                                  sa or ba, None, None)
            addr_tbl = Table([[bill_blk, ship_blk]], colWidths=[(pw-5*mm)/2, (pw-5*mm)/2],
                             spaceBefore=0)
            addr_tbl.setStyle(TableStyle([
                ('VALIGN',      (0,0),(-1,-1), 'TOP'),
                ('LEFTPADDING', (0,0),(0,0),   0),
                ('RIGHTPADDING',(0,0),(0,0),   2.5*mm),
                ('LEFTPADDING', (1,0),(1,0),   2.5*mm),
                ('RIGHTPADDING',(1,0),(1,0),   0),
            ]))
            elements.append(addr_tbl)
            elements.append(Spacer(1, 6*mm))

    # ─────────────────────────────────────────────────────────────
    # ── B. NON-GST → QUOTATION ───────────────────────────────────
    # ─────────────────────────────────────────────────────────────
    else:
        # No logo, no company name — just "QUOTATION" title
        pi_date = datetime.fromisoformat(pi['created_at']).strftime('%d %b %Y')
        quot_row = Table([[
            Paragraph('<b><font size=18>QUOTATION</font></b>',
                      sty('QT', fontSize=18, fontName='Helvetica-Bold', textColor=DGRAY)),
            Paragraph(
                f"<font color='#6B7280' size=8>Ref No.</font><br/>"
                f"<b><font size=11>{pi['pi_number']}</font></b><br/>"
                f"<font color='#6B7280' size=8>Date: {pi_date}</font>",
                sty('QN', fontSize=9, leading=13, alignment=TA_RIGHT)
            ),
        ]], colWidths=[pw*0.5, pw*0.5])
        quot_row.setStyle(TableStyle([
            ('VALIGN',      (0,0),(-1,-1), 'MIDDLE'),
            ('TOPPADDING',  (0,0),(-1,-1), 0),
            ('BOTTOMPADDING',(0,0),(-1,-1),0),
        ]))
        elements.append(quot_row)
        elements.append(Spacer(1, 2*mm))
        elements.append(sep(1.5, DGRAY))
        elements.append(Spacer(1, 5*mm))

        # Customer "To:" block
        if customer:
            ba = pi.get('billing_address') or {}
            cust_lines = [f"<b>{customer.get('name','')}</b>"]
            if customer.get('phone_numbers'):
                cust_lines.append(f"Ph: {', '.join(customer['phone_numbers'])}")
            if ba.get('address_line'):
                cust_lines.append(ba['address_line'])
                city_st = f"{ba.get('city','')}, {ba.get('state','')} – {ba.get('pincode','')}"
                if city_st.strip(', –'):
                    cust_lines.append(city_st)
            if customer.get('email'):
                cust_lines.append(f"Email: {customer['email']}")
            to_tbl = Table([
                [Paragraph("TO", sty('ToH', fontSize=7.5, fontName='Helvetica-Bold', textColor=colors.white))],
                [Paragraph("<br/>".join(cust_lines), sty('ToD', fontSize=9, leading=13))],
            ], colWidths=[pw])
            to_tbl.setStyle(TableStyle([
                ('BACKGROUND',  (0,0),(0,0), DGRAY),
                ('TOPPADDING',  (0,0),(0,0), 4), ('BOTTOMPADDING',(0,0),(0,0), 4),
                ('LEFTPADDING', (0,0),(-1,-1),8),
                ('TOPPADDING',  (0,1),(0,1), 6), ('BOTTOMPADDING',(0,1),(0,1), 6),
                ('BOX',         (0,0),(-1,-1), 0.5, SGRAY),
                ('RIGHTPADDING',(0,0),(-1,-1),8),
            ]))
            elements.append(to_tbl)
            elements.append(Spacer(1, 6*mm))

    # ─────────────────────────────────────────────────────────────
    # ── C. ITEMS TABLE (shared, logic unchanged) ─────────────────
    # ─────────────────────────────────────────────────────────────
    if is_gst:
        if pi.get("show_rate"):
            headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Rate', 'Amount', 'GST %', 'GST Amt', 'Total']
            col_widths = [8*mm, 40*mm, 14*mm, 14*mm, 20*mm, 21*mm, 14*mm, 20*mm, 22*mm]
        else:
            headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Amount', 'GST %', 'GST Amt', 'Total']
            col_widths = [8*mm, 52*mm, 16*mm, 14*mm, 24*mm, 16*mm, 24*mm, 27*mm]
    else:
        if pi.get("show_rate"):
            headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Rate', 'Amount']
            col_widths = [10*mm, 62*mm, 20*mm, 16*mm, 30*mm, 43*mm]
        else:
            headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Amount']
            col_widths = [10*mm, 76*mm, 24*mm, 16*mm, 53*mm]

    itm_p  = sty('IP', fontSize=8, leading=11)
    tbl_hdr= sty('TH', fontSize=8, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER)
    tbl_num= sty('TN', fontSize=8, alignment=TA_RIGHT)
    tbl_ctr= sty('TC', fontSize=8, alignment=TA_CENTER)

    table_data = [[Paragraph(h, tbl_hdr) for h in headers]]
    for i, item in enumerate(pi.get("items", [])):
        item_name = item.get("product_name", "")
        if item.get("description"):
            item_name += f"<br/><font size=7 color='#6B7280'>{item['description']}</font>"
        row = [
            Paragraph(str(i + 1), tbl_ctr),
            Paragraph(item_name, itm_p),
            Paragraph(str(item.get("qty", 0)), tbl_num),
            Paragraph(str(item.get("unit", "")), tbl_ctr),
        ]
        if pi.get("show_rate"):
            row.append(Paragraph(f"{item.get('rate', 0):.2f}", tbl_num))
        row.append(Paragraph(f"{item.get('amount', 0):.2f}", tbl_num))
        if is_gst:
            row.append(Paragraph(f"{item.get('gst_rate', 0)}%", tbl_ctr))
            row.append(Paragraph(f"{item.get('gst_amount', 0):.2f}", tbl_num))
            row.append(Paragraph(f"{item.get('total', 0):.2f}", tbl_num))
        table_data.append(row)

    items_t = Table(table_data, colWidths=col_widths, repeatRows=1)
    items_t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,0),   GREEN if is_gst else DGRAY),
        ('TEXTCOLOR',     (0,0),(-1,0),   colors.white),
        ('FONTSIZE',      (0,0),(-1,-1),  8),
        ('GRID',          (0,0),(-1,-1),  0.4, SGRAY),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),  [colors.white, BGRAY]),
        ('VALIGN',        (0,0),(-1,-1),  'MIDDLE'),
        ('TOPPADDING',    (0,0),(-1,-1),  4),
        ('BOTTOMPADDING', (0,0),(-1,-1),  4),
        ('LEFTPADDING',   (0,0),(-1,-1),  5),
        ('RIGHTPADDING',  (0,0),(-1,-1),  5),
    ]))
    elements.append(items_t)
    elements.append(Spacer(1, 5*mm))

    # ─────────────────────────────────────────────────────────────
    # ── D. TOTALS (logic unchanged, layout improved) ─────────────
    # ─────────────────────────────────────────────────────────────
    totals = []
    totals.append([Paragraph("Subtotal", tr), Paragraph(f"{pi.get('subtotal', 0):.2f}", tr)])
    if is_gst:
        cust_state = ""
        if pi.get("billing_address"):
            cust_state = pi["billing_address"].get("state", "")
        if cust_state.lower() == "maharashtra":
            cgst = round(pi.get("total_gst", 0) / 2, 2)
            totals.append([Paragraph("CGST", tr), Paragraph(f"{cgst:.2f}", tr)])
            totals.append([Paragraph("SGST", tr), Paragraph(f"{cgst:.2f}", tr)])
        else:
            totals.append([Paragraph("IGST", tr), Paragraph(f"{pi.get('total_gst', 0):.2f}", tr)])
    if pi.get("shipping_charge", 0) > 0:
        totals.append([Paragraph("Shipping Charges", tr), Paragraph(f"{pi['shipping_charge']:.2f}", tr)])
        if pi.get("shipping_gst", 0) > 0:
            totals.append([Paragraph("Shipping GST (18%)", tr), Paragraph(f"{pi['shipping_gst']:.2f}", tr)])
    # Additional charges in PI PDF
    for charge in pi.get("additional_charges", []):
        charge_label = charge.get("name", "Charge")
        charge_amt = charge.get("amount", 0)
        charge_gst = charge.get("gst_amount", 0)
        if charge_amt > 0:
            totals.append([Paragraph(charge_label, tr), Paragraph(f"{charge_amt:.2f}", tr)])
        if charge_gst > 0:
            totals.append([Paragraph(f"{charge_label} GST ({charge.get('gst_percent', 0)}%)", tr), Paragraph(f"{charge_gst:.2f}", tr)])
    totals.append([Paragraph("<b>GRAND TOTAL</b>", trb), Paragraph(f"<b>INR {pi.get('grand_total', 0):.0f}</b>", trb)])

    tt = Table(totals, colWidths=[pw - 62*mm, 62*mm])
    tt.setStyle(TableStyle([
        ('ALIGN',         (0,0),(-1,-1), 'RIGHT'),
        ('LINEABOVE',     (0,-1),(-1,-1), 1.5, GREEN if is_gst else DGRAY),
        ('BACKGROUND',    (0,-1),(-1,-1), LGREEN if is_gst else BGRAY),
        ('TOPPADDING',    (0,-1),(-1,-1), 6),
        ('BOTTOMPADDING', (0,-1),(-1,-1), 6),
        ('TOPPADDING',    (0,0),(-1,-2),  3),
        ('BOTTOMPADDING', (0,0),(-1,-2),  3),
        ('LEFTPADDING',   (0,0),(-1,-1),  5),
        ('RIGHTPADDING',  (0,0),(-1,-1),  5),
    ]))
    elements.append(tt)

    # ─────────────────────────────────────────────────────────────
    # ── E. REMARKS + FREE SAMPLES ────────────────────────────────
    # ─────────────────────────────────────────────────────────────
    extras = []
    if pi.get("remark"):
        extras.append(f"<b>Remarks:</b>  {pi['remark']}")
    if pi.get("free_samples"):
        extras.append("<b>Free Samples:</b>")
        for s in pi["free_samples"]:
            st = s.get("item_name", "")
            if s.get("description"):
                st += f" – {s['description']}"
            extras.append(f"   · {st}")
    if extras:
        elements.append(Spacer(1, 5*mm))
        elements.append(sep())
        elements.append(Spacer(1, 3*mm))
        for line in extras:
            elements.append(Paragraph(line, sty('Ex', fontSize=8.5, leading=13)))
            elements.append(Spacer(1, 1*mm))

    # ─────────────────────────────────────────────────────────────
    # ── F. BANK DETAILS + QR CODE (logic unchanged) ──────────────
    # ─────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 7*mm))
    bank = BANK_GST if is_gst else BANK_NON_GST
    upi_string = bank["upi_string"].format(amount=int(pi.get("grand_total", 0)))

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=6, border=2)
    qr.add_data(upi_string)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    qr_image = Image(qr_buffer, width=32*mm, height=32*mm)

    bank_detail_style = sty('Bk', fontSize=8.5, leading=13)
    bank_para = Paragraph(
        f"<b>A/c Name:</b>  {bank['account_name']}<br/>"
        f"<b>A/c No.:</b>   {bank['account_no']}<br/>"
        f"<b>IFSC:</b>      {bank['ifsc']}<br/>"
        f"<b>Bank:</b>      {bank['bank']}<br/>"
        f"<b>Branch:</b>    {bank['branch']}",
        bank_detail_style
    )
    qr_label = Paragraph(
        "<b>Scan to Pay</b><br/><font size=7 color='#6B7280'>UPI / PhonePe / GPay / Paytm</font>",
        sty('QL', fontSize=8, leading=11, alignment=TA_CENTER)
    )
    acc_label = Paragraph(
        "<b>PAYMENT DETAILS</b>",
        sty('PH', fontSize=8, fontName='Helvetica-Bold', textColor=colors.white)
    )

    pay_hdr_row  = [acc_label, Paragraph("<b>SCAN & PAY</b>",
                    sty('SH', fontSize=8, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER))]
    pay_data_row = [bank_para, Table([[qr_image],[qr_label]], colWidths=[36*mm])]

    pay_tbl = Table([pay_hdr_row, pay_data_row], colWidths=[pw - 40*mm, 40*mm])
    pay_tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,0),  GREEN if is_gst else DGRAY),
        ('TEXTCOLOR',    (0,0),(-1,0),  colors.white),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('ALIGN',        (1,1),(1,1),   'CENTER'),
        ('BOX',          (0,0),(-1,-1), 0.5, SGRAY),
        ('LINEBELOW',    (0,0),(-1,0),  0.5, SGRAY),
        ('LINEAFTER',    (0,0),(0,-1),  0.5, SGRAY),
        ('TOPPADDING',   (0,0),(-1,0),  4), ('BOTTOMPADDING',(0,0),(-1,0), 4),
        ('TOPPADDING',   (0,1),(-1,1),  6), ('BOTTOMPADDING',(0,1),(-1,1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (0,0),(-1,-1), 8),
    ]))
    elements.append(pay_tbl)

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={pi['pi_number']}.pdf"}
    )

# ═══════════════════════════════════════════════
#  AMAZON PDF ORDERS MODULE
# ═══════════════════════════════════════════════
import pdfplumber

def parse_amazon_pdf_text(filepath, ship_type="easy_ship"):
    """Parse Amazon PDF and extract orders."""
    with pdfplumber.open(filepath) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

    blocks = re.split(r'(?=Ship to:\n)', full_text)
    orders = []
    seen_ids = set()

    for block in blocks:
        if "Ship to:" not in block or "Order ID:" not in block:
            continue
        if block.strip().startswith("I hereby confirm") or block.strip().startswith("I confirm"):
            continue

        oid_match = re.search(r'Order ID:\s*(\d{3}-\d{7}-\d{7})', block)
        if not oid_match:
            continue
        amazon_order_id = oid_match.group(1)
        if amazon_order_id in seen_ids:
            continue
        seen_ids.add(amazon_order_id)

        ship_to_match = re.search(r'Ship to:\n(.+?)(?=\n)', block)
        customer_name = ship_to_match.group(1).strip() if ship_to_match else ""

        addr_match = re.search(r'Ship to:\n.+?\n(.*?)(?=Phone\s*:|Order ID:)', block, re.DOTALL)
        address = ""
        if addr_match:
            addr_lines = [l.strip() for l in addr_match.group(1).strip().split('\n') if l.strip() and 'COD' not in l]
            address = ", ".join(addr_lines)

        phone = ""
        if ship_type == "self_ship":
            phone_match = re.search(r'Phone\s*:\s*(\d+)', block)
            if phone_match:
                phone = phone_match.group(1)

        items = []
        item_pattern = re.findall(r'^(\d+)\s+(.+?)\s+₹([\d,]+\.\d{2})\s*$', block, re.MULTILINE)
        for qty_str, product_raw, price_str in item_pattern:
            qty = int(qty_str)
            price = float(price_str.replace(',', ''))
            items.append({
                "product_name": product_raw.strip(),
                "quantity": qty,
                "unit": "pcs",
                "unit_price": price,
                "amount": round(qty * price, 2),
            })

        grand_match = re.search(r'Grand total\s*₹([\d,]+\.\d{2})', block)
        grand_total = float(grand_match.group(1).replace(',', '')) if grand_match else sum(i["amount"] for i in items)

        if not items:
            continue

        orders.append({
            "amazon_order_id": amazon_order_id,
            "customer_name": customer_name,
            "address": address,
            "phone": phone,
            "items": items,
            "grand_total": grand_total,
        })

    return orders


async def get_next_am_number():
    """Get next AM-XXXX order number."""
    counter = await db.amazon_counter.find_one_and_update(
        {"_id": "amazon_order_counter"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
        projection={"_id": 0, "seq": 1}
    )
    seq = counter["seq"]
    return f"AM-{seq:04d}"


@api_router.post("/amazon/upload-pdf")
async def upload_amazon_pdf(
    file: UploadFile = File(...),
    ship_type: str = Query("easy_ship"),
    user=Depends(get_current_user)
):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if ship_type not in ["easy_ship", "self_ship"]:
        raise HTTPException(status_code=400, detail="Invalid ship type")

    tmp_path = UPLOAD_DIR / f"tmp_amazon_{uuid.uuid4().hex}.pdf"
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)
        parsed = parse_amazon_pdf_text(str(tmp_path), ship_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF parsing failed: {str(e)}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    if not parsed:
        raise HTTPException(status_code=400, detail="No orders found in PDF")

    created = []
    duplicates = []
    for p in parsed:
        existing = await db.amazon_orders.find_one({"amazon_order_id": p["amazon_order_id"]}, {"_id": 0})
        if existing:
            duplicates.append(p["amazon_order_id"])
            continue

        am_number = await get_next_am_number()
        shipping_method = "amazon" if ship_type == "easy_ship" else "courier"
        order = {
            "id": str(uuid.uuid4()),
            "am_order_number": am_number,
            "amazon_order_id": p["amazon_order_id"],
            "ship_type": ship_type,
            "shipping_method": shipping_method,
            "courier_name": "",
            "customer_name": p["customer_name"],
            "address": p["address"],
            "phone": p.get("phone", ""),
            "items": p["items"],
            "grand_total": p["grand_total"],
            "status": "new",
            "packaging": {
                "item_packed_by": [],
                "box_packed_by": [],
                "checked_by": [],
                "item_images": {},
                "order_images": [],
                "packed_box_images": [],
            },
            "dispatch": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.amazon_orders.insert_one(order)
        order.pop("_id", None)
        created.append(order)

    return {"created": len(created), "duplicates": len(duplicates), "duplicate_ids": duplicates, "orders": created}


@api_router.get("/amazon/orders")
async def list_amazon_orders(user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    orders = await db.amazon_orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return orders


@api_router.get("/amazon/orders/{order_id}")
async def get_amazon_order(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@api_router.put("/amazon/orders/{order_id}/packaging")
async def update_amazon_packaging(order_id: str, updates: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Packaging or admin only")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched" and user["role"] != "admin":
        raise HTTPException(status_code=400, detail="Cannot modify dispatched order")

    packaging = order.get("packaging", {})
    for key in ["item_packed_by", "box_packed_by", "checked_by", "item_images", "order_images", "packed_box_images"]:
        if key in updates:
            packaging[key] = updates[key]

    new_status = order.get("status", "new")
    if new_status == "new":
        new_status = "packaging"

    await db.amazon_orders.update_one(
        {"id": order_id},
        {"$set": {"packaging": packaging, "status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "updated"}


@api_router.put("/amazon/orders/{order_id}/mark-packed")
async def mark_amazon_packed(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await db.amazon_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "packed", "packaging.packed_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "packed"}


@api_router.put("/amazon/orders/{order_id}/dispatch")
async def dispatch_amazon_order(order_id: str, data: dict = {}, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    dispatch = {
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_by": user["username"],
    }
    if order.get("ship_type") == "self_ship":
        lr = data.get("lr_number", "").strip()
        if not lr:
            raise HTTPException(status_code=400, detail="LR number is required for self ship orders")
        dispatch["lr_number"] = lr
    await db.amazon_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "dispatched", "dispatch": dispatch, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "dispatched"}


@api_router.post("/amazon/orders/bulk-dispatch")
async def bulk_dispatch_amazon(data: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order_ids = data.get("order_ids", [])
    if not order_ids:
        raise HTTPException(status_code=400, detail="No order IDs provided")
    dispatched = 0
    for oid in order_ids:
        order = await db.amazon_orders.find_one({"id": oid}, {"_id": 0})
        if not order or order.get("status") == "dispatched":
            continue
        dispatch_data = {
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
            "dispatched_by": user["username"],
        }
        await db.amazon_orders.update_one(
            {"id": oid},
            {"$set": {"status": "dispatched", "dispatch": dispatch_data, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        dispatched += 1
    return {"dispatched": dispatched}


@api_router.put("/amazon/orders/{order_id}/courier")
async def update_amazon_courier(order_id: str, data: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched":
        raise HTTPException(status_code=400, detail="Cannot modify dispatched order")
    courier_name = data.get("courier_name", "")
    await db.amazon_orders.update_one(
        {"id": order_id},
        {"$set": {"courier_name": courier_name, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "updated", "courier_name": courier_name}


@api_router.delete("/amazon/orders/{order_id}")
async def delete_amazon_order(order_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched":
        raise HTTPException(status_code=400, detail="Cannot delete dispatched order")
    await db.amazon_orders.delete_one({"id": order_id})
    return {"status": "deleted"}


@api_router.delete("/amazon/orders/{order_id}/images")
async def delete_amazon_order_image(
    order_id: str,
    image_type: str = Query(...),
    image_url: str = Query(...),
    item_name: str = Query(""),
    user=Depends(get_current_user)
):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched" and user["role"] != "admin":
        raise HTTPException(status_code=400, detail="Cannot modify dispatched order")

    packaging = order.get("packaging", {})
    if image_type == "item_image" and item_name:
        imgs = packaging.get("item_images", {}).get(item_name, [])
        packaging["item_images"][item_name] = [u for u in imgs if u != image_url]
    elif image_type == "order_image":
        packaging["order_images"] = [u for u in packaging.get("order_images", []) if u != image_url]
    elif image_type == "packed_box_image":
        packaging["packed_box_images"] = [u for u in packaging.get("packed_box_images", []) if u != image_url]

    await db.amazon_orders.update_one({"id": order_id}, {"$set": {"packaging": packaging, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"status": "deleted"}

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
