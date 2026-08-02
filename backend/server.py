from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import json
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
import pytz
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from reportlab.lib.pagesizes import A4, A5, landscape
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
LOGO_PDF_PATH = ROOT_DIR / "logo_pdf.png"

COURIER_OPTIONS = ["DTDC", "Anjani", "India Post", "Others"]

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

class LocationPing(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None      # metres
    altitude: Optional[float] = None
    speed: Optional[float] = None         # m/s
    heading: Optional[float] = None
    battery: Optional[int] = None         # 0-100
    is_moving: Optional[bool] = None
    ts: Optional[str] = None              # ISO8601; server fills if absent

class LocationBatch(BaseModel):
    pings: List[LocationPing] = []

class AddressCreate(BaseModel):
    address_line: str
    city: str
    state: str
    pincode: str
    label: str = ""
    address_name: str = ""

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

# ─── DTDC Carrier Risk ────────────────────────────────────────────────────
# DTDC levies carrier risk (transit insurance) at 2% of the declared invoice
# value or a flat minimum, whichever is higher, plus GST. The charge appears on
# the invoice, so it raises the value the 2% is levied on. The amount is
# therefore the fixed point of
#     C = 0.02 * (base + C + C * gst)
#   =>  C = 0.02 * base / (1 - 0.02 * (1 + gst))
# where base is everything else on the invoice. Worked example: base 4882 with
# 18% GST gives C = 100, an invoice value of 4882 + 100 + 18 = 5000, and 2% of
# 5000 is exactly the 100 charged.
CARRIER_RISK_LABEL = "Carrier Risk"
CARRIER_RISK_MIN_AMOUNT = 100
CARRIER_RISK_RATE = 0.02
CARRIER_RISK_GST_PERCENT = 18
CARRIER_RISK_COURIER = "DTDC"


def calc_carrier_risk(base_value: float, gst_percent: int = CARRIER_RISK_GST_PERCENT) -> dict:
    """Carrier risk row for an invoice worth base_value before the charge is added."""
    base_value = max(0.0, float(base_value or 0))
    gst_percent = max(0, int(gst_percent or 0))
    gst_fraction = gst_percent / 100
    divisor = 1 - CARRIER_RISK_RATE * (1 + gst_fraction)
    raw = (CARRIER_RISK_RATE * base_value / divisor) if divisor > 0 else float(CARRIER_RISK_MIN_AMOUNT)
    # Round before the ceiling so float noise at an exact boundary (base 4882
    # lands on precisely 100) cannot push the charge a whole rupee higher.
    amount = max(CARRIER_RISK_MIN_AMOUNT, math.ceil(round(raw, 6)))
    return {
        "name": CARRIER_RISK_LABEL,
        "amount": float(amount),
        "gst_percent": gst_percent,
        "gst_amount": round(amount * gst_fraction, 2),
    }


def build_additional_charges(raw_charges, gst_applicable: bool, carrier_risk_applicable: bool, base_value: float):
    """Normalise additional charges, appending the derived carrier risk row when applicable.

    base_value is the rest of the invoice: items + item GST + shipping + shipping GST.
    Returns (charges, total_amount, total_gst).
    """
    charges = []
    total_amount = 0.0
    total_gst = 0.0
    for charge in raw_charges or []:
        c = charge.model_dump() if hasattr(charge, "model_dump") else dict(charge)
        # Carrier risk is always re-derived here, never trusted from the caller.
        if str(c.get("name", "")).strip().lower() == CARRIER_RISK_LABEL.lower():
            continue
        c["amount"] = max(0, c.get("amount", 0) or 0)
        c["gst_percent"] = c.get("gst_percent", 0) or 0
        if gst_applicable and c["gst_percent"] > 0:
            c["gst_amount"] = round(c["amount"] * c["gst_percent"] / 100, 2)
        else:
            c["gst_amount"] = 0
        total_amount += c["amount"]
        total_gst += c["gst_amount"]
        charges.append(c)

    if carrier_risk_applicable:
        # Carrier risk always carries 18% GST. On a GST invoice it's shown as
        # amount + GST; on a non-GST invoice the GST is folded into a single
        # inclusive amount (e.g. 118) with no GST line.
        cr = calc_carrier_risk(base_value + total_amount + total_gst, CARRIER_RISK_GST_PERCENT)
        if gst_applicable:
            carrier_risk = cr
        else:
            inclusive = float(math.ceil(cr["amount"] + cr["gst_amount"]))
            carrier_risk = {
                "name": CARRIER_RISK_LABEL,
                "amount": inclusive,
                "gst_percent": 0,
                "gst_amount": 0,
            }
        charges.append(carrier_risk)
        total_amount += carrier_risk["amount"]
        total_gst += carrier_risk["gst_amount"]

    return charges, total_amount, total_gst

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
    carrier_risk_applicable: bool = False
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
    dispatch_slip_images: List[str] = []
    porter_link: str = ""

class PICreate(BaseModel):
    customer_id: str
    items: List[OrderItemModel]
    free_samples: List[FreeSampleModel] = []
    gst_applicable: bool = False
    show_rate: bool = True
    shipping_charge: float = 0
    additional_charges: List[AdditionalChargeModel] = []
    carrier_risk_applicable: bool = False
    remark: str = ""
    billing_address_id: str = ""
    shipping_address_id: str = ""
    terms_and_conditions: str = ""

DEFAULT_PI_TERMS = [
    "Goods once sold will not be taken back or exchanged.",
    "All disputes are subject to Nagpur jurisdiction only.",
    "Dispatch will be done within 2\u20133 working days after receipt of full payment.",
    "Prices are subject to change without prior notice.",
    "Delivery timelines may vary due to transport or unforeseen circumstances.",
    "Any damage or shortage must be reported within 24 hours of delivery. Opening video of the package is mandatory for any claim.",
    "Payment once made is non-refundable except in mutually agreed cases.",
]

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

# Paths a field_executive account is permitted to reach. Everything else in the
# OMS (orders, customers, PIs, analytics, ...) is blocked for this role at the
# API layer so the account can only be used for location reporting.
FIELD_EXECUTIVE_ALLOWED_PREFIXES = (
    "/api/auth/",
    "/api/location/",
)

async def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="User not found or inactive")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if user.get("role") == "field_executive":
        path = request.url.path
        if not any(path.startswith(p) for p in FIELD_EXECUTIVE_ALLOWED_PREFIXES):
            raise HTTPException(status_code=403, detail="Not authorized for this resource")
    return user

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
    await db.edit_permissions.create_index("order_id")
    await db.edit_permissions.create_index("user_id")
    await db.locations.create_index([("user_id", 1), ("ts", 1)])
    await db.locations.create_index("ts")

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
    if req.role not in ["admin", "telecaller", "packaging", "dispatch", "accounts", "field_executive"]:
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

@api_router.get("/customers/count")
async def get_customers_count(user=Depends(get_current_user)):
    count = await db.customers.count_documents({})
    return {"count": count}

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
    # Propagate customer_name to all orders and PIs referencing this customer
    new_name = update_data["name"]
    await db.orders.update_many({"customer_id": customer_id}, {"$set": {"customer_name": new_name}})
    await db.proforma_invoices.update_many({"customer_id": customer_id}, {"$set": {"customer_name": new_name}})
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
        "address_name": req.address_name.strip() if req.address_name else customer.get("name", ""),
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
        "address_name": req.address_name.strip() if req.address_name else "",
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

    shipping_gst = 0
    if req.gst_applicable and req.shipping_charge > 0:
        shipping_gst = round(req.shipping_charge * 0.18, 2)

    # Process additional charges (carrier risk, if applicable, is appended here)
    additional_charges, total_additional, total_additional_gst = build_additional_charges(
        req.additional_charges,
        req.gst_applicable,
        req.carrier_risk_applicable,
        subtotal + total_gst + req.shipping_charge + shipping_gst,
    )

    raw_total = subtotal + total_gst + req.shipping_charge + shipping_gst + total_additional + total_additional_gst
    grand_total = math.ceil(raw_total)

    shipping_method = req.shipping_method
    courier_name = req.courier_name
    transporter_name = req.transporter_name
    if shipping_method == "courier":
        transporter_name = ""
    elif shipping_method == "transport":
        courier_name = ""
    else:
        courier_name = ""
        transporter_name = ""

    order_doc = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "customer_id": req.customer_id,
        "customer_name": customer["name"],
        "purpose": req.purpose,
        "items": items,
        "gst_applicable": req.gst_applicable,
        "shipping_method": shipping_method,
        "courier_name": courier_name,
        "transporter_name": transporter_name,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "additional_charges": additional_charges,
        "carrier_risk_applicable": req.carrier_risk_applicable,
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
    gst_only: Optional[bool] = False,
    payment_status: Optional[str] = None,
    check_status: Optional[str] = None,
    period: Optional[str] = None,
    shipping_method: Optional[str] = None,
    courier_name: Optional[str] = None,
    ready_to_book: Optional[bool] = False,
    page: int = 1,
    page_size: int = 50,
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
        if status == "yet_to_dispatch":
            query["status"] = {"$in": ["new", "packaging", "packed"]}
        else:
            query["status"] = status
    if telecaller_id and user["role"] == "admin":
        query["telecaller_id"] = telecaller_id
    if ready_to_book:
        # Weighed & released by packing, but not yet dispatched — the booking queue.
        query["packaging.ready_to_book"] = True
        query["status"] = {"$in": ["packaging", "packed"]}
    if customer_id:
        query["customer_id"] = customer_id
    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"

    if gst_only:
        query["gst_applicable"] = True

    # Payment status filter (computed field: amount_paid vs grand_total)
    if payment_status == "full":
        query["$expr"] = {"$and": [{"$gt": ["$grand_total", 0]}, {"$gte": [{"$ifNull": ["$amount_paid", 0]}, "$grand_total"]}]}
    elif payment_status == "partial":
        query["$expr"] = {"$and": [{"$gt": [{"$ifNull": ["$amount_paid", 0]}, 0]}, {"$lt": [{"$ifNull": ["$amount_paid", 0]}, "$grand_total"]}]}
    elif payment_status == "unpaid":
        query["$expr"] = {"$lte": [{"$ifNull": ["$amount_paid", 0]}, 0]}

    # Check status filter
    if check_status and check_status != "all":
        query["payment_check_status"] = check_status

    # Shipping method filter
    if shipping_method and shipping_method != "all":
        query["shipping_method"] = shipping_method
        if shipping_method == "courier" and courier_name and courier_name != "all":
            query["courier_name"] = courier_name

    # Period filter (server-side)
    if period and period != "all":
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query.setdefault("created_at", {})["$gte"] = start.isoformat()
        elif period == "yesterday":
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query.setdefault("created_at", {})["$gte"] = start.isoformat()
            query.setdefault("created_at", {})["$lte"] = end.isoformat()
        elif period == "week":
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            query.setdefault("created_at", {})["$gte"] = start.isoformat()
        elif period == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            query.setdefault("created_at", {})["$gte"] = start.isoformat()


    # Server-side search: search across order_number, customer_name, alias, phone numbers, and GST
    if search:
        # Find customer IDs matching alias, phone numbers (partial), or GST
        phone_gst_alias_cust_ids = set()
        async for c in db.customers.find(
            {"$or": [
                {"alias": {"$regex": search, "$options": "i"}},
                {"phone_numbers": {"$elemMatch": {"$regex": search, "$options": "i"}}},
                {"gst_no": {"$regex": search, "$options": "i"}},
            ]},
            {"_id": 0, "id": 1}
        ):
            phone_gst_alias_cust_ids.add(c["id"])

        or_conditions = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"shipping_address.city": {"$regex": search, "$options": "i"}},
            {"shipping_address.state": {"$regex": search, "$options": "i"}},
            {"billing_address.city": {"$regex": search, "$options": "i"}},
            {"billing_address.state": {"$regex": search, "$options": "i"}},
            {"dispatch.lr_no": {"$regex": search, "$options": "i"}},
        ]
        if phone_gst_alias_cust_ids:
            or_conditions.append({"customer_id": {"$in": list(phone_gst_alias_cust_ids)}})
        query["$or"] = or_conditions

    # Lean projection — exclude heavy nested data for list view
    # NOTE: shipping_address is kept so DTDC export can read destination info
    # NOTE: packaging is kept (minus its heavy image arrays) so the list view can
    # read weight_kg / num_boxes / ready_to_book for the DTDC export and queue.
    list_projection = {
        "_id": 0, "items": 0, "free_samples": 0,
        "billing_address": 0,
        "packaging.item_images": 0, "packaging.order_images": 0,
        "packaging.packed_box_images": 0,
        "dispatch_details": 0,
        "payment_mode_details": 0,
        "remark": 0, "purpose": 0, "extra_shipping_details": 0,
    }

    # Pagination
    total = await db.orders.count_documents(query)
    skip = (max(1, page) - 1) * page_size
    orders = await db.orders.find(query, list_projection).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)

    # Enrich with customer phone/gst/alias for search
    cust_ids = list(set(o.get("customer_id", "") for o in orders if o.get("customer_id")))
    custs = {}
    if cust_ids:
        async for c in db.customers.find({"id": {"$in": cust_ids}}, {"_id": 0, "id": 1, "phone_numbers": 1, "gst_no": 1, "alias": 1}):
            custs[c["id"]] = c

    # Get settings for formulation visibility
    settings = await db.settings.find_one({"_id": "global"})
    show_formulation_global = settings.get("show_formulation", False) if settings else False

    for o in orders:
        # Enrich with customer details
        c = custs.get(o.get("customer_id"), {})
        o["customer_phone"] = c.get("phone_numbers", [])
        o["customer_gst_no"] = c.get("gst_no", "")
        o["customer_alias"] = c.get("alias", "")

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

    return {"orders": orders, "total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}

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
    # Enrich with full customer data
    if order.get("customer_id"):
        cust = await db.customers.find_one({"id": order["customer_id"]}, {"_id": 0, "alias": 1, "name": 1, "phone_numbers": 1, "gst_no": 1, "email": 1})
        if cust:
            order["customer_alias"] = cust.get("alias", "")
            order["customer_name"] = cust.get("name", order.get("customer_name", ""))
            order["customer_phone"] = cust.get("phone_numbers", [])
            order["customer_gst_no"] = cust.get("gst_no", "")
            order["customer_email"] = cust.get("email", "")
    # Hide telecaller info for non-admin (keep telecaller_id for telecaller's own-order check)
    if user["role"] == "telecaller":
        order.pop("telecaller_name", None)
    elif user["role"] != "admin":
        order.pop("telecaller_name", None)
        order.pop("telecaller_id", None)
    # Formulation lock status - check BEFORE stripping formulations
    has_formulation = any(item.get("formulation") for item in order.get("items", []))
    if not has_formulation:
        has_formulation = any(s.get("formulation") for s in order.get("free_samples", []))
    
    # Strict formulation visibility - strip formulations for non-admin/non-packaging users
    settings = await db.settings.find_one({"_id": "global"})
    show_formulation_global = settings.get("show_formulation", False) if settings else False
    if user["role"] == "telecaller":
        for item in order.get("items", []):
            item.pop("formulation", None)
        for sample in order.get("free_samples", []):
            sample.pop("formulation", None)
    elif user["role"] == "packaging" and not show_formulation_global:
        for item in order.get("items", []):
            item.pop("formulation", None)
        for sample in order.get("free_samples", []):
            sample.pop("formulation", None)
    elif user["role"] in ["dispatch", "accounts"]:
        for item in order.get("items", []):
            item.pop("formulation", None)
        for sample in order.get("free_samples", []):
            sample.pop("formulation", None)
    order["formulation_locked"] = has_formulation
    # Check edit permission for non-admin
    if user["role"] != "admin" and has_formulation:
        perm = await db.edit_permissions.find_one(
            {"order_id": order_id, "user_id": user["id"], "status": "approved"}, {"_id": 0}
        )
        order["has_edit_permission"] = bool(perm)
    else:
        order["has_edit_permission"] = user["role"] == "admin"
    return order

@api_router.put("/orders/{order_id}")
async def update_order(order_id: str, updates: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Only admin or telecaller can edit orders")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Formulation lock: if order has any formulation, only admin can edit (unless approved)
    has_approved_permission = False
    if user["role"] != "admin":
        has_formulation = any(item.get("formulation") for item in order.get("items", []))
        if not has_formulation:
            has_formulation = any(s.get("formulation") for s in order.get("free_samples", []))
        if has_formulation:
            # Check if user has approved edit permission
            permission = await db.edit_permissions.find_one(
                {"order_id": order_id, "user_id": user["id"], "status": "approved"},
                {"_id": 0}
            )
            if not permission:
                raise HTTPException(status_code=403, detail="This order has formulations and is locked. Request edit permission from Admin.")
            # Permission used — revoke it after this edit
            await db.edit_permissions.update_one(
                {"id": permission["id"]},
                {"$set": {"status": "used", "used_at": datetime.now(timezone.utc).isoformat()}}
            )
            has_approved_permission = True

    # Dispatch lock: admins can edit everything; telecallers can edit payment fields on own orders
    if order.get("status") == "dispatched" and user["role"] != "admin":
        allowed_dispatched = {"payment_status", "amount_paid", "balance_amount", "mode_of_payment", "payment_mode_details", "payment_screenshots"}
        non_allowed = set(updates.keys()) - allowed_dispatched - {"id", "order_number", "updated_at"}
        if non_allowed:
            raise HTTPException(status_code=400, detail="Order is dispatched. Only payment details can be updated.")
    # Telecaller can only edit their own orders (unless admin-approved permission)
    if user["role"] == "telecaller" and order.get("telecaller_id") != user["id"] and not has_approved_permission:
        raise HTTPException(status_code=403, detail="You can only edit your own orders")
    updates.pop("id", None)
    updates.pop("order_number", None)

    # CRITICAL: Preserve formulations when items are updated
    if "items" in updates:
        existing_items = order.get("items", [])
        new_items = updates["items"]
        # Build lookup of existing formulations by product_name for fuzzy matching
        existing_formulations = {}
        for ei in existing_items:
            if ei.get("formulation"):
                existing_formulations[ei["product_name"]] = ei["formulation"]
        # Preserve formulations: merge from existing items
        for i, new_item in enumerate(new_items):
            if not new_item.get("formulation"):
                # Try exact index match first
                if i < len(existing_items) and existing_items[i].get("formulation"):
                    if existing_items[i]["product_name"] == new_item.get("product_name"):
                        new_item["formulation"] = existing_items[i]["formulation"]
                # Fallback: match by product_name
                if not new_item.get("formulation") and new_item.get("product_name") in existing_formulations:
                    new_item["formulation"] = existing_formulations[new_item["product_name"]]
        updates["items"] = new_items

    # CRITICAL: Preserve free_sample formulations
    if "free_samples" in updates:
        existing_fs = order.get("free_samples", [])
        new_fs = updates["free_samples"]
        existing_fs_formulations = {}
        for es in existing_fs:
            if es.get("formulation"):
                existing_fs_formulations[es.get("item_name", "")] = es["formulation"]
        for i, ns in enumerate(new_fs):
            if not ns.get("formulation"):
                if i < len(existing_fs) and existing_fs[i].get("formulation"):
                    if existing_fs[i].get("item_name") == ns.get("item_name"):
                        ns["formulation"] = existing_fs[i]["formulation"]
                if not ns.get("formulation") and ns.get("item_name") in existing_fs_formulations:
                    ns["formulation"] = existing_fs_formulations[ns["item_name"]]
        updates["free_samples"] = new_fs

    # Auto-recheck: if payment details change on an already-checked order
    if order.get("payment_check_status") == "received":
        payment_changed = (
            ("payment_status" in updates and updates["payment_status"] != order.get("payment_status")) or
            ("amount_paid" in updates and float(updates.get("amount_paid", 0)) != float(order.get("amount_paid", 0)))
        )
        if payment_changed:
            updates["payment_check_status"] = "pending_recheck"
    # Clean up shipping method specific fields in updates and dispatch nested object
    active_method = updates.get("shipping_method", order.get("shipping_method", ""))
    if active_method == "courier":
        updates["transporter_name"] = ""
    elif active_method == "transport":
        updates["courier_name"] = ""
    else:
        updates["courier_name"] = ""
        updates["transporter_name"] = ""

    dispatch_source = updates.get("dispatch") or order.get("dispatch")
    if dispatch_source and isinstance(dispatch_source, dict):
        dispatch = dispatch_source.copy()
        dispatch["dispatch_type"] = active_method
        if active_method == "courier":
            dispatch["courier_name"] = updates.get("courier_name", dispatch.get("courier_name", ""))
            dispatch["transporter_name"] = ""
            dispatch["porter_link"] = ""
        elif active_method == "transport":
            dispatch["transporter_name"] = updates.get("transporter_name", dispatch.get("transporter_name", ""))
            dispatch["courier_name"] = ""
            dispatch["porter_link"] = ""
        elif active_method == "porter":
            dispatch["courier_name"] = ""
            dispatch["transporter_name"] = ""
            dispatch["lr_no"] = ""
            dispatch["dispatch_slip_images"] = []
        else:
            dispatch["courier_name"] = ""
            dispatch["transporter_name"] = ""
            dispatch["lr_no"] = ""
            dispatch["dispatch_slip_images"] = []
            dispatch["porter_link"] = ""
        updates["dispatch"] = dispatch

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.orders.update_one({"id": order_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# ── Edit Permission Request System ──
@api_router.post("/orders/{order_id}/request-edit")
async def request_edit_permission(order_id: str, body: dict = {}, user=Depends(get_current_user)):
    if user["role"] == "admin":
        raise HTTPException(status_code=400, detail="Admin does not need edit permission")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Check if there's already a pending request
    existing = await db.edit_permissions.find_one(
        {"order_id": order_id, "user_id": user["id"], "status": "pending"}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="You already have a pending edit request for this order")
    request_doc = {
        "id": str(uuid.uuid4()),
        "order_id": order_id,
        "order_number": order.get("order_number", ""),
        "customer_name": order.get("customer_name", ""),
        "user_id": user["id"],
        "requested_by": user["name"],
        "requested_by_role": user["role"],
        "reason": body.get("reason", ""),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.edit_permissions.insert_one(request_doc)
    request_doc.pop("_id", None)
    return request_doc

@api_router.get("/edit-permissions")
async def list_edit_permissions(user=Depends(get_current_user)):
    if user["role"] == "admin":
        # Admin sees all pending + recent
        perms = await db.edit_permissions.find({"status": {"$in": ["pending", "approved", "rejected"]}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    else:
        perms = await db.edit_permissions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return perms

@api_router.put("/edit-permissions/{perm_id}")
async def handle_edit_permission(perm_id: str, body: dict, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    action = body.get("action")
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    perm = await db.edit_permissions.find_one({"id": perm_id}, {"_id": 0})
    if not perm:
        raise HTTPException(status_code=404, detail="Permission request not found")
    new_status = "approved" if action == "approve" else "rejected"
    await db.edit_permissions.update_one(
        {"id": perm_id},
        {"$set": {"status": new_status, "handled_by": user["name"], "handled_at": datetime.now(timezone.utc).isoformat()}}
    )
    updated = await db.edit_permissions.find_one({"id": perm_id}, {"_id": 0})
    return updated

# Check if order has formulation lock
@api_router.get("/orders/{order_id}/formulation-lock")
async def check_formulation_lock(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "items": 1, "free_samples": 1})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    has_formulation = any(item.get("formulation") for item in order.get("items", []))
    if not has_formulation:
        has_formulation = any(s.get("formulation") for s in order.get("free_samples", []))
    # Check if user has an approved permission
    has_permission = False
    if user["role"] != "admin" and has_formulation:
        perm = await db.edit_permissions.find_one(
            {"order_id": order_id, "user_id": user["id"], "status": "approved"}, {"_id": 0}
        )
        has_permission = bool(perm)
    return {
        "locked": has_formulation,
        "can_edit": user["role"] == "admin" or not has_formulation or has_permission,
        "has_permission": has_permission,
    }


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
    if "num_boxes" in updates:
        packaging["num_boxes"] = updates["num_boxes"]
    if "weight_kg" in updates:
        packaging["weight_kg"] = updates["weight_kg"]
        # Saving a weight means the box is sealed and weighed. That alone releases
        # the order to the booking queue — the DTDC label can't exist until the
        # parcel is booked, so we must not wait for "packed" here.
        if str(updates["weight_kg"]).strip():
            packaging["ready_to_book"] = True
            if not packaging.get("ready_to_book_at"):
                packaging["ready_to_book_at"] = datetime.now(timezone.utc).isoformat()
        else:
            packaging["ready_to_book"] = False
            packaging["ready_to_book_at"] = ""

    new_status = updates.get("status", order["status"])
    # Auto-transition: if status is "new" and packaging data is being saved, move to "packaging"
    if new_status == "new" and "status" not in updates:
        new_status = "packaging"
    if new_status == "packed":
        # Validate mandatory fields
        if not packaging.get("item_packed_by"):
            raise HTTPException(status_code=400, detail="Item Packed By is required")
        if not packaging.get("box_packed_by"):
            raise HTTPException(status_code=400, detail="Box Packed By is required")
        if not packaging.get("checked_by"):
            raise HTTPException(status_code=400, detail="Checked By is required")
        if order.get("shipping_method") == "courier" and not str(packaging.get("weight_kg", "")).strip():
            raise HTTPException(status_code=400, detail="Weight (KG) is required for courier orders before marking packed")
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
    if order.get("shipping_method") == "courier" and not str(packaging.get("weight_kg", "")).strip():
        raise HTTPException(status_code=400, detail="Weight (KG) is required for courier orders before marking packed")
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
    courier_partner = req.courier_name or order.get("courier_name", "")
    # Mandatory LR for transport, and for courier unless courier_name is "Others"
    if (shipping_method == "transport" or (shipping_method == "courier" and courier_partner != "Others")) and not req.lr_no:
        raise HTTPException(status_code=400, detail="LR / Tracking Number is mandatory for courier and transport dispatch")

    dispatch = {
        "courier_name": req.courier_name,
        "transporter_name": req.transporter_name or order.get("transporter_name", ""),
        "lr_no": req.lr_no,
        "dispatch_slip_images": req.dispatch_slip_images,
        "dispatch_type": req.dispatch_type or shipping_method,
        "porter_link": req.porter_link,
        "dispatched_by": user["name"],
        "dispatched_at": datetime.now(timezone.utc).isoformat()
    }
    # Clear irrelevant fields based on shipping method
    if shipping_method != "courier":
        dispatch["courier_name"] = ""
    if shipping_method != "transport":
        dispatch["transporter_name"] = ""
    if shipping_method not in ["courier", "transport"]:
        dispatch["lr_no"] = ""
        dispatch["dispatch_slip_images"] = []
    if shipping_method != "porter":
        dispatch["porter_link"] = ""

    update_fields = {
        "dispatch": dispatch,
        "status": "dispatched",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    # Always sync top-level fields and clear stale ones
    if req.shipping_method:
        update_fields["shipping_method"] = req.shipping_method
    update_fields["courier_name"] = dispatch["courier_name"]
    update_fields["transporter_name"] = dispatch["transporter_name"]
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
    new_method = body.get("shipping_method", order.get("shipping_method", ""))
    if "shipping_method" in body:
        update_fields["shipping_method"] = new_method
    # Set relevant field, clear the other
    if new_method == "courier":
        update_fields["courier_name"] = body.get("courier_name", "")
        update_fields["transporter_name"] = ""
    elif new_method == "transport":
        update_fields["transporter_name"] = body.get("transporter_name", "")
        update_fields["courier_name"] = ""
    else:
        update_fields["courier_name"] = ""
        update_fields["transporter_name"] = ""

    if "dispatch" in order and isinstance(order["dispatch"], dict):
        dispatch = order["dispatch"].copy()
        dispatch["dispatch_type"] = new_method
        if new_method == "courier":
            dispatch["courier_name"] = update_fields["courier_name"]
            dispatch["transporter_name"] = ""
            dispatch["porter_link"] = ""
        elif new_method == "transport":
            dispatch["transporter_name"] = update_fields["transporter_name"]
            dispatch["courier_name"] = ""
            dispatch["porter_link"] = ""
        elif new_method == "porter":
            dispatch["courier_name"] = ""
            dispatch["transporter_name"] = ""
            dispatch["lr_no"] = ""
            dispatch["dispatch_slip_images"] = []
        else:
            dispatch["courier_name"] = ""
            dispatch["transporter_name"] = ""
            dispatch["lr_no"] = ""
            dispatch["dispatch_slip_images"] = []
            dispatch["porter_link"] = ""
        update_fields["dispatch"] = dispatch

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


@api_router.put("/orders/{order_id}/slip-received")
async def update_slip_received(order_id: str, body: dict, user=Depends(get_current_user)):
    """Accounts marks that the physical courier/transport slip was received."""
    if user["role"] not in ["admin", "accounts"]:
        raise HTTPException(status_code=403, detail="Only accounts or admin can update slip received")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    received = bool(body.get("slip_received", False))
    now = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one({"id": order_id}, {"$set": {
        "slip_received": received,
        "slip_received_by": user["name"] if received else "",
        "slip_received_at": now if received else "",
        "updated_at": now,
    }})
    return await db.orders.find_one({"id": order_id}, {"_id": 0})

# Bulk Shipping Address Print
@api_router.post("/orders/print-addresses")
async def print_order_addresses(body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Admin or packaging only")

    order_ids = body.get("order_ids", [])
    quantities = body.get("quantities", {})  # {order_id: count}
    if not order_ids:
        raise HTTPException(status_code=400, detail="No orders selected")

    orders = []
    for oid in order_ids:
        o = await db.orders.find_one({"id": oid}, {"_id": 0})
        if o:
            orders.append(o)

    if not orders:
        raise HTTPException(status_code=404, detail="No valid orders found")

    customer_ids = list(set(o.get("customer_id", "") for o in orders if o.get("customer_id")))
    customers_list = await db.customers.find(
        {"id": {"$in": customer_ids}},
        {"_id": 0}
    ).to_list(500)
    customers = {c["id"]: c for c in customers_list}

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=5 * mm,   # reduced from 8mm
        rightMargin=5 * mm,  # reduced from 8mm
        topMargin=8 * mm,
        bottomMargin=8 * mm
    )

    styles = getSampleStyleSheet()

    # Bigger + still compact
    addr_style = ParagraphStyle(
        "AddrStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,   # increased from 9
        leading=12.5,    # adjusted accordingly
        spaceBefore=0,
        spaceAfter=0,
    )

    def make_address_cell(order, customer):
        name = (order.get("customer_name") or "Unknown").strip()
        sa = order.get("shipping_address") or {}
        # Use address_name if set, otherwise customer name
        name = sa.get("address_name") or order.get("customer_name", "Unknown")
        phones = customer.get("phone_numbers", []) if customer else []

        address_parts = []

        if sa.get("address_line"):
            address_parts.append(sa["address_line"].strip())

        city_state_line = []
        if sa.get("city"):
            if sa.get("pincode"):
                city_state_line.append(f"{sa['city'].strip()} - {sa['pincode']}")
            else:
                city_state_line.append(sa["city"].strip())

        if sa.get("state"):
            city_state_line.append(sa["state"].strip())

        if city_state_line:
            address_parts.append(", ".join(city_state_line))

        clean_phones = []
        for p in phones:
            if p:
                cp = p.replace("+91", "").replace("+", "").strip()
                if cp:
                    clean_phones.append(cp)

        mob_str = ", ".join(clean_phones)

        lines = [
            "<b>To</b>",
            f"<b>{name}</b>",
        ]

        for part in address_parts:
            lines.append(part)

        if mob_str:
            lines.append(f"<b>Mob no.- {mob_str}</b>")

        return Paragraph("<br/>".join(lines), addr_style)

    # 3 columns per row
    page_width = A4[0] - (10 * mm)  # because 5mm left + 5mm right
    gap = 3 * mm                    # slightly reduced gap between columns
    col_w = (page_width - 2 * gap) / 3

    # Build expanded list with quantities
    expanded_orders = []
    for o in orders:
        qty = max(1, int(quantities.get(o["id"], 1)))
        for _ in range(qty):
            expanded_orders.append(o)

    row_data = []
    for i in range(0, len(expanded_orders), 3):
        row = []

        for j in range(3):
            if i + j < len(expanded_orders):
                order = expanded_orders[i + j]
                customer = customers.get(order.get("customer_id", ""))
                row.append(make_address_cell(order, customer))
            else:
                row.append(Paragraph("", addr_style))  # or addr_style if that's your actual style

        row_data.append(row)

    table = Table(
        row_data,
        colWidths=[col_w, col_w, col_w],
        spaceBefore=0,
        spaceAfter=0
    )

    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.7, colors.black),

        ('VALIGN', (0, 0), (-1, -1), 'TOP'),

        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))

    doc.build([table])
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=shipping_addresses.pdf"}
    )

# Bulk Order Print (Packaging Sheets)
@api_router.post("/orders/print-packing-sheets")
async def print_bulk_packaging_sheets(body: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Admin, packaging, or accounts only")

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

    customer_ids = list(set(o.get("customer_id", "") for o in orders if o.get("customer_id")))
    customers_list = await db.customers.find(
        {"id": {"$in": customer_ids}},
        {"_id": 0}
    ).to_list(500)
    customers = {c["id"]: c for c in customers_list}

    page_size = A4
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page_size,
                            leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=10*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    elements = []
    pw = page_size[0] - 24*mm

    from reportlab.platypus import PageBreak

    # Colors
    GREEN  = colors.HexColor('#15803D')
    LGREEN = colors.HexColor('#F0FDF4')
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
    form_sty = ParagraphStyle('Form', parent=styles['Normal'], fontSize=9.5, leading=12,
                              textColor=AMBER, backColor=LAMBER)
    tot_sty  = ParagraphStyle('Tot',  parent=styles['Normal'], fontSize=9, leading=12, alignment=TA_RIGHT)
    totb_sty = ParagraphStyle('TotB', parent=styles['Normal'], fontSize=10, leading=13,
                              fontName='Helvetica-Bold', alignment=TA_RIGHT)

    for index, order in enumerate(orders):
        customer = customers.get(order.get("customer_id", ""))

        # ── 1. HEADER ──
        logo_cell = ''
        logo_src = str(LOGO_PDF_PATH) if LOGO_PDF_PATH.exists() else str(LOGO_PATH)
        if Path(logo_src).exists():
            try:
                tmp = Image(logo_src)
                aspect = tmp.imageHeight / tmp.imageWidth
                logo_h = 28*mm * aspect
                logo_cell = Image(logo_src, width=28*mm, height=logo_h)
            except Exception:
                pass

        co_info = Paragraph(
            f"<b><font size=11>{COMPANY['name']}</font></b><br/>"
            f"<font size=8 color='#15803D'><i>{COMPANY['brand']}</i></font><br/>"
            f"<font size=7 color='#6B7280'>{COMPANY['address']}</font><br/>"
            f"<font size=7 color='#6B7280'>Ph: {COMPANY['mobile']} | {COMPANY['email']}</font>",
            ParagraphStyle(f"CoInfo_{index}", parent=styles['Normal'], fontSize=9, leading=12)
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
            Paragraph(f"<b><font size=13>ORDER PACKING SHEET</font></b>", ParagraphStyle(f"T_{index}", parent=styles['Normal'], alignment=TA_CENTER)),
            Paragraph(f"<b><font size=11>{order['order_number']}</font></b>", ParagraphStyle(f"N_{index}", parent=styles['Normal'], alignment=TA_RIGHT, textColor=GREEN)),
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
            if customer.get('alias'):
                cust_lines.append(f"<font color='#6B7280'><i>{customer['alias']}</i></font>")
            if customer.get('phone_numbers'):
                cust_lines.append(f"<font color='#6B7280'>Ph:</font> {', '.join(customer['phone_numbers'])}")
            sa = order.get("shipping_address")
            if sa and sa.get("address_line"):
                ship_name = sa.get("address_name") or customer.get("name", "")
                cust_lines.append(f"<font color='#6B7280'>Ship To:</font> <b>{ship_name}</b> – {sa['address_line']}, {sa.get('city','')}, {sa.get('state','')} – {sa.get('pincode','')}")
            if customer.get("gst_no"):
                cust_lines.append(f"<font color='#6B7280'>GSTIN:</font> {customer['gst_no']}")
            cust_p = Paragraph("<br/>".join(cust_lines), ParagraphStyle(f"Cust_{index}", parent=styles['Normal'], fontSize=8.5, leading=12))
            cust_tbl = Table([[Paragraph("<b>CUSTOMER DETAILS</b>", ParagraphStyle(f"CustHdr_{index}", parent=styles['Normal'], fontSize=8, textColor=colors.white, fontName='Helvetica-Bold'))],
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

        # ── 5. ITEMS TABLE (includes free samples) ──
        headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Amount', 'Formulation']
        col_widths = [7*mm, pw*0.22, 12*mm, 12*mm, 20*mm, pw - 7*mm - pw*0.22 - 12*mm - 12*mm - 20*mm]
        hdr_style = ParagraphStyle(f"IH_{index}", parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold',
                                   textColor=colors.white, alignment=TA_CENTER)
        table_data = [[Paragraph(h, hdr_style) for h in headers]]
        row_num = 0
        for i, item in enumerate(order.get("items", [])):
            row_num += 1
            desc_text = item.get("product_name", "")
            if item.get("description"):
                desc_text += f"<br/><font color='#6B7280' size=7>{item['description']}</font>"
            formulation_text = item.get("formulation", "") or ""
            row = [
                Paragraph(str(row_num), ParagraphStyle(f"Num_{index}_{i}", parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
                Paragraph(desc_text, itm),
                Paragraph(str(item.get("qty", 0)), ParagraphStyle(f"Qty_{index}_{i}", parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT)),
                Paragraph(item.get("unit", ""), ParagraphStyle(f"Unit_{index}_{i}", parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
                Paragraph(f"{item.get('amount', 0):.2f}", ParagraphStyle(f"Amt_{index}_{i}", parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT, fontName='Helvetica-Bold')),
                Paragraph(formulation_text, form_sty) if formulation_text else Paragraph("", sm),
            ]
            table_data.append(row)

        # Append free samples into the same table
        free_sample_style = ParagraphStyle(f"FS_{index}", parent=styles['Normal'], fontSize=7.5, leading=10, textColor=colors.HexColor('#7C3AED'))
        for fsi, s in enumerate(order.get("free_samples", [])):
            row_num += 1
            fs_name = f"<b>{s.get('item_name', '')}</b>  <font color='#7C3AED' size=7>[Free Sample]</font>"
            if s.get("description"):
                fs_name += f"<br/><font color='#6B7280' size=7>{s['description']}</font>"
            fs_formulation = s.get("formulation", "") or ""
            row = [
                Paragraph(str(row_num), ParagraphStyle(f"NumFS_{index}_{fsi}", parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
                Paragraph(fs_name, itm),
                Paragraph(str(s.get("qty", 1)) if s.get("qty") else "1", ParagraphStyle(f"QtyFS_{index}_{fsi}", parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT)),
                Paragraph(s.get("unit", "") or "", ParagraphStyle(f"UnitFS_{index}_{fsi}", parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
                Paragraph("—", ParagraphStyle(f"FSA_{index}_{fsi}", parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor('#9CA3AF'))),
                Paragraph(fs_formulation, form_sty) if fs_formulation else Paragraph("", sm),
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

        # ── 7. PAYMENT / DISPATCH / REMARKS ──
        extras = []
        # Purpose / Requirement
        if order.get("purpose"):
            extras.append(("normal", f"<b>Purpose / Requirement:</b> {order['purpose']}"))
        if order.get("mode_of_payment"):
            mop = f"<b>Mode of Payment:</b> {order['mode_of_payment']}"
            if order.get("payment_mode_details"):
                mop += f" ({order['payment_mode_details']})"
            extras.append(("normal", mop))
        if order.get("extra_shipping_details"):
            extras.append(("normal", f"<b>Extra Shipping Details:</b> {order['extra_shipping_details']}"))
        if order.get("shipping_method"):
            dispatch_parts = [f"<b>Dispatch:</b> {order['shipping_method'].replace('_',' ').title()}"]
            if order.get("courier_name"):    dispatch_parts.append(f"Courier: {order['courier_name']}")
            if order.get("transporter_name"): dispatch_parts.append(f"Transporter: {order['transporter_name']}")
            extras.append(("normal", "  |  ".join(dispatch_parts)))
        if order.get("remark"):
            extras.append(("remark", order['remark']))

        remark_sty = ParagraphStyle(f"Rmk_{index}", parent=styles['Normal'], fontSize=11, leading=15,
                                    fontName='Helvetica-Bold', textColor=colors.HexColor('#B91C1C'),
                                    backColor=colors.HexColor('#FEF2F2'),
                                    borderPadding=6, spaceBefore=2, spaceAfter=2)

        if extras:
            elements.append(Spacer(1, 4*mm))
            elements.append(sep())
            elements.append(Spacer(1, 3*mm))
            for kind, line in extras:
                if kind == "remark":
                    elements.append(Paragraph(f"REMARKS / SPECIAL INSTRUCTIONS:", ParagraphStyle(f"RmkH_{index}", parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#991B1B'))))
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Paragraph(line, remark_sty))
                else:
                    elements.append(Paragraph(line, ParagraphStyle(f"Ex_{index}", parent=styles['Normal'], fontSize=8, leading=12)))
                elements.append(Spacer(1, 1.5*mm))

        # Add page break if it is not the last order
        if index < len(orders) - 1:
            elements.append(PageBreak())

    doc.build(elements)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=bulk_packing_sheets.pdf"}
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

@api_router.post("/scan-barcode")
async def scan_barcode(file: UploadFile = File(...), user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        from PIL import Image, ImageEnhance
        content = await file.read()
        img = Image.open(io.BytesIO(content))

        # Try original image first
        barcodes = pyzbar_decode(img)

        # If not found, try grayscale with enhanced contrast
        if not barcodes:
            gray = img.convert("L")
            enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
            barcodes = pyzbar_decode(enhanced)

        # If still not found, try sharpened version
        if not barcodes:
            sharp = ImageEnhance.Sharpness(gray).enhance(2.0)
            barcodes = pyzbar_decode(sharp)

        if barcodes:
            code = barcodes[0].data.decode("utf-8")
            return {"found": True, "code": code, "type": barcodes[0].type}
        return {"found": False, "code": "", "type": ""}
    except Exception as e:
        logging.error(f"Barcode scan error: {e}")
        return {"found": False, "code": "", "type": "", "error": str(e)}


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

def _calc_product_sales(order, exclude_gst: bool, exclude_shipping: bool) -> float:
    """Calculate product sales amount based on exclusion flags.
    
    exclude_shipping also excludes additional_charges (base + GST).
    total_gst in DB = items_gst + shipping_gst + additional_charges_gst.
    """
    subtotal = order.get("subtotal", 0)
    if exclude_gst and exclude_shipping:
        return subtotal
    shipping_charge = order.get("shipping_charge", 0)
    shipping_gst = order.get("shipping_gst", 0)
    additional_base = sum(c.get("amount", 0) for c in order.get("additional_charges", []))
    additional_gst = sum(c.get("gst_amount", 0) for c in order.get("additional_charges", []))
    total_gst_stored = order.get("total_gst", 0)
    items_gst = total_gst_stored - shipping_gst - additional_gst
    if exclude_gst:
        # All base amounts, no GST at all
        return subtotal + shipping_charge + additional_base
    if exclude_shipping:
        # Items base + items GST only (no shipping, no additional charges)
        return subtotal + items_gst
    return order.get("grand_total", 0)

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
        product_only_amount += _calc_product_sales(order, exclude_gst, exclude_shipping)

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
        product_sales += _calc_product_sales(o, exclude_gst, exclude_shipping)
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
        product_sales += _calc_product_sales(order, exclude_gst, exclude_shipping)
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
    form_sty = ParagraphStyle('Form', parent=styles['Normal'], fontSize=9.5, leading=12,
                              textColor=AMBER, backColor=LAMBER)
    tot_sty  = ParagraphStyle('Tot',  parent=styles['Normal'], fontSize=9, leading=12, alignment=TA_RIGHT)
    totb_sty = ParagraphStyle('TotB', parent=styles['Normal'], fontSize=10, leading=13,
                              fontName='Helvetica-Bold', alignment=TA_RIGHT)

    # ── 1. HEADER ──
    logo_cell = ''
    logo_src = str(LOGO_PDF_PATH) if LOGO_PDF_PATH.exists() else str(LOGO_PATH)
    if Path(logo_src).exists():
        try:
            tmp = Image(logo_src)
            aspect = tmp.imageHeight / tmp.imageWidth
            logo_h = 28*mm * aspect
            logo_cell = Image(logo_src, width=28*mm, height=logo_h)
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
        if customer.get('alias'):
            cust_lines.append(f"<font color='#6B7280'><i>{customer['alias']}</i></font>")
        if customer.get('phone_numbers'):
            cust_lines.append(f"<font color='#6B7280'>Ph:</font> {', '.join(customer['phone_numbers'])}")
        sa = order.get("shipping_address")
        if sa and sa.get("address_line"):
            ship_name = sa.get("address_name") or customer.get("name", "")
            cust_lines.append(f"<font color='#6B7280'>Ship To:</font> <b>{ship_name}</b> – {sa['address_line']}, {sa.get('city','')}, {sa.get('state','')} – {sa.get('pincode','')}")
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

    # ── 5. ITEMS TABLE (includes free samples) ──
    headers = ['#', 'Item / Description', 'Qty', 'Unit', 'Amount', 'Formulation']
    col_widths = [7*mm, pw*0.22, 12*mm, 12*mm, 20*mm, pw - 7*mm - pw*0.22 - 12*mm - 12*mm - 20*mm]
    hdr_style = ParagraphStyle('IH', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold',
                               textColor=colors.white, alignment=TA_CENTER)
    table_data = [[Paragraph(h, hdr_style) for h in headers]]
    row_num = 0
    for i, item in enumerate(order.get("items", [])):
        row_num += 1
        desc_text = item.get("product_name", "")
        if item.get("description"):
            desc_text += f"<br/><font color='#6B7280' size=7>{item['description']}</font>"
        formulation_text = item.get("formulation", "") or ""
        row = [
            Paragraph(str(row_num), ParagraphStyle('Num', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
            Paragraph(desc_text, itm),
            Paragraph(str(item.get("qty", 0)), ParagraphStyle('Qty', parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT)),
            Paragraph(item.get("unit", ""), ParagraphStyle('Unit', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
            Paragraph(f"{item.get('amount', 0):.2f}", ParagraphStyle('Amt', parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT, fontName='Helvetica-Bold')),
            Paragraph(formulation_text, form_sty) if formulation_text else Paragraph("", sm),
        ]
        table_data.append(row)

    # Append free samples into the same table
    free_sample_style = ParagraphStyle('FS', parent=styles['Normal'], fontSize=7.5, leading=10, textColor=colors.HexColor('#7C3AED'))
    for s in order.get("free_samples", []):
        row_num += 1
        fs_name = f"<b>{s.get('item_name', '')}</b>  <font color='#7C3AED' size=7>[Free Sample]</font>"
        if s.get("description"):
            fs_name += f"<br/><font color='#6B7280' size=7>{s['description']}</font>"
        fs_formulation = s.get("formulation", "") or ""
        row = [
            Paragraph(str(row_num), ParagraphStyle('Num', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
            Paragraph(fs_name, itm),
            Paragraph(str(s.get("qty", 1)) if s.get("qty") else "1", ParagraphStyle('Qty', parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT)),
            Paragraph(s.get("unit", "") or "", ParagraphStyle('Unit', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)),
            Paragraph("—", ParagraphStyle('FSA', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor('#9CA3AF'))),
            Paragraph(fs_formulation, form_sty) if fs_formulation else Paragraph("", sm),
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

    # ── 7. PAYMENT / DISPATCH / REMARKS ──
    extras = []
    # Purpose / Requirement
    if order.get("purpose"):
        extras.append(("normal", f"<b>Purpose / Requirement:</b> {order['purpose']}"))
    if order.get("mode_of_payment"):
        mop = f"<b>Mode of Payment:</b> {order['mode_of_payment']}"
        if order.get("payment_mode_details"):
            mop += f" ({order['payment_mode_details']})"
        extras.append(("normal", mop))
    if order.get("extra_shipping_details"):
        extras.append(("normal", f"<b>Extra Shipping Details:</b> {order['extra_shipping_details']}"))
    if order.get("shipping_method"):
        dispatch_parts = [f"<b>Dispatch:</b> {order['shipping_method'].replace('_',' ').title()}"]
        if order.get("courier_name"):    dispatch_parts.append(f"Courier: {order['courier_name']}")
        if order.get("transporter_name"): dispatch_parts.append(f"Transporter: {order['transporter_name']}")
        extras.append(("normal", "  |  ".join(dispatch_parts)))
    if order.get("remark"):
        extras.append(("remark", order['remark']))

    remark_sty = ParagraphStyle('Rmk', parent=styles['Normal'], fontSize=11, leading=15,
                                fontName='Helvetica-Bold', textColor=colors.HexColor('#B91C1C'),
                                backColor=colors.HexColor('#FEF2F2'),
                                borderPadding=6, spaceBefore=2, spaceAfter=2)

    if extras:
        elements.append(Spacer(1, 4*mm))
        elements.append(sep())
        elements.append(Spacer(1, 3*mm))
        for kind, line in extras:
            if kind == "remark":
                elements.append(Paragraph(f"REMARKS / SPECIAL INSTRUCTIONS:", ParagraphStyle('RmkH', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#991B1B'))))
                elements.append(Spacer(1, 1.5*mm))
                elements.append(Paragraph(line, remark_sty))
            else:
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

    # Process additional charges for PI (carrier risk, if applicable, is appended here)
    additional_charges, total_additional, total_additional_gst = build_additional_charges(
        req.additional_charges,
        req.gst_applicable,
        req.carrier_risk_applicable,
        subtotal + total_gst + req.shipping_charge + shipping_gst,
    )

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
        "carrier_risk_applicable": req.carrier_risk_applicable,
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
        "terms_and_conditions": req.terms_and_conditions,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.proforma_invoices.insert_one(pi_doc)
    created = await db.proforma_invoices.find_one({"id": pi_doc["id"]}, {"_id": 0})
    return created

@api_router.get("/proforma-invoices")
async def list_pis(search: Optional[str] = None, page: int = 1, page_size: int = 50, user=Depends(get_current_user)):
    query = {}
    if user["role"] == "telecaller":
        query["created_by"] = user["id"]
    if search:
        query["$or"] = [
            {"pi_number": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
        ]
    # Lean projection
    list_projection = {
        "_id": 0, "items": 0, "free_samples": 0,
        "billing_address": 0, "shipping_address": 0,
    }
    total = await db.proforma_invoices.count_documents(query)
    skip = (max(1, page) - 1) * page_size
    pis = await db.proforma_invoices.find(query, list_projection).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    # Enrich with customer details for search
    cust_ids = list(set(p.get("customer_id", "") for p in pis if p.get("customer_id")))
    custs = {}
    if cust_ids:
        async for c in db.customers.find({"id": {"$in": cust_ids}}, {"_id": 0, "id": 1, "phone_numbers": 1, "gst_no": 1, "alias": 1}):
            custs[c["id"]] = c
    for pi in pis:
        c = custs.get(pi.get("customer_id"), {})
        pi["customer_phone"] = c.get("phone_numbers", [])
        pi["customer_gst"] = c.get("gst_no", "")
        pi["customer_alias"] = c.get("alias", "")
    return {"pis": pis, "total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}

@api_router.get("/proforma-invoices/{pi_id}")
async def get_pi(pi_id: str, user=Depends(get_current_user)):
    pi = await db.proforma_invoices.find_one({"id": pi_id}, {"_id": 0})
    if not pi:
        raise HTTPException(status_code=404, detail="PI not found")
    # Enrich with full customer data
    if pi.get("customer_id"):
        cust = await db.customers.find_one({"id": pi["customer_id"]}, {"_id": 0, "alias": 1, "name": 1, "phone_numbers": 1, "gst_no": 1, "email": 1})
        if cust:
            pi["customer_alias"] = cust.get("alias", "")
            pi["customer_name"] = cust.get("name", pi.get("customer_name", ""))
            pi["customer_phone"] = cust.get("phone_numbers", [])
            pi["customer_gst_no"] = cust.get("gst_no", "")
            pi["customer_email"] = cust.get("email", "")
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

    # Process additional charges for PI update (carrier risk, if applicable, is appended here)
    additional_charges, total_additional, total_additional_gst = build_additional_charges(
        req.additional_charges,
        req.gst_applicable,
        req.carrier_risk_applicable,
        subtotal + total_gst + req.shipping_charge + shipping_gst,
    )

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
        "carrier_risk_applicable": req.carrier_risk_applicable,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst + total_additional_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "billing_address_id": req.billing_address_id,
        "shipping_address_id": req.shipping_address_id,
        "billing_address": billing_addr,
        "shipping_address": shipping_addr,
        "free_samples": [s.model_dump() for s in req.free_samples],
        "terms_and_conditions": req.terms_and_conditions,
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
    # Fetch live customer name
    cust = await db.customers.find_one({"id": order.get("customer_id", "")}, {"_id": 0, "name": 1})
    return {
        "customer_id": order.get("customer_id", ""),
        "customer_name": cust["name"] if cust else order.get("customer_name", ""),
        "purpose": order.get("purpose", ""),
        "items": order.get("items", []),
        "gst_applicable": order.get("gst_applicable", False),
        "shipping_method": order.get("shipping_method", ""),
        "courier_name": order.get("courier_name", ""),
        "transporter_name": order.get("transporter_name", ""),
        "shipping_charge": order.get("shipping_charge", 0),
        "additional_charges": order.get("additional_charges", []),
        "carrier_risk_applicable": order.get("carrier_risk_applicable", False),
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
    # Fetch live customer name
    cust = await db.customers.find_one({"id": pi.get("customer_id", "")}, {"_id": 0, "name": 1})
    return {
        "customer_id": pi.get("customer_id", ""),
        "customer_name": cust["name"] if cust else pi.get("customer_name", ""),
        "items": pi.get("items", []),
        "gst_applicable": pi.get("gst_applicable", False),
        "show_rate": pi.get("show_rate", True),
        "shipping_charge": pi.get("shipping_charge", 0),
        "additional_charges": pi.get("additional_charges", []),
        "carrier_risk_applicable": pi.get("carrier_risk_applicable", False),
        "remark": pi.get("remark", ""),
        "free_samples": pi.get("free_samples", []),
        "billing_address_id": pi.get("billing_address_id", ""),
        "shipping_address_id": pi.get("shipping_address_id", ""),
        "billing_address": pi.get("billing_address"),
        "shipping_address": pi.get("shipping_address"),
    }


class MakePIRequest(BaseModel):
    gst_applicable: bool
    show_rate: bool
    pi_date: str

@api_router.post("/orders/{order_id}/make-pi")
async def make_pi_from_order(order_id: str, req: MakePIRequest, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    counter = await db.counters.find_one_and_update(
        {"_id": "pi_number"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    pi_number = f"PI-{counter['seq']:04d}"
    
    # Process items and strip formulations
    items = []
    subtotal = 0
    total_gst = 0
    for item in order.get("items", []):
        d = dict(item)
        d["formulation"] = ""
        # Recalculate GST based on the new gst_applicable
        if req.gst_applicable and d.get("gst_rate", 0) > 0:
            d["gst_amount"] = round(d["amount"] * d.get("gst_rate", 0) / 100, 2)
        else:
            d["gst_amount"] = 0
        d["total"] = round(d["amount"] + d["gst_amount"], 2)
        subtotal += d["amount"]
        total_gst += d["gst_amount"]
        items.append(d)
        
    shipping_charge = order.get("shipping_charge", 0)
    shipping_gst = round(shipping_charge * 0.18, 2) if req.gst_applicable and shipping_charge > 0 else 0

    # Carrier risk is re-derived so it tracks the PI's own gst_applicable choice
    carrier_risk_applicable = order.get(
        "carrier_risk_applicable",
        any(str(c.get("name", "")).strip().lower() == CARRIER_RISK_LABEL.lower()
            for c in order.get("additional_charges", [])),
    )
    additional_charges, total_additional, total_additional_gst = build_additional_charges(
        order.get("additional_charges", []),
        req.gst_applicable,
        carrier_risk_applicable,
        subtotal + total_gst + shipping_charge + shipping_gst,
    )

    grand_total = math.ceil(subtotal + total_gst + shipping_charge + shipping_gst + total_additional + total_additional_gst)

    # Process free samples and strip formulations
    free_samples = []
    for s in order.get("free_samples", []):
        fs = dict(s)
        fs["formulation"] = ""
        free_samples.append(fs)

    # Parse user-defined PI date
    try:
        custom_date = datetime.strptime(req.pi_date, "%Y-%m-%d")
        now = datetime.now(timezone.utc)
        created_at_dt = custom_date.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond, tzinfo=timezone.utc)
        created_at_str = created_at_dt.isoformat()
    except Exception:
        created_at_str = datetime.now(timezone.utc).isoformat()

    terms_and_conditions = "\n".join(DEFAULT_PI_TERMS)

    pi_doc = {
        "id": str(uuid.uuid4()),
        "pi_number": pi_number,
        "customer_id": order.get("customer_id", ""),
        "customer_name": order.get("customer_name", ""),
        "items": items,
        "gst_applicable": req.gst_applicable,
        "show_rate": req.show_rate,
        "shipping_charge": shipping_charge,
        "shipping_gst": shipping_gst,
        "additional_charges": additional_charges,
        "carrier_risk_applicable": carrier_risk_applicable,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst + total_additional_gst, 2),
        "grand_total": grand_total,
        "remark": order.get("remark", ""),
        "status": "draft",
        "converted_order_id": order.get("id", ""),
        "billing_address_id": order.get("billing_address_id", ""),
        "shipping_address_id": order.get("shipping_address_id", ""),
        "billing_address": order.get("billing_address"),
        "shipping_address": order.get("shipping_address"),
        "free_samples": free_samples,
        "terms_and_conditions": terms_and_conditions,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": created_at_str,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.proforma_invoices.insert_one(pi_doc)
    created = await db.proforma_invoices.find_one({"id": pi_doc["id"]}, {"_id": 0})
    return created


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
    customer = await db.customers.find_one({"id": pi["customer_id"]}, {"_id": 0})
    order_doc = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "customer_id": pi["customer_id"],
        "customer_name": customer["name"] if customer else pi["customer_name"],
        "purpose": body.get("purpose", ""),
        "items": pi["items"],
        "gst_applicable": pi["gst_applicable"],
        "shipping_method": body.get("shipping_method", ""),
        "courier_name": body.get("courier_name", ""),
        "transporter_name": body.get("transporter_name", ""),
        "shipping_charge": pi["shipping_charge"],
        "shipping_gst": pi["shipping_gst"],
        "additional_charges": pi.get("additional_charges", []),
        "carrier_risk_applicable": pi.get("carrier_risk_applicable", False),
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
                            topMargin=3*mm, bottomMargin=3*mm)
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
        if LOGO_PDF_PATH.exists() or LOGO_PATH.exists():
            logo_src = str(LOGO_PDF_PATH) if LOGO_PDF_PATH.exists() else str(LOGO_PATH)
            try:
                tmp = Image(logo_src)
                aspect = tmp.imageHeight / tmp.imageWidth
                logo_cell = Image(logo_src, width=30*mm, height=30*mm * aspect)
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
    # ── F. BANK / PAYMENT DETAILS + QR CODE ──────────────────────
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

    # ─────────────────────────────────────────────────────────────
    # ── G. TERMS & CONDITIONS (smaller font, after payment) ──────
    # ─────────────────────────────────────────────────────────────
    terms_text = pi.get("terms_and_conditions", "")
    if terms_text:
        terms_list = [t.strip() for t in terms_text.strip().split("\n") if t.strip()]
    else:
        terms_list = DEFAULT_PI_TERMS

    elements.append(Spacer(1, 5*mm))
    tc_header = Table(
        [[Paragraph("<b>TERMS & CONDITIONS</b>",
                     sty('TCH', fontSize=7, fontName='Helvetica-Bold', textColor=colors.white))]],
        colWidths=[pw]
    )
    tc_header.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), GREEN if is_gst else DGRAY),
        ('TOPPADDING', (0,0),(-1,-1), 3), ('BOTTOMPADDING', (0,0),(-1,-1), 3),
        ('LEFTPADDING', (0,0),(-1,-1), 8), ('RIGHTPADDING', (0,0),(-1,-1), 8),
    ]))
    elements.append(tc_header)

    tc_lines = []
    for idx, term in enumerate(terms_list, 1):
        tc_lines.append(f"{idx}. {term}")
    tc_body = Paragraph(
        "<br/>".join(tc_lines),
        sty('TCBody', fontSize=6.5, leading=9, textColor=DGRAY)
    )
    tc_wrap = Table([[tc_body]], colWidths=[pw])
    tc_wrap.setStyle(TableStyle([
        ('VALIGN', (0,0),(-1,-1), 'TOP'),
        ('TOPPADDING', (0,0),(-1,-1), 4),
        ('BOTTOMPADDING', (0,0),(-1,-1), 4),
        ('LEFTPADDING', (0,0),(-1,-1), 8),
        ('RIGHTPADDING', (0,0),(-1,-1), 8),
        ('BOX', (0,0),(-1,-1), 0.5, SGRAY),
    ]))
    elements.append(tc_wrap)

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

# ─── DTDC Serviceability & Rate Calculator ───────────────────────────────

# Load DTDC pincodes into memory at startup
import openpyxl
_dtdc_pincodes = {}
try:
    _wb = openpyxl.load_workbook(os.path.join(os.path.dirname(__file__), "dtdc_pincodes.xlsx"), read_only=True)
    _ws = _wb.active
    for row in _ws.iter_rows(min_row=2, values_only=True):
        pincode = str(row[0]).strip() if row[0] else ""
        if pincode:
            _dtdc_pincodes[pincode] = {
                "pincode": pincode,
                "city": str(row[1]).strip() if row[1] else "",
                "state": str(row[2]).strip() if row[2] else "",
                "category": str(row[3]).strip() if row[3] else "",
            }
    _wb.close()
    logging.info(f"DTDC: Loaded {len(_dtdc_pincodes)} pincodes")
except Exception as e:
    logging.error(f"DTDC pincode load error: {e}")

GROUND_EXPRESS_RATES = {
    "Within City": {"base": 81, "per_kg": 21},
    "Within State": {"base": 97, "per_kg": 25},
    "Within Zone": {"base": 116, "per_kg": 32},
    "Metros": {"base": 147, "per_kg": 38},
    "Rest of India": {"base": 159, "per_kg": 43},
    "Special destination": {"base": 224, "per_kg": 60},
}

STANDARD_RATES = {
    "Within City": {"base": 25, "per_500g": 17},
    "Within State": {"base": 36, "per_500g": 21},
    "Within Zone": {"base": 38, "per_500g": 30},
    "Metros": {"base": 66, "per_500g": 59},
    "Rest of India": {"base": 72, "per_500g": 60},
    "Special destination": {"base": 102, "per_500g": 93},
}

import math

def calc_ground_express(category: str, weight_kg: float) -> int:
    rate = GROUND_EXPRESS_RATES.get(category)
    if not rate:
        return 0
    if weight_kg <= 3:
        return rate["base"]
    extra_kg = math.ceil(weight_kg - 3)
    return rate["base"] + extra_kg * rate["per_kg"]

def calc_standard(category: str, weight_kg: float) -> int:
    rate = STANDARD_RATES.get(category)
    if not rate:
        return 0
    if weight_kg <= 0.5:
        return rate["base"]
    extra_slabs = math.ceil((weight_kg - 0.5) / 0.5)
    return rate["base"] + extra_slabs * rate["per_500g"]

def ceil_to_10(value: int) -> int:
    return math.ceil(value / 10) * 10

def dtdc_quote_for(pincode: str, total_weight: float) -> Optional[dict]:
    """Cheaper of Ground Express / Standard for a pincode, and the series that implies.

    Shared by the /dtdc/calculate endpoint and the API booking flow so both route
    to exactly the same account.
    """
    pincode = str(pincode or "").strip()
    if pincode not in _dtdc_pincodes:
        return None
    info = _dtdc_pincodes[pincode]
    category = info["category"]
    ground_cost = calc_ground_express(category, total_weight)
    standard_cost = calc_standard(category, total_weight)
    if ground_cost <= standard_cost:
        final_cost, series, selected_method = ceil_to_10(ground_cost), "D-Series", "Ground Express"
    else:
        final_cost, series, selected_method = ceil_to_10(standard_cost), "M-Series", "Standard"
    return {
        "serviceable": True,
        "pincode": pincode,
        "city": info["city"],
        "state": info["state"],
        "category": category,
        "total_weight_kg": round(total_weight, 3),
        "ground_express_cost": ground_cost,
        "standard_cost": standard_cost,
        "selected_method": selected_method,
        "series": series,
        "final_charge": final_cost,
    }


@api_router.post("/dtdc/calculate")
async def dtdc_calculate(body: dict):
    pincode = str(body.get("pincode", "")).strip()
    kg = float(body.get("kg", 0))
    grams = float(body.get("grams", 0))
    total_weight = (kg * 1000 + grams) / 1000
    result = dtdc_quote_for(pincode, total_weight)
    if not result:
        return {"serviceable": False, "message": "This pincode is not serviceable by DTDC."}
    return result

@api_router.post("/dtdc/carrier-risk")
async def dtdc_carrier_risk(body: dict):
    """Carrier risk on a given invoice value. See calc_carrier_risk for the arithmetic."""
    try:
        invoice_value = float(body.get("invoice_value", 0) or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invoice_value must be a number")
    gst_applicable = body.get("gst_applicable", True)
    result = calc_carrier_risk(invoice_value, CARRIER_RISK_GST_PERCENT if gst_applicable else 0)
    total = round(result["amount"] + result["gst_amount"], 2)
    return {
        "invoice_value": round(max(0.0, invoice_value), 2),
        "carrier_risk": result["amount"],
        "gst_percent": result["gst_percent"],
        "gst_amount": result["gst_amount"],
        "total": total,
        "declared_value": round(max(0.0, invoice_value) + total, 2),
        "minimum_applied": result["amount"] <= CARRIER_RISK_MIN_AMOUNT,
        "rate_percent": CARRIER_RISK_RATE * 100,
        "min_amount": CARRIER_RISK_MIN_AMOUNT,
    }

@api_router.get("/dtdc/check/{pincode}")
async def dtdc_check_pincode(pincode: str):
    pincode = pincode.strip()
    if pincode in _dtdc_pincodes:
        return {"serviceable": True, **_dtdc_pincodes[pincode]}
    return {"serviceable": False, "message": "This pincode is not serviceable by DTDC."}


# ─── DTDC Consignment Booking API (Shipsy-hosted) ────────────────────────
# Replaces the manual Excel softdata upload. Three accounts with different
# booking conditions, mirroring the rules the Excel export used:
#   D-Series (Ground Express cheaper)  -> RL1386, GROUND EXPRESS
#   M-Series (Standard cheaper)        -> RL1423, STD EXP-A
#   Carrier risk ticked                -> RL1387, same service type, risk ON
import httpx

# NOTE: the API playground shows "API Server https://app.shipsy.in", but that
# host rejects DTDC customer keys (401). The live DTDC tenant is dtdcapi.shipsy.io.
DTDC_BASE_URL = os.environ.get("DTDC_BASE_URL", "https://dtdcapi.shipsy.io").rstrip("/")
DTDC_PATH_BOOK = "/api/customer/integration/consignment/upload/softdata/v2"
DTDC_PATH_TRACK = "/api/customer/integration/consignment/track"
DTDC_PATH_LABEL = "/api/customer/integration/consignment/shippinglabel/stream"
DTDC_PATH_CANCEL = "/api/customer/integration/consignment/cancel"

# Service type strings. DTDC's own Excel template used these names; they are
# env-overridable because the API may expect different service codes.
DTDC_SERVICE_GROUND = os.environ.get("DTDC_SERVICE_GROUND", "GROUND EXPRESS")
DTDC_SERVICE_STD = os.environ.get("DTDC_SERVICE_STD", "STD EXP-A")

# Pickup hub. RL1386/RL1423 auto-allocate to R11 (NAGPUR PANDE LAYOUT BRANCH);
# RL1387 has no auto-allocation mapping, so the hub must be sent explicitly.
DTDC_DEFAULT_HUB = os.environ.get("DTDC_HUB_CODE", "R11")

DTDC_ACCOUNTS = {
    "RL1386": {
        "api_key": os.environ.get("DTDC_API_KEY_RL1386", ""),
        "customer_code": os.environ.get("DTDC_CUSTOMER_CODE_RL1386", "RL1386"),
        "hub_code": os.environ.get("DTDC_HUB_RL1386", ""),
    },
    "RL1387": {
        "api_key": os.environ.get("DTDC_API_KEY_RL1387", ""),
        "customer_code": os.environ.get("DTDC_CUSTOMER_CODE_RL1387", "RL1387"),
        "hub_code": os.environ.get("DTDC_HUB_RL1387", DTDC_DEFAULT_HUB),
    },
    "RL1423": {
        "api_key": os.environ.get("DTDC_API_KEY_RL1423", ""),
        "customer_code": os.environ.get("DTDC_CUSTOMER_CODE_RL1423", "RL1423"),
        "hub_code": os.environ.get("DTDC_HUB_RL1423", ""),
    },
}


def _dtdc_configured() -> bool:
    return any(a["api_key"] for a in DTDC_ACCOUNTS.values())


def _dtdc_route(order: dict, series: str) -> tuple:
    """(account_key, service_type_id, risk_surcharge) for an order."""
    service = DTDC_SERVICE_GROUND if series == "D-Series" else DTDC_SERVICE_STD
    if order.get("carrier_risk_applicable"):
        # Carrier-risk consignments always book on RL1387 with the surcharge on;
        # the service type still follows the detected series.
        return "RL1387", service, True
    return ("RL1386" if series == "D-Series" else "RL1423"), service, False


def _dtdc_party_origin() -> dict:
    return {
        "name": COMPANY["name"],
        "phone": _to_local_phone(COMPANY["mobile"]),
        "address_line_1": "B Wing, Poonam Heights, Pandey Layout, Khamla",
        "address_line_2": "Nagpur",
        "pincode": os.environ.get("DTDC_ORIGIN_PINCODE", "440025"),
        "city": "Nagpur",
        "district": "Nagpur",
        "state": "Maharashtra",
        "country": "India",
    }


def _dtdc_softdata_payload(order, account, service, risk, weight, boxes, phones) -> dict:
    sa = order.get("shipping_address") or {}
    line1, line2 = _address_lines(sa)
    phone = phones[0] if phones else ""
    alt_phone = phones[1] if len(phones) > 1 else ""
    declared = _declared_value(order)
    created = (order.get("created_at") or datetime.now(timezone.utc).isoformat())[:10]
    per_piece = round(weight / max(1, boxes), 3)
    origin = _dtdc_party_origin()
    hub = account.get("hub_code") or ""
    if hub:
        # RL1387 cannot auto-allocate a pickup hub; it needs both of these set.
        origin["address_hub_code"] = hub
    payload = {
        "action_type": "single_pickup",
        "consignment_type": "forward",
        "movement_type": "forward",
        "load_type": "NON-DOCUMENT",
        "description": "Aroma products",
        "customer_code": account["customer_code"],
        # reference_number is DTDC's consignment number and must come from the
        # D/M series that matches the service type — omitting it makes DTDC
        # allocate the correct one. Our order number goes in the customer ref.
        "customer_reference_number": order.get("order_number") or order["id"][:20],
        "service_type_id": service,
        "is_risk_surcharge_applicable": bool(risk),
        "dimension_unit": "cm",
        "length": "5", "width": "5", "height": "5",
        "weight_unit": "kg",
        "weight": str(weight),
        "num_pieces": boxes,
        "declared_value": declared,
        "declared_value_without_tax": declared,
        "invoice_number": order.get("order_number") or "",
        "invoice_date": created,
        "tax_details": [{"sender_gstin": COMPANY["gstin"]}],
        "origin_details": origin,
        "destination_details": {
            "name": sa.get("address_name") or order.get("customer_name") or "Customer",
            "phone": phone,
            "alternate_phone": alt_phone,
            "address_line_1": line1,
            "address_line_2": line2,
            "pincode": sa.get("pincode") or "",
            "city": sa.get("city") or "",
            "district": sa.get("city") or "",
            "state": sa.get("state") or "",
            "country": "India",
        },
        "pieces_detail": [{
            "description": "Aroma products",
            "declared_value": str(round(declared / max(1, boxes), 2)),
            "weight": str(per_piece),
            "length": "5", "width": "5", "height": "5",
            "weight_unit": "kg",
            "dimension_unit": "cm",
        } for _ in range(max(1, boxes))],
    }
    if hub:
        payload["hub_code"] = hub
    return payload


async def _dtdc_prepare(order: dict, force_account: Optional[str] = None) -> dict:
    """Resolve weight, series, account and payload for an order — books nothing."""
    pkg = order.get("packaging") or {}
    raw_weight = str(pkg.get("weight_kg", "")).strip()
    if not raw_weight:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    weight = float(raw_weight)
    if weight <= 0:
        raise HTTPException(status_code=400, detail="Weight must be greater than zero")
    try:
        boxes = max(1, int(float(pkg.get("num_boxes") or 1)))
    except (TypeError, ValueError):
        boxes = 1
    sa = order.get("shipping_address") or {}
    quote = dtdc_quote_for(sa.get("pincode"), weight)
    if not quote:
        raise HTTPException(status_code=400, detail="This pincode is not serviceable by DTDC")
    acct_key, service, risk = _dtdc_route(order, quote["series"])
    if force_account:
        if force_account not in DTDC_ACCOUNTS:
            raise HTTPException(status_code=400, detail=f"Unknown DTDC account {force_account}")
        acct_key = force_account
        risk = force_account == "RL1387"
    account = DTDC_ACCOUNTS[acct_key]
    if not account["api_key"]:
        raise HTTPException(status_code=400, detail=f"DTDC account {acct_key} has no API key configured")
    phones = await _order_phones(order)
    if not phones:
        raise HTTPException(status_code=400, detail="Customer has no valid phone number — add one before booking")
    sa_full = order.get("shipping_address") or {}
    missing = [f for f in ("address_line", "city", "state", "pincode") if not str(sa_full.get(f) or "").strip()]
    if missing:
        raise HTTPException(status_code=400, detail=f"Shipping address incomplete — missing: {', '.join(missing)}")
    return {
        "account_key": acct_key, "account": account, "service": service, "risk": risk,
        "quote": quote, "weight": weight, "boxes": boxes,
        "payload": _dtdc_softdata_payload(order, account, service, risk, weight, boxes, phones),
    }


@api_router.get("/dtdc/bookable")
async def dtdc_bookable_orders(user=Depends(get_current_user)):
    """DTDC orders packing has weighed, with the account each would book on."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    orders = await db.orders.find({
        "courier_name": {"$regex": r"^\s*dtdc", "$options": "i"},
        "status": {"$nin": ["cancelled", "dispatched"]},
        "packaging.weight_kg": {"$nin": ["", None]},
    }, {"_id": 0}).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        sa = o.get("shipping_address") or {}
        try:
            weight = float(str(pkg.get("weight_kg", "")).strip() or 0)
        except ValueError:
            continue
        if weight <= 0:
            continue
        quote = dtdc_quote_for(sa.get("pincode"), weight)
        acct_key, service, risk = _dtdc_route(o, quote["series"]) if quote else ("", "", False)
        out.append({
            "id": o["id"], "order_number": o.get("order_number"),
            "customer_name": o.get("customer_name"), "status": o.get("status"),
            "weight_kg": pkg.get("weight_kg"), "num_boxes": pkg.get("num_boxes") or "1",
            "shipping_address": {"city": sa.get("city"), "pincode": sa.get("pincode")},
            "carrier_risk": bool(o.get("carrier_risk_applicable")),
            "serviceable": bool(quote),
            "series": (quote or {}).get("series"),
            "est_charge": (quote or {}).get("final_charge"),
            "account": acct_key, "service_type": service, "risk_surcharge": risk,
            "dtdc_shipment": o.get("dtdc_shipment"),
        })
    return out


class DtdcBookRequest(BaseModel):
    order_id: str
    # Force a specific account instead of the automatic routing (admin testing).
    account: Optional[str] = None
    allow_rebook: Optional[bool] = False


@api_router.post("/dtdc/preview")
async def dtdc_preview(req: DtdcBookRequest, user=Depends(get_current_user)):
    """Exactly what would be booked — account, service, charge. Books nothing."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    p = await _dtdc_prepare(order)
    return {
        "ok": True, "account": p["account_key"], "service_type": p["service"],
        "risk_surcharge": p["risk"], "series": p["quote"]["series"],
        "est_charge": p["quote"]["final_charge"], "city": p["quote"]["city"],
        "weight_kg": p["weight"], "num_boxes": p["boxes"],
        "declared_value": p["payload"]["declared_value"],
    }


@api_router.post("/dtdc/book")
async def dtdc_book(req: DtdcBookRequest, user=Depends(get_current_user)):
    """BOOKS a real DTDC consignment on the routed account."""
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized to book")
    order = await db.orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("dtdc_shipment") or {}).get("reference_number") and not req.allow_rebook:
        raise HTTPException(status_code=400, detail="This order is already booked with DTDC")
    p = await _dtdc_prepare(order, force_account=req.account)
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(f"{DTDC_BASE_URL}{DTDC_PATH_BOOK}",
                         headers={"api-key": p["account"]["api_key"], "content-type": "application/json"},
                         json=p["payload"])
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:500]}
    if r.status_code not in (200, 201) or data.get("success") is False:
        logging.error(f"DTDC booking failed ({p['account_key']}): {r.status_code} {r.text[:400]}")
        raise HTTPException(status_code=400, detail=f"DTDC booking failed: {str(data)[:300]}")

    # DTDC returns the consignment number it allocated, e.g. {"reference_number": "M1001198344"}
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    awb = ""
    for key in ("reference_number", "consignment_number", "cn_number", "awb", "awb_number"):
        val = (payload or {}).get(key)
        if isinstance(val, str) and val.strip():
            awb = val.strip()
            break
    if not awb and isinstance(data.get("data"), list) and data["data"]:
        first = data["data"][0]
        if isinstance(first, dict):
            awb = str(first.get("reference_number") or first.get("consignment_number") or "").strip()
    if not awb:
        logging.error(f"DTDC booked but no consignment number in response: {str(data)[:400]}")
        raise HTTPException(status_code=400, detail="DTDC accepted the booking but returned no consignment number")
    reference = awb
    piece_refs = [str(x.get("reference_number") or "") for x in (payload.get("pieces") or [])
                  if isinstance(x, dict)]

    shipment = {
        "account": p["account_key"],
        "customer_code": p["account"]["customer_code"],
        "service_type": p["service"],
        "risk_surcharge": p["risk"],
        "series": p["quote"]["series"],
        "reference_number": reference,
        "awb": awb,
        "piece_refs": piece_refs,
        "customer_reference": p["payload"]["customer_reference_number"],
        "est_charge": p["quote"]["final_charge"],
        "weight_kg": p["weight"],
        "num_boxes": p["boxes"],
        "declared_value": p["payload"]["declared_value"],
        "recipient_phone": p["payload"]["destination_details"]["phone"],
        "booked_by": user["name"],
        "booked_at": datetime.now(timezone.utc).isoformat(),
        "raw_response": str(data)[:1000],
    }
    await db.orders.update_one({"id": req.order_id}, {"$set": {
        "dtdc_shipment": shipment,
        "courier_name": "DTDC",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    safe = {k: v for k, v in shipment.items() if k != "raw_response"}
    return {"ok": True, "shipment": safe}


@api_router.get("/dtdc/label/{order_id}")
async def dtdc_label(order_id: str, token: str = "", user=None):
    """Stream the DTDC shipping label for a booked consignment."""
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    sh = order.get("dtdc_shipment") or {}
    ref = sh.get("awb") or sh.get("reference_number")
    if not ref:
        raise HTTPException(status_code=404, detail="This order is not booked with DTDC")
    account = DTDC_ACCOUNTS.get(sh.get("account") or "", {})
    if not account.get("api_key"):
        raise HTTPException(status_code=400, detail="DTDC API key not configured for this account")
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_LABEL}",
                        params={"reference_number": ref},
                        headers={"api-key": account["api_key"]})
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"DTDC label failed: {r.text[:300]}")
    media, ext = _sniff_media(r.content, r.headers.get("content-type", ""))
    return StreamingResponse(
        io.BytesIO(r.content), media_type=media,
        headers={"Content-Disposition": f"inline; filename=dtdc-label-{ref}.{ext}"},
    )


def _sniff_media(raw: bytes, header_value: str = "") -> tuple:
    """(media_type, extension). DTDC returns an empty content-type, so trust the
    file signature over the header."""
    if raw[:4] == b"%PDF":
        return "application/pdf", "pdf"
    if raw[:4] == b"\x89PNG":
        return "image/png", "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    header = (header_value or "").split(";")[0].strip()
    if header:
        ext = "pdf" if "pdf" in header else ("png" if "png" in header else "bin")
        return header, ext
    return "application/pdf", "pdf"


async def _dtdc_fetch_label_bytes(shipment: dict):
    """(bytes, content_type) for a booked consignment's label, or (None, '')."""
    ref = shipment.get("awb") or shipment.get("reference_number")
    account = DTDC_ACCOUNTS.get(shipment.get("account") or "", {})
    if not ref or not account.get("api_key"):
        return None, ""
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_LABEL}",
                            params={"reference_number": ref},
                            headers={"api-key": account["api_key"]})
        if r.status_code == 200 and r.content:
            media, _ext = _sniff_media(r.content, r.headers.get("content-type", ""))
            return r.content, media
    except Exception as e:
        logging.error(f"DTDC label fetch failed for {ref}: {e}")
    return None, ""


async def _dtdc_save_label_as_slip(shipment: dict) -> str:
    raw, _media = await _dtdc_fetch_label_bytes(shipment)
    if not raw:
        return ""
    _m, ext = _sniff_media(raw)
    filename = f"{uuid.uuid4()}.{ext}"
    async with aiofiles.open(UPLOAD_DIR / filename, "wb") as f:
        await f.write(raw)
    return f"/api/uploads/{filename}"


async def _dtdc_mark_dispatched(order: dict, when: str, by: str, docket: str = "", slip_url: str = "") -> dict:
    """Shared dispatch write for both the manual button and the pickup poller."""
    shipment = order.get("dtdc_shipment") or {}
    dispatch = order.get("dispatch") or {}
    slips = list(dispatch.get("dispatch_slip_images") or [])
    if slip_url and slip_url not in slips:
        slips.append(slip_url)
    if not slips:
        auto = await _dtdc_save_label_as_slip(shipment)
        if auto:
            slips.append(auto)
    lr = docket or shipment.get("awb") or shipment.get("reference_number") or ""
    dispatch.update({
        "courier_name": "DTDC",
        "transporter_name": "",
        "lr_no": lr,
        "dispatch_slip_images": slips,
        "dispatch_type": "courier",
        "porter_link": "",
        "dispatched_by": by,
        "dispatched_at": when,
    })
    await db.orders.update_one({"id": order["id"]}, {"$set": {
        "dispatch": dispatch,
        "status": "dispatched",
        "courier_name": "DTDC",
        "dtdc_shipment.docket_no": lr,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"lr_no": lr, "slips": slips}


class DtdcDispatchRequest(BaseModel):
    order_id: str
    docket_no: Optional[str] = ""
    slip_image_url: Optional[str] = ""


@api_router.post("/dtdc/dispatch")
async def dtdc_manual_dispatch(req: DtdcDispatchRequest, user=Depends(get_current_user)):
    """Dispatch now, without waiting for DTDC to report pickup."""
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched":
        raise HTTPException(status_code=400, detail="Order is already dispatched")
    shipment = order.get("dtdc_shipment") or {}
    docket = (req.docket_no or "").strip() or shipment.get("awb") or shipment.get("reference_number") or ""
    if not docket:
        raise HTTPException(status_code=400, detail="Docket / consignment number is required")
    res = await _dtdc_mark_dispatched(
        order, datetime.now(timezone.utc).isoformat(), user["name"],
        docket=docket, slip_url=(req.slip_image_url or "").strip(),
    )
    return {"ok": True, **res}


# DTDC pickup detection — statuses that mean the parcel has left us.
DTDC_PICKED_HINTS = ("PICKED", "PICKUP", "IN TRANSIT", "INTRANSIT", "DISPATCH",
                     "SHIPPED", "OUT FOR DELIVERY", "DELIVERED", "BOOKED")


def _dtdc_pickup_time(tracking: dict):
    """Timestamp if DTDC tracking shows the parcel picked up, else None."""
    if not tracking:
        return None
    blob = json.dumps(tracking).upper() if isinstance(tracking, (dict, list)) else str(tracking).upper()
    if not any(h in blob for h in DTDC_PICKED_HINTS):
        return None
    # Try to surface a real event time; fall back to now.
    def walk(node):
        if isinstance(node, dict):
            status = str(node.get("status") or node.get("action") or node.get("activity") or "").upper()
            when = node.get("timestamp") or node.get("date") or node.get("event_time") or node.get("activity_date")
            if status and any(h in status for h in DTDC_PICKED_HINTS) and when:
                return str(when)
            for v in node.values():
                got = walk(v)
                if got:
                    return got
        elif isinstance(node, list):
            for v in node:
                got = walk(v)
                if got:
                    return got
        return None
    return walk(tracking) or datetime.now(timezone.utc).isoformat()


async def _dtdc_sync_all() -> list:
    if not _dtdc_configured():
        return []
    pending = await db.orders.find({
        "dtdc_shipment.reference_number": {"$exists": True, "$ne": ""},
        "status": {"$nin": ["dispatched", "cancelled"]},
    }, {"_id": 0}).to_list(200)
    notes = []
    for o in pending:
        try:
            sh = o.get("dtdc_shipment") or {}
            ref = sh.get("awb") or sh.get("reference_number")
            account = DTDC_ACCOUNTS.get(sh.get("account") or "", {})
            if not ref or not account.get("api_key"):
                continue
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_TRACK}",
                                params={"reference_number": ref},
                                headers={"api-key": account["api_key"]})
            if r.status_code != 200:
                continue
            picked = _dtdc_pickup_time(r.json())
            if not picked:
                continue
            await _dtdc_mark_dispatched(o, picked, "DTDC (auto)")
            notes.append(f"{o.get('order_number')} dispatched (picked up {picked})")
        except Exception as e:
            logging.error(f"DTDC sync failed for {o.get('order_number')}: {e}")
    return notes


@api_router.post("/dtdc/sync-tracking")
async def dtdc_sync_tracking(user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    notes = await _dtdc_sync_all()
    return {"ok": True, "dispatched": notes, "count": len(notes)}


async def _dtdc_sync_loop():
    await asyncio.sleep(45)
    while True:
        try:
            await _dtdc_sync_all()
        except Exception as e:
            logging.error(f"DTDC sync loop error: {e}")
        await asyncio.sleep(AMAZON_SYNC_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_dtdc_sync():
    if _dtdc_configured():
        asyncio.create_task(_dtdc_sync_loop())


@api_router.get("/dtdc/track/{order_id}")
async def dtdc_track(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    sh = order.get("dtdc_shipment") or {}
    ref = sh.get("awb") or sh.get("reference_number")
    if not ref:
        raise HTTPException(status_code=404, detail="This order is not booked with DTDC")
    account = DTDC_ACCOUNTS.get(sh.get("account") or "", {})
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_TRACK}",
                        params={"reference_number": ref},
                        headers={"api-key": account.get("api_key", "")})
    if r.status_code != 200:
        return {"ok": False, "message": f"HTTP {r.status_code}", "detail": r.text[:300]}
    return {"ok": True, "tracking": r.json()}


# ─── Courier Expense Calculation (what we pay DTDC / Anjani) ─────────────
# Separate from the customer-facing DTDC calculator above: these are cost rates.
# DTDC = base rate + fuel surcharge + 18% GST. Nothing is rounded — the paise
# matter when reconciling a monthly invoice.
DTDC_EXPENSE_GROUND = {          # up to 3 kg, then per additional kg
    "Within City":         {"base": 59,  "per_kg": 15},
    "Within State":        {"base": 71,  "per_kg": 18},
    "Within Zone":         {"base": 85,  "per_kg": 23},
    "Metros":              {"base": 108, "per_kg": 28},
    "Rest of India":       {"base": 117, "per_kg": 31},
    "Special destination": {"base": 165, "per_kg": 44},
}
DTDC_EXPENSE_STANDARD = {        # up to 500 g, then per additional 500 g
    "Within City":         {"base": 18, "per_500g": 12},
    "Within State":        {"base": 26, "per_500g": 15},
    "Within Zone":         {"base": 28, "per_500g": 22},
    "Metros":              {"base": 48, "per_500g": 43},
    "Rest of India":       {"base": 53, "per_500g": 44},
    "Special destination": {"base": 75, "per_500g": 68},
}
DTDC_EXPENSE_GST_PERCENT = 18.0
DEFAULT_FUEL_SURCHARGE = 15.0
EXPENSE_START_DATE = os.environ.get("EXPENSE_START_DATE", "2026-08-01")

ANJANI_RATE_MAHARASHTRA = float(os.environ.get("ANJANI_RATE_MH", "40"))
ANJANI_RATE_REST = float(os.environ.get("ANJANI_RATE_REST", "50"))


def dtdc_expense_base(category: str, weight: float, service: str) -> float:
    """DTDC base freight before fuel surcharge and GST."""
    if service == "GROUND EXPRESS":
        rate = DTDC_EXPENSE_GROUND.get(category)
        if not rate:
            return 0.0
        if weight <= 3:
            return float(rate["base"])
        return float(rate["base"] + math.ceil(weight - 3) * rate["per_kg"])
    rate = DTDC_EXPENSE_STANDARD.get(category)
    if not rate:
        return 0.0
    if weight <= 0.5:
        return float(rate["base"])
    return float(rate["base"] + math.ceil((weight - 0.5) / 0.5) * rate["per_500g"])


async def _fuel_surcharge_periods() -> list:
    """Effective-dated fuel surcharge, newest first. DTDC revises this often."""
    rows = await db.fuel_surcharges.find({}, {"_id": 0}).sort("from_date", -1).to_list(200)
    if not rows:
        rows = [{"id": "default", "from_date": EXPENSE_START_DATE,
                 "percent": DEFAULT_FUEL_SURCHARGE, "note": "default"}]
    return rows


def _fuel_percent_on(periods: list, when: str) -> float:
    """Surcharge in force on a given date (periods are newest-first)."""
    day = (when or "")[:10]
    for p in periods:
        if day >= str(p.get("from_date", ""))[:10]:
            return float(p.get("percent", DEFAULT_FUEL_SURCHARGE))
    return float(periods[-1].get("percent", DEFAULT_FUEL_SURCHARGE)) if periods else DEFAULT_FUEL_SURCHARGE


def _expense_date(order: dict) -> str:
    d = (order.get("dispatch") or {}).get("dispatched_at")
    if not d:
        d = (order.get("packaging") or {}).get("packed_at")
    return (d or order.get("created_at") or "")[:10]


def _order_courier(order: dict) -> str:
    name = str(order.get("courier_name") or "").strip().lower()
    if name.startswith("dtdc"):
        return "DTDC"
    if name.startswith("anjani") or "anjani" in name:
        return "Anjani"
    return ""


def compute_order_expense(order: dict, periods: list) -> Optional[dict]:
    """Per-order courier cost. None when it cannot be costed."""
    courier = _order_courier(order)
    if not courier:
        return None
    pkg = order.get("packaging") or {}
    try:
        weight = float(str(pkg.get("weight_kg", "")).strip() or 0)
    except (TypeError, ValueError):
        return None
    if weight <= 0:
        return None
    sa = order.get("shipping_address") or {}
    dispatch = order.get("dispatch") or {}
    when = _expense_date(order)
    row = {
        "order_id": order.get("id"),
        "order_number": order.get("order_number"),
        "customer_name": order.get("customer_name"),
        "date": when,
        "courier": courier,
        # Docket / LR / consignment number on the dispatch slip, for reconciling
        # each line against the courier's invoice.
        "docket_no": (dispatch.get("lr_no")
                      or (order.get("dtdc_shipment") or {}).get("awb")
                      or ""),
        "weight_kg": weight,
        "num_boxes": pkg.get("num_boxes") or "1",
        "city": sa.get("city"),
        "state": sa.get("state"),
        "pincode": sa.get("pincode"),
        "damaged": bool(order.get("damaged")),
        "damaged_note": order.get("damaged_note") or "",
        "damaged_by": order.get("damaged_by") or "",
    }

    if courier == "Anjani":
        in_mh = "maharashtra" in str(sa.get("state") or "").strip().lower()
        base = ANJANI_RATE_MAHARASHTRA if in_mh else ANJANI_RATE_REST
        row.update({"zone": "Maharashtra" if in_mh else "Rest of India",
                    "service": "Anjani", "base": base, "fuel_percent": 0.0,
                    "fuel": 0.0, "base_plus_fuel": base,
                    "gst_percent": 0.0, "gst": 0.0, "total": base})
        return row

    info = _dtdc_pincodes.get(str(sa.get("pincode") or "").strip())
    if not info:
        row.update({"zone": None, "service": None, "base": 0.0, "fuel_percent": 0.0,
                    "fuel": 0.0, "base_plus_fuel": 0.0,
                    "gst_percent": 0.0, "gst": 0.0, "total": 0.0,
                    "error": "Pincode not in the DTDC zone list"})
        return row
    category = info["category"]
    # Use the service actually booked when we have it, else the cheaper option
    # (the same rule the booking flow applies).
    booked = (order.get("dtdc_shipment") or {}).get("service_type")
    if booked in ("GROUND EXPRESS", "STD EXP-A"):
        service = booked
    else:
        g = dtdc_expense_base(category, weight, "GROUND EXPRESS")
        s = dtdc_expense_base(category, weight, "STD EXP-A")
        service = "GROUND EXPRESS" if g <= s else "STD EXP-A"
    base = dtdc_expense_base(category, weight, service)
    fuel_pct = _fuel_percent_on(periods, when)
    fuel = base * fuel_pct / 100.0
    gst = (base + fuel) * DTDC_EXPENSE_GST_PERCENT / 100.0
    row.update({
        "zone": category, "service": service,
        "base": round(base, 2), "fuel_percent": fuel_pct, "fuel": round(fuel, 2),
        # DTDC's invoice reads as (freight + fuel) then GST on that, so carry the
        # subtotal explicitly rather than making the reader add it up.
        "base_plus_fuel": round(base + fuel, 2),
        "gst_percent": DTDC_EXPENSE_GST_PERCENT, "gst": round(gst, 2),
        "total": round(base + fuel + gst, 2),
    })
    return row


class DamagedRequest(BaseModel):
    order_id: str
    damaged: bool = True
    note: Optional[str] = ""


@api_router.put("/orders/{order_id}/damaged")
async def mark_order_damaged(order_id: str, req: DamagedRequest, user=Depends(get_current_user)):
    """Flag a consignment as received damaged, so accounts can raise it with the courier."""
    if user["role"] not in ["admin", "accounts", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    now = datetime.now(timezone.utc).isoformat()
    update = {
        "damaged": bool(req.damaged),
        "damaged_note": (req.note or "").strip() if req.damaged else "",
        "damaged_by": user["name"] if req.damaged else "",
        "damaged_at": now if req.damaged else "",
        "updated_at": now,
    }
    await db.orders.update_one({"id": order_id}, {"$set": update})
    return {"ok": True, **{k: v for k, v in update.items() if k != "updated_at"}}


async def _anjani_track(docket: str) -> Optional[dict]:
    """Shree Anjani public tracking — GET /public/awb/{docket}, no auth needed."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://api-customer.shreeanjani.co.in/public/awb/{docket}")
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                return d.get("data") or {}
    except Exception as e:
        logging.warning(f"Anjani tracking failed for {docket}: {e}")
    return None


@api_router.get("/courier-status/{order_id}")
async def courier_status(order_id: str, user=Depends(get_current_user)):
    """Live status from the courier for a dispatched order (DTDC or Anjani)."""
    if user["role"] == "telecaller":
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    courier = _order_courier(order)
    docket = (order.get("dispatch") or {}).get("lr_no") or \
             (order.get("dtdc_shipment") or {}).get("awb") or ""
    if not docket:
        return {"ok": False, "message": "No docket number on this order"}

    if courier == "Anjani":
        data = await _anjani_track(docket)
        if not data:
            return {"ok": False, "courier": courier, "docket": docket,
                    "message": "Anjani returned no data for this docket"}
        b = data.get("booking") or {}
        return {"ok": True, "courier": courier, "docket": docket,
                "status": b.get("status_name") or "-",
                "booking_date": b.get("booking_date"),
                "from": b.get("from_center_name"), "to": b.get("to_center_name"),
                "raw": data}

    if courier == "DTDC":
        sh = order.get("dtdc_shipment") or {}
        account = DTDC_ACCOUNTS.get(sh.get("account") or "", {})
        key = account.get("api_key") or next(
            (a["api_key"] for a in DTDC_ACCOUNTS.values() if a["api_key"]), "")
        if not key:
            return {"ok": False, "message": "No DTDC API key configured"}
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_TRACK}",
                            params={"reference_number": docket},
                            headers={"api-key": key})
        if r.status_code != 200:
            return {"ok": False, "courier": courier, "docket": docket,
                    "message": f"DTDC returned HTTP {r.status_code}", "detail": r.text[:200]}
        d = r.json()
        events = d.get("events") or []
        return {"ok": True, "courier": courier, "docket": docket,
                "status": d.get("status") or "-",
                "hub": d.get("hub_code"),
                "last_event": (events[0] if events else None),
                "events": events[:12], "raw_status": d.get("status")}

    return {"ok": False, "message": "Order is not on DTDC or Anjani"}


@api_router.get("/courier-expenses/fuel-surcharges")
async def list_fuel_surcharges(user=Depends(get_current_user)):
    if user["role"] == "telecaller":
        raise HTTPException(status_code=403, detail="Not authorized")
    return await _fuel_surcharge_periods()


@api_router.post("/courier-expenses/fuel-surcharges")
async def add_fuel_surcharge(body: dict, admin=Depends(require_admin)):
    from_date = str(body.get("from_date") or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", from_date):
        raise HTTPException(status_code=400, detail="from_date must be YYYY-MM-DD")
    try:
        percent = float(body.get("percent"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="percent must be a number")
    if percent < 0 or percent > 100:
        raise HTTPException(status_code=400, detail="percent must be between 0 and 100")
    doc = {"id": str(uuid.uuid4()), "from_date": from_date, "percent": percent,
           "note": str(body.get("note") or ""), "created_at": datetime.now(timezone.utc).isoformat(),
           "created_by": admin["name"]}
    await db.fuel_surcharges.update_one({"from_date": from_date}, {"$set": doc}, upsert=True)
    return doc


@api_router.delete("/courier-expenses/fuel-surcharges/{surcharge_id}")
async def delete_fuel_surcharge(surcharge_id: str, admin=Depends(require_admin)):
    res = await db.fuel_surcharges.delete_one({"id": surcharge_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


@api_router.get("/courier-expenses")
async def courier_expenses(date_from: str = "", date_to: str = "",
                           courier: str = "all", user=Depends(get_current_user)):
    """Courier cost per shipment for a period, with per-courier totals."""
    if user["role"] == "telecaller":
        raise HTTPException(status_code=403, detail="Not authorized")
    start = (date_from or EXPENSE_START_DATE)[:10]
    end = (date_to or datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d"))[:10]
    periods = await _fuel_surcharge_periods()

    orders = await db.orders.find({
        "status": {"$ne": "cancelled"},
        "courier_name": {"$regex": r"^\s*(dtdc|anjani)", "$options": "i"},
        "packaging.weight_kg": {"$nin": ["", None]},
    }, {"_id": 0}).to_list(5000)

    rows, skipped = [], 0
    for o in orders:
        row = compute_order_expense(o, periods)
        if not row:
            skipped += 1
            continue
        if not (start <= (row["date"] or "") <= end):
            continue
        if courier != "all" and row["courier"].lower() != courier.lower():
            continue
        rows.append(row)

    rows.sort(key=lambda r: (r["date"], r.get("order_number") or ""))
    summary = {}
    for r in rows:
        s = summary.setdefault(r["courier"], {
            "shipments": 0, "weight_kg": 0.0, "base": 0.0, "fuel": 0.0,
            "base_plus_fuel": 0.0, "gst": 0.0, "total": 0.0,
            "damaged_count": 0, "damaged_total": 0.0,
        })
        s["shipments"] += 1
        s["weight_kg"] = round(s["weight_kg"] + r["weight_kg"], 3)
        for k in ("base", "fuel", "base_plus_fuel", "gst", "total"):
            s[k] = round(s[k] + r.get(k, 0), 2)
        if r.get("damaged"):
            s["damaged_count"] += 1
            s["damaged_total"] = round(s["damaged_total"] + r["total"], 2)
    grand = round(sum(v["total"] for v in summary.values()), 2)
    damaged_total = round(sum(v["damaged_total"] for v in summary.values()), 2)
    return {
        "date_from": start, "date_to": end,
        "fuel_surcharges": periods,
        "rows": rows, "summary": summary, "grand_total": grand,
        "damaged_total": damaged_total,
        "damaged_count": sum(v["damaged_count"] for v in summary.values()),
        "count": len(rows), "unpriced": skipped,
    }


# ─── Shree Anjani Serviceability Checker ─────────────────────────────────

@api_router.get("/anjani/check/{pincode}")
async def anjani_check_pincode(pincode: str):
    pincode = pincode.strip()
    if not pincode.isdigit() or len(pincode) != 6:
        return {"serviceable": False, "message": "Invalid pincode format."}
    try:
        async with httpx.AsyncClient(timeout=10) as client_http:
            resp = await client_http.get(f"https://api-customer.shreeanjani.co.in/public/centers-by-pincode/{pincode}")
            data = resp.json()
        if data.get("success") and data.get("data") and len(data["data"]) > 0:
            return {"serviceable": True, "centers": data["data"]}
        return {"serviceable": False, "message": "This pincode is not serviceable by Shree Anjani."}
    except Exception as e:
        logging.error(f"Anjani API error: {e}")
        return {"serviceable": False, "message": "Unable to check serviceability right now. Please try again."}


# ─── Amazon Shipping Serviceability (via Amazon Shipping API v2 getRates) ──
# Serviceability is implicit: if Amazon returns rates for origin -> destination,
# the pincode is serviceable. Credentials come from the server .env so the
# feature activates the moment they are added (nothing hard-coded).
AMAZON_SHIP = {
    "client_id": os.environ.get("AMAZON_SHIP_CLIENT_ID", ""),
    "client_secret": os.environ.get("AMAZON_SHIP_CLIENT_SECRET", ""),
    "refresh_token": os.environ.get("AMAZON_SHIP_REFRESH_TOKEN", ""),
    # India is served by the EU regional endpoint of the Amazon Shipping / SP-API.
    "endpoint": os.environ.get("AMAZON_SHIP_ENDPOINT", "https://sellingpartnerapi-eu.amazon.com").rstrip("/"),
    "origin_pincode": os.environ.get("AMAZON_SHIP_ORIGIN_PINCODE", "440025"),
    "origin_city": os.environ.get("AMAZON_SHIP_ORIGIN_CITY", "Nagpur"),
    "origin_state": os.environ.get("AMAZON_SHIP_ORIGIN_STATE", "Maharashtra"),
    "origin_name": os.environ.get("AMAZON_SHIP_ORIGIN_NAME", COMPANY["name"]),
    "origin_phone": os.environ.get("AMAZON_SHIP_ORIGIN_PHONE", COMPANY["mobile"]),
    "origin_addr": os.environ.get("AMAZON_SHIP_ORIGIN_ADDR", COMPANY["address"]),
}

_amazon_token_cache = {"token": "", "expires_at": 0.0}
_pincode_geo_cache = {}


async def _resolve_pincode_geo(pincode: str) -> tuple:
    """(city, state) for a pincode. Amazon rejects placeholder city/state with
    NO_COVERAGE, so a real locality is required for an accurate answer."""
    if pincode in _pincode_geo_cache:
        return _pincode_geo_cache[pincode]
    # Local DTDC table first — instant, no network.
    info = _dtdc_pincodes.get(pincode)
    if info and info.get("city") and info.get("state"):
        geo = (info["city"], info["state"])
        _pincode_geo_cache[pincode] = geo
        return geo
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://api.postalpincode.in/pincode/{pincode}")
            data = r.json()
        if data and data[0].get("Status") == "Success" and data[0].get("PostOffice"):
            po = data[0]["PostOffice"][0]
            geo = (po.get("District") or po.get("Block") or "", po.get("State") or "")
            if geo[0] and geo[1]:
                _pincode_geo_cache[pincode] = geo
                return geo
    except Exception as e:
        logging.warning(f"Pincode geo lookup failed for {pincode}: {e}")
    return ("", "")


def _amazon_configured() -> bool:
    return bool(AMAZON_SHIP["client_id"] and AMAZON_SHIP["client_secret"] and AMAZON_SHIP["refresh_token"])


async def _amazon_access_token() -> str:
    """Exchange the LWA refresh token for a short-lived access token (cached ~1h)."""
    import time
    now = time.time()
    if _amazon_token_cache["token"] and _amazon_token_cache["expires_at"] - 60 > now:
        return _amazon_token_cache["token"]
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post("https://api.amazon.com/auth/o2/token", data={
            "grant_type": "refresh_token",
            "refresh_token": AMAZON_SHIP["refresh_token"],
            "client_id": AMAZON_SHIP["client_id"],
            "client_secret": AMAZON_SHIP["client_secret"],
        })
        resp.raise_for_status()
        data = resp.json()
    _amazon_token_cache["token"] = data["access_token"]
    _amazon_token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _amazon_token_cache["token"]


@api_router.get("/amazon/check/{pincode}")
async def amazon_check_pincode(pincode: str, weight: float = 1.0):
    pincode = pincode.strip()
    if not pincode.isdigit() or len(pincode) != 6:
        return {"serviceable": False, "configured": True, "message": "Invalid pincode format."}
    if not _amazon_configured():
        return {
            "serviceable": None, "configured": False,
            "message": "Amazon Shipping API is not configured yet. Add the API credentials on the server to enable this.",
        }
    try:
        token = await _amazon_access_token()
        city, state = await _resolve_pincode_geo(pincode)
        pkg_weight = max(0.1, float(weight or 1))
        body = {
            "shipFrom": {
                "name": AMAZON_SHIP["origin_name"], "addressLine1": AMAZON_SHIP["origin_addr"][:60],
                "city": AMAZON_SHIP["origin_city"], "stateOrRegion": AMAZON_SHIP["origin_state"],
                "postalCode": AMAZON_SHIP["origin_pincode"], "countryCode": "IN",
                "phoneNumber": AMAZON_SHIP["origin_phone"],
            },
            "shipTo": {
                "name": "Serviceability Check", "addressLine1": "Main Road",
                "city": city or "NA", "stateOrRegion": state or "NA",
                "postalCode": pincode, "countryCode": "IN",
                "phoneNumber": "9999999999",
            },
            "packages": [{
                "dimensions": {"length": 10, "width": 10, "height": 10, "unit": "CENTIMETER"},
                "weight": {"unit": "KILOGRAM", "value": pkg_weight},
                "insuredValue": {"value": 100, "unit": "INR"},
                "packageClientReferenceId": "svc-check-1",
                "items": [{
                    "itemValue": {"value": 100, "unit": "INR"},
                    "description": "Aroma product",
                    "itemIdentifier": "item-1",
                    "quantity": 1,
                    "weight": {"unit": "KILOGRAM", "value": pkg_weight},
                }],
            }],
            "channelDetails": {"channelType": "EXTERNAL"},
            # Mandatory for Indian Amazon Shipping accounts.
            "taxDetails": [{"taxType": "GST", "taxRegistrationNumber": COMPANY["gstin"]}],
        }
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.post(
                f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments/rates",
                headers={"x-amz-access-token": token, "content-type": "application/json"},
                json=body,
            )
        if resp.status_code == 200:
            payload = (resp.json().get("payload") or resp.json())
            rates = payload.get("rates") or []
            if rates:
                # Amazon returns the same service more than once; collapse duplicates.
                seen, simple = set(), []
                for r in rates:
                    charge = r.get("totalCharge") or {}
                    key = (r.get("serviceId") or r.get("serviceName"), charge.get("value"))
                    if key in seen:
                        continue
                    seen.add(key)
                    simple.append({
                        "service": r.get("serviceName") or r.get("serviceId") or "Amazon Shipping",
                        "carrier": r.get("carrierName") or r.get("carrierId"),
                        "amount": charge.get("value"),
                        "currency": charge.get("unit"),
                        "promise": r.get("promise"),
                    })
                return {
                    "serviceable": True, "configured": True,
                    "rates": simple, "count": len(simple),
                    "city": city, "state": state,
                }
            reason = ""
            for ir in payload.get("ineligibleRates") or []:
                reasons = ir.get("ineligibilityReasons") or []
                if reasons:
                    reason = reasons[0].get("message") or reasons[0].get("code") or ""
                    break
            return {
                "serviceable": False, "configured": True,
                "message": "Amazon Shipping does not serve this pincode.",
                "detail": reason, "city": city, "state": state,
            }
        # Non-200 usually means not serviceable, or a credential/region mismatch to fix on first setup.
        return {
            "serviceable": False, "configured": True,
            "message": f"Amazon Shipping returned HTTP {resp.status_code}.",
            "detail": resp.text[:500],
        }
    except Exception as e:
        logging.error(f"Amazon serviceability error: {e}")
        return {"serviceable": False, "configured": True, "message": "Unable to check Amazon serviceability right now."}


def _to_local_phone(raw) -> str:
    """Last 10 digits — Amazon India wants a plain local mobile number."""
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def _declared_value(order: dict) -> float:
    """Declared (insured) value for Amazon.

    GST invoices already carry tax in the grand total, so it is declared as-is.
    Non-GST invoices are grossed up by 18% so the declared value reflects the
    true worth of the goods.
    """
    total = float(order.get("grand_total") or 0)
    if order.get("gst_applicable"):
        return round(total, 2)          # GST invoices already include tax
    return float(math.ceil(total * 1.18))   # e.g. 101 -> 119.18 -> 120


async def _order_phones(order: dict) -> list:
    """All valid contact numbers for the customer, primary first."""
    out = []
    for p in (order.get("customer_phone") or []):
        v = _to_local_phone(p)
        if v and v not in out:
            out.append(v)
    cid = order.get("customer_id")
    if cid:
        cust = await db.customers.find_one({"id": cid}, {"_id": 0, "phone_numbers": 1})
        for p in ((cust or {}).get("phone_numbers") or []):
            v = _to_local_phone(p)
            if v and v not in out:
                out.append(v)
    return out


async def _order_recipient_phone(order: dict) -> str:
    """The customer's real contact number for the shipping label."""
    phones = await _order_phones(order)
    return phones[0] if phones else ""


# Words that mean `label` is a category name ("Billing address", "Home") rather
# than real address text — those must not be printed on the shipping label.
_ADDRESS_LABEL_WORDS = ("billing", "shipping", "home", "office", "work", "branch",
                        "warehouse", "godown", "factory", "default", "primary",
                        "secondary", "adress", "address")


def _address_lines(sa: dict) -> tuple:
    """(line1, line2) for a courier label.

    The OMS address has no address_line2. Users sometimes put real address text
    (flat / building / landmark) into `label` — that must be carried through or
    the parcel ships to an incomplete address — and sometimes just a category
    like "Billing address", which must not be printed.
    """
    line1 = str(sa.get("address_line") or "").strip()
    label = str(sa.get("label") or "").strip()
    normalised = re.sub(r"[^a-z ]", "", label.lower()).strip()
    is_category = len(normalised) <= 25 and any(w in normalised for w in _ADDRESS_LABEL_WORDS)
    line2 = "" if is_category else label
    if not line1:
        line1, line2 = line2, ""
    return line1[:120], line2[:120]


def _amazon_ship_from() -> dict:
    return {
        "name": AMAZON_SHIP["origin_name"],
        "addressLine1": AMAZON_SHIP["origin_addr"][:60],
        "city": AMAZON_SHIP["origin_city"],
        "stateOrRegion": AMAZON_SHIP["origin_state"],
        "postalCode": AMAZON_SHIP["origin_pincode"],
        "countryCode": "IN",
        "phoneNumber": AMAZON_SHIP["origin_phone"],
    }


def _amazon_rates_body(ship_to: dict, weight_kg: float, declared_value: float, ref: str) -> dict:
    """Shared getRates payload. items + root taxDetails are mandatory for IN accounts."""
    w = max(0.1, float(weight_kg or 1))
    val = max(1, int(round(float(declared_value or 100))))
    return {
        "shipFrom": _amazon_ship_from(),
        "shipTo": ship_to,
        "packages": [{
            "dimensions": {"length": 20, "width": 15, "height": 10, "unit": "CENTIMETER"},
            "weight": {"unit": "KILOGRAM", "value": w},
            "insuredValue": {"value": val, "unit": "INR"},
            "packageClientReferenceId": ref,
            "items": [{
                "itemValue": {"value": val, "unit": "INR"},
                "description": "Aroma product",
                "itemIdentifier": ref,
                "quantity": 1,
                "weight": {"unit": "KILOGRAM", "value": w},
            }],
        }],
        "channelDetails": {"channelType": "EXTERNAL"},
        "taxDetails": [{"taxType": "GST", "taxRegistrationNumber": COMPANY["gstin"]}],
    }


class AmazonBookRequest(BaseModel):
    order_id: str
    service_id: Optional[str] = None   # which quoted service to buy; cheapest if omitted


# Couriers are free text ("Amazon", "Amazon shipping", ...), so match loosely.
AMAZON_COURIER_RE = {"$regex": r"^\s*amazon", "$options": "i"}


@api_router.get("/amazon/bookable")
async def amazon_bookable_orders(user=Depends(get_current_user)):
    """Orders assigned to Amazon courier that packing has weighed and that are not booked yet."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    orders = await db.orders.find({
        "courier_name": AMAZON_COURIER_RE,
        # Dispatched orders have already shipped, so there is nothing left to book.
        "status": {"$nin": ["cancelled", "dispatched"]},
        "packaging.weight_kg": {"$nin": ["", None]},
    }, {
        "_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "grand_total": 1,
        "shipping_address": 1, "packaging": 1, "amazon_shipment": 1, "status": 1,
    }).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        # Guard against whitespace-only / zero weights that the query can't catch.
        try:
            if float(str(pkg.get("weight_kg", "")).strip() or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        out.append({
            "id": o["id"], "order_number": o.get("order_number"),
            "customer_name": o.get("customer_name"), "grand_total": o.get("grand_total"),
            "status": o.get("status"),
            "weight_kg": pkg.get("weight_kg"), "num_boxes": pkg.get("num_boxes") or "1",
            "shipping_address": o.get("shipping_address") or {},
            "amazon_shipment": o.get("amazon_shipment"),
        })
    return out


@api_router.post("/amazon/quote")
async def amazon_quote_order(req: AmazonBookRequest, user=Depends(get_current_user)):
    """Live rates for a specific order — read-only, books nothing."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not _amazon_configured():
        raise HTTPException(status_code=400, detail="Amazon Shipping API is not configured")
    order = await db.orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    pkg = order.get("packaging") or {}
    if not str(pkg.get("weight_kg", "")).strip():
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    sa = order.get("shipping_address") or {}
    phone = await _order_recipient_phone(order)
    ship_to = {
        "name": sa.get("address_name") or order.get("customer_name") or "Customer",
        "addressLine1": (sa.get("address_line") or "Address")[:60],
        "city": sa.get("city") or "", "stateOrRegion": sa.get("state") or "",
        "postalCode": sa.get("pincode") or "", "countryCode": "IN",
        "phoneNumber": phone or AMAZON_SHIP["origin_phone"],
    }
    token = await _amazon_access_token()
    body = _amazon_rates_body(ship_to, pkg.get("weight_kg"), _declared_value(order), order.get("order_number") or "ord")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments/rates",
                         headers={"x-amz-access-token": token, "content-type": "application/json"}, json=body)
    if r.status_code != 200:
        return {"ok": False, "message": f"Amazon returned HTTP {r.status_code}", "detail": r.text[:400]}
    payload = r.json().get("payload") or r.json()
    rates, seen = [], set()
    for x in payload.get("rates") or []:
        ch = x.get("totalCharge") or {}
        key = (x.get("serviceId") or x.get("serviceName"), ch.get("value"))
        if key in seen:
            continue
        seen.add(key)
        rates.append({
            "rate_id": x.get("rateId"), "service_id": x.get("serviceId"),
            "service": x.get("serviceName"), "amount": ch.get("value"), "currency": ch.get("unit"),
            "promise": x.get("promise"),
        })
    if not rates:
        reason = ""
        for ir in payload.get("ineligibleRates") or []:
            rs = (ir.get("ineligibilityReasons") or [{}])[0]
            reason = rs.get("message") or rs.get("code") or ""
            break
        return {"ok": False, "message": "Amazon Shipping does not serve this address.", "detail": reason}
    return {"ok": True, "rates": rates, "request_token": payload.get("requestToken")}


@api_router.post("/amazon/book")
async def amazon_book_order(req: AmazonBookRequest, user=Depends(get_current_user)):
    """PURCHASES a real Amazon shipment (this costs money and schedules a pickup)."""
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized to book shipments")
    if not _amazon_configured():
        raise HTTPException(status_code=400, detail="Amazon Shipping API is not configured")
    order = await db.orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("amazon_shipment") or {}).get("shipment_id"):
        raise HTTPException(status_code=400, detail="This order is already booked with Amazon")
    pkg = order.get("packaging") or {}
    if not str(pkg.get("weight_kg", "")).strip():
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")

    sa = order.get("shipping_address") or {}
    # Never ship with a placeholder number — the courier calls this to deliver.
    phone = await _order_recipient_phone(order)
    if not phone:
        raise HTTPException(
            status_code=400,
            detail="Customer has no valid phone number. Add one to the customer record before booking — the courier needs it for delivery.",
        )
    ship_to = {
        "name": sa.get("address_name") or order.get("customer_name") or "Customer",
        "addressLine1": (sa.get("address_line") or "Address")[:60],
        "city": sa.get("city") or "", "stateOrRegion": sa.get("state") or "",
        "postalCode": sa.get("pincode") or "", "countryCode": "IN",
        "phoneNumber": phone,
    }
    token = await _amazon_access_token()
    ref = order.get("order_number") or req.order_id[:20]
    headers = {"x-amz-access-token": token, "content-type": "application/json"}

    async with httpx.AsyncClient(timeout=40) as c:
        rr = await c.post(f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments/rates",
                          headers=headers,
                          json=_amazon_rates_body(ship_to, pkg.get("weight_kg"), _declared_value(order), ref))
        if rr.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Amazon rates failed: {rr.text[:300]}")
        payload = rr.json().get("payload") or rr.json()
        rates = payload.get("rates") or []
        if not rates:
            raise HTTPException(status_code=400, detail="Amazon Shipping does not serve this address")
        chosen = None
        if req.service_id:
            chosen = next((x for x in rates if x.get("serviceId") == req.service_id or x.get("rateId") == req.service_id), None)
        if not chosen:
            chosen = min(rates, key=lambda x: (x.get("totalCharge") or {}).get("value", 1e9))

        purchase = {
            "requestToken": payload.get("requestToken"),
            "rateId": chosen.get("rateId"),
            "requestedDocumentSpecification": {
                "format": "PNG",
                "size": {"length": 6, "width": 4, "unit": "INCH"},
                "dpi": 300,
                "pageLayout": "DEFAULT",
                "needFileJoining": False,
                "requestedDocumentTypes": ["LABEL"],
            },
        }
        pr = await c.post(f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments",
                          headers=headers, json=purchase)
    if pr.status_code not in (200, 201):
        logging.error(f"Amazon purchase failed: {pr.status_code} {pr.text[:500]}")
        raise HTTPException(status_code=400, detail=f"Amazon booking failed: {pr.text[:300]}")

    pp = pr.json().get("payload") or pr.json()
    tracking_id, label_b64, label_fmt = "", "", "PNG"
    for pd in pp.get("packageDocumentDetails") or []:
        tracking_id = tracking_id or pd.get("trackingId") or ""
        for doc in pd.get("packageDocuments") or []:
            if not label_b64:
                label_b64 = doc.get("contents") or ""
                label_fmt = doc.get("format") or "PNG"

    charge = chosen.get("totalCharge") or {}
    shipment = {
        "shipment_id": pp.get("shipmentId") or "",
        "tracking_id": tracking_id,
        "service": chosen.get("serviceName"),
        "service_id": chosen.get("serviceId"),
        "carrier_id": chosen.get("carrierId") or "ATS",
        "amount": charge.get("value"),
        "currency": charge.get("unit"),
        "promise": chosen.get("promise"),
        "label_format": label_fmt,
        "label_base64": label_b64,
        "recipient_phone": phone,
        "booked_by": user["name"],
        "booked_at": datetime.now(timezone.utc).isoformat(),
    }
    update = {"amazon_shipment": shipment, "updated_at": datetime.now(timezone.utc).isoformat()}
    if tracking_id:
        dispatch = order.get("dispatch") or {}
        dispatch["courier_name"] = "Amazon"
        dispatch.setdefault("lr_no", tracking_id)
        update["dispatch"] = dispatch
    await db.orders.update_one({"id": req.order_id}, {"$set": update})
    safe = {k: v for k, v in shipment.items() if k != "label_base64"}
    return {"ok": True, "shipment": safe, "has_label": bool(label_b64)}


# ─── Amazon pickup tracking → auto-dispatch ───────────────────────────────
# Amazon emits "PickupDone" when the parcel leaves us; the summary status also
# moves past "ReadyForReceive" once it is in the network.
AMAZON_PICKUP_EVENTS = {"PickupDone", "PickedUp", "Departed"}
AMAZON_PICKED_STATUSES = {"InTransit", "OutForDelivery", "Delivering", "Delivered", "AttemptFail"}
AMAZON_SYNC_INTERVAL_SECONDS = int(os.environ.get("AMAZON_SYNC_INTERVAL_SECONDS", "600"))


async def _amazon_track(tracking_id: str, carrier_id: str = "ATS") -> Optional[dict]:
    token = await _amazon_access_token()
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(f"{AMAZON_SHIP['endpoint']}/shipping/v2/tracking",
                        params={"trackingId": tracking_id, "carrierId": carrier_id or "ATS"},
                        headers={"x-amz-access-token": token})
    if r.status_code != 200:
        logging.warning(f"Amazon tracking {tracking_id}: HTTP {r.status_code} {r.text[:200]}")
        return None
    return r.json().get("payload") or r.json()


def _amazon_pickup_time(payload: dict) -> Optional[str]:
    """Pickup timestamp if the parcel has left us, else None."""
    if not payload:
        return None
    for ev in (payload.get("eventHistory") or []):
        if ev.get("eventCode") in AMAZON_PICKUP_EVENTS:
            return ev.get("eventTime")
    status = ((payload.get("summary") or {}).get("status") or "")
    if status in AMAZON_PICKED_STATUSES:
        events = payload.get("eventHistory") or []
        return (events[-1].get("eventTime") if events else datetime.now(timezone.utc).isoformat())
    return None


async def _save_label_as_slip(shipment: dict) -> str:
    """Persist the label PNG (portrait, as Amazon issued it) as a dispatch slip image."""
    b64 = shipment.get("label_base64")
    if not b64:
        return ""
    import base64 as _b64
    raw = _b64.b64decode(b64)
    filename = f"{uuid.uuid4()}.png"
    async with aiofiles.open(UPLOAD_DIR / filename, "wb") as f:
        await f.write(raw)
    return f"/api/uploads/{filename}"


async def _amazon_sync_order(order: dict) -> Optional[str]:
    """Mark an order dispatched once Amazon reports pickup. Returns a status note."""
    shipment = order.get("amazon_shipment") or {}
    tracking = shipment.get("tracking_id")
    if not tracking or order.get("status") == "dispatched":
        return None
    payload = await _amazon_track(tracking, shipment.get("carrier_id") or "ATS")
    picked_at = _amazon_pickup_time(payload)
    if not picked_at:
        return None

    dispatch = order.get("dispatch") or {}
    slips = list(dispatch.get("dispatch_slip_images") or [])
    if not slips:
        url = await _save_label_as_slip(shipment)
        if url:
            slips.append(url)
    dispatch.update({
        "courier_name": "Amazon",
        "transporter_name": "",
        "lr_no": tracking,
        "dispatch_slip_images": slips,
        "dispatch_type": "courier",
        "porter_link": "",
        "dispatched_by": dispatch.get("dispatched_by") or "Amazon Shipping (auto)",
        "dispatched_at": picked_at,
    })
    await db.orders.update_one({"id": order["id"]}, {"$set": {
        "dispatch": dispatch,
        "status": "dispatched",
        "courier_name": "Amazon",
        "amazon_shipment.picked_up_at": picked_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    logging.info(f"Amazon auto-dispatch: {order.get('order_number')} picked up at {picked_at}")
    return f"{order.get('order_number')} dispatched (picked up {picked_at})"


async def _amazon_sync_all() -> list:
    if not _amazon_configured():
        return []
    pending = await db.orders.find({
        "amazon_shipment.tracking_id": {"$exists": True, "$ne": ""},
        "status": {"$nin": ["dispatched", "cancelled"]},
    }, {"_id": 0}).to_list(200)
    notes = []
    for o in pending:
        try:
            note = await _amazon_sync_order(o)
            if note:
                notes.append(note)
        except Exception as e:
            logging.error(f"Amazon sync failed for {o.get('order_number')}: {e}")
    return notes


class AmazonLinkRequest(BaseModel):
    order_id: str
    tracking_id: str
    service: Optional[str] = "Amazon Shipping Standard"
    amount: Optional[float] = None
    carrier_id: Optional[str] = "ATS"


@api_router.post("/amazon/link-shipment")
async def amazon_link_shipment(req: AmazonLinkRequest, user=Depends(get_current_user)):
    """Attach a shipment that was booked directly in the Amazon portal, so the
    OMS can track it and auto-dispatch on pickup. No label is available for
    these — Amazon only returns documents to the caller that purchased them."""
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    tracking = re.sub(r"\s", "", req.tracking_id or "")
    if not tracking:
        raise HTTPException(status_code=400, detail="Tracking ID is required")
    existing = order.get("amazon_shipment") or {}
    if existing.get("tracking_id") and existing["tracking_id"] != tracking:
        raise HTTPException(status_code=400, detail=f"Order already linked to {existing['tracking_id']}")
    shipment = {
        **existing,
        "tracking_id": tracking,
        "service": req.service or "Amazon Shipping Standard",
        "carrier_id": req.carrier_id or "ATS",
        "amount": req.amount if req.amount is not None else existing.get("amount"),
        "currency": "INR",
        "linked_manually": True,
        "booked_by": existing.get("booked_by") or f"{user['name']} (linked)",
        "booked_at": existing.get("booked_at") or datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.update_one({"id": req.order_id}, {"$set": {
        "amazon_shipment": shipment,
        "courier_name": "Amazon",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    note = await _amazon_sync_order({**order, "amazon_shipment": shipment})
    return {"ok": True, "tracking_id": tracking, "dispatched": bool(note), "note": note}


@api_router.post("/amazon/sync-tracking")
async def amazon_sync_tracking(user=Depends(get_current_user)):
    """Check Amazon tracking now and dispatch anything already picked up."""
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    notes = await _amazon_sync_all()
    return {"ok": True, "dispatched": notes, "count": len(notes)}


async def _amazon_sync_loop():
    # Give the app a moment to finish starting before the first poll.
    await asyncio.sleep(30)
    while True:
        try:
            await _amazon_sync_all()
        except Exception as e:
            logging.error(f"Amazon sync loop error: {e}")
        await asyncio.sleep(AMAZON_SYNC_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_amazon_sync():
    if _amazon_configured():
        asyncio.create_task(_amazon_sync_loop())
        logging.info(f"Amazon pickup sync every {AMAZON_SYNC_INTERVAL_SECONDS}s")


@api_router.get("/amazon/label/{order_id}")
async def amazon_label_pdf(order_id: str, token: str = "", user=None):
    """Amazon shipping label rendered on a landscape A5 page."""
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    shipment = order.get("amazon_shipment") or {}
    if not shipment.get("label_base64"):
        raise HTTPException(status_code=404, detail="No Amazon label stored for this order")

    import base64
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas

    raw = base64.b64decode(shipment["label_base64"])
    page = landscape(A5)                      # 210mm x 148mm
    margin = 6 * mm
    avail_w, avail_h = page[0] - 2 * margin, page[1] - 2 * margin
    buffer = io.BytesIO()
    try:
        img = ImageReader(io.BytesIO(raw))
        iw, ih = img.getSize()
        c = pdf_canvas.Canvas(buffer, pagesize=page)
        # Shipping labels are portrait (4x6). Rotating them onto the landscape
        # page roughly doubles the printed size, which keeps the barcode scannable.
        if ih > iw:
            s = min(avail_w / ih, avail_h / iw)
            w, h = iw * s, ih * s          # image dims in its own orientation
            c.saveState()
            c.translate(page[0] / 2 + h / 2, page[1] / 2 - w / 2)
            c.rotate(90)
            c.drawImage(img, 0, 0, width=w, height=h, preserveAspectRatio=True, anchor="sw")
            c.restoreState()
        else:
            s = min(avail_w / iw, avail_h / ih)
            w, h = iw * s, ih * s
            c.drawImage(img, (page[0] - w) / 2, (page[1] - h) / 2,
                        width=w, height=h, preserveAspectRatio=True, anchor="c")
        c.showPage()
        c.save()
    except Exception as e:
        logging.error(f"Amazon label render error: {e}")
        raise HTTPException(status_code=500, detail="Could not render the stored label image")
    buffer.seek(0)
    fname = f"amazon-label-{order.get('order_number') or order_id}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"inline; filename={fname}"})


# ─── Admin Alert / Urgent Notification System ────────────────────────────

@api_router.get("/admin/alerts/other-users")
async def get_crm_users(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        crm_db = client["crm_database"]
        crm_users = await crm_db.users.find({"active": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "username": 1, "role": 1}).to_list(1000)
        return crm_users
    except Exception as e:
        logging.error(f"Failed to fetch CRM users: {e}")
        return []

@api_router.get("/admin/alerts/mappings")
async def get_user_mappings(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    mappings = await db.user_mappings.find({}, {"_id": 0}).to_list(1000)
    return mappings

@api_router.post("/admin/alerts/mappings")
async def save_user_mappings(body: dict, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    mappings = body.get("mappings", [])
    await db.user_mappings.delete_many({})
    if mappings:
        valid_mappings = []
        for m in mappings:
            oms_id = m.get("oms_user_id")
            crm_id = m.get("crm_user_id")
            if oms_id and crm_id:
                valid_mappings.append({"oms_user_id": oms_id, "crm_user_id": crm_id})
        if valid_mappings:
            await db.user_mappings.insert_many(valid_mappings)
    return {"status": "success", "message": "Mappings saved successfully"}

@api_router.post("/admin/alerts")
async def create_admin_alert(body: dict, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can send alerts")
    title = body.get("title", "").strip()
    message = body.get("message", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    recipients = body.get("recipients", [])  # list of user IDs
    recipient_roles = body.get("recipient_roles", [])  # list of roles
    order_id = body.get("order_id", "")
    customer_name = body.get("customer_name", "")

    # Build list of target user IDs
    target_user_ids = set(recipients)
    if recipient_roles:
        role_users = await db.users.find({"role": {"$in": recipient_roles}, "active": {"$ne": False}}, {"_id": 0, "id": 1}).to_list(500)
        for u in role_users:
            target_user_ids.add(u["id"])

    if not target_user_ids:
        raise HTTPException(status_code=400, detail="No recipients selected")

    alert_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    alert_doc = {
        "id": alert_id,
        "title": title,
        "message": message,
        "sent_by": user["name"],
        "sent_by_id": user["id"],
        "order_id": order_id,
        "customer_name": customer_name,
        "recipient_ids": list(target_user_ids),
        "recipient_roles": recipient_roles,
        "acknowledgements": {},
        "created_at": now,
    }
    await db.admin_alerts.insert_one(alert_doc)

    # ─── Bidirectional Sync: Forward Alert to CRM ───
    try:
        crm_db = client["crm_database"]
        # Find detail info of the OMS target recipients
        oms_target_users = await db.users.find({"id": {"$in": list(target_user_ids)}}, {"_id": 0, "id": 1, "username": 1}).to_list(500)

        # Get the mappings from the shared user_mappings collection
        mappings = await db.user_mappings.find({}).to_list(1000)
        oms_to_crm = {m["oms_user_id"]: m["crm_user_id"] for m in mappings if m.get("oms_user_id") and m.get("crm_user_id")}

        crm_target_ids = set()
        mapped_oms_ids = set()

        for u in oms_target_users:
            oms_uid = u["id"]
            if oms_uid in oms_to_crm:
                crm_target_ids.add(oms_to_crm[oms_uid])
                mapped_oms_ids.add(oms_uid)

        # Fallback to username for users that do not have an explicit mapping
        unmapped_users = [u for u in oms_target_users if u["id"] not in mapped_oms_ids]
        if unmapped_users:
            unmapped_usernames = [u["username"] for u in unmapped_users if u.get("username")]
            if unmapped_usernames:
                crm_users_fallback = await crm_db.users.find({"username": {"$in": unmapped_usernames}, "active": {"$ne": False}}, {"_id": 0, "id": 1}).to_list(500)
                for cu in crm_users_fallback:
                    crm_target_ids.add(cu["id"])

        # Map recipient roles from OMS to CRM as role-based fallback sync
        crm_recipient_roles = []
        for r in recipient_roles:
            if r == "admin":
                crm_recipient_roles.append("admin")
            elif r == "telecaller":
                crm_recipient_roles.append("executive")

        if crm_recipient_roles:
            crm_users_by_role = await crm_db.users.find({"role": {"$in": crm_recipient_roles}, "active": {"$ne": False}}, {"_id": 0, "id": 1}).to_list(500)
            for cu in crm_users_by_role:
                crm_target_ids.add(cu["id"])

        if crm_target_ids:
            crm_alert_doc = alert_doc.copy()
            crm_alert_doc["recipient_ids"] = list(crm_target_ids)
            crm_alert_doc["recipient_roles"] = crm_recipient_roles
            await crm_db.admin_alerts.insert_one(crm_alert_doc)
    except Exception as e:
        logging.error(f"Alert sync to CRM failed: {e}")

    return {"id": alert_id, "message": f"Alert sent to {len(target_user_ids)} user(s)"}

@api_router.get("/admin/alerts/pending")
async def get_pending_alerts(user=Depends(get_current_user)):
    uid = user["id"]
    alerts = await db.admin_alerts.find(
        {"recipient_ids": uid, f"acknowledgements.{uid}": {"$exists": False}, "cancelled": {"$ne": True}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return alerts

@api_router.put("/admin/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, user=Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    result = await db.admin_alerts.update_one(
        {"id": alert_id, "recipient_ids": user["id"]},
        {"$set": {f"acknowledgements.{user['id']}": {"name": user["name"], "at": now}}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    # ─── Bidirectional Sync: Acknowledge Alert in CRM ───
    try:
        crm_db = client["crm_database"]
        # Check explicit mapping first
        mapping = await db.user_mappings.find_one({"oms_user_id": user["id"]})
        crm_user = None
        if mapping and mapping.get("crm_user_id"):
            crm_user = await crm_db.users.find_one({"id": mapping["crm_user_id"]})

        if not crm_user:
            # Fallback to username
            crm_user = await crm_db.users.find_one({"username": user["username"]})

        if crm_user:
            await crm_db.admin_alerts.update_one(
                {"id": alert_id, "recipient_ids": crm_user["id"]},
                {"$set": {f"acknowledgements.{crm_user['id']}": {"name": crm_user["name"], "at": now}}}
            )
    except Exception as e:
        logging.error(f"Acknowledgement sync to CRM failed: {e}")

    return {"message": "Acknowledged"}

@api_router.put("/admin/alerts/{alert_id}/cancel")
async def cancel_alert(alert_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can cancel alerts")
    now = datetime.now(timezone.utc).isoformat()
    result = await db.admin_alerts.update_one(
        {"id": alert_id},
        {"$set": {"cancelled": True, "cancelled_at": now, "cancelled_by": user["name"]}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    # ─── Bidirectional Sync: Cancel Alert in CRM ───
    try:
        crm_db = client["crm_database"]
        await crm_db.admin_alerts.update_one(
            {"id": alert_id},
            {"$set": {"cancelled": True, "cancelled_at": now, "cancelled_by": user["name"]}}
        )
    except Exception as e:
        logging.error(f"Cancellation sync to CRM failed: {e}")

    return {"message": "Alert cancelled"}


@api_router.get("/admin/alerts/history")
async def get_alert_history(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    alerts = await db.admin_alerts.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    # Enrich with user names for display
    all_user_ids = set()
    for a in alerts:
        all_user_ids.update(a.get("recipient_ids", []))
    users_map = {}
    if all_user_ids:
        users_list = await db.users.find({"id": {"$in": list(all_user_ids)}}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(500)
        users_map = {u["id"]: u for u in users_list}
    for a in alerts:
        a["recipients_info"] = [users_map.get(uid, {"id": uid, "name": "Unknown"}) for uid in a.get("recipient_ids", [])]
        total = len(a.get("recipient_ids", []))
        acked = len(a.get("acknowledgements", {}))
        a["ack_count"] = acked
        a["total_count"] = total
        a["fully_acknowledged"] = acked >= total
    return alerts




# ============================================================
# Field-Executive Location Tracking
# ============================================================
IST = pytz.timezone("Asia/Kolkata")


def _parse_iso(value: str) -> datetime:
    """Parse an ISO8601 string (accepts a trailing 'Z') into an aware UTC datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _ist_day_bounds(date_str: Optional[str]) -> tuple:
    """Return (start_utc_iso, end_utc_iso) for an IST calendar day. Defaults to today (IST)."""
    if date_str:
        y, m, d = (int(x) for x in date_str.split("-"))
        day = IST.localize(datetime(y, m, d, 0, 0, 0))
    else:
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        day = IST.localize(datetime(now_ist.year, now_ist.month, now_ist.day, 0, 0, 0))
    start = day.astimezone(timezone.utc).isoformat()
    end = (day + timedelta(days=1)).astimezone(timezone.utc).isoformat()
    return start, end


async def _store_pings(user: dict, pings: List[LocationPing]) -> int:
    docs = []
    for p in pings:
        try:
            ts = _parse_iso(p.ts).isoformat() if p.ts else datetime.now(timezone.utc).isoformat()
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc).isoformat()
        docs.append({
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "lat": p.lat,
            "lng": p.lng,
            "accuracy": p.accuracy,
            "altitude": p.altitude,
            "speed": p.speed,
            "heading": p.heading,
            "battery": p.battery,
            "is_moving": p.is_moving,
            "ts": ts,
            "server_ts": datetime.now(timezone.utc).isoformat(),
        })
    if docs:
        await db.locations.insert_many(docs)
    return len(docs)


@api_router.post("/location/ping")
async def location_ping(ping: LocationPing, user=Depends(get_current_user)):
    if user["role"] not in ("field_executive", "admin"):
        raise HTTPException(status_code=403, detail="Not a tracking account")
    count = await _store_pings(user, [ping])
    return {"stored": count}


@api_router.post("/location/batch")
async def location_batch(batch: LocationBatch, user=Depends(get_current_user)):
    if user["role"] not in ("field_executive", "admin"):
        raise HTTPException(status_code=403, detail="Not a tracking account")
    count = await _store_pings(user, batch.pings)
    return {"stored": count}


@api_router.get("/location/executives")
async def list_tracked_executives(admin=Depends(require_admin)):
    """All field-executive accounts with their most recent fix."""
    users = await db.users.find(
        {"role": "field_executive"}, {"_id": 0, "password_hash": 0}
    ).to_list(500)
    result = []
    for u in users:
        last = await db.locations.find(
            {"user_id": u["id"]}, {"_id": 0}
        ).sort("ts", -1).limit(1).to_list(1)
        last_fix = last[0] if last else None
        result.append({
            "id": u["id"],
            "name": u["name"],
            "username": u["username"],
            "active": u.get("active", True),
            "last_fix": last_fix,
        })
    return result


@api_router.get("/location/history/{user_id}")
async def location_history(user_id: str, date: Optional[str] = None, admin=Depends(require_admin)):
    """Full ordered track for one executive on an IST calendar day + total distance."""
    start, end = _ist_day_bounds(date)
    pings = await db.locations.find(
        {"user_id": user_id, "ts": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).sort("ts", 1).to_list(20000)

    total_m = 0.0
    prev = None
    for p in pings:
        if prev is not None:
            # skip obviously bad jumps from low-accuracy fixes
            if (p.get("accuracy") or 0) <= 100:
                total_m += _haversine_m(prev["lat"], prev["lng"], p["lat"], p["lng"])
        prev = p
    return {
        "user_id": user_id,
        "date": date or datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d"),
        "count": len(pings),
        "distance_km": round(total_m / 1000.0, 2),
        "points": pings,
    }


@api_router.get("/location/staypoints/{user_id}")
async def location_staypoints(
    user_id: str,
    date: Optional[str] = None,
    radius_m: float = 60.0,
    min_minutes: float = 5.0,
    admin=Depends(require_admin),
):
    """Cluster consecutive fixes into 'stay points' (where the person lingered)."""
    start, end = _ist_day_bounds(date)
    pings = await db.locations.find(
        {"user_id": user_id, "ts": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).sort("ts", 1).to_list(20000)

    stays = []
    i = 0
    n = len(pings)
    while i < n:
        anchor = pings[i]
        j = i + 1
        sum_lat, sum_lng, cnt = anchor["lat"], anchor["lng"], 1
        while j < n:
            c_lat, c_lng = sum_lat / cnt, sum_lng / cnt
            if _haversine_m(c_lat, c_lng, pings[j]["lat"], pings[j]["lng"]) <= radius_m:
                sum_lat += pings[j]["lat"]
                sum_lng += pings[j]["lng"]
                cnt += 1
                j += 1
            else:
                break
        arrival = _parse_iso(pings[i]["ts"])
        departure = _parse_iso(pings[j - 1]["ts"])
        dur_min = (departure - arrival).total_seconds() / 60.0
        if dur_min >= min_minutes:
            stays.append({
                "lat": sum_lat / cnt,
                "lng": sum_lng / cnt,
                "arrival": arrival.astimezone(IST).isoformat(),
                "departure": departure.astimezone(IST).isoformat(),
                "duration_min": round(dur_min, 1),
                "fixes": cnt,
            })
        i = j if j > i + 1 else i + 1

    stays.sort(key=lambda s: s["duration_min"], reverse=True)
    return {"user_id": user_id, "date": date, "stay_points": stays}


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
