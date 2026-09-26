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
# The CRM shares this MongoDB. Attendance and leaves live there and stay the
# single source of truth: the OMS only reads attendance and writes leave
# requests in the CRM's own document shape, so the CRM shows them as its own.
crm_db = client[os.environ.get("CRM_DB_NAME", "crm_database")]

# Auth
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.environ.get("JWT_SECRET", "fallback_secret")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()

UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ═══════════════════════════════════════════════════════════════════════════
# SECURITY: buyer PII encryption at rest, security log, login throttling.
# Amazon buyer name / address / phone are stored AES-256-GCM encrypted; the
# key lives in the environment (AMZ_PII_KEY), never in the database or the
# repo, so a database dump or backup alone cannot reveal them.
# ═══════════════════════════════════════════════════════════════════════════
import base64 as _b64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM

try:
    _PII_KEY = _b64.b64decode(os.environ.get("AMZ_PII_KEY", ""))
except Exception:
    _PII_KEY = b""
if len(_PII_KEY) != 32:
    _PII_KEY = b""            # not configured: values pass through unchanged
PII_FIELDS = ("customer_name", "address", "phone")
_PII_PREFIX = "enc:v1:"


def _pii_enc(value):
    if not _PII_KEY or not isinstance(value, str) or not value or value.startswith(_PII_PREFIX):
        return value
    nonce = os.urandom(12)
    return _PII_PREFIX + _b64.b64encode(nonce + _AESGCM(_PII_KEY).encrypt(nonce, value.encode("utf-8"), None)).decode()


def _pii_dec(value):
    if not isinstance(value, str) or not value.startswith(_PII_PREFIX):
        return value
    if not _PII_KEY:
        return "[encrypted]"
    try:
        raw = _b64.b64decode(value[len(_PII_PREFIX):])
        return _AESGCM(_PII_KEY).decrypt(raw[:12], raw[12:], None).decode("utf-8")
    except Exception:
        return "[unreadable]"


def _pii_seal(doc: dict) -> dict:
    for f in PII_FIELDS:
        if f in doc:
            doc[f] = _pii_enc(doc[f])
    return doc


def _pii_open(doc: dict) -> dict:
    for f in PII_FIELDS:
        if f in doc:
            doc[f] = _pii_dec(doc[f])
    return doc


# Need-to-know: only these roles ever see a buyer's name, street or phone.
# Packing works from the item list and the city; it never needs the person.
PII_ROLES = ("admin", "dispatch")
PII_BULK_VIEWS_PER_HOUR = 30


def _pii_mask(doc: dict) -> dict:
    if doc.get("has_buyer_pii") and not doc.get("pii_purged_at"):
        doc["customer_name"] = "Amazon customer"
        doc["address"] = doc.get("address_public") or ""
        doc["phone"] = ""
    return doc


async def _pii_view_logged(user: dict, order_no: str):
    """Log the view; an unusual number of views in an hour alerts the admins once."""
    await _sec_log("pii_view", username=user.get("username"), role=user["role"], order=order_no)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    n = await db.security_log.count_documents({"event": "pii_view", "username": user.get("username"),
                                               "at_dt": {"$gte": since}})
    if n == PII_BULK_VIEWS_PER_HOUR:
        admins = [u["id"] for u in await db.users.find({"role": "admin", "active": {"$ne": False}},
                                                       {"_id": 0, "id": 1}).to_list(50)]
        await db.admin_alerts.insert_one({
            "id": str(uuid.uuid4()), "title": f"Security: unusual buyer-data access by '{user.get('username')}'",
            "message": f"'{user.get('username')}' opened {n} orders containing buyer details in the last hour. "
                       f"Check the Security Log.",
            "sent_by": "System", "sent_by_id": None, "order_id": "", "customer_name": "",
            "recipient_ids": admins, "recipient_roles": ["admin"], "acknowledgements": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "meta": {"type": "security_pii_bulk", "username": user.get("username")}})
        await _sec_log("pii_bulk_alert", username=user.get("username"), count=n)


def _client_ip(request) -> str:
    try:
        return (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or \
            (request.client.host if request.client else "")
    except Exception:
        return ""


async def _sec_log(event: str, **fields):
    """Security log: logins, lockouts, buyer-data access. Kept 400 days (TTL index)."""
    try:
        await db.security_log.insert_one({"event": event, "at": datetime.now(timezone.utc).isoformat(),
                                          "at_dt": datetime.now(timezone.utc), **fields})
    except Exception as e:
        logging.error(f"security log write failed: {e}")


LOGIN_MAX_FAILS = 8           # per username ...
LOGIN_WINDOW_MIN = 15         # ... inside this window -> locked for the rest of it


async def _login_guard(username: str, ip: str):
    since = datetime.now(timezone.utc) - timedelta(minutes=LOGIN_WINDOW_MIN)
    fails = await db.security_log.count_documents({"event": "login_failed", "username": username,
                                                   "at_dt": {"$gte": since}})
    if fails >= LOGIN_MAX_FAILS:
        await _sec_log("login_blocked", username=username, ip=ip)
        raise HTTPException(status_code=429, detail="Too many wrong passwords. Try again in 15 minutes.")


async def _login_failed(username: str, ip: str):
    await _sec_log("login_failed", username=username, ip=ip)
    since = datetime.now(timezone.utc) - timedelta(minutes=LOGIN_WINDOW_MIN)
    fails = await db.security_log.count_documents({"event": "login_failed", "username": username,
                                                   "at_dt": {"$gte": since}})
    if fails == LOGIN_MAX_FAILS:              # crossing the line: tell the admins once
        admins = [u["id"] for u in await db.users.find({"role": "admin", "active": {"$ne": False}},
                                                       {"_id": 0, "id": 1}).to_list(50)]
        await db.admin_alerts.insert_one({
            "id": str(uuid.uuid4()), "title": f"Security: login locked for '{username}'",
            "message": f"{LOGIN_MAX_FAILS} wrong passwords for '{username}' in {LOGIN_WINDOW_MIN} minutes "
                       f"(last from {ip or 'unknown address'}). The login is locked for 15 minutes.",
            "sent_by": "System", "sent_by_id": None, "order_id": "", "customer_name": "",
            "recipient_ids": admins, "recipient_roles": ["admin"], "acknowledgements": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "meta": {"type": "security_login_lock", "username": username}})


@app.on_event("startup")
async def _security_indexes():
    try:
        await db.security_log.create_index("at_dt", expireAfterSeconds=400 * 86400)
        await db.security_log.create_index([("event", 1), ("username", 1), ("at_dt", -1)])
    except Exception as e:
        logging.error(f"security index setup failed: {e}")

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

# ─── Companies ────────────────────────────────────────────────────────────
# Two businesses share this OMS. Every order and PI carries a `company` key;
# CitSpray is the default so nothing existing changes. Each company owns its
# own number series and counter, so CS and FV sequences never interfere.
DEFAULT_COMPANY = "citspray"

COMPANIES = {
    "citspray": {
        "key": "citspray",
        "label": "CitSpray",
        "name": COMPANY["name"],
        "brand": COMPANY["brand"],
        "address": COMPANY["address"],
        "mobile": COMPANY["mobile"],
        "gstin": COMPANY["gstin"],
        "email": COMPANY["email"],
        "website": COMPANY["website"],
        "state_code": COMPANY["state_code"],
        "order_prefix": "CS",
        "pi_prefix": "PI",
        "order_counter": "order_number",
        "pi_counter": "pi_number",
        "logo": LOGO_PATH,
        "logo_pdf": LOGO_PDF_PATH,
    },
    "fragvansh": {
        "key": "fragvansh",
        "label": "FragVansh",
        "name": "FragVansh",
        "brand": "FragVansh Aromatic Elements",
        "address": ("B Wing, Poonam Heights, Behind Gulmohar Hall, Pande Layout, "
                    "Khamla, Nagpur, Maharashtra, 440025"),
        "mobile": "7447717744",
        "gstin": "27CBKPA6724N1ZB",
        "email": "Info@fragvansh.com",
        "website": "www.fragvansh.com",
        "state_code": "27",
        "order_prefix": "FV",
        "pi_prefix": "FVPI",
        "order_counter": "order_number_fragvansh",
        "pi_counter": "pi_number_fragvansh",
        "logo": ROOT_DIR / "assets" / "fragvansh_logo.png",
        "logo_pdf": ROOT_DIR / "assets" / "fragvansh_logo.png",
    },
}


def company_of(doc) -> dict:
    """Company profile for an order/PI, defaulting to CitSpray.

    Documents created before the second company existed have no `company`
    key, so they resolve to CitSpray and keep printing exactly as before.
    """
    key = (doc or {}).get("company") if isinstance(doc, dict) else doc
    return COMPANIES.get(str(key or "").strip().lower(), COMPANIES[DEFAULT_COMPANY])


BANK_FRAGVANSH = {
    "account_name": "FragVansh",
    "account_no": "1472002100033922",
    "ifsc": "PUNB0147200",
    "bank": "Punjab National Bank",
    "branch": "Khamla, Nagpur",
    "upi_string": "upi://pay?pa=arnavagrawal22@okicici&mam=1&am={amount}&cu=INR",
}


def company_bank(company: dict, gst_applicable: bool) -> dict:
    """Bank block for a company's PI.

    Non-GST PIs use the personal account whatever the company; GST PIs use
    the respective company's account.
    """
    if not gst_applicable:
        return BANK_NON_GST
    return BANK_FRAGVANSH if company["key"] == "fragvansh" else BANK_GST


async def next_document_number(company: dict, kind: str) -> str:
    """Next order/PI number for a company, from that company's own counter."""
    counter_id = company["order_counter"] if kind == "order" else company["pi_counter"]
    prefix = company["order_prefix"] if kind == "order" else company["pi_prefix"]
    counter = await db.counters.find_one_and_update(
        {"_id": counter_id}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    return f"{prefix}-{counter['seq']:04d}"


COURIER_OPTIONS = ["DTDC", "Anjani", "Amazon", "Shiprocket", "Delhivery", "Delhivery B2B", "India Post", "Others"]

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
    "account_name": "Mrs. Lata Agrawal",
    "account_no": "1472000100430026",
    "ifsc": "PUNB0147200",
    "bank": "Punjab National Bank",
    "branch": "Khamla, Nagpur",
    "upi_string": "upi://pay?pa=citsprayhr@okicici&mam=1&am={amount}&cu=INR",
}
BANK_ARNAV = {                       # previous non-GST account, selectable by admins
    "account_name": "Arnav Mukul Agrawal",
    "account_no": "1472000100369074",
    "ifsc": "PUNB0147200",
    "bank": "Punjab National Bank",
    "branch": "Khamla, Nagpur",
    "upi_string": "upi://pay?pa=citronellaoilnagpur-2@okaxis&mam=1&am={amount}&cu=INR",
}

# Every selectable bank account, for the admin-only picker on a PI. A PI with
# no bank_account key keeps today's automatic choice (company + GST rules).
BANK_ACCOUNTS = {
    "citspray_gst":    {"label": "Mangalam Agro (GST a/c)",       "details": None},
    "citspray_nongst": {"label": "Mrs. Lata Agrawal (non-GST)",   "details": None},
    "arnav_personal":  {"label": "Arnav Agrawal (old non-GST)",   "details": None},
    "fragvansh":       {"label": "FragVansh",                     "details": None},
}


def _bank_by_key(key: str):
    return {"citspray_gst": BANK_GST, "citspray_nongst": BANK_NON_GST,
            "arnav_personal": BANK_ARNAV, "fragvansh": BANK_FRAGVANSH}.get(key)


# The three slots an admin can point at any account, from Settings. A slot
# with no mapping keeps its historical default. Non-GST PIs use the personal
# account whatever the company; GST PIs use the respective company's account.
BANK_SLOTS = {
    "citspray_gst":    {"label": "CitSpray - GST PIs",          "default": "citspray_gst"},
    "citspray_nongst": {"label": "Non-GST PIs (all companies)", "default": "citspray_nongst"},
    "fragvansh":       {"label": "FragVansh - GST PIs",         "default": "fragvansh"},
}


def _bank_slot_for(company: dict, gst_applicable: bool) -> str:
    if not gst_applicable:
        return "citspray_nongst"
    return "fragvansh" if company["key"] == "fragvansh" else "citspray_gst"


async def resolve_pi_bank(pi: dict, company: dict, gst_applicable: bool) -> dict:
    """Bank block for a PI PDF, from the admin's Settings mapping.

    One global mapping per slot (CitSpray GST / CitSpray non-GST / FragVansh),
    applied to every PI. Unset or invalid mappings fall back to the slot's
    historical default, so existing documents render unchanged.
    """
    slot = _bank_slot_for(company, gst_applicable)
    settings = await db.settings.find_one({"_id": "global"}) or {}
    mapping = settings.get("bank_mapping") or {}
    return (_bank_by_key(str(mapping.get(slot) or ""))
            or _bank_by_key(BANK_SLOTS[slot]["default"])
            or company_bank(company, gst_applicable))

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
    discount: float = 0                 # per-item discount, used in "items" mode
    discount_is_percent: bool = False

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


# Only this OMS user may attach an order-level discount, and only its orders
# skip the grand-total round-up. Telecallers have no discount field at all.
WEBSITE_USERNAME = "website"


def carrier_risk_allowed(req) -> bool:
    """Carrier risk is a DTDC-only charge and is never applied automatically.

    Guards the stored value so it cannot end up on another courier if a client
    sends it - it is a real charge to the customer, not a default.
    """
    if not bool(getattr(req, "carrier_risk_applicable", False)):
        return False
    if (getattr(req, "shipping_method", "") or "").strip().lower() not in ("", "courier"):
        return False
    return (getattr(req, "courier_name", "") or "").strip().upper() == "DTDC"


def compute_manual_discount(req, items: list, subtotal: float, total_gst: float):
    """(discount, discount_gst) for a manually entered discount, pre-GST.

    Callers emit it as a negative additional-charge row - the same shape the
    website discount uses - so screens and PDFs render it with no changes.
    GST reversal is exact per item rate in items mode and pro-rata in total
    mode; both give GST-charged-on-the-discounted-value semantics. Discounts
    are capped so a document can never go negative.
    """
    if not getattr(req, "discount_enabled", False) or subtotal <= 0:
        return 0.0, 0.0
    gst_on = bool(getattr(req, "gst_applicable", False))
    if (getattr(req, "discount_mode", "total") or "total").lower() == "items":
        disc = gst_rev = 0.0
        for src, d in zip(req.items, items):
            v = float(getattr(src, "discount", 0) or 0)
            if v <= 0:
                continue
            amt = float(d.get("amount") or 0)
            di = amt * v / 100 if getattr(src, "discount_is_percent", False) else v
            di = min(round(di, 2), amt)
            disc += di
            if gst_on and d.get("gst_rate"):
                gst_rev += di * float(d["gst_rate"]) / 100
        return round(disc, 2), round(gst_rev, 2)
    v = float(getattr(req, "discount_value", 0) or 0)
    if v <= 0:
        return 0.0, 0.0
    disc = subtotal * v / 100 if getattr(req, "discount_is_percent", False) else v
    disc = min(round(disc, 2), round(subtotal, 2))
    gst_rev = round(total_gst * (disc / subtotal), 2) if (gst_on and total_gst > 0) else 0.0
    return disc, gst_rev


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
    company: str = DEFAULT_COMPANY   # which business this document belongs to
    # Manual discount, off unless ticked in the form. Mode "total" or "items";
    # value/is_percent apply to total mode, per-item fields to items mode.
    discount_enabled: bool = False
    discount_mode: str = "total"
    discount_value: float = 0
    discount_is_percent: bool = False
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
    is_cod: bool = False
    cod_amount: float = 0          # blank means collect whatever is outstanding
    amount_paid: float = 0
    discount: float = 0            # ex-GST discount; ONLY honoured for the website user
    discount_label: str = ""       # e.g. "Discount (WELCOME10)"
    payment_screenshots: List[str] = []
    mode_of_payment: str = ""
    payment_mode_details: str = ""
    billing_address_id: str = ""
    shipping_address_id: str = ""
    extra_shipping_details: str = ""
    # Carrier the telecaller picked from Shiprocket's live quote while making the
    # order: {courier_id, name, rate, weight_kg, cod, quoted_at}. Booking preselects it.
    shiprocket_courier: Optional[dict] = None
    # Set by the CRM for website orders: the Shopify order this one mirrors.
    shopify_order_id: str = ""
    shopify_order_name: str = ""

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
    company: str = DEFAULT_COMPANY   # which business this document belongs to
    # Manual discount, off unless ticked in the form. Mode "total" or "items";
    # value/is_percent apply to total mode, per-item fields to items mode.
    discount_enabled: bool = False
    discount_mode: str = "total"
    discount_value: float = 0
    discount_is_percent: bool = False
    bank_account: str = ""           # admin-chosen bank for the PDF; blank = automatic
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
PASSWORD_MAX_AGE_DAYS = 365


def check_password_policy(password: str):
    """12+ characters with upper and lower case, a digit and a special character.
    Applied whenever a password is set or changed; existing logins are not interrupted."""
    pw = password or ""
    problems = []
    if len(pw) < 12:
        problems.append("at least 12 characters")
    if not re.search(r"[a-z]", pw) or not re.search(r"[A-Z]", pw):
        problems.append("upper and lower case letters")
    if not re.search(r"\d", pw):
        problems.append("a number")
    if not re.search(r"[^A-Za-z0-9]", pw):
        problems.append("a special character")
    if problems:
        raise HTTPException(status_code=400, detail="Password needs " + ", ".join(problems) + ".")


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
async def login(req: LoginRequest, request: Request):
    ip = _client_ip(request)
    await _login_guard(req.username, ip)
    user = await db.users.find_one({"username": req.username}, {"_id": 0})
    if not user or not verify_password(req.password, user["password_hash"]):
        await _login_failed(req.username, ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("active", True):
        raise HTTPException(status_code=401, detail="Account is deactivated")
    changed = user.get("password_changed_at") or user.get("created_at") or ""
    try:
        pw_age = (datetime.now(timezone.utc) - datetime.fromisoformat(changed)).days if changed else None
    except ValueError:
        pw_age = None
    pw_expired = pw_age is not None and pw_age > PASSWORD_MAX_AGE_DAYS
    await _sec_log("login_ok", username=user["username"], role=user["role"], ip=ip, password_expired=pw_expired)
    token = create_token(user["id"], user["role"], user["name"], user["username"])
    return {
        "token": token,
        "user": {
            "id": user["id"], "username": user["username"],
            "name": user["name"], "role": user["role"]
        },
        "password_expired": pw_expired,
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
    check_password_policy(req.password)
    user_doc = {
        "id": str(uuid.uuid4()),
        "username": req.username,
        "password_hash": hash_password(req.password),
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
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
        check_password_policy(req.password)
        update["password_hash"] = hash_password(req.password)
        update["password_changed_at"] = datetime.now(timezone.utc).isoformat()
        await _sec_log("password_changed", username=admin.get("username"), target_user_id=user_id)
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

@api_router.get("/settings/bank-mapping")
async def get_bank_mapping(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    settings = await db.settings.find_one({"_id": "global"}) or {}
    mapping = settings.get("bank_mapping") or {}
    return {"slots": [{"slot": k, "label": v["label"],
                       "current": mapping.get(k) or v["default"],
                       "default": v["default"]}
                      for k, v in BANK_SLOTS.items()]}


@api_router.put("/settings/bank-mapping")
async def set_bank_mapping(body: dict, user=Depends(get_current_user)):
    """Admin-only: point each PI slot at a bank account, applied globally."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    mapping = {}
    for slot in BANK_SLOTS:
        key = str((body or {}).get(slot) or "").strip()
        if key:
            if not _bank_by_key(key):
                raise HTTPException(status_code=400, detail=f"Unknown account '{key}'")
            mapping[slot] = key
    await db.settings.update_one({"_id": "global"},
                                 {"$set": {"bank_mapping": mapping}}, upsert=True)
    return {"ok": True, "bank_mapping": mapping}


@api_router.get("/bank-accounts")
async def list_bank_accounts(user=Depends(get_current_user)):
    """Accounts an admin may put on a PI. Admin-only by design."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    out = []
    for key, meta in BANK_ACCOUNTS.items():
        d = _bank_by_key(key)
        out.append({"key": key, "label": meta["label"],
                    "account_no": d["account_no"], "bank": d["bank"]})
    return out


@api_router.get("/companies")
async def list_companies(user=Depends(get_current_user)):
    """Selectable companies for the order and PI forms."""
    return [{"key": c["key"], "label": c["label"], "brand": c["brand"],
             "order_prefix": c["order_prefix"], "gstin": c["gstin"],
             "is_default": c["key"] == DEFAULT_COMPANY,
             "configured": bool(c["gstin"])}
            for c in COMPANIES.values()]


# Order Routes
@api_router.post("/orders")
async def create_order(req: OrderCreate, user=Depends(get_current_user)):
    company = company_of({"company": req.company})
    order_number = await next_document_number(company, "order")
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

    # Website-only order discount. Telecallers cannot send this: the field is
    # ignored for every other user, so there is nothing to abuse from the UI.
    is_website = str(user.get("username") or "").strip().lower() == WEBSITE_USERNAME
    discount = 0.0
    discount_gst = 0.0
    if is_website and float(req.discount or 0) > 0 and subtotal > 0:
        discount = min(round(float(req.discount), 2), round(subtotal, 2))
        if req.gst_applicable and total_gst > 0:
            discount_gst = round(total_gst * (discount / subtotal), 2)
        # Emitted as a negative additional-charge row so the existing invoice
        # and order screens render it with no frontend change.
        additional_charges.append({
            "name": (req.discount_label or "Discount").strip(),
            "amount": -discount,
            "gst_percent": 0,
            "gst_amount": -discount_gst,
        })
        raw_total -= discount + discount_gst

    # Manual discount (admin/telecaller form). Stored in the same fields as the
    # website discount, so the edit guard preserves it identically.
    if not is_website:
        mdisc, mdisc_gst = compute_manual_discount(req, items, subtotal, total_gst)
        if mdisc > 0:
            discount, discount_gst = mdisc, mdisc_gst
            additional_charges.append({"name": "Discount", "amount": -mdisc,
                                       "gst_percent": 0, "gst_amount": -mdisc_gst})
            raw_total -= mdisc + mdisc_gst

    # Website orders must match the amount the customer actually paid online,
    # so they are never rounded up. Manual orders keep the round-to-rupee.
    grand_total = round(raw_total, 2) if is_website else math.ceil(raw_total)

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
        "company": company["key"],
        "customer_id": req.customer_id,
        "customer_name": customer["name"],
        "purpose": req.purpose,
        "items": items,
        "gst_applicable": req.gst_applicable,
        "shipping_method": shipping_method,
        "courier_name": courier_name,
        "transporter_name": transporter_name,
        "shiprocket_courier": req.shiprocket_courier if courier_name == "Shiprocket" else None,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "additional_charges": additional_charges,
        "carrier_risk_applicable": carrier_risk_allowed(req),
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst + total_additional_gst - discount_gst, 2),
        "grand_total": grand_total,
        "discount": discount,
        "website_order": is_website,
        "shopify_order_id": (req.shopify_order_id or "").strip(),
        "shopify_order_name": (req.shopify_order_name or "").strip(),
        "discount_enabled": (not is_website) and bool(req.discount_enabled),
        "discount_mode": req.discount_mode or "total",
        "discount_value": float(req.discount_value or 0),
        "discount_is_percent": bool(req.discount_is_percent),
        "discount_gst": discount_gst,
        "remark": req.remark,
        "status": "new",
        "payment_status": req.payment_status,
        "is_cod": bool(req.is_cod),
        "cod_amount": round(float(req.cod_amount or 0), 2),
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

# Payment fields accounts may edit. Everything else on an order stays with
# admin and the owning telecaller.
PAYMENT_FIELDS = {"payment_status", "amount_paid", "balance_amount",
                  "mode_of_payment", "payment_mode_details", "payment_screenshots"}


@api_router.put("/orders/{order_id}")
async def update_order(order_id: str, updates: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller", "accounts"]:
        raise HTTPException(status_code=403,
                            detail="Only admin, telecaller or accounts can edit orders")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if user["role"] == "accounts":
        # Accounts reconcile payments; they must not touch items, pricing or
        # dispatch. Anything outside the payment set is refused outright rather
        # than silently dropped, so a blocked edit is visible.
        outside = set(updates.keys()) - PAYMENT_FIELDS - {"id", "order_number", "updated_at"}
        if outside:
            raise HTTPException(
                status_code=403,
                detail="Accounts can only update payment details, not: "
                       + ", ".join(sorted(outside)))

    # Formulation lock: if order has any formulation, only admin can edit (unless
    # approved). A payment-only edit cannot touch a formulation, so recording a
    # payment is not blocked by it - accounts are restricted to payment fields
    # anyway, and this is the same set the dispatched-order rule already allows.
    payment_only = bool(updates) and not (
        set(updates.keys()) - PAYMENT_FIELDS - {"id", "order_number", "updated_at"})
    has_approved_permission = False
    if user["role"] != "admin" and not payment_only:
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
        allowed_dispatched = set(PAYMENT_FIELDS)
        non_allowed = set(updates.keys()) - allowed_dispatched - {"id", "order_number", "updated_at"}
        if non_allowed:
            raise HTTPException(status_code=400, detail="Order is dispatched. Only payment details can be updated.")
    # Telecaller can only edit their own orders (unless admin-approved permission)
    if user["role"] == "telecaller" and order.get("telecaller_id") != user["id"] and not has_approved_permission:
        raise HTTPException(status_code=403, detail="You can only edit your own orders")
    updates.pop("id", None)
    updates.pop("order_number", None)

    # Discounts are website-only and cannot be created or altered by an edit.
    # Every negative charge the client sent is dropped, then the order's own
    # stored discount is re-attached, so a routine edit can neither invent a
    # discount nor silently delete the one the customer already received.
    stored_disc = round(float(order.get("discount") or 0), 2)
    stored_disc_gst = round(float(order.get("discount_gst") or 0), 2)

    # Manual discounts are editable from the edit screen. Website discounts
    # stay locked: they must keep matching what the customer paid online. An
    # order whose stored discount predates the config fields is treated as
    # website too, which fails safe (locked rather than silently editable).
    website_locked = bool(order.get("website_order")) or (
        stored_disc > 0 and "discount_enabled" not in order)
    manual_edit = (not website_locked) and ("discount_enabled" in updates)
    if manual_edit:
        line_items = updates.get("items") or order.get("items") or []
        _sub = round(sum(float(i.get("amount") or 0) for i in line_items), 2)
        _igst = round(sum(float(i.get("gst_amount") or 0) for i in line_items), 2)
        import types as _t
        shim = _t.SimpleNamespace(
            discount_enabled=bool(updates.get("discount_enabled")),
            discount_mode=str(updates.get("discount_mode") or "total"),
            discount_value=float(updates.get("discount_value") or 0),
            discount_is_percent=bool(updates.get("discount_is_percent")),
            gst_applicable=bool(updates.get("gst_applicable",
                                            order.get("gst_applicable"))),
            items=[_t.SimpleNamespace(
                discount=float(i.get("discount") or 0),
                discount_is_percent=bool(i.get("discount_is_percent")))
                for i in line_items])
        stored_disc, stored_disc_gst = compute_manual_discount(shim, line_items, _sub, _igst)
        updates["discount"] = stored_disc
        updates["discount_gst"] = stored_disc_gst
        updates["discount_label"] = "Discount"
        if "additional_charges" not in updates:
            updates["additional_charges"] = [
                c for c in (order.get("additional_charges") or [])
                if float(c.get("amount") or 0) >= 0]
    if "additional_charges" in updates:
        cleaned = [c for c in (updates.get("additional_charges") or [])
                   if float(c.get("amount") or 0) >= 0]
        if stored_disc > 0:
            cleaned.append({
                "name": order.get("discount_label") or "Discount",
                "amount": -stored_disc,
                "gst_percent": 0,
                "gst_amount": -stored_disc_gst,
            })
        updates["additional_charges"] = cleaned

    if stored_disc > 0 or manual_edit:
        # The edit screen cannot compute the discount authoritatively, so the
        # figure is rebuilt here: website orders keep exact paise to match
        # what was paid online, manual orders keep the round-up-to-rupee.
        updates["discount"] = stored_disc
        updates["discount_gst"] = stored_disc_gst
        charges = updates.get("additional_charges") or order.get("additional_charges") or []
        line_items = updates.get("items") or order.get("items") or []
        sub_amt = round(sum(float(i.get("amount") or 0) for i in line_items), 2)
        item_gst = round(sum(float(i.get("gst_amount") or 0) for i in line_items), 2)
        ship = float(updates.get("shipping_charge", order.get("shipping_charge") or 0) or 0)
        ship_gst = float(updates.get("shipping_gst", order.get("shipping_gst") or 0) or 0)
        add_amt = round(sum(float(c.get("amount") or 0) for c in charges), 2)
        add_gst = round(sum(float(c.get("gst_amount") or 0) for c in charges), 2)
        gt = round(sub_amt + item_gst + ship + ship_gst + add_amt + add_gst, 2)
        if not website_locked:
            gt = float(math.ceil(gt))
        updates["subtotal"] = sub_amt
        updates["total_gst"] = round(item_gst + ship_gst + add_gst, 2)
        updates["grand_total"] = gt
        pstatus = updates.get("payment_status", order.get("payment_status"))
        paid = float(updates.get("amount_paid", order.get("amount_paid") or 0) or 0)
        if pstatus == "full":
            updates["amount_paid"] = gt
            updates["balance_amount"] = 0
        elif pstatus == "partial":
            updates["balance_amount"] = round(max(0.0, gt - paid), 2)
        else:
            updates["balance_amount"] = gt

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

    # Moving an order to the other company renumbers it into that company's
    # series (CS-xxxx <-> FV-xxxx). The old number is kept in renumber_history
    # so anything already quoting it can still be traced. A courier booking
    # holds the old number as its customer reference and is not rewritten.
    if "company" in updates:
        new_key = company_of({"company": updates["company"]})["key"]
        updates["company"] = new_key
        if new_key != company_of(order)["key"]:
            old_number = order.get("order_number") or ""
            updates["order_number"] = await next_document_number(
                COMPANIES[new_key], "order")
            updates["renumber_history"] = (order.get("renumber_history") or []) + [{
                "from": old_number, "to": updates["order_number"],
                "at": datetime.now(timezone.utc).isoformat(), "by": user["name"],
            }]

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
class UndispatchRequest(BaseModel):
    reason: str = ""


@api_router.post("/orders/{order_id}/undispatch")
async def undispatch_order(order_id: str, req: UndispatchRequest,
                           user=Depends(get_current_user)):
    """Admin-only reversal of a mistaken dispatch.

    Moves the order back to packaging and clears the dispatch record, archiving
    it in undispatch_log so nothing is destroyed. Deliberately does NOT touch
    any courier booking (Amazon/DTDC shipment records stay) - a booked parcel
    must be cancelled with the courier, not by editing our status.
    """
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") != "dispatched":
        raise HTTPException(status_code=400, detail="Order is not dispatched")
    now = datetime.now(timezone.utc).isoformat()
    log = (order.get("undispatch_log") or []) + [{
        "at": now, "by": user["name"],
        "reason": (req.reason or "").strip() or "Dispatched by mistake",
        "previous_dispatch": order.get("dispatch") or {},
    }]
    await db.orders.update_one({"id": order_id}, {
        "$set": {"status": "packaging", "dispatch": {},
                 "undispatch_log": log, "updated_at": now},
        "$unset": {"dispatched_at": ""}})
    return {"ok": True, "status": "packaging",
            "had_courier_booking": bool((order.get("amazon_shipment") or {}).get("shipment_id")
                                        or (order.get("dtdc_shipment") or {}).get("reference_number"))}


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
    # ── Stale-save protection ──
    # The same order is often open on the packing phone and on an admin's
    # screen at once. A save from an editor opened BEFORE someone else's change
    # must not wipe what arrived in between (CS-1643, 2026-09-24: a photo save
    # blanked the weight that had been entered and booked meanwhile). When the
    # client says what it loaded and that is no longer current, photos are
    # merged instead of replaced; a weight is never blanked by an empty field.
    loaded_at = str(updates.get("loaded_at") or "")
    stale = bool(loaded_at) and loaded_at != str(order.get("updated_at") or "")
    if stale:
        logging.info(f"packaging save by {user['name']} on {order.get('order_number')} is stale (loaded {loaded_at}); merging")

    def _merge_list(old, new):
        new = list(new or [])
        return new + [x for x in (old or []) if x not in new]

    _before = {"item": dict(packaging.get("item_images") or {}), "order": list(packaging.get("order_images") or []),
               "box": list(packaging.get("packed_box_images") or [])}
    if "item_images" in updates:
        inc = dict(updates["item_images"] or {})
        if stale:
            merged = dict(packaging.get("item_images") or {})
            for k, v in inc.items():
                merged[k] = _merge_list(merged.get(k), v)
            inc = merged
        packaging["item_images"] = inc
    if "order_images" in updates:
        packaging["order_images"] = _merge_list(packaging.get("order_images"), updates["order_images"]) if stale else updates["order_images"]
    if "packed_box_images" in updates:
        packaging["packed_box_images"] = _merge_list(packaging.get("packed_box_images"), updates["packed_box_images"]) if stale else updates["packed_box_images"]
    # Photo recycle bin: every reference this save drops is kept on the order.
    _now = datetime.now(timezone.utc).isoformat()
    _trash = list(packaging.get("image_trash") or [])
    for k, urls in _before["item"].items():
        for u in urls:
            if u not in ((packaging.get("item_images") or {}).get(k) or []):
                _trash.append({"url": u, "group": "item", "key": k, "removed_at": _now, "by": user["name"]})
    for grp, field in (("order", "order_images"), ("box", "packed_box_images")):
        for u in _before[grp]:
            if u not in (packaging.get(field) or []):
                _trash.append({"url": u, "group": grp, "key": "", "removed_at": _now, "by": user["name"]})
    if _trash:
        packaging["image_trash"] = _trash[-60:]
    # Who packed is recorded by the My Work tracker (PIN), never picked by hand.
    # Only an admin may set names directly, as an override for exceptions.
    if user["role"] == "admin":
        for _f in ("item_packed_by", "box_packed_by", "checked_by"):
            if _f in updates:
                packaging[_f] = updates[_f]
    # Names recorded by the work tracker are authoritative and merged in here.
    # Orders the tracker never touched skip this entirely.
    _tracked = await _work_names_for_order(order_id)
    if any(_tracked.values()) or packaging.get("tracker_added"):
        _work_merge_packed_by(packaging, _tracked)
    if "num_boxes" in updates and not (stale and not str(updates["num_boxes"] or "").strip()):
        packaging["num_boxes"] = updates["num_boxes"]
    # Box dimensions in cm. Optional for DTDC/Amazon, but India Post prices on
    # the greater of actual and volumetric weight and rejects parcels booked
    # without them, so packing can record them at the same time as the weight.
    for dim in ("length_cm", "breadth_cm", "height_cm"):
        if dim in updates:
            packaging[dim] = updates[dim]
    # An empty weight from the form never erases a weight already on the order
    # (that weight may already be booked with a courier). Clearing it on
    # purpose needs an explicit clear_weight flag.
    if "weight_kg" in updates and not str(updates["weight_kg"] or "").strip() \
            and str(packaging.get("weight_kg") or "").strip() and not updates.get("clear_weight"):
        logging.info(f"packaging save by {user['name']} on {order.get('order_number')}: kept weight {packaging.get('weight_kg')} (form sent empty)")
        updates = {k: v for k, v in updates.items() if k != "weight_kg"}
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
        _work_require_tracked(packaging, user)
        if order.get("shipping_method") == "courier" and not str(packaging.get("weight_kg", "")).strip():
            raise HTTPException(status_code=400, detail="Weight (KG) is required for courier orders before marking packed")
        packaging["packed_at"] = datetime.now(timezone.utc).isoformat()

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"packaging": packaging, "status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if new_status == "packed":
        await _work_finish_order(order_id, "order")
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
    _tracked = await _work_names_for_order(order_id)
    if any(_tracked.values()) or packaging.get("tracker_added"):
        _work_merge_packed_by(packaging, _tracked)
    _work_require_tracked(packaging, user)
    if order.get("shipping_method") == "courier" and not str(packaging.get("weight_kg", "")).strip():
        raise HTTPException(status_code=400, detail="Weight (KG) is required for courier orders before marking packed")
    packaging["packed_at"] = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one({"id": order_id}, {"$set": {"status": "packed", "packaging": packaging, "updated_at": datetime.now(timezone.utc).isoformat()}})
    await _work_finish_order(order_id, "order")
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


class RestoreImagesRequest(BaseModel):
    urls: Optional[List[str]] = None       # none = restore everything in the bin


@api_router.post("/orders/{order_id}/packaging/restore-images")
async def restore_packaging_images(order_id: str, req: RestoreImagesRequest = RestoreImagesRequest(), user=Depends(get_current_user)):
    """Put removed photos back where they were (admin / packaging)."""
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Packaging or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    pkg = order.get("packaging") or {}
    trash = list(pkg.get("image_trash") or [])
    if not trash:
        return {"ok": True, "restored": 0}
    want = set(req.urls or [t["url"] for t in trash])
    keep, restored = [], 0
    for t in trash:
        if t["url"] not in want:
            keep.append(t)
            continue
        if t["group"] == "item":
            imgs = dict(pkg.get("item_images") or {})
            lst = list(imgs.get(t["key"]) or [])
            if t["url"] not in lst:
                lst.append(t["url"])
            imgs[t["key"]] = lst
            pkg["item_images"] = imgs
        else:
            field = "order_images" if t["group"] == "order" else "packed_box_images"
            lst = list(pkg.get(field) or [])
            if t["url"] not in lst:
                lst.append(t["url"])
            pkg[field] = lst
        restored += 1
    pkg["image_trash"] = keep
    await db.orders.update_one({"id": order_id}, {"$set": {"packaging": pkg, "updated_at": datetime.now(timezone.utc).isoformat()}})
    logging.info(f"{user['name']} restored {restored} photo(s) on {order.get('order_number')}")
    return {"ok": True, "restored": restored}


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
    from pypdf import PdfReader, PdfWriter
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
    # Same roles the All Orders page shows the button to.
    if user["role"] not in ["admin", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized to print addresses")

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
        company = company_of(order)

        # ── 1. HEADER ──
        logo_cell = ''
        logo_src = (str(company["logo_pdf"]) if company["logo_pdf"].exists()
                    else str(company["logo"]))
        if Path(logo_src).exists():
            try:
                tmp = Image(logo_src)
                aspect = tmp.imageHeight / tmp.imageWidth
                logo_h = 28*mm * aspect
                logo_cell = Image(logo_src, width=28*mm, height=logo_h)
            except Exception:
                pass

        co_info = Paragraph(
            f"<b><font size=11>{company['name']}</font></b><br/>"
            f"<font size=8 color='#15803D'><i>{company['brand']}</i></font><br/>"
            f"<font size=7 color='#6B7280'>{company['address']}</font><br/>"
            f"<font size=7 color='#6B7280'>Ph: {company['mobile']} | {company['email']}</font>",
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


# ═══════════════════════════════════════════════════════════════════════════
# PACKING WORK TRACKER
# A separate module: its own collections (work_sessions, staff_pins), its own
# routes, and it never writes to orders or to the existing packing form data.
# Executives share two phones, so identity is name + PIN per action instead of
# a login. Steps mirror the packing form's three "by" fields plus weighing.
# ═══════════════════════════════════════════════════════════════════════════
WORK_STEPS = [
    {"key": "filling",  "label": "Filling material"},
    {"key": "boxing",   "label": "Making box & packing"},
    {"key": "checking", "label": "Checking"},
    {"key": "weighing", "label": "Weighing & label"},
]
WORK_STEP_LABEL = {s["key"]: s["label"] for s in WORK_STEPS}
# Work is never stopped mid-day: a job takes as long as it takes. The only
# automatic close is for a DONE that was forgotten overnight.
WORK_DAY_END_HOUR_IST = 20   # anything still running at 8 PM IST is closed and flagged
WORK_NUDGE_MIN = 0           # 0 = no "still working?" prompt
WORK_AUTO_CLOSE_MIN = 0
WORK_VIEW_ROLES = ["admin", "dispatch", "accounts"]
WORK_DO_ROLES = ["packaging", "admin", "dispatch"]
IST = timezone(timedelta(hours=5, minutes=30))


def _work_now() -> datetime:
    return datetime.now(timezone.utc)


def _work_day_bounds(day: Optional[str]):
    """(utc_start_iso, utc_end_iso, day_str) for an IST calendar day."""
    d = datetime.fromisoformat(day).date() if day else datetime.now(IST).date()
    start = datetime(d.year, d.month, d.day, tzinfo=IST)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat(), d.isoformat()


def _work_public(sess: dict) -> dict:
    """Session with a live duration and the step label filled in."""
    out = {k: v for k, v in sess.items() if k != "_id"}
    started = datetime.fromisoformat(sess["started_at"])
    if sess.get("ended_at"):
        end = datetime.fromisoformat(sess["ended_at"])
    else:
        end = _work_now()
    out["duration_sec"] = max(0, int((end - started).total_seconds()))
    out["step_label"] = "Amazon order" if sess.get("kind") == "amazon" else WORK_STEP_LABEL.get(sess.get("step") or "", "")
    if sess.get("status") == "active" and sess.get("last_confirmed_at"):
        since = (_work_now() - datetime.fromisoformat(sess["last_confirmed_at"])).total_seconds()
        out["needs_confirm"] = bool(WORK_NUDGE_MIN) and since >= WORK_NUDGE_MIN * 60
    return out


# The tracker fills the packing form's three "by" fields, so nobody picks
# names by hand. Weighing has no field of its own.
WORK_STEP_TO_FIELD = {"filling": "item_packed_by", "boxing": "box_packed_by", "checking": "checked_by"}
# Only a genuine mis-tap is ignored. Logging a step that was physically done a
# moment earlier takes well under half a minute and must still be credited.
WORK_MIN_COUNTED_SEC = 5


async def _work_names_for_order(order_id: str) -> dict:
    """{field: [names]} from the tracker: finished work of 30 s+, plus anything running."""
    out = {f: [] for f in WORK_STEP_TO_FIELD.values()}
    async for sess in db.work_sessions.find({"order_id": order_id, "kind": "order"},
                                            {"_id": 0}).sort("started_at", 1):
        field = WORK_STEP_TO_FIELD.get(sess.get("step") or "")
        if not field:
            continue
        if sess.get("status") != "active" and int(sess.get("duration_sec") or 0) < WORK_MIN_COUNTED_SEC:
            continue
        if sess["staff"] not in out[field]:
            out[field].append(sess["staff"])
    return out


def _work_merge_packed_by(packaging: dict, tracked: dict) -> dict:
    """Hand-picked names stay; names the tracker added earlier are replaced by
    what it says now (so a corrected entry propagates). Mutates and returns."""
    prev_auto = packaging.get("tracker_added") or {}
    for field, names in tracked.items():
        manual = [n for n in (packaging.get(field) or []) if n not in (prev_auto.get(field) or [])]
        packaging[field] = manual + [n for n in names if n not in manual]
    packaging["tracker_added"] = tracked
    return packaging


WORK_FIELD_STEP = {"item_packed_by": "Filling material", "box_packed_by": "Making box & packing", "checked_by": "Checking"}


def _work_require_tracked(packaging: dict, user: dict):
    """An order cannot be marked packed until every step has a name, and names
    only come from My Work. Admins are exempt (phones down, genuine exceptions)."""
    if user.get("role") == "admin":
        return
    missing = [label for f, label in WORK_FIELD_STEP.items() if not packaging.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=(
            "Not started in My Work: " + ", ".join(missing) +
            ". Start it there with your PIN first, then mark packed."))


async def _work_amazon_names(amazon_order_id: str) -> list:
    names = []
    async for sess in db.work_sessions.find({"kind": "amazon", "order_id": amazon_order_id},
                                            {"_id": 0}).sort("started_at", 1):
        if sess.get("status") != "active" and int(sess.get("duration_sec") or 0) < WORK_MIN_COUNTED_SEC:
            continue
        if sess["staff"] not in names:
            names.append(sess["staff"])
    return names


async def _work_sync_amazon(amazon_order_id: Optional[str]):
    """One executive does a whole Amazon order, so her name fills all three
    fields, and starting it moves the order from new to packaging."""
    if not amazon_order_id:
        return
    ao = await db.amazon_orders.find_one({"id": amazon_order_id}, {"_id": 0, "status": 1, "packaging": 1})
    if not ao or ao.get("status") in ("dispatched", "cancelled"):
        return
    names = await _work_amazon_names(amazon_order_id)
    packaging = dict(ao.get("packaging") or {})
    if not names and not packaging.get("tracker_added"):
        return
    _work_merge_packed_by(packaging, {f: list(names) for f in WORK_FIELD_STEP})
    upd = {**{f"packaging.{f}": packaging[f] for f in WORK_FIELD_STEP},
           "packaging.tracker_added": packaging["tracker_added"]}
    if names and ao.get("status") == "new":
        upd["status"] = "packaging"
    await db.amazon_orders.update_one({"id": amazon_order_id}, {"$set": upd})


async def _work_finish_order(order_id: str, kind: str):
    """Marking an order packed is the end of the work on it: whatever is still
    running there is closed at that moment, so nobody goes back to press DONE."""
    now = _work_now()
    for sess in await db.work_sessions.find({"status": "active", "kind": kind, "order_id": order_id},
                                            {"_id": 0}).to_list(50):
        await _work_close(sess, now, "done")


async def _work_sync_packed_by(order_id: Optional[str]):
    """Push tracker names onto the order. Dispatched/cancelled orders and
    orders the tracker never touched are left exactly as they are."""
    if not order_id:
        return
    order = await db.orders.find_one({"id": order_id}, {"_id": 0, "status": 1, "packaging": 1})
    if not order or order.get("status") in ("dispatched", "cancelled"):
        return
    tracked = await _work_names_for_order(order_id)
    packaging = dict(order.get("packaging") or {})
    if not any(tracked.values()) and not packaging.get("tracker_added"):
        return
    _work_merge_packed_by(packaging, tracked)
    # Dotted paths: only these four keys change, so a photo upload saved at
    # the same moment is never overwritten.
    await db.orders.update_one({"id": order_id}, {"$set": {
        **{f"packaging.{f}": packaging[f] for f in WORK_STEP_TO_FIELD.values()},
        "packaging.tracker_added": packaging["tracker_added"],
    }})


async def _work_close(sess: dict, ended: datetime, status: str, remark: Optional[str] = None):
    started = datetime.fromisoformat(sess["started_at"])
    if ended < started:
        ended = started
    fields = {
        "ended_at": ended.isoformat(),
        "duration_sec": int((ended - started).total_seconds()),
        "status": status,
    }
    remark = (remark or "").strip()
    if remark:
        fields["remark"] = remark[:300]     # what got done, e.g. "cleaned 40 diffusers"
    await db.work_sessions.update_one({"id": sess["id"]}, {"$set": fields})
    if sess.get("kind") == "order":
        await _work_sync_packed_by(sess.get("order_id"))
    elif sess.get("kind") == "amazon":
        await _work_sync_amazon(sess.get("order_id"))


async def _work_sweep():
    """Work is never cut off while someone is working. It ends by itself only
    when the person punches out on the attendance device (ended at the punch
    time) or at 8 PM IST of the day it started - whichever comes first."""
    now_ist = datetime.now(IST)
    running = await db.work_sessions.find({"status": "active"}, {"_id": 0}).to_list(300)
    if not running:
        return
    crm_map = await _crm_map_for_staff()
    for sess in running:
        started_ist = datetime.fromisoformat(sess["started_at"]).astimezone(IST)
        day_end = started_ist.replace(hour=WORK_DAY_END_HOUR_IST, minute=0, second=0, microsecond=0)
        if started_ist >= day_end:                      # started after 8 PM: give it until midnight
            day_end = started_ist.replace(hour=23, minute=59, second=0, microsecond=0)
        end_at, reason = (day_end, "day_end") if now_ist > day_end else (None, None)

        uid = crm_map.get(sess["staff"])
        if uid:
            log = await crm_db.attendance_logs.find_one(
                {"user_id": uid, "date": started_ist.strftime("%Y-%m-%d")}, {"_id": 0, "check_out": 1})
            out_raw = ((log or {}).get("check_out") or {}).get("time")
            if out_raw:
                try:
                    out_ist = datetime.fromisoformat(out_raw)
                    out_ist = out_ist.replace(tzinfo=IST) if out_ist.tzinfo is None else out_ist.astimezone(IST)
                    # a punch-out from before this work began is not about this work
                    if out_ist >= started_ist and (end_at is None or out_ist < end_at):
                        end_at, reason = out_ist, "punch_out"
                except ValueError:
                    pass
        if end_at:
            await db.work_sessions.update_one({"id": sess["id"]}, {"$set": {"auto_reason": reason}})
            await _work_close(sess, end_at.astimezone(timezone.utc), "auto_closed")


async def _work_staff_auth(name: str, pin: str) -> str:
    name = (name or "").strip()
    staff = await db.packaging_staff.find_one({"name": name, "active": True})
    if not staff:
        raise HTTPException(status_code=404, detail="Name not found")
    rec = await db.staff_pins.find_one({"name": name})
    if not rec:
        raise HTTPException(status_code=400, detail="No PIN set for this name. Ask admin to set it.")
    if not verify_password(str(pin or "").strip(), rec["pin_hash"]):
        raise HTTPException(status_code=403, detail="Wrong PIN")
    return name


def _work_require(user, roles):
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Not authorized")


class WorkPinRequest(BaseModel):
    name: str
    pin: str


class WorkStartRequest(BaseModel):
    name: str
    pin: str
    kind: str = "order"            # "order" | "other"
    order_id: Optional[str] = None
    step: Optional[str] = None
    note: Optional[str] = None
    device: Optional[str] = None   # which phone, free text


@api_router.get("/work/config")
async def work_config(user=Depends(get_current_user)):
    return {"steps": WORK_STEPS, "nudge_min": WORK_NUDGE_MIN, "auto_close_min": WORK_AUTO_CLOSE_MIN}


@api_router.get("/work/staff")
async def work_staff(user=Depends(get_current_user)):
    staff = await db.packaging_staff.find({"active": True}, {"_id": 0, "name": 1}).sort("name", 1).to_list(100)
    pins = {p["name"]: p for p in await db.staff_pins.find({}, {"_id": 0, "name": 1, "pin": 1, "pin_len": 1}).to_list(200)}
    is_admin = user["role"] == "admin"
    return [{"name": s["name"], "has_pin": s["name"] in pins,
             "pin_len": (pins.get(s["name"]) or {}).get("pin_len"),
             # Admins see the digits; PINs set before this field existed show
             # as None until reset.
             "pin": (pins.get(s["name"]) or {}).get("pin") if is_admin else None}
            for s in staff]


@api_router.put("/work/pin")
async def work_set_pin(req: WorkPinRequest, admin=Depends(require_admin)):
    """Admin sets or resets an executive's PIN (4-6 digits)."""
    pin = req.pin.strip()
    if not pin.isdigit() or len(pin) != 4:
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits")
    staff = await db.packaging_staff.find_one({"name": req.name.strip(), "active": True})
    if not staff:
        raise HTTPException(status_code=404, detail="Name not found")
    # The PIN alone identifies a person on the shared phones, so no two may match.
    async for other in db.staff_pins.find({"name": {"$ne": staff["name"]}}, {"_id": 0}):
        same = (other.get("pin") == pin) if other.get("pin") else verify_password(pin, other["pin_hash"])
        if same:
            raise HTTPException(status_code=409, detail="This PIN is already used by someone else. Pick another.")
    await db.staff_pins.update_one({"name": staff["name"]},
                                   {"$set": {"pin_hash": hash_password(pin),
                                             "pin": pin,   # admin-visible lookup
                                             "pin_len": len(pin),  # lets the keypad auto-submit
                                             "updated_at": _work_now().isoformat(),
                                             "updated_by": admin["name"]}}, upsert=True)
    return {"ok": True, "name": staff["name"]}


@api_router.post("/work/pin/check")
async def work_check_pin(req: WorkPinRequest, user=Depends(get_current_user)):
    _work_require(user, WORK_DO_ROLES)
    name = await _work_staff_auth(req.name, req.pin)
    return {"ok": True, "name": name}


@api_router.get("/work/orders")
async def work_orders(q: str = "", user=Depends(get_current_user)):
    """Orders an executive can pick: anything not yet dispatched or cancelled."""
    _work_require(user, WORK_DO_ROLES)
    query = {"status": {"$nin": ["dispatched", "cancelled"]}}
    q = (q or "").strip()
    if q:
        query["$or"] = [{"order_number": {"$regex": re.escape(q), "$options": "i"}},
                        {"customer_name": {"$regex": re.escape(q), "$options": "i"}}]
    orders = await db.orders.find(query, {
        "_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "status": 1,
        "items": 1, "packaging.weight_kg": 1, "shipping_address.city": 1,
    }).sort("created_at", -1).to_list(40)
    active = await db.work_sessions.find({"status": "active", "kind": "order"},
                                         {"_id": 0, "order_id": 1, "staff": 1, "step": 1}).to_list(100)
    busy = {}
    for a in active:
        busy.setdefault(a["order_id"], []).append(f"{a['staff']} ({WORK_STEP_LABEL.get(a.get('step') or '', '')})")
    return [{
        "id": o["id"], "order_number": o.get("order_number"), "customer_name": o.get("customer_name"),
        "status": o.get("status"), "items_count": len(o.get("items") or []),
        "weight_kg": (o.get("packaging") or {}).get("weight_kg") or "",
        "city": (o.get("shipping_address") or {}).get("city") or "",
        "working_now": busy.get(o["id"], []),
    } for o in orders]


@api_router.post("/work/start")
async def work_start(req: WorkStartRequest, user=Depends(get_current_user)):
    """Start a piece of work. Starting anything ends what that person was doing."""
    _work_require(user, WORK_DO_ROLES)
    name = await _work_staff_auth(req.name, req.pin)
    await _work_sweep()
    now = _work_now()
    doc = {"id": str(uuid.uuid4()), "staff": name, "kind": req.kind,
           "order_id": None, "order_number": None, "customer_name": None,
           "step": None, "note": None,
           "started_at": now.isoformat(), "last_confirmed_at": now.isoformat(),
           "ended_at": None, "duration_sec": None, "status": "active",
           "device": (req.device or "")[:40], "logged_in_as": user.get("username") or user.get("name")}
    if req.kind == "order":
        if not req.order_id or req.step not in WORK_STEP_LABEL:
            raise HTTPException(status_code=400, detail="Pick an order and a step")
        order = await db.orders.find_one({"id": req.order_id}, {"_id": 0, "order_number": 1, "customer_name": 1})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        doc.update({"order_id": req.order_id, "order_number": order.get("order_number"),
                    "customer_name": order.get("customer_name"), "step": req.step})
    elif req.kind == "other":
        note = (req.note or "").strip()
        if not note:
            raise HTTPException(status_code=400, detail="Say or type what work you are doing")
        doc["note"] = note[:200]
    else:
        raise HTTPException(status_code=400, detail="kind must be order or other")
    for prev in await db.work_sessions.find({"staff": name, "status": "active"}, {"_id": 0}).to_list(10):
        await _work_close(prev, now, "done")
    await db.work_sessions.insert_one(doc)
    if req.kind == "order":
        await _work_sync_packed_by(req.order_id)
    return {"ok": True, "session": _work_public(doc)}


class WorkStopRequest(BaseModel):
    name: str
    pin: str
    remark: Optional[str] = None


@api_router.post("/work/stop")
async def work_stop(req: WorkStopRequest, user=Depends(get_current_user)):
    _work_require(user, WORK_DO_ROLES)
    name = await _work_staff_auth(req.name, req.pin)
    now = _work_now()
    closed = []
    for sess in await db.work_sessions.find({"staff": name, "status": "active"}, {"_id": 0}).to_list(10):
        await _work_close(sess, now, "done", req.remark)
        closed.append(sess["id"])
    if not closed:
        raise HTTPException(status_code=400, detail="Nothing is running for you")
    return {"ok": True, "closed": closed}


@api_router.post("/work/confirm")
async def work_confirm(req: WorkPinRequest, user=Depends(get_current_user)):
    """The executive answered 'yes, still working' - resets the auto-close clock."""
    _work_require(user, WORK_DO_ROLES)
    name = await _work_staff_auth(req.name, req.pin)
    r = await db.work_sessions.update_many({"staff": name, "status": "active"},
                                           {"$set": {"last_confirmed_at": _work_now().isoformat()}})
    return {"ok": True, "confirmed": r.modified_count}


WORK_PIN_MAX_FAILS = 5
WORK_PIN_LOCK_MIN = 2


async def _work_pin_guard(key: str):
    doc = await db.work_pin_locks.find_one({"key": key})
    if doc and (doc.get("locked_until") or "") > _work_now().isoformat():
        raise HTTPException(status_code=429, detail="Too many wrong PINs. Wait 2 minutes.")


async def _work_pin_fail(key: str):
    doc = await db.work_pin_locks.find_one({"key": key}) or {}
    fails = int(doc.get("fails") or 0) + 1
    upd = {"fails": fails}
    if fails >= WORK_PIN_MAX_FAILS:
        upd = {"fails": 0, "locked_until": (_work_now() + timedelta(minutes=WORK_PIN_LOCK_MIN)).isoformat()}
    await db.work_pin_locks.update_one({"key": key}, {"$set": upd}, upsert=True)


async def _work_identify(pin: str, key: str) -> str:
    """Who owns this PIN. Guessing is rate-limited per phone login."""
    await _work_pin_guard(key)
    pin = str(pin or "").strip()
    active = {s["name"] for s in await db.packaging_staff.find({"active": True}, {"_id": 0, "name": 1}).to_list(200)}
    matches = []
    if pin.isdigit() and len(pin) >= 4:
        async for rec in db.staff_pins.find({}, {"_id": 0}):
            if rec["name"] not in active:
                continue
            # PINs set before the plain copy existed can only be hash-checked.
            ok = (rec.get("pin") == pin) if rec.get("pin") else verify_password(pin, rec["pin_hash"])
            if ok:
                matches.append(rec["name"])
    if len(matches) == 1:
        await db.work_pin_locks.delete_one({"key": key})
        return matches[0]
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Two people have this PIN. Ask admin to reset.")
    await _work_pin_fail(key)
    raise HTTPException(status_code=403, detail="Wrong PIN")


class WorkIdentifyRequest(BaseModel):
    pin: str
    device: Optional[str] = None


class WorkGroupStartRequest(BaseModel):
    members: List[WorkPinRequest]
    kind: str = "order"
    order_id: Optional[str] = None
    step: Optional[str] = None
    note: Optional[str] = None
    device: Optional[str] = None


class WorkGroupStopRequest(BaseModel):
    pin: str
    session_id: str
    device: Optional[str] = None
    remark: Optional[str] = None


def _work_lock_key(user: dict, device: Optional[str]) -> str:
    return f"{user.get('id') or user.get('username')}:{(device or '')[:40]}"


@api_router.post("/work/pin/identify")
async def work_identify(req: WorkIdentifyRequest, user=Depends(get_current_user)):
    """PIN-only sign-in for the shared phones: returns whose PIN it is and
    what that person is doing right now (starting new work will end it)."""
    _work_require(user, WORK_DO_ROLES)
    name = await _work_identify(req.pin, _work_lock_key(user, req.device))
    cur = await db.work_sessions.find_one({"staff": name, "status": "active"}, {"_id": 0})
    return {"ok": True, "name": name, "current": _work_public(cur) if cur else None}


@api_router.post("/work/start-group")
async def work_start_group(req: WorkGroupStartRequest, user=Depends(get_current_user)):
    """One task picked once, started for everyone who signed it with a PIN."""
    _work_require(user, WORK_DO_ROLES)
    if not req.members:
        raise HTTPException(status_code=400, detail="Nobody entered a PIN")
    names = []
    for m in req.members:
        n = await _work_staff_auth(m.name, m.pin)
        if n not in names:
            names.append(n)
    await _work_sweep()
    base = {"kind": req.kind, "order_id": None, "order_number": None, "customer_name": None,
            "step": None, "note": None}
    if req.kind == "order":
        if not req.order_id or req.step not in WORK_STEP_LABEL:
            raise HTTPException(status_code=400, detail="Pick an order and a step")
        order = await db.orders.find_one({"id": req.order_id}, {"_id": 0, "order_number": 1, "customer_name": 1})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        base.update({"order_id": req.order_id, "order_number": order.get("order_number"),
                     "customer_name": order.get("customer_name"), "step": req.step})
    elif req.kind == "amazon":
        ao = await db.amazon_orders.find_one({"id": req.order_id or ""}, {"_id": 0, "am_order_number": 1, "status": 1, "items": 1})
        if not ao:
            raise HTTPException(status_code=404, detail="Amazon order not found")
        if ao.get("status") in ("dispatched", "cancelled"):
            raise HTTPException(status_code=400, detail=f"This Amazon order is already {ao['status']}")
        base.update({"order_id": req.order_id, "order_number": ao.get("am_order_number"),
                     "customer_name": _work_amazon_summary(ao)})
    elif req.kind == "other":
        note = (req.note or "").strip()
        if not note:
            raise HTTPException(status_code=400, detail="Say or type what work you are doing")
        base["note"] = note[:200]
    else:
        raise HTTPException(status_code=400, detail="kind must be order, amazon or other")
    now = _work_now()
    group_id = str(uuid.uuid4())
    started = []
    for name in names:
        for prev in await db.work_sessions.find({"staff": name, "status": "active"}, {"_id": 0}).to_list(10):
            await _work_close(prev, now, "done")
        doc = {"id": str(uuid.uuid4()), "staff": name, **base, "group_id": group_id,
               "started_at": now.isoformat(), "last_confirmed_at": now.isoformat(),
               "ended_at": None, "duration_sec": None, "status": "active",
               "device": (req.device or "")[:40], "logged_in_as": user.get("username") or user.get("name")}
        await db.work_sessions.insert_one(dict(doc))
        started.append(_work_public(doc))
    if req.kind == "order":
        await _work_sync_packed_by(req.order_id)
    elif req.kind == "amazon":
        await _work_sync_amazon(req.order_id)
    return {"ok": True, "sessions": started}


def _work_amazon_summary(ao: dict) -> str:
    items = ao.get("items") or []
    text = ", ".join(f"{i.get('quantity')} x {(i.get('product_name') or '')[:38]}" for i in items[:2])
    return text + (f" +{len(items) - 2} more" if len(items) > 2 else "")


def _work_task_query(sess: dict) -> dict:
    """Everyone active on the same task: same order+step, or the same group for other work."""
    if sess.get("kind") == "amazon":
        return {"status": "active", "kind": "amazon", "order_id": sess["order_id"]}
    if sess.get("kind") == "order":
        return {"status": "active", "kind": "order", "order_id": sess["order_id"], "step": sess["step"]}
    return {"status": "active", "group_id": sess.get("group_id") or "-none-"} if sess.get("group_id") \
        else {"status": "active", "id": sess["id"]}


@api_router.post("/work/stop-group")
async def work_stop_group(req: WorkGroupStopRequest, user=Depends(get_current_user)):
    """'Done for all': any one member's PIN ends the task for everybody on it."""
    _work_require(user, WORK_DO_ROLES)
    name = await _work_identify(req.pin, _work_lock_key(user, req.device))
    sess = await db.work_sessions.find_one({"id": req.session_id, "status": "active"}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="This work is already finished")
    members = await db.work_sessions.find(_work_task_query(sess), {"_id": 0}).to_list(50)
    if name not in {m["staff"] for m in members}:
        raise HTTPException(status_code=403, detail=f"{name} is not working on this. Only someone doing it can finish it for all.")
    now = _work_now()
    for m in members:
        await _work_close(m, now, "done", req.remark)
    return {"ok": True, "closed": [m["staff"] for m in members], "by": name}


@api_router.get("/work/amazon-orders")
async def work_amazon_orders(q: str = "", user=Depends(get_current_user)):
    """Amazon orders still to be packed, most urgent ship-by date first."""
    _work_require(user, WORK_DO_ROLES)
    query = {"status": {"$in": ["new", "packaging"]}}
    q = (q or "").strip()
    if q:
        query["$or"] = [{"am_order_number": {"$regex": re.escape(q), "$options": "i"}},
                        {"amazon_order_id": {"$regex": re.escape(q), "$options": "i"}},
                        {"items.product_name": {"$regex": re.escape(q), "$options": "i"}}]
    rows = await db.amazon_orders.find(query, {"_id": 0, "id": 1, "am_order_number": 1, "amazon_order_id": 1,
                                               "status": 1, "items": 1, "latest_ship_date": 1,
                                               "ship_type": 1}).to_list(200)
    rows.sort(key=lambda o: o.get("latest_ship_date") or "9999")
    busy = {}
    async for a in db.work_sessions.find({"status": "active", "kind": "amazon"}, {"_id": 0, "order_id": 1, "staff": 1}):
        busy.setdefault(a["order_id"], []).append(a["staff"])
    return [{"id": o["id"], "order_number": o.get("am_order_number"), "amazon_order_id": o.get("amazon_order_id"),
             "customer_name": _work_amazon_summary(o), "status": o.get("status"),
             "ship_by": o.get("latest_ship_date") or "", "ship_type": o.get("ship_type"),
             "working_now": busy.get(o["id"], [])} for o in rows[:60]]


@api_router.post("/work/next-step")
async def work_next_step(req: WorkGroupStopRequest, user=Depends(get_current_user)):
    """Same people, same order, next step: ends the current step and starts the
    following one for everyone on it at the same instant - no re-selecting."""
    _work_require(user, WORK_DO_ROLES)
    name = await _work_identify(req.pin, _work_lock_key(user, req.device))
    sess = await db.work_sessions.find_one({"id": req.session_id, "status": "active"}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="This work is already finished")
    if sess.get("kind") != "order":
        raise HTTPException(status_code=400, detail="Only order work has steps")
    keys = [x["key"] for x in WORK_STEPS]
    idx = keys.index(sess["step"])
    if idx + 1 >= len(keys):
        raise HTTPException(status_code=400, detail="This is the last step. Press DONE.")
    members = await db.work_sessions.find(_work_task_query(sess), {"_id": 0}).to_list(50)
    if name not in {m["staff"] for m in members}:
        raise HTTPException(status_code=403, detail=f"{name} is not working on this.")
    now = _work_now()
    nxt, group_id, started = keys[idx + 1], str(uuid.uuid4()), []
    for m in members:
        await _work_close(m, now, "done", req.remark)
        doc = {"id": str(uuid.uuid4()), "staff": m["staff"], "kind": "order", "order_id": sess["order_id"],
               "order_number": sess.get("order_number"), "customer_name": sess.get("customer_name"),
               "step": nxt, "note": None, "group_id": group_id,
               "started_at": now.isoformat(), "last_confirmed_at": now.isoformat(),
               "ended_at": None, "duration_sec": None, "status": "active",
               "device": (req.device or "")[:40], "logged_in_as": user.get("username") or user.get("name")}
        await db.work_sessions.insert_one(dict(doc))
        started.append(m["staff"])
    await _work_sync_packed_by(sess["order_id"])
    return {"ok": True, "step": nxt, "step_label": WORK_STEP_LABEL[nxt], "people": started, "by": name}


@api_router.get("/work/active")
async def work_active(user=Depends(get_current_user)):
    """Everything running right now - the shared phone's home board."""
    _work_require(user, WORK_DO_ROLES)
    await _work_sweep()
    rows = await db.work_sessions.find({"status": "active"}, {"_id": 0}).sort("started_at", 1).to_list(200)
    return [_work_public(r) for r in rows]


@api_router.get("/work/me")
async def work_me(name: str, user=Depends(get_current_user)):
    """What this person is doing now, and their day so far. Read-only, no PIN."""
    _work_require(user, WORK_DO_ROLES)
    await _work_sweep()
    name = (name or "").strip()
    active = await db.work_sessions.find_one({"staff": name, "status": "active"}, {"_id": 0})
    start, end, day = _work_day_bounds(None)
    today = await db.work_sessions.find({"staff": name, "started_at": {"$gte": start, "$lt": end}},
                                        {"_id": 0}).sort("started_at", -1).to_list(200)
    pub = [_work_public(s) for s in today]
    uid = (await _crm_map_for_staff()).get(name)
    attendance = dict((await _crm_attendance([uid]))[uid], linked=True) if uid else {"linked": False}
    return {"name": name, "day": day, "active": _work_public(active) if active else None,
            "attendance": attendance,
            "today": pub, "today_total_sec": sum(s["duration_sec"] for s in pub),
            "today_orders": len({s["order_id"] for s in pub if s.get("order_id")})}


def _work_staff_summary(sessions: list) -> dict:
    """Per-staff totals for a list of (public) sessions."""
    out = {}
    for s in sessions:
        h = out.setdefault(s["staff"], {"staff": s["staff"], "total_sec": 0, "order_sec": 0,
                                        "other_sec": 0, "sessions": 0, "orders": set(),
                                        "auto_closed": 0, "first_start": None, "last_end": None,
                                        "current": None})
        h["total_sec"] += s["duration_sec"]
        h["sessions"] += 1
        if s["kind"] in ("order", "amazon"):
            h["order_sec"] += s["duration_sec"]
            h["orders"].add(s.get("order_number") or s.get("order_id"))
        else:
            h["other_sec"] += s["duration_sec"]
        if s["status"] == "auto_closed":
            h["auto_closed"] += 1
        if s["status"] == "active":
            h["current"] = s
        h["first_start"] = min(filter(None, [h["first_start"], s["started_at"]]))
        end = s.get("ended_at") or _work_now().isoformat()
        h["last_end"] = max(filter(None, [h["last_end"], end]))
    for h in out.values():
        h["orders_count"] = len(h["orders"])
        h["orders"] = sorted(x for x in h["orders"] if x)
    return out


@api_router.get("/work/live")
async def work_live(user=Depends(get_current_user)):
    """The live board: who is doing what right now, plus today's totals."""
    _work_require(user, WORK_VIEW_ROLES)
    await _work_sweep()
    start, end, day = _work_day_bounds(None)
    sessions = [_work_public(s) for s in await db.work_sessions.find(
        {"$or": [{"status": "active"}, {"started_at": {"$gte": start, "$lt": end}}]},
        {"_id": 0}).sort("started_at", 1).to_list(2000)]
    staff_names = [s["name"] for s in await db.packaging_staff.find({"active": True}, {"_id": 0, "name": 1}).sort("name", 1).to_list(100)]
    summary = _work_staff_summary(sessions)
    crm_map = await _crm_map_for_staff()
    att = await _crm_attendance(list(set(crm_map.values())))
    people = []
    for n in staff_names:
        h = summary.get(n) or {"staff": n, "total_sec": 0, "order_sec": 0, "other_sec": 0,
                               "sessions": 0, "orders": [], "orders_count": 0, "auto_closed": 0,
                               "first_start": None, "last_end": None, "current": None}
        uid = crm_map.get(n)
        h["attendance"] = dict(att.get(uid) or {}, linked=bool(uid))
        people.append(h)
    # orders touched today, with per-step progress
    orders = {}
    for s in sessions:
        if s["kind"] not in ("order", "amazon"):
            continue
        if s["kind"] == "amazon":
            s = dict(s, step="amazon")
        o = orders.setdefault(s["order_id"], {"order_id": s["order_id"], "order_number": s["order_number"],
                                              "customer_name": s["customer_name"], "steps": {},
                                              "total_sec": 0, "first_start": s["started_at"], "active": False})
        st = o["steps"].setdefault(s["step"], {"step": s["step"], "label": s["step_label"], "people": set(),
                                               "total_sec": 0, "first_start": s["started_at"], "last_end": None, "active": False})
        st["people"].add(s["staff"])
        st["total_sec"] += s["duration_sec"]
        o["total_sec"] += s["duration_sec"]
        st["first_start"] = min(st["first_start"], s["started_at"])
        o["first_start"] = min(o["first_start"], s["started_at"])
        if s["status"] == "active":
            st["active"] = True
            o["active"] = True
        else:
            st["last_end"] = max(filter(None, [st["last_end"], s.get("ended_at")]))
    order_rows = []
    for o in orders.values():
        steps = [dict(v, people=sorted(v["people"])) for k, v in o["steps"].items()]
        _order = [x["key"] for x in WORK_STEPS]
        steps.sort(key=lambda v: _order.index(v["step"]) if v["step"] in _order else 99)
        order_rows.append(dict(o, steps=steps))
    order_rows.sort(key=lambda o: (not o["active"], o["first_start"]))
    return {"day": day, "now": _work_now().isoformat(), "people": people,
            "orders": order_rows, "active": [s for s in sessions if s["status"] == "active"]}


@api_router.get("/work/day")
async def work_day(date: str = "", staff: str = "", user=Depends(get_current_user)):
    """Full timeline for one IST day, optionally one person, with idle gaps."""
    _work_require(user, WORK_VIEW_ROLES)
    await _work_sweep()
    start, end, day = _work_day_bounds(date or None)
    q = {"started_at": {"$gte": start, "$lt": end}}
    if staff.strip():
        q["staff"] = staff.strip()
    sessions = [_work_public(s) for s in await db.work_sessions.find(q, {"_id": 0}).sort("started_at", 1).to_list(3000)]
    by_staff = {}
    for s in sessions:
        by_staff.setdefault(s["staff"], []).append(s)
    timelines = []
    for name, rows in sorted(by_staff.items()):
        items, prev_end = [], None
        for s in rows:
            if prev_end and s["started_at"] > prev_end:
                gap = int((datetime.fromisoformat(s["started_at"]) - datetime.fromisoformat(prev_end)).total_seconds())
                if gap >= 120:
                    items.append({"gap": True, "from": prev_end, "to": s["started_at"], "duration_sec": gap})
            items.append(s)
            prev_end = s.get("ended_at") or _work_now().isoformat()
        summ = _work_staff_summary(rows)[name]
        timelines.append({"staff": name, "items": items, "summary": summ})
    return {"day": day, "timelines": timelines}


@api_router.get("/work/packed-by/{order_id}")
async def work_packed_by(order_id: str, user=Depends(get_current_user)):
    """Names the tracker has for this order's packing form fields."""
    return await _work_names_for_order(order_id)


@api_router.get("/work/order/{order_id}")
async def work_order(order_id: str, user=Depends(get_current_user)):
    """How one order was made: every step, who did it, how long."""
    _work_require(user, WORK_VIEW_ROLES + ["packaging"])
    sessions = [_work_public(s) for s in await db.work_sessions.find(
        {"order_id": order_id}, {"_id": 0}).sort("started_at", 1).to_list(500)]
    steps = []
    for step in WORK_STEPS:
        rows = [s for s in sessions if s["step"] == step["key"]]
        if not rows:
            continue
        steps.append({"step": step["key"], "label": step["label"],
                      "people": sorted({r["staff"] for r in rows}),
                      "total_sec": sum(r["duration_sec"] for r in rows),
                      "first_start": rows[0]["started_at"],
                      "last_end": max((r.get("ended_at") or "" for r in rows), default=None) or None,
                      "active": any(r["status"] == "active" for r in rows),
                      "sessions": rows})
    am = [s for s in sessions if s.get("kind") == "amazon"]
    if am:
        steps.append({"step": "amazon", "label": "Amazon order", "people": sorted({r["staff"] for r in am}),
                      "total_sec": sum(r["duration_sec"] for r in am), "first_start": am[0]["started_at"],
                      "last_end": max((r.get("ended_at") or "" for r in am), default=None) or None,
                      "active": any(r["status"] == "active" for r in am), "sessions": am})
    return {"order_id": order_id, "steps": steps, "total_sec": sum(s["duration_sec"] for s in sessions),
            "first_start": sessions[0]["started_at"] if sessions else None,
            "last_end": max((s.get("ended_at") or "" for s in sessions), default=None) or None}


@api_router.get("/work/report")
async def work_report(from_date: str = "", to_date: str = "", user=Depends(get_current_user)):
    """Per person per day totals over a date range (IST days)."""
    _work_require(user, WORK_VIEW_ROLES)
    await _work_sweep()
    to_d = datetime.fromisoformat(to_date).date() if to_date else datetime.now(IST).date()
    from_d = datetime.fromisoformat(from_date).date() if from_date else to_d - timedelta(days=6)
    if (to_d - from_d).days > 62:
        raise HTTPException(status_code=400, detail="Max 62 days")
    start, _, _ = _work_day_bounds(from_d.isoformat())
    _, end, _ = _work_day_bounds(to_d.isoformat())
    sessions = [_work_public(s) for s in await db.work_sessions.find(
        {"started_at": {"$gte": start, "$lt": end}}, {"_id": 0}).to_list(20000)]
    days = {}
    for s in sessions:
        d = datetime.fromisoformat(s["started_at"]).astimezone(IST).date().isoformat()
        days.setdefault(d, []).append(s)
    rows = []
    for d in sorted(days):
        for name, h in sorted(_work_staff_summary(days[d]).items()):
            rows.append({"day": d, **{k: v for k, v in h.items() if k != "current"}})
    return {"from": from_d.isoformat(), "to": to_d.isoformat(), "rows": rows}


# ── CRM bridge: attendance (read) and leave requests (write) ────────────────
# Packing executives have no OMS login, so they are linked to their CRM user
# by name (packing_staff_crm_map). OMS logins (accounts, telecallers) reuse
# the CRM's own user_mappings collection, which already links them.
def _ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


async def _crm_user(uid: str) -> Optional[dict]:
    if not uid:
        return None
    return await crm_db.users.find_one({"id": uid}, {"_id": 0, "id": 1, "name": 1, "username": 1,
                                                     "department": 1, "active": 1, "role": 1})


async def _crm_map_for_staff() -> dict:
    rows = await db.packing_staff_crm_map.find({}, {"_id": 0}).to_list(300)
    return {r["staff_name"]: r["crm_user_id"] for r in rows if r.get("crm_user_id")}


async def _crm_user_for_oms_user(user: dict) -> Optional[dict]:
    m = await db.user_mappings.find_one({"oms_user_id": user["id"]}, {"_id": 0, "crm_user_id": 1})
    return await _crm_user((m or {}).get("crm_user_id"))


async def _crm_attendance(crm_ids: list, day: Optional[str] = None) -> dict:
    """{crm_user_id: {present, check_in, check_out, on_leave, leave_pending}} for one IST day."""
    day = day or _ist_today()
    out = {uid: {"date": day, "present": False, "check_in": None, "check_out": None,
                 "att_status": None, "on_leave": False, "leave_pending": False} for uid in crm_ids}
    if not crm_ids:
        return out
    async for log in crm_db.attendance_logs.find({"user_id": {"$in": crm_ids}, "date": day}, {"_id": 0}):
        o = out.get(log["user_id"])
        if o is None:
            continue
        o["present"] = "check_in" in log
        o["check_in"] = (log.get("check_in") or {}).get("time")
        o["check_out"] = (log.get("check_out") or {}).get("time")
        o["att_status"] = log.get("status")
    async for lv in crm_db.leaves.find({"user_id": {"$in": crm_ids}, "cancelled": {"$ne": True},
                                        "status": {"$ne": "rejected"},
                                        "start_date": {"$lte": day}, "end_date": {"$gte": day}}, {"_id": 0}):
        o = out.get(lv["user_id"])
        if o is None:
            continue
        if lv.get("status") == "pending":
            o["leave_pending"] = True
        else:
            o["on_leave"] = True
    return out


def _valid_day(s: str) -> bool:
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or "")) and datetime.strptime(s, "%Y-%m-%d") is not None
    except ValueError:
        return False


async def _crm_apply_leave(crm_user: dict, start_date: str, end_date: str, reason: str) -> dict:
    """Same document, activity log and admin alert the CRM's own /leaves/apply
    writes, so the request shows up in the CRM exactly like one made there."""
    if not _valid_day(start_date) or not _valid_day(end_date):
        raise HTTPException(status_code=400, detail="Pick the dates")
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Please give a proper reason for the leave")
    if not crm_user.get("active", True):
        raise HTTPException(status_code=400, detail="Your CRM user is inactive - ask admin")
    overlap = await crm_db.leaves.find_one({
        "user_id": crm_user["id"], "cancelled": {"$ne": True}, "status": {"$ne": "rejected"},
        "start_date": {"$lte": end_date}, "end_date": {"$gte": start_date}}, {"_id": 0, "id": 1})
    if overlap:
        raise HTTPException(status_code=409, detail="You already have a leave request on these dates")
    now = datetime.now(timezone.utc).isoformat()
    leave = {"id": str(uuid.uuid4()), "user_id": crm_user["id"],
             "start_date": start_date, "end_date": end_date, "reason": reason,
             "status": "pending", "cancelled": False, "created_at": now,
             "created_by": crm_user["id"], "source": "oms"}
    await crm_db.leaves.insert_one(dict(leave))
    await crm_db.activity_logs.insert_one({"id": str(uuid.uuid4()), "actor_id": crm_user["id"],
                                           "action": "leave_applied", "lead_id": None,
                                           "meta": {"start_date": start_date, "end_date": end_date, "source": "oms"},
                                           "at": now})
    admin_ids = [a["id"] for a in await crm_db.users.find({"role": "admin", "active": True},
                                                          {"_id": 0, "id": 1}).to_list(50)]
    if admin_ids:
        await crm_db.admin_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "title": f"Leave request: {crm_user['name']}",
            "message": f"{crm_user['name']} applied for leave {start_date} \u2192 {end_date} (from OMS). Reason: {reason}",
            "sent_by": "System", "sent_by_id": None, "order_id": "", "customer_name": "",
            "recipient_ids": admin_ids, "recipient_roles": [], "acknowledgements": {},
            "created_at": now, "meta": {"type": "leave_request", "dedup_key": f"leave_request:{leave['id']}"},
        })
    return leave


async def _crm_my_leaves(crm_user_id: str) -> list:
    rows = await crm_db.leaves.find({"user_id": crm_user_id, "cancelled": {"$ne": True}},
                                    {"_id": 0}).sort("start_date", -1).to_list(30)
    for lv in rows:
        lv["status"] = lv.get("status") or "approved"
    return rows


class WorkLeaveRequest(BaseModel):
    name: str
    pin: str
    start_date: str
    end_date: str
    reason: str


class LeaveApplyRequest(BaseModel):
    start_date: str
    end_date: str
    reason: str


class CrmMapRequest(BaseModel):
    staff_name: str
    crm_user_id: Optional[str] = ""     # empty clears the link


@api_router.get("/work/crm-map")
async def work_crm_map(admin=Depends(require_admin)):
    """Admin: link each packing name to its CRM user (attendance + leave)."""
    staff = await db.packaging_staff.find({"active": True}, {"_id": 0, "name": 1}).sort("name", 1).to_list(100)
    mapping = await _crm_map_for_staff()
    users = await crm_db.users.find({"active": True, "role": {"$ne": "admin"},
                                     "username": {"$nin": ["scanner", "test_user"]}},
                                    {"_id": 0, "id": 1, "name": 1, "username": 1, "department": 1, "role": 1}
                                    ).sort("name", 1).to_list(300)
    by_id = {u["id"]: u for u in users}
    out = []
    for st in staff:
        uid = mapping.get(st["name"])
        # suggestion: exact name, else first word match, packing department first
        key = st["name"].strip().lower()
        sugg = [u for u in users if u["name"].strip().lower() == key] or \
               [u for u in users if key in u["name"].lower() or u["name"].lower().split()[0] == key.split()[0]]
        sugg.sort(key=lambda u: (u.get("department") != "packing", u["name"]))
        out.append({"staff_name": st["name"], "crm_user_id": uid,
                    "crm_user": by_id.get(uid), "suggested": sugg[0] if sugg else None})
    return {"staff": out, "crm_users": users}


@api_router.put("/work/crm-map")
async def work_set_crm_map(req: CrmMapRequest, admin=Depends(require_admin)):
    name = req.staff_name.strip()
    if not await db.packaging_staff.find_one({"name": name, "active": True}):
        raise HTTPException(status_code=404, detail="Name not found")
    uid = (req.crm_user_id or "").strip()
    if not uid:
        await db.packing_staff_crm_map.delete_one({"staff_name": name})
        return {"ok": True, "staff_name": name, "crm_user_id": None}
    if not await _crm_user(uid):
        raise HTTPException(status_code=404, detail="CRM user not found")
    await db.packing_staff_crm_map.update_one({"staff_name": name},
                                              {"$set": {"crm_user_id": uid, "updated_by": admin["name"],
                                                        "updated_at": _work_now().isoformat()}}, upsert=True)
    return {"ok": True, "staff_name": name, "crm_user_id": uid}


@api_router.post("/work/leave/apply")
async def work_leave_apply(req: WorkLeaveRequest, user=Depends(get_current_user)):
    """Packing executive applies for leave from the shared phone (name + PIN)."""
    _work_require(user, WORK_DO_ROLES)
    name = await _work_staff_auth(req.name, req.pin)
    crm_user = await _crm_user((await _crm_map_for_staff()).get(name))
    if not crm_user:
        raise HTTPException(status_code=400, detail="Your name is not linked to the CRM yet. Ask admin.")
    leave = await _crm_apply_leave(crm_user, req.start_date, req.end_date, req.reason)
    return {"ok": True, "leave": leave}


@api_router.get("/work/leave/my")
async def work_leave_my(name: str, user=Depends(get_current_user)):
    _work_require(user, WORK_DO_ROLES)
    crm_user = await _crm_user((await _crm_map_for_staff()).get((name or "").strip()))
    if not crm_user:
        return {"linked": False, "leaves": [], "attendance": None}
    att = await _crm_attendance([crm_user["id"]])
    return {"linked": True, "crm_name": crm_user["name"], "leaves": await _crm_my_leaves(crm_user["id"]),
            "attendance": att[crm_user["id"]]}


@api_router.post("/leave/apply")
async def leave_apply(req: LeaveApplyRequest, user=Depends(get_current_user)):
    """OMS login (accounts, telecallers) applies for leave; lands in the CRM."""
    if user["role"] == "admin":
        raise HTTPException(status_code=400, detail="Admins add leaves directly in the CRM Payroll page")
    crm_user = await _crm_user_for_oms_user(user)
    if not crm_user:
        raise HTTPException(status_code=400, detail="Your login is not linked to a CRM user. Ask admin.")
    leave = await _crm_apply_leave(crm_user, req.start_date, req.end_date, req.reason)
    return {"ok": True, "leave": leave}


@api_router.get("/leave/my")
async def leave_my(user=Depends(get_current_user)):
    crm_user = await _crm_user_for_oms_user(user)
    if not crm_user:
        return {"linked": False, "leaves": [], "attendance": None}
    att = await _crm_attendance([crm_user["id"]])
    return {"linked": True, "crm_name": crm_user["name"], "leaves": await _crm_my_leaves(crm_user["id"]),
            "attendance": att[crm_user["id"]]}


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
        {"_id": 0, "order_number": 1, "id": 1, "items": 1, "free_samples": 1,
         "created_at": 1, "customer_name": 1, "gst_applicable": 1}
    ).sort("created_at", -1).to_list(50)
    history = []
    for order in orders:
        # Mirror the fields the editor shows for the current order, so a past
        # formulation can be read in the same context it was written in.
        items_with_formulation = [
            {"product_name": item["product_name"],
             "description": item.get("description", ""),
             "formulation": item.get("formulation", ""),
             "qty": item.get("qty", 0), "unit": item.get("unit", ""),
             "amount": item.get("amount", 0)}
            for item in order.get("items", []) if item.get("formulation")
        ]
        samples_with_formulation = [
            {"item_name": s.get("item_name", ""),
             "description": s.get("description", ""),
             "formulation": s.get("formulation", "")}
            for s in (order.get("free_samples") or []) if s.get("formulation")
        ]
        if items_with_formulation or samples_with_formulation:
            history.append({
                "order_number": order["order_number"],
                "order_id": order["id"],
                "customer_name": order.get("customer_name", ""),
                "created_at": order["created_at"],
                "gst_applicable": bool(order.get("gst_applicable")),
                "items": items_with_formulation,
                "free_samples": samples_with_formulation,
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
    company = company_of(order)

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
    logo_src = str(company["logo_pdf"]) if company["logo_pdf"].exists() else str(company["logo"])
    if Path(logo_src).exists():
        try:
            tmp = Image(logo_src)
            aspect = tmp.imageHeight / tmp.imageWidth
            logo_h = 28*mm * aspect
            logo_cell = Image(logo_src, width=28*mm, height=logo_h)
        except Exception:
            pass

    co_info = Paragraph(
        f"<b><font size=11>{company['name']}</font></b><br/>"
        f"<font size=8 color='#15803D'><i>{company['brand']}</i></font><br/>"
        f"<font size=7 color='#6B7280'>{company['address']}</font><br/>"
        f"<font size=7 color='#6B7280'>Ph: {company['mobile']} | {company['email']}</font>",
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
    company = company_of({"company": req.company})
    pi_number = await next_document_number(company, "pi")
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

    mdisc, mdisc_gst = compute_manual_discount(req, items, subtotal, total_gst)
    if mdisc > 0:
        additional_charges.append({"name": "Discount", "amount": -mdisc,
                                   "gst_percent": 0, "gst_amount": -mdisc_gst})
        total_additional -= mdisc
        total_additional_gst -= mdisc_gst
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
        "company": company["key"],
        "bank_account": req.bank_account if req.bank_account else "",
        "discount_enabled": bool(getattr(req, "discount_enabled", False)),
        "discount_mode": getattr(req, "discount_mode", "total") or "total",
        "discount_value": float(getattr(req, "discount_value", 0) or 0),
        "discount_is_percent": bool(getattr(req, "discount_is_percent", False)),
        "customer_id": req.customer_id,
        "customer_name": customer["name"],
        "items": items,
        "gst_applicable": req.gst_applicable,
        "show_rate": req.show_rate,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "additional_charges": additional_charges,
        "carrier_risk_applicable": carrier_risk_allowed(req),
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

    mdisc, mdisc_gst = compute_manual_discount(req, items, subtotal, total_gst)
    if mdisc > 0:
        additional_charges.append({"name": "Discount", "amount": -mdisc,
                                   "gst_percent": 0, "gst_amount": -mdisc_gst})
        total_additional -= mdisc
        total_additional_gst -= mdisc_gst
    grand_total = math.ceil(subtotal + total_gst + req.shipping_charge + shipping_gst + total_additional + total_additional_gst)

    billing_addr = None
    shipping_addr = None
    if req.billing_address_id:
        billing_addr = await db.addresses.find_one({"id": req.billing_address_id}, {"_id": 0})
    if req.shipping_address_id:
        shipping_addr = await db.addresses.find_one({"id": req.shipping_address_id}, {"_id": 0})

    # Switching a PI's company renumbers it into that company's series, the
    # same rule orders follow.
    new_company = company_of({"company": req.company})
    pi_renumber = {}
    if new_company["key"] != company_of(pi)["key"]:
        pi_renumber = {
            "pi_number": await next_document_number(new_company, "pi"),
            "renumber_history": (pi.get("renumber_history") or []) + [{
                "from": pi.get("pi_number", ""), "at": datetime.now(timezone.utc).isoformat(),
                "by": user["name"],
            }],
        }
        pi_renumber["renumber_history"][-1]["to"] = pi_renumber["pi_number"]

    update_data = {
        "customer_id": req.customer_id,
        "customer_name": customer["name"] if customer else pi["customer_name"],
        "company": company_of({"company": req.company})["key"],
        "bank_account": req.bank_account if req.bank_account else "",
        "discount_enabled": bool(getattr(req, "discount_enabled", False)),
        "discount_mode": getattr(req, "discount_mode", "total") or "total",
        "discount_value": float(getattr(req, "discount_value", 0) or 0),
        "discount_is_percent": bool(getattr(req, "discount_is_percent", False)),
        "items": items,
        "gst_applicable": req.gst_applicable,
        "show_rate": req.show_rate,
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "additional_charges": additional_charges,
        "carrier_risk_applicable": carrier_risk_allowed(req),
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
        **pi_renumber,
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
    bank_account: str = ""           # admin-chosen bank for the PDF; blank = automatic

@api_router.post("/orders/{order_id}/make-pi")
async def make_pi_from_order(order_id: str, req: MakePIRequest, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Admin or telecaller only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    company = company_of(order)
    pi_number = await next_document_number(company, "pi")
    
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
        "company": company["key"],
        "bank_account": req.bank_account if req.bank_account else "",
        "discount_enabled": bool(getattr(req, "discount_enabled", False)),
        "discount_mode": getattr(req, "discount_mode", "total") or "total",
        "discount_value": float(getattr(req, "discount_value", 0) or 0),
        "discount_is_percent": bool(getattr(req, "discount_is_percent", False)),
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
    company = company_of(pi)
    order_number = await next_document_number(company, "order")
    customer = await db.customers.find_one({"id": pi["customer_id"]}, {"_id": 0})
    order_doc = {
        "id": str(uuid.uuid4()),
        "order_number": order_number,
        "company": company["key"],
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
        "is_cod": bool(body.get("is_cod", False)),
        "cod_amount": round(float(body.get("cod_amount") or 0), 2),
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
    company = company_of(pi)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=3*mm, bottomMargin=3*mm)
    styles = getSampleStyleSheet()
    elements = []
    pw = A4[0] - 30*mm
    is_gst = pi.get("gst_applicable", False)

    # ── Colours & shared styles ──
    # Accent colours follow the company's logo: CitSpray green, FragVansh the
    # navy of its flask mark. The names stay GREEN/LGREEN for the code below.
    if company["key"] == "fragvansh":
        ACCENT_HEX, GREEN, LGREEN = '#1B2F5E', colors.HexColor('#1B2F5E'), colors.HexColor('#EEF2FA')
    else:
        ACCENT_HEX, GREEN, LGREEN = '#15803D', colors.HexColor('#15803D'), colors.HexColor('#F0FDF4')
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
        if company["logo_pdf"].exists() or company["logo"].exists():
            logo_src = str(company["logo_pdf"]) if company["logo_pdf"].exists() else str(company["logo"])
            try:
                tmp = Image(logo_src)
                aspect = tmp.imageHeight / tmp.imageWidth
                logo_cell = Image(logo_src, width=30*mm, height=30*mm * aspect)
            except Exception:
                pass

        co_para = Paragraph(
            f"<b><font size=13>{company['name']}</font></b><br/>"
            f"<font size=8 color='{ACCENT_HEX}'><i>{company['brand']}</i></font><br/>"
            f"<font size=7.5 color='#374151'>{company['address']}</font><br/>"
            f"<font size=7.5 color='#6B7280'>"
            f"Ph: {company['mobile']}  |  {company['email']}  |  {company['website']}</font><br/>"
            f"<font size=7.5 color='#374151'><b>GSTIN:</b> {company['gstin']}</font>",
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
    # Order: Subtotal -> Discount -> Shipping (excl GST) -> other charges ->
    # one combined GST figure (items + shipping + charges, net of discount
    # reversal) -> Grand Total. Every line is pre-GST so the column adds up.
    totals = []
    totals.append([Paragraph("Subtotal", tr), Paragraph(f"{pi.get('subtotal', 0):.2f}", tr)])
    combined_gst = round(float(pi.get("total_gst", 0) or 0) + float(pi.get("shipping_gst", 0) or 0), 2)
    for charge in pi.get("additional_charges", []):
        charge_amt = float(charge.get("amount", 0) or 0)
        combined_gst = round(combined_gst + float(charge.get("gst_amount", 0) or 0), 2)
        if charge_amt < 0:
            totals.append([Paragraph(charge.get("name", "Discount"), tr),
                           Paragraph(f"- {abs(charge_amt):.2f}", tr)])
    if pi.get("shipping_charge", 0) > 0:
        totals.append([Paragraph("Shipping Charges", tr), Paragraph(f"{pi['shipping_charge']:.2f}", tr)])
    for charge in pi.get("additional_charges", []):
        charge_amt = float(charge.get("amount", 0) or 0)
        if charge_amt > 0:
            totals.append([Paragraph(charge.get("name", "Charge"), tr), Paragraph(f"{charge_amt:.2f}", tr)])
    if is_gst and combined_gst > 0:
        cust_state = ""
        if pi.get("billing_address"):
            cust_state = pi["billing_address"].get("state", "")
        if cust_state.lower() == "maharashtra":
            cgst = round(combined_gst / 2, 2)
            totals.append([Paragraph("CGST", tr), Paragraph(f"{cgst:.2f}", tr)])
            totals.append([Paragraph("SGST", tr), Paragraph(f"{combined_gst - cgst:.2f}", tr)])
        else:
            totals.append([Paragraph("IGST", tr), Paragraph(f"{combined_gst:.2f}", tr)])
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
    bank = await resolve_pi_bank(pi, company, is_gst)
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


# ─── Amazon product formulations ─────────────────────────────────────────
# Amazon order lines carry a marketplace listing title, not our product names,
# and one formulation covers every variant of a product — all the eucalyptus
# oil listings share a recipe. So formulations are held per product keyword and
# matched against the listing title, with a per-line override when a specific
# order needs something different.

def _formulation_key(text: str) -> str:
    """Lowercase alphanumeric words, so listing titles and keys compare fairly."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower()).split())


def resolve_amazon_formulation(product_name: str, defaults: list) -> Optional[dict]:
    """Best product-level formulation for a listing title.

    Longest matching keyword wins, so "eucalyptus oil blue gum" beats a generic
    "eucalyptus oil" entry when both are configured.
    """
    title = _formulation_key(product_name)
    if not title:
        return None
    best = None
    for d in defaults:
        key = _formulation_key(d.get("product_key"))
        if key and key in title and (best is None or len(key) > len(_formulation_key(best["product_key"]))):
            best = d
    return best


async def _amazon_apply_formulations(orders: list, user: dict) -> list:
    """Attach the resolved formulation to each line, honouring visibility.

    Same rules as our own orders: telecallers never see one, packaging only
    when the global toggle is on, dispatch and accounts never, admin always.
    """
    role = user["role"]
    settings = await db.settings.find_one({"_id": "global"})
    show_global = bool((settings or {}).get("show_formulation", False))
    visible = role == "admin" or (role == "packaging" and show_global)

    defaults = await db.amazon_formulations.find({}, {"_id": 0}).to_list(500) if visible else []
    for o in orders:
        for item in o.get("items") or []:
            if not visible:
                item.pop("formulation", None)
                item.pop("formulation_source", None)
                continue
            if str(item.get("formulation") or "").strip():
                item["formulation_source"] = "order"
                continue
            match = resolve_amazon_formulation(item.get("product_name") or item.get("title"), defaults)
            item["formulation"] = (match or {}).get("formulation", "")
            item["formulation_source"] = "product" if match else ""
            item["formulation_product_key"] = (match or {}).get("product_key", "")
    return orders


class AmazonFormulationModel(BaseModel):
    product_key: str            # keyword matched against the listing title
    formulation: str = ""
    label: str = ""


@api_router.get("/amazon/formulations")
async def list_amazon_formulations(user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    rows = await db.amazon_formulations.find({}, {"_id": 0}).sort("product_key", 1).to_list(500)
    return rows


@api_router.post("/amazon/formulations")
async def upsert_amazon_formulation(req: AmazonFormulationModel, user=Depends(get_current_user)):
    """Create or update the default formulation for a product keyword."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    key = _formulation_key(req.product_key)
    if not key:
        raise HTTPException(status_code=400, detail="Product keyword is required")
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.amazon_formulations.find_one({"product_key": key}, {"_id": 0})
    doc = {"product_key": key, "label": req.label or req.product_key,
           "formulation": req.formulation, "updated_at": now, "updated_by": user["name"]}
    if existing:
        await db.amazon_formulations.update_one({"product_key": key}, {"$set": doc})
    else:
        doc.update({"id": str(uuid.uuid4()), "created_at": now})
        await db.amazon_formulations.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"ok": True, "formulation": doc}


@api_router.delete("/amazon/formulations/{product_key}")
async def delete_amazon_formulation(product_key: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    res = await db.amazon_formulations.delete_one({"product_key": _formulation_key(product_key)})
    return {"ok": True, "deleted": res.deleted_count}


class AmazonItemFormulationRequest(BaseModel):
    item_index: int
    formulation: str = ""       # blank clears the override, reverting to the product default


@api_router.put("/amazon/orders/{order_id}/formulation")
async def set_amazon_item_formulation(order_id: str, req: AmazonItemFormulationRequest,
                                      user=Depends(get_current_user)):
    """Override one line's formulation for this order only."""
    if user["role"] not in ["admin", "packaging"]:
        raise HTTPException(status_code=403, detail="Packaging or admin only")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    items = order.get("items") or []
    if not 0 <= req.item_index < len(items):
        raise HTTPException(status_code=400, detail="No such item on this order")
    items[req.item_index]["formulation"] = req.formulation.strip()
    await db.amazon_orders.update_one({"id": order_id}, {"$set": {
        "items": items, "updated_at": datetime.now(timezone.utc).isoformat(),
        "formulation_by": user["name"]}})
    return {"ok": True}


@api_router.get("/amazon/orders")
async def list_amazon_orders(user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    orders = [_pii_open(o) for o in await db.amazon_orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)]
    if user["role"] not in PII_ROLES:
        orders = [_pii_mask(o) for o in orders]
    else:
        with_pii = sum(1 for o in orders if o.get("has_buyer_pii") and not o.get("pii_purged_at"))
        if with_pii:
            await _sec_log("pii_list", username=user.get("username"), role=user["role"], count=with_pii)
    return await _amazon_apply_formulations(orders, user)


@api_router.get("/amazon/orders/{order_id}")
async def get_amazon_order(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    _pii_open(order)
    order.pop("ship_to", None)          # served, access-checked, by /amazon/orders/{id}/ship-to
    if user["role"] not in PII_ROLES:
        _pii_mask(order)
    elif order.get("has_buyer_pii") and not order.get("pii_purged_at"):
        await _pii_view_logged(user, order.get("am_order_number"))
    return (await _amazon_apply_formulations([order], user))[0]


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
    for key in ("num_boxes", "length_cm", "breadth_cm", "height_cm"):
        if key in updates and str(updates[key] or "").strip():
            packaging[key] = updates[key]
    if "weight_kg" in updates and str(updates["weight_kg"] or "").strip():
        packaging["weight_kg"] = str(updates["weight_kg"]).strip()
        packaging["ready_to_book"] = True
        packaging.setdefault("ready_to_book_at", datetime.now(timezone.utc).isoformat())
    for key in ["item_packed_by", "box_packed_by", "checked_by", "item_images", "order_images", "packed_box_images"]:
        if key in WORK_FIELD_STEP and user["role"] != "admin":
            continue                      # names come from My Work, never picked by hand
        if key in updates:
            packaging[key] = updates[key]
    _names = await _work_amazon_names(order_id)
    if _names or packaging.get("tracker_added"):
        _work_merge_packed_by(packaging, {f: list(_names) for f in WORK_FIELD_STEP})

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
    await _work_sync_amazon(order_id)
    fresh = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0, "packaging": 1}) or {}
    if user["role"] != "admin" and not (fresh.get("packaging") or {}).get("item_packed_by"):
        raise HTTPException(status_code=400, detail="Not started in My Work. Open My Work, tap Amazon orders, "
                                                    "pick this order and enter your PIN first.")
    await db.amazon_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "packed", "packaging.packed_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await _work_finish_order(order_id, "amazon")
    return {"status": "packed"}


@api_router.put("/amazon/orders/{order_id}/dispatch")
async def dispatch_amazon_order(order_id: str, data: dict = {}, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.get("ship_type") != "self_ship":
        raise HTTPException(status_code=400, detail="Easy Ship orders are dispatched automatically when Amazon's courier scans the pickup - nothing to do by hand")
    dispatch = {
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_by": user["username"],
    }
    if order.get("ship_type") == "self_ship":
        lr = data.get("lr_number", "").strip()
        if not lr:
            raise HTTPException(status_code=400, detail="LR number is required for self ship orders")
        dispatch["lr_number"] = lr
    if order.get("ship_type") == "self_ship":
        dispatch["lr_no"] = dispatch["lr_number"]
        dispatch.setdefault("courier_name", order.get("courier_name") or "")
    await db.amazon_orders.update_one(
        {"id": order_id},
        {"$set": {"status": "dispatched", "dispatch": dispatch, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    confirm = await _amz_confirm_shipment(order_id) if order.get("ship_type") == "self_ship" else None
    return {"status": "dispatched", "amazon_confirm": confirm}


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
        # Easy Ship leaves only when Amazon's courier scans it; never by hand.
        if not order or order.get("status") == "dispatched" or order.get("ship_type") != "self_ship":
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
    upd = {"courier_name": courier_name, "updated_at": datetime.now(timezone.utc).isoformat()}
    # The Shiprocket carrier picked with live fares; booking preselects it.
    sr = data.get("shiprocket_courier")
    upd["shiprocket_courier"] = sr if (courier_name or "").lower().startswith("shiprocket") and isinstance(sr, dict) else None
    await db.amazon_orders.update_one({"id": order_id}, {"$set": upd})
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
        # DTDC dedupes on this ref, and a cancelled consignment keeps it locked
        # ("Consignment is already complete"), so each rebook gets -R<n>.
        "customer_reference_number": (
            (order.get("order_number") or order["id"][:20])
            + (f"-R{sum(1 for c in (order.get('cancelled_shipments') or []) if (c.get('courier') or '').upper() == 'DTDC')}"
               if any((c.get("courier") or "").upper() == "DTDC"
                      for c in (order.get("cancelled_shipments") or [])) else "")
        ),
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
    orders = await ship_orders.find({
        "courier_name": {"$regex": r"^\s*dtdc", "$options": "i"},
        "status": {"$nin": ["cancelled", "dispatched"]},
        "$or": [{"packaging.weight_kg": {"$nin": ["", None]}},
                {"dtdc_shipment.reference_number": {"$nin": ["", None]}}],
    }, {"_id": 0}).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        sa = o.get("shipping_address") or {}
        booked = bool((o.get("dtdc_shipment") or {}).get("reference_number"))
        try:
            weight = float(str(pkg.get("weight_kg", "")).strip() or 0)
        except ValueError:
            weight = 0.0
        if weight <= 0:
            weight = float((o.get("dtdc_shipment") or {}).get("weight_kg") or 0) if booked else 0.0
        if weight <= 0 and not booked:
            continue
        quote = dtdc_quote_for(sa.get("pincode"), weight) if weight > 0 else None
        acct_key, service, risk = _dtdc_route(o, quote["series"]) if quote else ("", "", False)
        out.append({
            "id": o["id"], "order_number": o.get("order_number"),
            "customer_name": o.get("customer_name"), "status": o.get("status"),
            "grand_total": o.get("grand_total"),
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
    # Declared value entered at booking time; required when the order total is 0
    # (free samples), ignored otherwise.
    declared_value: Optional[float] = None


@api_router.post("/dtdc/preview")
async def dtdc_preview(req: DtdcBookRequest, user=Depends(get_current_user)):
    """Exactly what would be booked — account, service, charge. Books nothing."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
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
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized to book")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("dtdc_shipment") or {}).get("reference_number") and not req.allow_rebook:
        raise HTTPException(status_code=400, detail="This order is already booked with DTDC")
    if req.declared_value and float(req.declared_value) > 0:
        order["declared_value_override"] = float(req.declared_value)
    elif float(order.get("grand_total") or 0) <= 0:
        raise HTTPException(status_code=400,
                            detail="Order total is \u20b90 - enter a declared value for the shipment before booking")
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
    await ship_orders.update_one({"id": req.order_id}, {"$set": {
        "dtdc_shipment": shipment,
        "courier_name": "DTDC",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    safe = {k: v for k, v in shipment.items() if k != "raw_response"}
    return {"ok": True, "shipment": safe}


class BulkBookRequest(BaseModel):
    order_ids: List[str]
    payment_mode: Optional[str] = None      # Amazon only; prepaid unless stated
    # order_id -> declared value for zero-total orders in the batch.
    declared_values: Optional[dict] = None
    # order_id -> {"payment_mode", "service_id" (Amazon), "courier_id" (Shiprocket), "insure"}
    # reviewed per order on the Book Shipments screen; overrides the batch mode.
    choices: Optional[dict] = None


async def _bulk_book(order_ids, book_one, user, label):
    """Book many consignments one at a time, never aborting the batch.

    Deliberately sequential: each booking spends money and schedules a pickup,
    so a courier rate limit or one bad address must not take the rest down or
    leave a half-booked batch nobody can account for. Every order gets its own
    result line.
    """
    seen, ordered = set(), []
    for oid in order_ids:
        if oid and oid not in seen:
            seen.add(oid)
            ordered.append(oid)
    if not ordered:
        raise HTTPException(status_code=400, detail="No orders selected")
    if len(ordered) > 50:
        raise HTTPException(status_code=400, detail="Book at most 50 orders at a time")

    booked, failed = [], []
    for oid in ordered:
        order = await ship_orders.find_one({"id": oid}, {"_id": 0, "order_number": 1})
        num = (order or {}).get("order_number") or oid[:8]
        try:
            res = await book_one(oid)
            booked.append({"order_id": oid, "order_number": num, "result": res})
        except HTTPException as e:
            failed.append({"order_id": oid, "order_number": num, "error": str(e.detail)})
        except Exception as e:
            logging.error(f"{label} bulk book failed for {num}: {e}")
            failed.append({"order_id": oid, "order_number": num, "error": str(e)[:200]})
    return {"ok": True, "requested": len(ordered),
            "booked": booked, "failed": failed,
            "booked_count": len(booked), "failed_count": len(failed)}


@api_router.post("/dtdc/bulk-book")
async def dtdc_bulk_book(req: BulkBookRequest, user=Depends(get_current_user)):
    """BOOKS real DTDC consignments for several orders."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized to book")

    async def one(oid):
        return await dtdc_book(DtdcBookRequest(
            order_id=oid,
            declared_value=(req.declared_values or {}).get(oid)), user=user)

    return await _bulk_book(req.order_ids, one, user, "DTDC")


class CancelLabelRequest(BaseModel):
    order_id: str


async def _dtdc_cancel_one(order_id: str, user) -> dict:
    """Cancels a booked DTDC consignment and clears it off the order."""
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    shp = order.get("dtdc_shipment") or {}
    awb = shp.get("reference_number") or shp.get("awb")
    if not awb:
        raise HTTPException(status_code=400, detail="No DTDC booking on this order")
    if (order.get("status") or "") == "dispatched":
        raise HTTPException(status_code=400,
                            detail="Order is already dispatched - undo the dispatch before cancelling the label")
    account = DTDC_ACCOUNTS.get(shp.get("account") or "") or {}
    if not account.get("api_key"):
        raise HTTPException(status_code=400, detail=f"No API key for account {shp.get('account')}")
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(f"{DTDC_BASE_URL}{DTDC_PATH_CANCEL}",
                         headers={"api-key": account["api_key"], "content-type": "application/json"},
                         json={"AWBNo": [awb], "customerCode": account.get("customer_code")})
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:400]}
    blob = str(data).lower()
    # Shipsy reports per-AWB outcomes; a failure line means it stays booked.
    if r.status_code not in (200, 201) or data.get("success") is False or "failure" in blob:
        logging.error(f"DTDC cancel failed for {awb}: {r.status_code} {str(data)[:400]}")
        raise HTTPException(status_code=400, detail=f"DTDC cancel failed: {str(data)[:300]}")
    now = datetime.now(timezone.utc).isoformat()
    await ship_orders.update_one({"id": order_id}, {
        "$push": {"cancelled_shipments": {"courier": "DTDC", **shp,
                                          "cancelled_by": user["name"], "cancelled_at": now}},
        "$unset": {"dtdc_shipment": ""},
        "$set": {"updated_at": now},
    })
    return {"ok": True, "cancelled": awb}


@api_router.post("/dtdc/cancel")
async def dtdc_cancel(req: CancelLabelRequest, user=Depends(get_current_user)):
    """Cancels one DTDC consignment so the order can be rebooked."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await _dtdc_cancel_one(req.order_id, user)


@api_router.post("/dtdc/bulk-cancel")
async def dtdc_bulk_cancel(req: BulkBookRequest, user=Depends(get_current_user)):
    """Cancels several DTDC consignments, one result line each."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    async def one(oid):
        return await _dtdc_cancel_one(oid, user)

    return await _bulk_book(req.order_ids, one, user, "DTDC cancel")


@api_router.get("/dtdc/labels-sheet")
async def dtdc_labels_sheet(ids: str, token: str = "", user=None):
    """Selected DTDC labels, each label page on its own full A4 page.

    DTDC's label is itself an A4 three-copy sheet (one page per piece for
    multi-box consignments); every page is rasterised and printed full size.
    """
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    order_ids = [x.strip() for x in (ids or "").split(",") if x.strip()][:40]
    if not order_ids:
        raise HTTPException(status_code=400, detail="No orders given")

    images, missing = [], []
    for oid in order_ids:
        o = await ship_orders.find_one({"id": oid}, {"_id": 0})
        sh = (o or {}).get("dtdc_shipment") or {}
        raw, media = await _dtdc_fetch_label_bytes(sh, order=o)
        if not raw:
            num = (o or {}).get("order_number") or oid[:8]
            missing.append(f"{num} ({media})" if media else num)
            continue
        if "pdf" in (media or ""):
            pages = _pdf_pages_jpg(raw)
            if pages:
                images.extend(pages)
            else:
                missing.append((o or {}).get("order_number") or oid[:8])
        else:
            images.append(raw)
    if not images:
        raise HTTPException(status_code=404,
                            detail=f"No labels available for: {', '.join(missing)}")
    # DTDC labels are full A4 three-copy sheets: one label page per A4 page.
    buffer = _quarter_sheet_pdf(images, per_page=1)
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition":
                                      "inline; filename=dtdc-labels-sheet.pdf"})


@api_router.get("/dtdc/label/{order_id}")
async def dtdc_label(order_id: str, token: str = "", user=None):
    """Stream the DTDC shipping label for a booked consignment."""
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    sh = order.get("dtdc_shipment") or {}
    ref = sh.get("awb") or sh.get("reference_number")
    if not ref:
        raise HTTPException(status_code=404, detail="This order is not booked with DTDC")
    raw, media = await _dtdc_fetch_label_bytes(sh, order=order)
    if not raw:
        raise HTTPException(status_code=400, detail=f"DTDC label failed: {media}")
    ext = "pdf" if "pdf" in media else _sniff_media(raw)[1]
    return StreamingResponse(
        io.BytesIO(raw), media_type=media,
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


DTDC_LOGO_PATH = Path(__file__).parent / "assets" / "dtdc_logo.png"

# The R11 booking branch printed on every DTDC label, exactly as their PDF has it.
DTDC_LABEL_BRANCH = {
    "name": "NAGPUR PANDE LAYOUT BRANCH",
    "address": "58.59 AGNE LAYOUT, NEAR ANAND PURTI SUPER BAZAR, JAITALA ROAD, "
               "KHAMLA, NAGPUR-440025, NAGPUR, MAHARASHTRA, 440025",
    "phone": "9916088912/7718823039",
}


def _dtdc_render_label_pdf(order: dict, shipment: dict) -> bytes:
    """Replica of DTDC's own A4 label sheet, rendered from our booking data.

    DTDC's API refuses labels until its booking sync completes (minutes after
    softdata upload), while their portal prints instantly from the same data.
    This renders the identical three-copy sheet (Sender's / Account's / POD)
    so book-then-print works without the wait. Layout measured off a real
    label (CS-1238 / M1001198347).
    """
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.graphics.barcode import code128

    sa = order.get("shipping_address") or {}
    line1, line2 = _address_lines(sa)
    consignee_addr = ", ".join(x for x in [line1, line2, sa.get("city"),
                                           (sa.get("state") or "").upper(),
                                           sa.get("pincode")] if x)
    origin = _dtdc_party_origin()
    consignor_addr = (f"{origin['address_line_1']}, {origin['city']}, "
                      f"{origin['city'].upper()}, {origin['state'].upper()}, {origin['pincode']}")
    awb = shipment.get("awb") or shipment.get("reference_number") or ""
    service = shipment.get("service_type") or ""
    mode = "AIR" if service.upper().startswith("STD") else "SURFACE"
    risk = bool(shipment.get("risk_surcharge"))
    weight = str(shipment.get("weight_kg") or "")
    pieces = str(shipment.get("num_boxes") or "1")
    declared = shipment.get("declared_value")
    declared = str(int(declared)) if declared not in (None, "") else ""
    try:
        booked = datetime.fromisoformat(str(shipment.get("booked_at")).replace("Z", "+00:00"))
    except Exception:
        booked = datetime.now(timezone.utc)
    date_str = booked.strftime("%a %b %d %Y")
    dest_city = (sa.get("city") or "").upper()

    buf = _io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    W, H = A4
    logo = ImageReader(str(DTDC_LOGO_PATH)) if DTDC_LOGO_PATH.exists() else None

    def kv(x, y, caption, value, size=7, vbold=True, cap_bold=False):
        c.setFont("Helvetica-Bold" if cap_bold else "Helvetica", size)
        c.drawString(x, y, caption)
        cw = c.stringWidth(caption, "Helvetica-Bold" if cap_bold else "Helvetica", size)
        c.setFont("Helvetica-Bold" if vbold else "Helvetica", size)
        c.drawString(x + cw + 2, y, value)

    def wrapped(x, y, text, size, width, bold=True):
        font = "Helvetica-Bold" if bold else "Helvetica"
        lines = simpleSplit(text, font, size, width)
        c.setFont(font, size)
        for i, ln in enumerate(lines):
            c.drawString(x, y - i * (size + 1.5), ln)
        return y - (len(lines) - 1) * (size + 1.5)

    def copy_block(top, copy_name):
        T = H - top
        B = T - 253
        L, R = 7, 588
        xm1, xm2 = 299, 443
        xl = 155

        c.setLineWidth(0.8)
        c.rect(L, B, R - L, 253)
        hb = T - 47
        c.line(L, hb, R, hb)
        c.line(xm1, T, xm1, hb)
        c.line(xm2, T, xm2, hb)
        if logo:
            c.drawImage(logo, L + 8, T - 40, width=125, height=30,
                        preserveAspectRatio=True, anchor="w", mask="auto")
        else:
            c.setFont("Helvetica-Bold", 20)
            c.drawString(L + 10, T - 30, "DTDC")
        c.setFont("Helvetica", 7)
        c.drawString(L + 145, T - 14, "DTDC Express Limited")
        c.drawString(L + 145, T - 23, "Regd. Office No. 3, Victoria Road")
        c.drawString(L + 145, T - 32, "Bengaluru - 560047")
        c.line(xm1, T - 23.5, xm2, T - 23.5)
        kv(xm1 + 38, T - 16, "Origin:", "NAGPUR", 8)
        kv(xm1 + 28, T - 39, "PRODUCT:", service, 8)
        c.line(xm2, T - 15.7, R, T - 15.7)
        c.line(xm2, T - 31.3, R, T - 31.3)
        kv(xm2 + 22, T - 11.5, "Dest:", dest_city, 7)
        kv(xm2 + 10, T - 27, "Type:", "NON-DOCUMENT", 7)
        kv(xm2 + 10, T - 42.5, "Date:", date_str, 7, vbold=False)
        cb = T - 102
        c.line(L, cb, R, cb)
        c.line(xm1, hb, xm1, cb)
        y = T - 56
        kv(L + 3, y, "Consignor's Name:", (COMPANY.get("name") or "").upper(), 7)
        c.setFont("Helvetica", 7)
        c.drawString(L + 3, y - 9, "Consignor's Address:")
        ay = wrapped(L + 72, y - 9, consignor_addr, 7, xm1 - L - 78)
        kv(L + 3, ay - 10, "GSTIN No.:", COMPANY.get("gstin") or "", 7, vbold=False)
        kv(L + 3, ay - 19, "Phone:", _to_local_phone(COMPANY.get("mobile")), 7)
        y2 = T - 56
        kv(xm1 + 3, y2, "Customer Ref No:", order.get("order_number") or "", 7)
        kv(xm1 + 3, y2 - 9, "Consignee's Name:", order.get("customer_name") or "", 7)
        c.setFont("Helvetica", 7)
        c.drawString(xm1 + 3, y2 - 18, "Consignee's Address:")
        ay2 = wrapped(xm1 + 75, y2 - 18, consignee_addr, 7, R - xm1 - 82)
        kv(xm1 + 3, ay2 - 10, "GSTIN No.:", "", 7, vbold=False)
        kv(xm1 + 3, ay2 - 19, "Phone:", shipment.get("recipient_phone") or "", 7)
        mb = T - 228
        c.line(L, mb, R, mb)
        c.line(xl, cb, xl, mb)
        c.line(xm1, cb, xm1, mb)
        kv(L + 3, cb - 10, "Content Specification:", "OTHERS", 7, cap_bold=True, vbold=False)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(L + 3, cb - 26, "Paperwork Enclosed :")
        decl = ("I/We declare that this consignment does not contain personal mail, cash, "
                "jewellery, contraband, illegal drugs, any prohibited items and commodities "
                "which can cause safety hazards while transporting")
        c.setFont("Helvetica", 6.5)
        yy = cb - 38
        for ln in simpleSplit(decl, "Helvetica", 6.5, xl - L - 8):
            c.drawCentredString((L + xl) / 2, yy, ln)
            yy -= 8
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString((L + xl) / 2, yy - 3, "Sender's Signature & Seal")
        terms = ("I have read and understood terms & conditions of carriage mentioned on "
                 "website www.dtdc.in, and I agree to the same.")
        c.setFont("Helvetica", 6.5)
        yy -= 13
        for ln in simpleSplit(terms, "Helvetica", 6.5, xl - L - 8):
            c.drawCentredString((L + xl) / 2, yy, ln)
            yy -= 8
        rows = [("Declared Value:", declared, True), ("No Of Pieces:", pieces, True),
                ("Actual Weight:", weight + " Kgs", True), ("Ewaybill Number:", "", False),
                ("Dim:", "Not Applicable", True), ("Charged weight:", weight + " Kgs", True)]
        ry = cb
        for cap, val, vb in rows:
            ry -= 10.5
            kv(xl + 3, ry, cap, val, 7, vbold=vb)
            c.line(xl, ry - 3, xm1, ry - 3)
        by_ = ry - 3
        kv(xl + 3, by_ - 9, "Name :", DTDC_LABEL_BRANCH["name"], 6.5, cap_bold=True, vbold=False)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(xl + 3, by_ - 17, "Address:")
        ay3 = wrapped(xl + 32, by_ - 17, DTDC_LABEL_BRANCH["address"], 6.5, xm1 - xl - 38, bold=False)
        kv(xl + 3, ay3 - 9, "Phone :", DTDC_LABEL_BRANCH["phone"], 6.5, cap_bold=True, vbold=False)
        c.setFont("Helvetica", 10)
        c.drawCentredString((xm1 + R) / 2 - 20, cb - 14, "Mode:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString((xm1 + R) / 2 + 8, cb - 14, mode)
        bc = code128.Code128(awb, barHeight=26, barWidth=1.15, quiet=False)
        bc.drawOn(c, (xm1 + R) / 2 - bc.width / 2, cb - 46)
        c.setFont("Helvetica", 9)
        c.drawCentredString((xm1 + R) / 2 - 25, cb - 58, "AWB No:")
        c.setFont("Helvetica-Bold", 9)
        c.drawString((xm1 + R) / 2 + 12, cb - 58, awb)
        rc = cb - 68
        c.line(xm1, rc, R, rc)
        c.line(xm2, rc, xm2, mb)
        if copy_name != "POD Copy":
            c.line(xm2, (rc + mb) / 2, R, (rc + mb) / 2)
            xbox = 505
            c.setFont("Helvetica-Bold", 13)
            c.drawCentredString((xm1 + xm2) / 2, (rc + mb) / 2 - 4, "Risk Surcharge")
            c.setFont("Helvetica", 9)
            c.drawCentredString((xm2 + xbox) / 2 + 10, rc - 18, "Owner")
            c.drawCentredString((xm2 + xbox) / 2 + 10, (rc + mb) / 2 - 18, "Carrier")
            for i, ticked in enumerate([not risk, risk]):
                yb = (rc - 26) if i == 0 else ((rc + mb) / 2 - 26)
                c.roundRect(xbox + 30, yb, 16, 16, 3)
                if ticked:
                    c.setFont("ZapfDingbats", 11)
                    c.drawString(xbox + 33.5, yb + 3.5, "4")
        else:
            c.line(xm1, (rc + mb) / 2, xm2, (rc + mb) / 2)
            c.setFont("Helvetica", 9)
            c.drawString(xm1 + 6, rc - 18, "Receiver's Name :")
            c.drawString(xm1 + 6, (rc + mb) / 2 - 18, "Phone Number :")
            c.drawString(xm2 + 8, rc - 18, "Receiver's Signature and Stamp")
        lb = B + 14
        c.line(L, lb, R, lb)
        c.setFont("Helvetica", 7)
        c.drawString(L + 12, mb - 9, "https://www.dtdc.in")
        c.drawString(L + 95, mb - 9, "|  customersupport@dtdc.com")
        c.drawString(L + 212, mb - 9, "|  +91-9606911811")
        c.drawString(xm1 + 3, mb - 9, "Remark :")
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString((L + R) / 2 - 30, B + 4,
                            "THIS DOCUMENT IS NOT A TAX INVOICE. WEIGHT CAPTURED BY DTDC "
                            "WILL BE USED FOR INVOICE GENERATION.")
        c.setFont("Helvetica", 7)
        c.drawString(R - 62, B + 4, copy_name)

    for i, name in enumerate(["Sender's Copy", "Account's Copy", "POD Copy"]):
        copy_block(7 + i * 258, name)
    c.showPage()
    c.save()
    return buf.getvalue()


async def _dtdc_fetch_label_bytes(shipment: dict, order: dict = None):
    """(bytes, content_type) for a booked consignment's label, or (None, reason).

    DTDC refuses labels until its booking sync completes ("Label cannot be
    generated until booking sync is complete"), minutes after softdata upload,
    although the consignment is real. When the order is supplied, that window
    is bridged by rendering our replica of their label from the booking data —
    the same thing DTDC's own portal does. Once their sync finishes, the
    official artwork is served again.
    """
    ref = shipment.get("awb") or shipment.get("reference_number")
    account = DTDC_ACCOUNTS.get(shipment.get("account") or "", {})
    if not ref or not account.get("api_key"):
        return None, "not booked through the DTDC API"
    reason = ""
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_LABEL}",
                            params={"reference_number": ref},
                            headers={"api-key": account["api_key"]})
        if r.status_code == 200 and r.content:
            media, _ext = _sniff_media(r.content, r.headers.get("content-type", ""))
            return r.content, media
        try:
            reason = (r.json().get("error") or {}).get("message") or f"HTTP {r.status_code}"
        except Exception:
            reason = f"HTTP {r.status_code}"
    except Exception as e:
        logging.error(f"DTDC label fetch failed for {ref}: {e}")
        reason = str(e)[:120]
    if order is not None:
        try:
            return _dtdc_render_label_pdf(order, shipment), "application/pdf"
        except Exception as e:
            logging.error(f"DTDC replica label render failed for {ref}: {e}")
    return None, reason


def _pdf_pages_jpg(raw: bytes, scale: float = 2.5, max_pages: int = 8) -> list:
    """Pages of a PDF rendered as JPEGs (~180 dpi). Empty list on failure."""
    out = []
    try:
        import pypdfium2 as pdfium
        import io as _io
        pdf = pdfium.PdfDocument(raw)
        try:
            for i in range(min(len(pdf), max_pages)):
                bmp = pdf[i].render(scale=scale)
                img = bmp.to_pil().convert("RGB")
                buf = _io.BytesIO()
                img.save(buf, format="JPEG", quality=88)
                out.append(buf.getvalue())
        finally:
            pdf.close()
    except Exception as e:
        logging.error(f"PDF->JPG render failed: {e}")
    return out


def _pdf_first_page_jpg(raw: bytes, scale: float = 2.5) -> Optional[bytes]:
    pages = _pdf_pages_jpg(raw, scale=scale, max_pages=1)
    return pages[0] if pages else None


def _quarter_sheet_pdf(images: list, per_page: int = 4):
    """Images laid out on A4 pages, in the order given, never stretched.

    per_page=4: quarter slots — 1 image fills one quarter, 4 fill the page,
    more continue overleaf (Amazon's 4x6 labels). per_page=1: each image gets
    a whole A4 page (DTDC's label is itself a full A4 three-copy sheet, which
    becomes unreadable shrunk to a quarter).
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.utils import ImageReader
    import io as _io

    page_w, page_h = A4
    if per_page == 1:
        quad_w, quad_h = page_w, page_h
        quads = [(0, 0)]
    else:
        per_page = 4
        quad_w, quad_h = page_w / 2, page_h / 2
        quads = [(0, quad_h), (quad_w, quad_h), (0, 0), (quad_w, 0)]
    pad = 8
    buffer = _io.BytesIO()
    c = pdfcanvas.Canvas(buffer, pagesize=A4)
    for idx, raw in enumerate(images):
        if idx and idx % per_page == 0:
            c.showPage()
        qx, qy = quads[idx % per_page]
        img = ImageReader(_io.BytesIO(raw))
        iw, ih = img.getSize()
        avail_w, avail_h = quad_w - 2 * pad, quad_h - 2 * pad
        scale = min(avail_w / iw, avail_h / ih)
        w, h = iw * scale, ih * scale
        c.drawImage(img, qx + pad + (avail_w - w) / 2, qy + pad + (avail_h - h) / 2,
                    width=w, height=h, preserveAspectRatio=True, anchor="c")
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


async def _dtdc_save_label_as_slip(shipment: dict) -> str:
    raw, _media = await _dtdc_fetch_label_bytes(shipment)
    if not raw:
        return ""
    _m, ext = _sniff_media(raw)
    if ext == "pdf":
        # Slips are shared to customers on WhatsApp and shown as thumbnails;
        # a JPG works everywhere a PDF does not. Keep the PDF only if the
        # render fails, so a slip is never silently lost.
        jpg = _pdf_first_page_jpg(raw)
        if jpg:
            raw, ext = jpg, "jpg"
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
    await ship_orders.update_one({"id": order["id"]}, {"$set": {
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
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
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
# Statuses that mean the parcel is genuinely in DTDC's hands. Anything not on
# this list — notably pickup_awaited and softdata_upload — is NOT a pickup.
#
# This used to be a substring search over the whole tracking JSON for hints
# including "PICKUP" and "BOOKED", so a freshly booked consignment showing
# "Pickup Awaited" matched "PICKUP" and was auto-dispatched on the spot.
DTDC_PICKED_STATUSES = {
    "pickup_accepted", "pickup_completed", "picked_up", "pickedup",
    "booked_at_hub", "in_transit", "intransit", "reached_at_hub",
    "out_for_delivery", "delivered",
}
DTDC_PICKED_EVENTS = {"pickup completed", "pickup accepted", "picked up"}


def _dtdc_norm(value) -> str:
    return re.sub(r"[^a-z_ ]", "", str(value or "").strip().lower())


def _dtdc_pickup_time(tracking: dict):
    """Timestamp if DTDC confirms the parcel was collected, else None.

    Matches the consignment status explicitly rather than searching the blob,
    so 'Pickup Awaited' can never be read as 'picked up'.
    """
    if not isinstance(tracking, dict):
        return None

    status = _dtdc_norm(tracking.get("status")).replace(" ", "_")
    events = tracking.get("events") or []

    picked = status in DTDC_PICKED_STATUSES
    event_time = None
    for ev in events:
        label = _dtdc_norm(ev.get("customer_update") or ev.get("type") or ev.get("status"))
        if label in DTDC_PICKED_EVENTS or label.replace(" ", "_") in DTDC_PICKED_STATUSES:
            picked = True
            event_time = event_time or ev.get("event_time") or ev.get("timestamp") or ev.get("date")
    if not picked:
        return None

    when = event_time
    if when is None:
        for ev in events:
            when = ev.get("event_time") or ev.get("timestamp") or ev.get("date")
            if when:
                break
    if when is None:
        return datetime.now(timezone.utc).isoformat()
    try:                                    # DTDC sends epoch milliseconds
        return datetime.fromtimestamp(int(when) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return str(when)


async def _dtdc_sync_all() -> list:
    if not _dtdc_configured():
        return []
    pending = await ship_orders.find({
        "dtdc_shipment.reference_number": {"$exists": True, "$ne": ""},
        "status": {"$nin": ["dispatched", "cancelled"]},
    }, {"_id": 0}).to_list(200)
    notes = []
    for o in pending:
        try:
            sh = o.get("dtdc_shipment") or {}
            ref = sh.get("awb") or sh.get("reference_number")
            if not ref:
                continue
            r = await _dtdc_track_any(ref, sh.get("account"))
            if r is None or r.status_code != 200:
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
    r = await _dtdc_track_any(ref, sh.get("account"))
    if r is None:
        return {"ok": False, "message": "No DTDC API key configured"}
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
        "rto": bool(order.get("rto")),
        "issue_note": order.get("issue_note") or order.get("damaged_note") or "",
        "issue_by": order.get("issue_by") or order.get("damaged_by") or "",
    }

    if courier == "Anjani":
        in_mh = "maharashtra" in str(sa.get("state") or "").strip().lower()
        # Rs40/kg within Maharashtra, Rs50/kg elsewhere, charged per started
        # kilogram — 2.619 kg bills as 3 kg. No GST on Anjani.
        rate = ANJANI_RATE_MAHARASHTRA if in_mh else ANJANI_RATE_REST
        chargeable = max(1, int(math.ceil(weight)))
        base = round(rate * chargeable, 2)
        row.update({"zone": "Maharashtra" if in_mh else "Rest of India",
                    "service": "Anjani", "rate_per_kg": rate,
                    "chargeable_weight_kg": chargeable,
                    "base": base, "fuel_percent": 0.0,
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


class OrderFlagsRequest(BaseModel):
    order_id: str
    damaged: bool = False
    rto: bool = False
    note: Optional[str] = ""


@api_router.put("/orders/{order_id}/flags")
async def set_order_flags(order_id: str, req: OrderFlagsRequest, user=Depends(get_current_user)):
    """Consignment issue flags — damaged and/or RTO — so accounts can raise them
    with the courier. Either, both, or neither (clearing the flags)."""
    if user["role"] not in ["admin", "accounts", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    now = datetime.now(timezone.utc).isoformat()
    any_flag = bool(req.damaged or req.rto)
    update = {
        "damaged": bool(req.damaged),
        "rto": bool(req.rto),
        "issue_note": (req.note or "").strip() if any_flag else "",
        "issue_by": user["name"] if any_flag else "",
        "issue_at": now if any_flag else "",
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


def _dtdc_account_for_docket(docket: str) -> str:
    """Which account a docket most likely belongs to, from its series.

    Mirrors _dtdc_route: D-series books on RL1386, M-series on RL1423. Only a
    hint — carrier-risk consignments of either series sit on RL1387 — so the
    caller still falls back to the other keys.
    """
    first = (str(docket or "").strip()[:1] or "").upper()
    return {"D": "RL1386", "M": "RL1423"}.get(first, "")


async def _dtdc_track_any(docket: str, preferred: str = ""):
    """Track a docket, trying the account that owns it.

    DTDC's tracking API is account-scoped: a consignment booked on RL1423
    returns 400 "Reference number is not valid" from any other key. Orders
    booked through the Excel flow carry no dtdc_shipment, so the account has
    to be inferred from the series and then confirmed by trying the rest.
    Returns the first 200, else the last response, or None if unconfigured.
    """
    order_keys, seen = [], set()
    for k in (preferred, _dtdc_account_for_docket(docket)):
        if k and k in DTDC_ACCOUNTS and k not in seen:
            order_keys.append(k)
            seen.add(k)
    order_keys += [k for k in DTDC_ACCOUNTS if k not in seen]

    last = None
    async with httpx.AsyncClient(timeout=25) as c:
        for name in order_keys:
            key = DTDC_ACCOUNTS[name].get("api_key")
            if not key:
                continue
            try:
                r = await c.get(f"{DTDC_BASE_URL}{DTDC_PATH_TRACK}",
                                params={"reference_number": docket},
                                headers={"api-key": key})
            except Exception as e:
                logging.warning(f"DTDC track {docket} on {name} failed: {e}")
                continue
            if r.status_code == 200:
                return r
            last = r
    return last


@api_router.get("/courier-status/{order_id}")
async def courier_status(order_id: str, user=Depends(get_current_user)):
    """Live status from the courier for a dispatched order (DTDC or Anjani).

    Open to every role: telecallers field "where is my parcel" calls, and the
    docket is already on the order they can see, so withholding the tracking
    only pushed them to ask someone else to look it up.
    """
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    courier = _order_courier(order)
    amazon = order.get("amazon_shipment") or {}
    if not courier and (amazon.get("tracking_id")
                        or str(order.get("courier_name") or "").strip().lower().startswith("amazon")):
        courier = "Amazon"
    docket = (order.get("dispatch") or {}).get("lr_no") or \
             (order.get("dtdc_shipment") or {}).get("awb") or \
             amazon.get("tracking_id") or ""
    if not docket:
        return {"ok": False, "message": "No docket number on this order"}

    if courier == "Amazon":
        if not _amazon_configured():
            return {"ok": False, "courier": courier, "docket": docket,
                    "message": "Amazon Shipping API is not configured"}
        payload = await _amazon_track(docket, amazon.get("carrier_id") or "ATS")
        if not payload:
            return {"ok": False, "courier": courier, "docket": docket,
                    "message": "Amazon returned no tracking data for this shipment"}
        events = []
        for ev in (payload.get("eventHistory") or []):
            loc = ev.get("location") or {}
            events.append({
                "type": ev.get("eventCode"),
                "customer_update": ev.get("eventCode"),
                "hub_name": " ".join(x for x in (loc.get("city"), loc.get("postalCode")) if x) or None,
                "event_time": ev.get("eventTime"),
            })
        events.reverse()          # newest first, matching the DTDC shape
        promised = payload.get("promisedDeliveryDate")
        return {
            "ok": True, "courier": courier, "docket": docket,
            "status": (payload.get("summary") or {}).get("status") or "-",
            "promised_delivery": promised,
            "last_event": (events[0] if events else None),
            "events": events[:12],
        }

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
        r = await _dtdc_track_any(docket, sh.get("account"))
        if r is None:
            return {"ok": False, "message": "No DTDC API key configured"}
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
            "rto_count": 0, "rto_total": 0.0,
        })
        s["shipments"] += 1
        s["weight_kg"] = round(s["weight_kg"] + r["weight_kg"], 3)
        for k in ("base", "fuel", "base_plus_fuel", "gst", "total"):
            s[k] = round(s[k] + r.get(k, 0), 2)
        if r.get("damaged"):
            s["damaged_count"] += 1
            s["damaged_total"] = round(s["damaged_total"] + r["total"], 2)
        if r.get("rto"):
            s["rto_count"] += 1
            s["rto_total"] = round(s["rto_total"] + r["total"], 2)
    grand = round(sum(v["total"] for v in summary.values()), 2)
    damaged_total = round(sum(v["damaged_total"] for v in summary.values()), 2)
    return {
        "date_from": start, "date_to": end,
        "fuel_surcharges": periods,
        "rows": rows, "summary": summary, "grand_total": grand,
        "damaged_total": damaged_total,
        "damaged_count": sum(v["damaged_count"] for v in summary.values()),
        "rto_total": round(sum(v["rto_total"] for v in summary.values()), 2),
        "rto_count": sum(v["rto_count"] for v in summary.values()),
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
                # Same weight-derived box the booking path uses, so the quote
                # shown here matches what is actually charged.
                "dimensions": {**_amazon_box({"packaging": {"weight_kg": pkg_weight}}),
                               "unit": "CENTIMETER"},
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


# ═══════════════════════════════════════════════════════════════════════════
# COURIER COMPARE: one pincode + weight -> every courier side by side.
# Each option is put on the same basis - what we actually pay, GST included -
# so "cheapest" compares like with like. DTDC, Anjani and Amazon reuse the
# exact logic of their own checker pages; Shiprocket is queried live.
# ═══════════════════════════════════════════════════════════════════════════
SHIPROCKET = {
    "email": os.environ.get("SHIPROCKET_EMAIL", ""),
    # The password has shell/compose-special characters, so the env file holds it base64-encoded.
    "password": os.environ.get("SHIPROCKET_PASSWORD", "") or _b64.b64decode(os.environ.get("SHIPROCKET_PASSWORD_B64", "") or b"").decode("utf-8", "ignore"),
    "pickup_pincode": os.environ.get("SHIPROCKET_PICKUP_PINCODE", os.environ.get("AMAZON_SHIP_ORIGIN_PINCODE", "440025")),
}
_shiprocket_token = {"token": "", "expires": 0.0}
COMPARE_GST = 18.0


async def _shiprocket_auth() -> str:
    import time
    if _shiprocket_token["token"] and _shiprocket_token["expires"] > time.time():
        return _shiprocket_token["token"]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://apiv2.shiprocket.in/v1/external/auth/login",
                         json={"email": SHIPROCKET["email"], "password": SHIPROCKET["password"]})
    if r.status_code != 200 or not r.json().get("token"):
        raise RuntimeError(f"Shiprocket login failed ({r.status_code})")
    _shiprocket_token.update(token=r.json()["token"], expires=time.time() + 8 * 86400)   # valid 10 days
    return _shiprocket_token["token"]


async def _compare_shiprocket(pincode: str, weight: float, cod: bool) -> list:
    if not (SHIPROCKET["email"] and SHIPROCKET["password"]):
        return [{"carrier": "Shiprocket", "service": "", "serviceable": None, "note": "Not configured on the server"}]
    try:
        token = await _shiprocket_auth()
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get("https://apiv2.shiprocket.in/v1/external/courier/serviceability/",
                            params={"pickup_postcode": SHIPROCKET["pickup_pincode"], "delivery_postcode": pincode,
                                    "weight": weight, "cod": 1 if cod else 0},
                            headers={"Authorization": f"Bearer {token}"})
        data = (r.json() or {}).get("data") or {}
        rows = data.get("available_courier_companies") or []
        if not rows:
            return [{"carrier": "Shiprocket", "service": "", "serviceable": False,
                     "note": "No Shiprocket courier serves this pincode"}]
        out = []
        for x in sorted(rows, key=lambda x: float(x.get("rate") or 0))[:6]:
            out.append({"carrier": "Shiprocket", "service": x.get("courier_name") or "",
                        "serviceable": True, "total": round(float(x.get("rate") or 0), 2),
                        "gst_note": "GST included", "eta": x.get("etd") or "",
                        "pickup": f"same day if booked before {x.get('cutoff_time')}" if x.get("cutoff_time") else "",
                        "rto_charges": x.get("rto_charges"),
                        "note": f"rating {x.get('rating')}" if x.get("rating") else "",
                        "cod_charge": x.get("cod_charges") if cod else None})
        return out
    except Exception as e:
        logging.error(f"compare/shiprocket: {e}")
        return [{"carrier": "Shiprocket", "service": "", "serviceable": None, "note": "Could not reach Shiprocket right now"}]


async def _compare_dtdc(pincode: str, weight: float) -> list:
    info = _dtdc_pincodes.get(pincode)
    if not info:
        return [{"carrier": "DTDC", "service": "", "serviceable": False, "note": "Not in DTDC's serviceable list"}]
    periods = await _fuel_surcharge_periods()
    fuel_pct = _fuel_percent_on(periods, datetime.now(IST).strftime("%Y-%m-%d"))
    quote = dtdc_quote_for(pincode, weight)
    out = []
    for svc, label, series in (("GROUND EXPRESS", "Ground Express", "D-Series"), ("STD EXP-A", "Standard", "M-Series")):
        base = dtdc_expense_base(info["category"], weight, svc)
        if not base:
            continue
        fuel = base * fuel_pct / 100.0
        total = (base + fuel) * (1 + DTDC_EXPENSE_GST_PERCENT / 100.0)
        out.append({"carrier": "DTDC", "service": f"{label} ({series})", "serviceable": True,
                    # what the telecaller quotes the customer - the old DTDC calculator figure
                    "charge_customer": (quote or {}).get("final_charge") if (quote or {}).get("series") == series else None,
                    "total": round(total, 2), "gst_note": f"freight {base:.0f} + fuel {fuel_pct:g}% + GST",
                    "eta": "", "note": f"{info.get('city', '')} - zone {info['category']}"})
    return out or [{"carrier": "DTDC", "service": "", "serviceable": False, "note": "No DTDC rate for this zone"}]


# Anjani marks every area of a pincode with a delivery type. Only some of them
# can take our parcels, so the pincode merely existing proves nothing.
ANJANI_DELIVERY_TYPES = {
    "1": ("normal", "Normal delivery"),
    "2": ("restricted", "Restricted / special delivery"),
    "3": ("documents", "Documents only - no parcels"),
    "9": ("none", "Not serviceable"),
}


async def _compare_anjani(pincode: str, weight: float, state: str) -> list:
    res = await anjani_check_pincode(pincode)
    if not res.get("serviceable"):
        return [{"carrier": "Anjani", "service": "", "serviceable": False, "note": res.get("message") or "Not serviceable"}]
    seen, areas = set(), []
    for center in res.get("centers") or []:
        for a in center.get("areas") or []:
            name = " ".join(str(a.get("areaName") or "").split())
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            kind, label = ANJANI_DELIVERY_TYPES.get(str(a.get("deliveryType") or "").strip(),
                                                    ("unknown", f"Type {a.get('deliveryType')} - confirm with Anjani"))
            areas.append({"name": name, "kind": kind, "label": label, "center": center.get("centerName") or ""})
    order = {"normal": 0, "restricted": 1, "unknown": 2, "documents": 3, "none": 4}
    areas.sort(key=lambda a: (order[a["kind"]], a["name"].lower()))
    usable = [a for a in areas if a["kind"] in ("normal", "restricted", "unknown")]
    if areas and not usable:
        return [{"carrier": "Anjani", "service": "", "serviceable": False, "areas": areas[:80],
                 "note": "Pincode is listed, but no area in it takes parcels (documents only / not serviceable)"}]
    in_mh = "maharashtra" in (state or "").lower()
    rate = ANJANI_RATE_MAHARASHTRA if in_mh else ANJANI_RATE_REST
    kg = max(1, int(math.ceil(weight)))
    centers = []
    for c in res.get("centers") or []:
        ad = c.get("address") or {}
        phones = sorted({x.strip() for x in f"{ad.get('mobile') or ''},{ad.get('phoneNumber') or ''}".split(",") if x.strip()})
        centers.append({"name": c.get("centerName") or "", "franchise": c.get("franchiseName") or "",
                        "address": ", ".join(x.strip() for x in (ad.get("address1"), ad.get("address2"), ad.get("city")) if x and x.strip()),
                        "phones": phones, "hub": (c.get("hub") or {}).get("centerName") or ""})
    normal = sum(1 for a in areas if a["kind"] == "normal")
    blocked = len(areas) - len(usable)
    if not areas:
        warning = "Anjani did not list areas for this pincode. Call the centre to confirm before choosing it."
    elif normal == 0:
        warning = "No area here has normal delivery - only restricted delivery. Confirm with Anjani before choosing it."
    else:
        warning = ("Anjani delivers area by area. Choose it only if the customer's area is marked Normal delivery below"
                   + (f" - {blocked} area(s) here are NOT serviceable." if blocked else "."))
    return [{"carrier": "Anjani", "service": "Surface", "serviceable": True, "total": round(rate * kg, 2),
             "gst_note": f"Rs {rate:g}/kg x {kg} kg, no GST", "eta": "",
             "warning": warning, "areas": areas[:80], "centers": centers,
             "note": ", ".join(sorted({c.get("centerName") or "" for c in res.get("centers") or []} - {""}))}]


def _compare_day(iso) -> str:
    """'2026-09-24T12:30:00Z' -> 'Sep 24, 2026' in IST; '' when absent."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(IST).strftime("%b %d, %Y") if iso else ""
    except ValueError:
        return ""


async def _compare_amazon(pincode: str, weight: float, cod: bool) -> list:
    res = await amazon_check_pincode(pincode, weight)
    if res.get("configured") is False:
        return [{"carrier": "Amazon Shipping", "service": "", "serviceable": None, "note": "Not configured"}]
    if not res.get("serviceable"):
        msg = res.get("detail") or res.get("message") or "Not serviceable"
        return [{"carrier": "Amazon Shipping", "service": "", "serviceable": False, "note": str(msg)[:140]}]
    out = []
    for r in res.get("rates") or []:
        base = float(r.get("amount") or 0)
        cod_fee = 30.0 if cod else 0.0
        out.append({"carrier": "Amazon Shipping", "service": r.get("service") or "", "serviceable": True,
                    "total": round((base + cod_fee) * (1 + COMPARE_GST / 100.0), 2),
                    "gst_note": f"{base:.0f}" + (" + 30 COD" if cod else "") + " + 18% GST",
                    "eta": _compare_day(((r.get("promise") or {}).get("deliveryWindow") or {}).get("end")),
                    "pickup": _compare_day(((r.get("promise") or {}).get("pickupWindow") or {}).get("start")),
                    "note": "max 22 kg per parcel" if weight > 22 else ""})
    return out


# ═══════════════════════════════════════════════════════════════════════════
# SHIPROCKET: pincode check, per-order quotes, booking, label, cancel, dispatch.
# Mirrors the DTDC / Amazon flows. One Shiprocket account fronts many couriers,
# so booking always means "pick a courier from the live quote, then buy it".
# ═══════════════════════════════════════════════════════════════════════════
SR_BASE = "https://apiv2.shiprocket.in/v1/external"
SR_PICKUP_LOCATION = os.environ.get("SHIPROCKET_PICKUP_LOCATION", "Primary")
SR_ROLES = ["admin", "dispatch", "packaging", "accounts"]
SR_COURIER_RE = {"$regex": r"^\s*shiprocket", "$options": "i"}


def _sr_configured() -> bool:
    return bool(SHIPROCKET["email"] and SHIPROCKET["password"])


async def _sr_call(method: str, path: str, **kw) -> tuple:
    """(status_code, json) against the Shiprocket API with the cached token."""
    token = await _shiprocket_auth()
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.request(method, SR_BASE + path, headers={"Authorization": f"Bearer {token}"}, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:400]}


async def _sr_couriers(pincode: str, weight: float, cod: bool, declared: float = 0) -> list:
    params = {"pickup_postcode": SHIPROCKET["pickup_pincode"], "delivery_postcode": pincode,
              "weight": weight, "cod": 1 if cod else 0}
    if declared:
        params["declared_value"] = int(declared)
    code, data = await _sr_call("GET", "/courier/serviceability/", params=params)
    rows = ((data or {}).get("data") or {}).get("available_courier_companies") or []
    out = [{"courier_id": x.get("courier_company_id"), "name": x.get("courier_name") or "",
            "rate": round(float(x.get("rate") or 0), 2), "freight": x.get("freight_charge"),
            "cod_charges": x.get("cod_charges"), "etd": x.get("etd") or "",
            "days": x.get("estimated_delivery_days"), "rating": x.get("rating"),
            "surface": bool(x.get("is_surface")), "min_weight": x.get("min_weight"),
            "rto_charges": x.get("rto_charges"), "cutoff_time": x.get("cutoff_time") or "",
            "pickup_performance": x.get("pickup_performance"),
            "delivery_performance": x.get("delivery_performance")} for x in rows]
    out.sort(key=lambda x: x["rate"])
    return out


def _sr_weight(order: dict) -> tuple:
    """(weight_kg, source). Only the weight packing entered counts - the
    telecaller's estimate from the carrier picker is for quoting, never booking."""
    try:
        w = float(str((order.get("packaging") or {}).get("weight_kg") or "").strip() or 0)
    except ValueError:
        w = 0.0
    return (w, "packing") if w > 0 else (0.0, "")


def courier_name_is_sr(order: dict) -> bool:
    return (order.get("courier_name") or "").strip().lower().startswith("shiprocket")


def _sr_require(user):
    if user["role"] not in SR_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not _sr_configured():
        raise HTTPException(status_code=400, detail="Shiprocket is not configured on the server")


@api_router.get("/shiprocket/check/{pincode}")
async def shiprocket_check(pincode: str, weight: float = 1.0, cod: bool = False, user=Depends(get_current_user)):
    """Which Shiprocket couriers serve a pincode, with live rates (GST included)."""
    pincode = pincode.strip()
    if not pincode.isdigit() or len(pincode) != 6:
        return {"serviceable": False, "configured": True, "message": "Invalid pincode format."}
    if not _sr_configured():
        return {"serviceable": None, "configured": False, "message": "Shiprocket is not configured on the server."}
    try:
        city, state = await _resolve_pincode_geo(pincode)
        couriers = await _sr_couriers(pincode, max(0.05, float(weight or 1)), cod)
        if not couriers:
            return {"serviceable": False, "configured": True, "city": city, "state": state,
                    "message": "No Shiprocket courier serves this pincode" + (" for COD." if cod else ".")}
        return {"serviceable": True, "configured": True, "city": city, "state": state,
                "couriers": couriers, "count": len(couriers)}
    except Exception as e:
        logging.error(f"shiprocket check: {e}")
        return {"serviceable": False, "configured": True, "message": "Unable to reach Shiprocket right now."}


@api_router.get("/shiprocket/wallet")
async def shiprocket_wallet(user=Depends(get_current_user)):
    _sr_require(user)
    code, data = await _sr_call("GET", "/account/details/wallet-balance")
    return {"balance": float(((data or {}).get("data") or {}).get("balance_amount") or 0)}


@api_router.get("/shiprocket/bookable")
async def shiprocket_bookable(user=Depends(get_current_user)):
    """Orders assigned to Shiprocket that packing has weighed and that are not dispatched."""
    _sr_require(user)
    orders = await ship_orders.find({
        "courier_name": SR_COURIER_RE, "status": {"$nin": ["cancelled", "dispatched"]},
        "$or": [{"packaging.weight_kg": {"$nin": ["", None]}}, {"shiprocket_shipment.awb": {"$nin": ["", None]}}],
    }, {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "grand_total": 1, "shipping_address": 1,
        "packaging": 1, "shiprocket_shipment": 1, "status": 1, "is_cod": 1, "amount_paid": 1, "cod_amount": 1,
        "shiprocket_courier": 1}).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        sh = o.get("shiprocket_shipment") or None
        weight, source = _sr_weight(o)
        if weight <= 0 and sh and sh.get("awb"):
            weight, source = float(sh.get("weight_kg") or 0), "booked"     # what the label was bought at
        if weight <= 0:
            continue
        out.append({"id": o["id"], "order_number": o.get("order_number"), "customer_name": o.get("customer_name"),
                    "grand_total": o.get("grand_total"), "status": o.get("status"),
                    "weight_kg": weight, "weight_source": source, "num_boxes": pkg.get("num_boxes") or "1",
                    "shipping_address": o.get("shipping_address") or {},
                    "is_cod": bool(o.get("is_cod")), "cod_amount": _amazon_cod_amount(o),
                    "shiprocket_courier": o.get("shiprocket_courier") or None,
                    "shiprocket_shipment": ({k: v for k, v in sh.items() if k != "raw"} if sh else None)})
    return out


class ShiprocketBookRequest(BaseModel):
    order_id: str
    courier_id: Optional[int] = None         # which quoted courier to buy; cheapest if omitted
    payment_mode: Optional[str] = None       # "prepaid" | "cod"; prepaid unless stated
    declared_value: Optional[float] = None   # required when the order total is 0
    insure: Optional[bool] = False           # Shiprocket "Secure Shipment" cover


def _sr_cod(order: dict, mode: Optional[str]) -> float:
    mode = (mode or "").strip().lower()
    if mode == "cod":
        return _amazon_cod_amount({**order, "is_cod": True})
    return 0.0          # prepaid unless COD is stated - never inferred


@api_router.post("/shiprocket/quote")
async def shiprocket_quote(req: ShiprocketBookRequest, user=Depends(get_current_user)):
    """Live courier list for one order - books nothing."""
    _sr_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    sa = order.get("shipping_address") or {}
    weight, weight_source = _sr_weight(order)
    if weight <= 0:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    cod = _sr_cod(order, req.payment_mode)
    if (req.payment_mode or "").lower() == "cod" and cod <= 0:
        raise HTTPException(status_code=400, detail="Nothing left to collect - this order is fully paid.")
    couriers = await _sr_couriers(str(sa.get("pincode") or ""), weight, cod > 0, _declared_value(order))
    if not couriers:
        return {"ok": False, "message": "No Shiprocket courier serves this address" + (" for COD" if cod > 0 else "")}
    pref = (order.get("shiprocket_courier") or {})
    return {"ok": True, "couriers": couriers, "is_cod": cod > 0, "cod_amount": cod, "weight_kg": weight,
            "weight_source": weight_source,
            "preferred_courier_id": pref.get("courier_id"), "preferred_name": pref.get("name"),
            "preferred_rate": pref.get("rate"), "preferred_weight_kg": pref.get("weight_kg")}


@api_router.post("/shiprocket/book")
async def shiprocket_book(req: ShiprocketBookRequest, user=Depends(get_current_user)):
    """BUYS a real Shiprocket shipment: creates the order, assigns the AWB, schedules pickup."""
    _sr_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("shiprocket_shipment") or {}).get("awb"):
        raise HTTPException(status_code=400, detail="This order is already booked with Shiprocket")
    if req.declared_value and float(req.declared_value) > 0:
        order["declared_value_override"] = float(req.declared_value)
    elif float(order.get("grand_total") or 0) <= 0:
        raise HTTPException(status_code=400, detail="Order total is \u20b90 - enter a declared value for the shipment before booking")
    pkg = order.get("packaging") or {}
    weight, weight_source = _sr_weight(order)
    if weight <= 0:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    phone = await _order_recipient_phone(order)
    if not phone:
        raise HTTPException(status_code=400, detail="Customer has no valid phone number. Add one before booking.")
    sa = order.get("shipping_address") or {}
    line1, line2 = _address_lines(sa, cap=160)
    if len((line1 or "").strip()) < 3:
        raise HTTPException(status_code=400, detail="Shipping address is too short for the courier")
    cod = _sr_cod(order, req.payment_mode)
    if (req.payment_mode or "").lower() == "cod" and cod <= 0:
        raise HTTPException(status_code=400, detail="Nothing left to collect - this order is fully paid.")
    declared = _declared_value(order)
    couriers = await _sr_couriers(str(sa.get("pincode") or ""), weight, cod > 0, declared)
    if not couriers:
        raise HTTPException(status_code=400, detail="No Shiprocket courier serves this address")
    want = req.courier_id or ((order.get("shiprocket_courier") or {}).get("courier_id") if courier_name_is_sr(order) else None)
    chosen = next((c for c in couriers if want and c["courier_id"] == want), None) or couriers[0]

    # Shiprocket de-duplicates on order_id, so a cancelled or half-made earlier
    # attempt must never be reused: every retry gets a fresh reference.
    rebooks = sum(1 for c in (order.get("cancelled_shipments") or []) if (c.get("courier") or "") == "Shiprocket")
    rebooks += int(order.get("shiprocket_failed_attempts") or 0)
    ref = (order.get("order_number") or order["id"][:20]) + (f"-R{rebooks}" if rebooks else "")
    name = (sa.get("address_name") or order.get("customer_name") or "Customer").strip()
    box = _amazon_box(order)
    value = cod if cod > 0 else declared          # a COD parcel collects exactly what is due
    items = []
    for it in order.get("items") or []:
        amt = float(it.get("total") or it.get("amount") or 0)
        items.append({"name": (it.get("product_name") or "Item")[:100],
                      "sku": re.sub(r"[^A-Za-z0-9]+", "-", (it.get("product_name") or "item"))[:40] or "item",
                      "units": 1, "selling_price": round(amt, 2)})
    if not items or sum(i["selling_price"] for i in items) <= 0:
        items = [{"name": "Aroma products", "sku": "AROMA", "units": 1, "selling_price": round(value, 2)}]
    payload = {
        "order_id": ref, "order_date": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
        "pickup_location": SR_PICKUP_LOCATION,
        "billing_customer_name": name[:50], "billing_last_name": "",
        "billing_address": line1, "billing_address_2": line2 or "",
        "billing_city": sa.get("city") or "", "billing_pincode": str(sa.get("pincode") or ""),
        "billing_state": sa.get("state") or "", "billing_country": "India",
        "billing_email": await _amazon_recipient_email(order), "billing_phone": phone,
        "shipping_is_billing": True, "order_items": items,
        "payment_method": "COD" if cod > 0 else "Prepaid", "sub_total": round(value, 2),
        "length": box["length"], "breadth": box["width"], "height": box["height"], "weight": weight,
        "is_insurance_opt": bool(req.insure),
    }
    code, created = await _sr_call("POST", "/orders/create/adhoc", json=payload)
    shipment_id, sr_order_id = (created or {}).get("shipment_id"), (created or {}).get("order_id")
    if code not in (200, 201) or not shipment_id:
        logging.error(f"Shiprocket create failed: {code} {str(created)[:400]}")
        raise HTTPException(status_code=400, detail=f"Shiprocket refused the order: {str(created)[:250]}")

    code, awb = await _sr_call("POST", "/courier/assign/awb",
                               json={"shipment_id": shipment_id, "courier_id": chosen["courier_id"]})
    d = ((awb or {}).get("response") or {}).get("data") or {}
    awb_code = d.get("awb_code") or (awb or {}).get("awb_code")
    if not awb_code:
        # do not leave a half-made order sitting in the Shiprocket panel
        await _sr_call("POST", "/orders/cancel", json={"ids": [sr_order_id]})
        await ship_orders.update_one({"id": req.order_id}, {"$inc": {"shiprocket_failed_attempts": 1}})
        reason = d.get("awb_assign_error") or (awb or {}).get("message") or str(awb)[:200]
        raise HTTPException(status_code=400, detail=f"Shiprocket could not assign {chosen['name']}: {reason}")

    code, pk = await _sr_call("POST", "/courier/generate/pickup", json={"shipment_id": [shipment_id]})
    pickup = (pk or {}).get("response") or {}
    pickup_date = pickup.get("pickup_scheduled_date") or ""
    if isinstance(pickup_date, dict):
        pickup_date = pickup_date.get("date") or ""
    code, lb = await _sr_call("POST", "/courier/generate/label", json={"shipment_id": [shipment_id]})
    shipment = {
        "sr_order_id": sr_order_id, "shipment_id": shipment_id, "reference": ref,
        "awb": awb_code, "tracking_id": awb_code,
        "courier_id": chosen["courier_id"], "courier_name": d.get("courier_name") or chosen["name"],
        "rate": chosen["rate"], "etd": chosen.get("etd") or "", "days": chosen.get("days"),
        "pickup_date": str(pickup_date)[:19], "pickup_note": str(pickup.get("data") or "")[:160],
        "is_cod": cod > 0, "cod_amount": cod, "declared_value": round(value, 2), "insured": bool(req.insure),
        "weight_kg": weight, "weight_source": weight_source, "label_url": (lb or {}).get("label_url") or "",
        "booked_by": user["name"], "booked_at": datetime.now(timezone.utc).isoformat(),
    }
    await ship_orders.update_one({"id": req.order_id}, {"$set": {
        "shiprocket_shipment": shipment, "courier_name": "Shiprocket",
        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "shipment": shipment}


@api_router.post("/shiprocket/bulk-book")
async def shiprocket_bulk_book(req: BulkBookRequest, user=Depends(get_current_user)):
    """Books several orders, each on its cheapest courier. Prepaid unless stated."""
    _sr_require(user)
    mode = (req.payment_mode or "prepaid").strip().lower()
    if mode not in ("prepaid", "cod"):
        raise HTTPException(status_code=400, detail="payment_mode must be prepaid or cod")

    async def one(oid):
        ch = (req.choices or {}).get(oid) or {}
        return await shiprocket_book(ShiprocketBookRequest(
            order_id=oid, payment_mode=(ch.get("payment_mode") or mode),
            courier_id=int(ch["courier_id"]) if ch.get("courier_id") else None,
            insure=bool(ch.get("insure")),
            declared_value=(req.declared_values or {}).get(oid)), user=user)

    return await _bulk_book(req.order_ids, one, user, "Shiprocket")


async def _sr_cancel_one(order_id: str, user) -> dict:
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    shp = order.get("shiprocket_shipment") or {}
    if not shp.get("sr_order_id"):
        raise HTTPException(status_code=400, detail="No Shiprocket booking on this order")
    if (order.get("status") or "") == "dispatched":
        raise HTTPException(status_code=400, detail="Order is already dispatched - undo the dispatch before cancelling the label")
    code, data = await _sr_call("POST", "/orders/cancel", json={"ids": [shp["sr_order_id"]]})
    if code not in (200, 201, 204):
        raise HTTPException(status_code=400, detail=f"Shiprocket cancel failed: {str(data)[:250]}")
    now = datetime.now(timezone.utc).isoformat()
    await ship_orders.update_one({"id": order_id}, {
        "$push": {"cancelled_shipments": {"courier": "Shiprocket", **shp, "cancelled_by": user["name"], "cancelled_at": now}},
        "$unset": {"shiprocket_shipment": ""}, "$set": {"updated_at": now}})
    return {"ok": True, "cancelled": shp.get("awb") or shp.get("sr_order_id")}


@api_router.post("/shiprocket/cancel")
async def shiprocket_cancel(req: CancelLabelRequest, user=Depends(get_current_user)):
    _sr_require(user)
    return await _sr_cancel_one(req.order_id, user)


@api_router.post("/shiprocket/bulk-cancel")
async def shiprocket_bulk_cancel(req: BulkBookRequest, user=Depends(get_current_user)):
    _sr_require(user)

    async def one(oid):
        return await _sr_cancel_one(oid, user)

    return await _bulk_book(req.order_ids, one, user, "Shiprocket cancel")


@api_router.get("/shiprocket/labels")
async def shiprocket_labels(ids: str, token: str = "", user=None):
    """One PDF with the labels of the selected orders (Shiprocket renders it)."""
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    wanted = [i for i in (ids or "").split(",") if i][:50]
    shipment_ids = []
    async for o in ship_orders.find({"id": {"$in": wanted}}, {"_id": 0, "shiprocket_shipment": 1}):
        sid = (o.get("shiprocket_shipment") or {}).get("shipment_id")
        if sid:
            shipment_ids.append(sid)
    if not shipment_ids:
        raise HTTPException(status_code=404, detail="None of these orders has a Shiprocket label")
    code, lb = await _sr_call("POST", "/courier/generate/label", json={"shipment_id": shipment_ids})
    url = (lb or {}).get("label_url")
    if not url:
        raise HTTPException(status_code=400, detail=f"Shiprocket did not return a label: {str(lb)[:200]}")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.get(url)
    return StreamingResponse(io.BytesIO(r.content), media_type="application/pdf",
                             headers={"Content-Disposition": "inline; filename=shiprocket-labels.pdf"})


class ShiprocketDispatchRequest(BaseModel):
    order_id: str
    docket_no: Optional[str] = ""


@api_router.post("/shiprocket/dispatch")
async def shiprocket_dispatch(req: ShiprocketDispatchRequest, user=Depends(get_current_user)):
    """Mark a booked Shiprocket order dispatched; the label's first page becomes the slip image."""
    _sr_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    docket = (req.docket_no or "").strip() or (order.get("shiprocket_shipment") or {}).get("awb") or ""
    if not docket:
        raise HTTPException(status_code=400, detail="Tracking / AWB number is required")
    return await _shiprocket_mark_dispatched(order, datetime.now(timezone.utc).isoformat(), user["name"], docket)


async def _shiprocket_mark_dispatched(order: dict, when: str, by: str, docket: str = "") -> dict:
    """Shared dispatch write for the manual button and the pickup poller."""
    shp = order.get("shiprocket_shipment") or {}
    docket = docket or shp.get("awb") or ""
    dispatch = order.get("dispatch") or {}
    slips = list(dispatch.get("dispatch_slip_images") or [])
    if not slips and shp.get("label_url"):
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
                pdf = (await c.get(shp["label_url"])).content
            jpg = _pdf_first_page_jpg(pdf)
            jpg = jpg[0] if isinstance(jpg, (list, tuple)) else jpg
            if jpg:
                fname = f"{uuid.uuid4()}.jpg"
                async with aiofiles.open(UPLOAD_DIR / fname, "wb") as f:
                    await f.write(jpg)
                slips.append(f"/api/uploads/{fname}")
        except Exception as e:
            logging.warning(f"shiprocket slip image failed: {e}")
    dispatch.update({"courier_name": "Shiprocket", "courier_partner": shp.get("courier_name") or "",
                     "transporter_name": "", "lr_no": docket, "dispatch_slip_images": slips,
                     "dispatch_type": "courier", "porter_link": "",
                     "dispatched_by": by, "dispatched_at": when})
    await ship_orders.update_one({"id": order["id"]}, {"$set": {
        "dispatch": dispatch, "status": "dispatched", "courier_name": "Shiprocket",
        "shiprocket_shipment.picked_up_at": when, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "lr_no": docket, "slips": slips}


# Shiprocket shipment_status codes that mean the parcel has left us.
SR_GONE_STATUSES = {6, 7, 17, 18, 38, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 59}
SR_GONE_WORDS = ("picked up", "in transit", "shipped", "out for delivery", "delivered", "reached")
SR_SYNC_INTERVAL = int(os.environ.get("SHIPROCKET_SYNC_INTERVAL", "180"))


async def _shiprocket_sync_all() -> int:
    """Booked Shiprocket orders that the courier has collected become dispatched."""
    n = 0
    async for o in ship_orders.find({"shiprocket_shipment.awb": {"$nin": ["", None]},
                                   "status": {"$nin": ["dispatched", "cancelled"]}}, {"_id": 0}).limit(100):
        awb = o["shiprocket_shipment"]["awb"]
        try:
            code, d = await _sr_call("GET", f"/courier/track/awb/{awb}")
        except Exception as e:
            logging.warning(f"shiprocket track {awb}: {e}")
            continue
        td = (d or {}).get("tracking_data") or {}
        status = td.get("shipment_status")
        current = " ".join(str(t.get("current_status") or "") for t in (td.get("shipment_track") or [])).lower()
        gone = (isinstance(status, int) and status in SR_GONE_STATUSES) or any(w in current for w in SR_GONE_WORDS)
        if not gone:
            continue
        when = datetime.now(timezone.utc).isoformat()
        for a in td.get("shipment_track_activities") or []:
            if "picked up" in str(a.get("sr-status-label") or a.get("status") or "").lower() and a.get("date"):
                try:
                    when = datetime.strptime(a["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
                break
        await _shiprocket_mark_dispatched(o, when, "Shiprocket (auto)", awb)
        n += 1
        logging.info(f"Shiprocket pickup: {o.get('order_number')} dispatched ({current or status})")
    return n


async def _shiprocket_sync_loop():
    await asyncio.sleep(60)
    while True:
        try:
            await _shiprocket_sync_all()
        except Exception as e:
            logging.error(f"Shiprocket sync loop error: {e}")
        await asyncio.sleep(SR_SYNC_INTERVAL)


@app.on_event("startup")
async def _start_shiprocket_sync():
    if _sr_configured():
        asyncio.create_task(_shiprocket_sync_loop())
        logging.info(f"Shiprocket pickup sync every {SR_SYNC_INTERVAL}s")


@api_router.post("/shiprocket/sync-tracking")
async def shiprocket_sync_now(user=Depends(get_current_user)):
    _sr_require(user)
    return {"count": await _shiprocket_sync_all()}


# ═══════════════════════════════════════════════════════════════════════════
# AMAZON SELF-SHIP THROUGH OUR COURIERS. Self-ship Amazon orders are shipped by
# us, so every courier (booking, labels, cancel, dispatch, pickup pollers) sees
# them through `ship_orders`, which reads regular orders first and then Amazon
# self-ship orders presented in the same shape. Lists only ever see the city and
# pincode; the buyer's name, street and phone (typed in from Seller Central,
# stored encrypted) are read only when a label is bought. On dispatch the order
# is confirmed to Amazon with the carrier and tracking number.
# ═══════════════════════════════════════════════════════════════════════════
_AMZ_PUBLIC_RE = re.compile(r"^(.*?),\s*(.*?)\s*-\s*(\d{6})$")


def _amz_public_place(a: dict) -> tuple:
    st = a.get("ship_to") or {}
    m = _AMZ_PUBLIC_RE.match((a.get("address_public") or "").strip())
    city = st.get("city") or (m.group(1).strip() if m else "")
    state = st.get("state") or ((m.group(2).strip().title()) if m else "")
    pin = st.get("pincode") or (m.group(3) if m else "")
    return city, state, pin


def _amz_as_order(a: dict, full: bool = True) -> dict:
    st = a.get("ship_to") or {}
    city, state, pin = _amz_public_place(a)
    public_name = f"Amazon customer ({city or 'India'})"
    sa = {"city": city, "state": state, "pincode": pin, "label": ""}
    phone = ""
    if full:
        sa["address_name"] = _pii_dec(st.get("name") or "") or ""
        sa["address_line"] = _pii_dec(st.get("line1") or "") or ""
        phone = _pii_dec(st.get("phone") or "") or ""
    o = {k: v for k, v in a.items() if k not in ("address", "phone")}
    total = float(a.get("grand_total") or 0)
    o.update({
        "order_number": a.get("am_order_number"), "customer_name": public_name,
        "customer_phone": [phone] if phone else [], "customer_id": None, "shipping_address": sa,
        "items": [{**it, "total": it.get("amount"), "product_name": it.get("product_name") or "Item"} for it in (a.get("items") or [])],
        "gst_applicable": True, "company": DEFAULT_COMPANY, "carrier_risk_applicable": False,
        "amount_paid": 0.0 if a.get("is_cod") else total, "transporter_name": a.get("transporter_name") or "",
        "shipping_method": a.get("shipping_method") or "courier", "source_collection": "amazon_orders",
        "ship_to_ready": bool(st.get("name") and st.get("line1") and st.get("phone") and pin),
    })
    return o


def _amz_translate_update(upd: dict) -> dict:
    out = {}
    for op, body in (upd or {}).items():
        body = dict(body) if isinstance(body, dict) else body
        if op == "$set" and isinstance(body, dict):
            d = body.get("dispatch")
            if isinstance(d, dict) and d.get("lr_no") and not d.get("lr_number"):
                body["dispatch"] = {**d, "lr_number": d["lr_no"]}
            if "dispatch.lr_no" in body:
                body["dispatch.lr_number"] = body["dispatch.lr_no"]
        out[op] = body
    return out


class _ShipCursor:
    def __init__(self, flt, proj):
        self.flt, self.proj, self._sort, self._limit = flt, proj, None, 0

    def sort(self, *a, **k):
        self._sort = (a, k)
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, n=None):
        cur = db.orders.find(self.flt, self.proj) if self.proj is not None else db.orders.find(self.flt)
        if self._sort:
            cur = cur.sort(*self._sort[0], **self._sort[1])
        cap = self._limit or n or 1000
        out = await cur.to_list(cap)
        acur = db.amazon_orders.find({**self.flt, "ship_type": "self_ship"}, {"_id": 0})
        async for a in acur.limit(200):
            out.append(_amz_as_order(a, full=False))
        return out[:cap] if (self._limit or n) else out

    def __aiter__(self):
        async def gen():
            for o in await self.to_list():
                yield o
        return gen()


class _ShipOrders:
    """db.orders for courier code, extended with Amazon self-ship orders."""

    async def find_one(self, flt, proj=None, **kw):
        doc = await (db.orders.find_one(flt, proj, **kw) if proj is not None else db.orders.find_one(flt, **kw))
        if doc is not None:
            return doc
        a = await db.amazon_orders.find_one({**flt, "ship_type": "self_ship"}, {"_id": 0})
        return _amz_as_order(a) if a else None

    def find(self, flt, proj=None):
        return _ShipCursor(flt, proj)

    async def update_one(self, flt, upd, **kw):
        r = await db.orders.update_one(flt, upd, **kw)
        if r.matched_count:
            return r
        r2 = await db.amazon_orders.update_one({**flt, "ship_type": "self_ship"}, _amz_translate_update(upd), **kw)
        if r2.matched_count and ((upd or {}).get("$set") or {}).get("status") == "dispatched" and flt.get("id"):
            asyncio.create_task(_amz_confirm_shipment(flt["id"]))
        return r2


ship_orders = _ShipOrders()


# Amazon's own carrier codes for the couriers we use; anything else goes as "Other".
_AMZ_CARRIER_CODES = {"dtdc": "DTDC", "delhivery": "Delhivery", "blue dart": "Blue Dart", "bluedart": "Blue Dart",
                      "xpressbees": "Xpressbees", "ekart": "Ekart", "india post": "India Post", "ecom express": "Ecom Express",
                      "shadowfax": "Shadowfax", "amazon": "Amazon Shipping"}


def _amz_carrier(order: dict) -> tuple:
    d = order.get("dispatch") or {}
    raw = (d.get("courier_partner") or d.get("courier_name") or order.get("courier_name") or "").strip()
    if raw.lower().startswith("shiprocket"):
        raw = (order.get("shiprocket_shipment") or {}).get("courier_name") or raw
    name = raw.replace("(via Shiprocket)", "").replace("(LTL)", "").strip() or "Other"
    low = name.lower()
    code = next((v for k, v in _AMZ_CARRIER_CODES.items() if low.startswith(k)), "Other")
    return code, name


async def _amz_confirm_shipment(order_id: str, force: bool = False) -> dict:
    """Tell Amazon a self-ship order has shipped (carrier + tracking number)."""
    a = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not a or a.get("ship_type") != "self_ship" or not _spapi_configured():
        return {"status": "skipped"}
    prev = a.get("amazon_confirm") or {}
    if prev.get("status") == "confirmed" and not force:
        return prev
    d = a.get("dispatch") or {}
    lr = (d.get("lr_no") or d.get("lr_number") or "").strip()
    rec = {"attempts": int(prev.get("attempts") or 0) + 1, "at": datetime.now(timezone.utc).isoformat()}
    if not lr:
        rec.update(status="failed", error="No tracking / LR number on the dispatch")
    else:
        code, name = _amz_carrier(a)
        try:
            when = datetime.fromisoformat(str(d.get("dispatched_at") or rec["at"]).replace("Z", "+00:00"))
        except ValueError:
            when = datetime.now(timezone.utc)
        items = [{"orderItemId": it["order_item_id"], "quantity": int(it.get("quantity") or 1)}
                 for it in (a.get("items") or []) if it.get("order_item_id")]
        body = {"marketplaceId": SPAPI["marketplace"], "packageDetail": {
            "packageReferenceId": "1", "carrierCode": code, "carrierName": name, "shippingMethod": "Standard",
            "trackingNumber": lr, "shipDate": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "orderItems": items}}
        if code != "Other":
            body["packageDetail"].pop("carrierName", None)
        try:
            token = await _spapi_token()
            async with httpx.AsyncClient(timeout=40) as c:
                r = await c.post(f"{SPAPI['endpoint']}/orders/v0/orders/{a['amazon_order_id']}/shipmentConfirmation",
                                 json=body, headers={"x-amz-access-token": token, "Content-Type": "application/json"})
            if r.status_code in (200, 204):
                rec.update(status="confirmed", carrier=name, carrier_code=code, tracking=lr, error="")
            else:
                rec.update(status="failed", carrier=name, tracking=lr, error=f"{r.status_code}: {r.text[:240]}")
        except Exception as e:
            rec.update(status="failed", error=str(e)[:240])
    await db.amazon_orders.update_one({"id": order_id}, {"$set": {"amazon_confirm": rec}})
    if rec["status"] != "confirmed":
        logging.warning(f"Amazon ship-confirm {a.get('am_order_number')}: {rec.get('error')}")
    return rec


async def _amz_confirm_sweep():
    async for a in db.amazon_orders.find({"ship_type": "self_ship", "status": "dispatched",
                                         "amazon_confirm.status": {"$ne": "confirmed"},
                                         "$or": [{"amazon_confirm.attempts": {"$exists": False}}, {"amazon_confirm.attempts": {"$lt": 6}}],
                                         "$and": [{"$or": [{"dispatch.lr_no": {"$nin": ["", None]}}, {"dispatch.lr_number": {"$nin": ["", None]}}]}],
                                         "dispatch.dispatched_at": {"$gte": "2026-09-26T00:00:00"}},
                                        {"_id": 0, "id": 1}).limit(20):
        await _amz_confirm_shipment(a["id"])


async def _amz_confirm_loop():
    await asyncio.sleep(120)
    while True:
        try:
            await _amz_confirm_sweep()
        except Exception as e:
            logging.error(f"Amazon ship-confirm sweep: {e}")
        await asyncio.sleep(300)


@app.on_event("startup")
async def _start_amz_confirm():
    if _spapi_configured():
        asyncio.create_task(_amz_confirm_loop())


class AmazonShipTo(BaseModel):
    name: str
    line1: str
    city: str
    state: str
    pincode: str
    phone: str


@api_router.put("/amazon/orders/{order_id}/ship-to")
async def amazon_set_ship_to(order_id: str, req: AmazonShipTo, user=Depends(get_current_user)):
    """Buyer's delivery details copied from Seller Central, for a self-ship label."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    a = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Order not found")
    if a.get("ship_type") != "self_ship":
        raise HTTPException(status_code=400, detail="Only self-ship orders need a delivery address - Amazon ships Easy Ship orders")
    pin = re.sub(r"\D", "", req.pincode or "")
    phone = _to_local_phone(req.phone)
    if len(pin) != 6:
        raise HTTPException(status_code=400, detail="Pincode must be 6 digits")
    if not phone:
        raise HTTPException(status_code=400, detail="Enter the buyer's 10-digit phone number")
    if len((req.name or "").strip()) < 2 or len((req.line1 or "").strip()) < 5:
        raise HTTPException(status_code=400, detail="Enter the buyer's name and full street address")
    ship_to = {"name": _pii_enc(req.name.strip()), "line1": _pii_enc(" ".join(req.line1.split())),
               "city": req.city.strip(), "state": req.state.strip(), "pincode": pin, "phone": _pii_enc(phone),
               "entered_by": user["name"], "entered_at": datetime.now(timezone.utc).isoformat()}
    await db.amazon_orders.update_one({"id": order_id}, {"$set": {"ship_to": ship_to, "has_buyer_pii": True,
                                                                  "updated_at": datetime.now(timezone.utc).isoformat()}})
    await _sec_log("amazon_ship_to_entered", user=user.get("username") or user["name"], order=a.get("am_order_number"))
    return {"ok": True}


@api_router.get("/amazon/orders/{order_id}/ship-to")
async def amazon_get_ship_to(order_id: str, user=Depends(get_current_user)):
    a = await db.amazon_orders.find_one({"id": order_id}, {"_id": 0, "ship_to": 1, "am_order_number": 1, "address_public": 1, "pii_purged_at": 1})
    if not a:
        raise HTTPException(status_code=404, detail="Order not found")
    st = a.get("ship_to") or {}
    city, state, pin = _amz_public_place(a)
    ready = bool(st.get("name") and st.get("line1") and st.get("phone") and pin)
    out = {"ready": ready, "city": city, "state": state, "pincode": pin, "entered_by": st.get("entered_by") or "",
           "entered_at": st.get("entered_at") or "", "purged": bool(a.get("pii_purged_at"))}
    if user["role"] in PII_ROLES and ready:
        out.update(name=_pii_dec(st["name"]), line1=_pii_dec(st["line1"]), phone=_pii_dec(st["phone"]), visible=True)
        await _pii_view_logged(user, a.get("am_order_number"))
    return out


@api_router.post("/amazon/orders/{order_id}/confirm-shipment")
async def amazon_confirm_shipment_now(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await _amz_confirm_shipment(order_id, force=True)


# ═══════════════════════════════════════════════════════════════════════════
# DELHIVERY EXPRESS (parcel): serviceability, rates, booking, label, cancel,
# pickup poller. Token-authenticated (Delhivery One API token in the env).
# Delhivery B2B / LTL ("transport") is a different API and is NOT covered here.
# ═══════════════════════════════════════════════════════════════════════════
DLV_BASE = "https://track.delhivery.com"
DELHIVERY = {
    "token": os.environ.get("DELHIVERY_TOKEN", "").strip(),
    "pickup_name": os.environ.get("DELHIVERY_PICKUP_NAME", "MANGALAM AGRO").strip(),
    "origin_pin": os.environ.get("DELHIVERY_ORIGIN_PINCODE", os.environ.get("AMAZON_SHIP_ORIGIN_PINCODE", "440025")),
}
DLV_ROLES = ["admin", "dispatch", "packaging", "accounts"]
DLV_COURIER_RE = {"$regex": r"^\s*delhivery", "$options": "i"}
DLV_MODES = {1: ("S", "Delhivery Surface"), 2: ("E", "Delhivery Express (Air)")}
DLV_SYNC_INTERVAL = int(os.environ.get("DELHIVERY_SYNC_INTERVAL", "180"))
DLV_NOT_GONE = ("manifested", "not picked", "cancel", "open", "pending pickup")
DLV_GONE_WORDS = ("picked", "in transit", "dispatched", "delivered", "out for delivery", "reached")


def _dlv_configured() -> bool:
    return bool(DELHIVERY["token"])


def _dlv_headers() -> dict:
    return {"Authorization": f"Token {DELHIVERY['token']}", "Accept": "application/json"}


def _dlv_require(user):
    if user["role"] not in DLV_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not _dlv_configured():
        raise HTTPException(status_code=400, detail="Delhivery is not configured on the server")


async def _dlv_pin(pincode: str) -> Optional[dict]:
    """Delhivery's own word on a pincode: {cod, pre_paid, district, state_code} or None."""
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(f"{DLV_BASE}/c/api/pin-codes/json/", params={"filter_codes": pincode}, headers=_dlv_headers())
    rows = (r.json() or {}).get("delivery_codes") or [] if r.status_code == 200 else []
    return (rows[0] or {}).get("postal_code") if rows else None


async def _dlv_rate(pincode: str, weight_kg: float, cod_amount: float = 0, mode: str = "S") -> Optional[dict]:
    """GST-inclusive charge for one parcel, as Delhivery would bill it."""
    params = {"md": mode, "ss": "Delivered", "d_pin": pincode, "o_pin": DELHIVERY["origin_pin"],
              "cgm": max(1, int(round(float(weight_kg) * 1000))), "pt": "COD" if cod_amount > 0 else "Pre-paid"}
    if cod_amount > 0:
        params["cod"] = int(round(cod_amount))
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{DLV_BASE}/api/kinko/v1/invoice/charges/.json", params=params, headers=_dlv_headers())
    if r.status_code != 200:
        return None
    rows = r.json() if isinstance(r.json(), list) else []
    if not rows:
        return None
    x = rows[0]
    total = float(x.get("total_amount") or 0)
    if total <= 0:
        return None
    return {"total": round(total, 2), "gross": float(x.get("gross_amount") or 0), "cod_fee": float(x.get("charge_COD") or 0),
            "freight": float(x.get("charge_DL") or 0), "zone": x.get("zone") or "", "charged_weight_g": x.get("charged_weight")}


async def _dlv_options(pincode: str, weight_kg: float, cod_amount: float) -> list:
    out = []
    for cid, (mode, name) in DLV_MODES.items():
        try:
            q = await _dlv_rate(pincode, weight_kg, cod_amount, mode)
        except Exception as e:
            logging.warning(f"delhivery rate {mode}: {e}")
            q = None
        if q:
            out.append({"courier_id": cid, "name": name, "rate": q["total"], "surface": mode == "S", "zone": q["zone"],
                        "cod_charges": q["cod_fee"], "freight": q["freight"], "etd": "", "days": None,
                        "charged_weight_g": q["charged_weight_g"]})
    out.sort(key=lambda x: x["rate"])
    return out


@api_router.get("/delhivery/check/{pincode}")
async def delhivery_check(pincode: str, weight: float = 1.0, cod: bool = False, user=Depends(get_current_user)):
    pincode = pincode.strip()
    if not pincode.isdigit() or len(pincode) != 6:
        return {"serviceable": False, "configured": True, "message": "Invalid pincode format."}
    if not _dlv_configured():
        return {"serviceable": None, "configured": False, "message": "Delhivery is not configured on the server."}
    try:
        pin = await _dlv_pin(pincode)
        if not pin:
            return {"serviceable": False, "configured": True, "message": "Delhivery does not serve this pincode."}
        if cod and str(pin.get("cod", "")).upper() != "Y":
            return {"serviceable": False, "configured": True, "message": "Delhivery serves this pincode but not for COD."}
        opts = await _dlv_options(pincode, max(0.05, float(weight or 1)), 100.0 if cod else 0.0)
        return {"serviceable": True, "configured": True, "city": pin.get("district") or "", "state": pin.get("state_code") or "",
                "cod": str(pin.get("cod", "")).upper() == "Y", "couriers": opts, "count": len(opts)}
    except Exception as e:
        logging.error(f"delhivery check: {e}")
        return {"serviceable": False, "configured": True, "message": "Unable to reach Delhivery right now."}


@api_router.get("/delhivery/bookable")
async def delhivery_bookable(user=Depends(get_current_user)):
    _dlv_require(user)
    orders = await ship_orders.find({
        "courier_name": DLV_COURIER_RE, "status": {"$nin": ["cancelled", "dispatched"]},
        "$or": [{"packaging.weight_kg": {"$nin": ["", None]}}, {"delhivery_shipment.awb": {"$nin": ["", None]}}],
    }, {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "grand_total": 1, "shipping_address": 1,
        "packaging": 1, "delhivery_shipment": 1, "status": 1, "is_cod": 1, "amount_paid": 1, "cod_amount": 1,
        }).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        sh = o.get("delhivery_shipment") or None
        try:
            weight = float(str(pkg.get("weight_kg", "")).strip() or 0)
        except (TypeError, ValueError):
            weight = 0.0
        if weight <= 0 and sh and sh.get("awb"):
            weight = float(sh.get("weight_kg") or 0)
        if weight <= 0:
            continue
        out.append({"id": o["id"], "order_number": o.get("order_number"), "customer_name": o.get("customer_name"),
                    "grand_total": o.get("grand_total"), "status": o.get("status"),
                    "weight_kg": weight, "num_boxes": pkg.get("num_boxes") or "1",
                    "shipping_address": o.get("shipping_address") or {},
                    "is_cod": bool(o.get("is_cod")), "cod_amount": _amazon_cod_amount(o),
                    "delhivery_shipment": ({k: v for k, v in sh.items() if k != "raw"} if sh else None)})
    return out


class DelhiveryBookRequest(BaseModel):
    order_id: str
    courier_id: Optional[int] = None         # 1 = Surface (default), 2 = Express (air)
    payment_mode: Optional[str] = None       # "prepaid" | "cod"; prepaid unless stated
    declared_value: Optional[float] = None


def _dlv_cod(order: dict, mode: Optional[str]) -> float:
    mode = (mode or "").strip().lower()
    if mode == "cod":
        return _amazon_cod_amount({**order, "is_cod": True})
    return 0.0


@api_router.post("/delhivery/quote")
async def delhivery_quote(req: DelhiveryBookRequest, user=Depends(get_current_user)):
    _dlv_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    sa = order.get("shipping_address") or {}
    weight = float(str((order.get("packaging") or {}).get("weight_kg") or 0).strip() or 0)
    if weight <= 0:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    cod = _dlv_cod(order, req.payment_mode)
    if (req.payment_mode or "").lower() == "cod" and cod <= 0:
        raise HTTPException(status_code=400, detail="Nothing left to collect - this order is fully paid.")
    pin = await _dlv_pin(str(sa.get("pincode") or ""))
    if not pin:
        return {"ok": False, "message": "Delhivery does not serve this address"}
    if cod > 0 and str(pin.get("cod", "")).upper() != "Y":
        return {"ok": False, "message": "Delhivery does not do COD at this pincode"}
    opts = await _dlv_options(str(sa.get("pincode") or ""), weight, cod)
    if not opts:
        return {"ok": False, "message": "Delhivery returned no rate for this parcel"}
    return {"ok": True, "couriers": opts, "is_cod": cod > 0, "cod_amount": cod, "weight_kg": weight}


@api_router.post("/delhivery/book")
async def delhivery_book(req: DelhiveryBookRequest, user=Depends(get_current_user)):
    """BUYS a real Delhivery Express shipment (manifest + AWB) and asks for a pickup."""
    _dlv_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("delhivery_shipment") or {}).get("awb"):
        raise HTTPException(status_code=400, detail="This order is already booked with Delhivery")
    if req.declared_value and float(req.declared_value) > 0:
        order["declared_value_override"] = float(req.declared_value)
    elif float(order.get("grand_total") or 0) <= 0:
        raise HTTPException(status_code=400, detail="Order total is \u20b90 - enter a declared value for the shipment before booking")
    pkg = order.get("packaging") or {}
    weight = float(str(pkg.get("weight_kg") or 0).strip() or 0)
    if weight <= 0:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    phone = await _order_recipient_phone(order)
    if not phone:
        raise HTTPException(status_code=400, detail="Customer has no valid phone number. Add one before booking.")
    sa = order.get("shipping_address") or {}
    line1, line2 = _address_lines(sa, cap=150)
    if len((line1 or "").strip()) < 3:
        raise HTTPException(status_code=400, detail="Shipping address is too short for the courier")
    cod = _dlv_cod(order, req.payment_mode)
    if (req.payment_mode or "").lower() == "cod" and cod <= 0:
        raise HTTPException(status_code=400, detail="Nothing left to collect - this order is fully paid.")
    declared = _declared_value(order)
    mode, mode_name = DLV_MODES.get(int(req.courier_id or 1), DLV_MODES[1])
    quote = await _dlv_rate(str(sa.get("pincode") or ""), weight, cod, mode)

    rebooks = sum(1 for c in (order.get("cancelled_shipments") or []) if (c.get("courier") or "") == "Delhivery")
    rebooks += int(order.get("delhivery_failed_attempts") or 0)
    ref = (order.get("order_number") or order["id"][:20]) + (f"-R{rebooks}" if rebooks else "")
    box = _amazon_box(order)
    items = [(it.get("product_name") or "").strip() for it in (order.get("items") or []) if it.get("product_name")]
    desc = (", ".join(items) or "Aroma products")[:120]
    shipment = {
        "name": (sa.get("address_name") or order.get("customer_name") or "Customer").strip()[:60],
        "add": (line1 + (", " + line2 if line2 else ""))[:250], "pin": str(sa.get("pincode") or ""),
        "city": sa.get("city") or "", "state": sa.get("state") or "", "country": "India", "phone": phone,
        "order": ref, "payment_mode": "COD" if cod > 0 else "Prepaid",
        "return_pin": DELHIVERY["origin_pin"], "return_city": "Nagpur", "return_phone": COMPANY["mobile"],
        "return_add": COMPANY["address"], "return_state": "Maharashtra", "return_country": "India",
        "products_desc": desc, "hsn_code": "", "cod_amount": str(int(round(cod))) if cod > 0 else "",
        "order_date": None, "total_amount": str(int(round(declared))),
        "seller_add": COMPANY["address"], "seller_name": COMPANY["brand"], "seller_inv": order.get("order_number") or ref,
        "seller_gst_tin": COMPANY["gstin"], "quantity": str(len(items) or 1), "waybill": "",
        "shipment_width": str(box["width"]), "shipment_height": str(box["height"]), "shipment_length": str(box["length"]),
        "weight": str(int(round(weight * 1000))), "shipping_mode": "Express" if mode == "E" else "Surface", "address_type": "",
    }
    payload = {"shipments": [shipment], "pickup_location": {"name": DELHIVERY["pickup_name"]}}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{DLV_BASE}/api/cmu/create.json", data={"format": "json", "data": json.dumps(payload)},
                         headers={"Authorization": f"Token {DELHIVERY['token']}"})
    try:
        data = r.json()
    except Exception:
        data = {"rmk": r.text[:300]}
    pk = ((data or {}).get("packages") or [{}])[0]
    awb = pk.get("waybill") if str(pk.get("status", "")).lower() == "success" else ""
    if r.status_code != 200 or not awb:
        reason = "; ".join(str(x) for x in (pk.get("remarks") or [])) or data.get("rmk") or str(data)[:250]
        await ship_orders.update_one({"id": req.order_id}, {"$inc": {"delhivery_failed_attempts": 1}})
        logging.error(f"Delhivery create failed for {ref}: {r.status_code} {str(data)[:400]}")
        raise HTTPException(status_code=400, detail=f"Delhivery refused the booking: {reason}")

    # One pickup request per day is enough; Delhivery ignores/refuses duplicates.
    pickup_note = ""
    try:
        now_ist = datetime.now(IST)
        day = now_ist.date() if now_ist.hour < 13 else (now_ist + timedelta(days=1)).date()
        async with httpx.AsyncClient(timeout=30) as c:
            pr = await c.post(f"{DLV_BASE}/fm/request/new/", json={
                "pickup_time": "14:00:00", "pickup_date": day.isoformat(),
                "pickup_location": DELHIVERY["pickup_name"], "expected_package_count": 1},
                headers={**_dlv_headers(), "Content-Type": "application/json"})
        pickup_note = f"{pr.status_code}: {pr.text[:160]}"
    except Exception as e:
        pickup_note = f"pickup request failed: {e}"
    shipment_doc = {
        "awb": awb, "tracking_id": awb, "reference": ref, "mode": mode, "courier_name": mode_name,
        "rate": (quote or {}).get("total"), "zone": (quote or {}).get("zone"),
        "is_cod": cod > 0, "cod_amount": cod, "declared_value": round(declared, 2), "weight_kg": weight,
        "pickup_date": day.isoformat() if pickup_note and not pickup_note.startswith("pickup request failed") else "",
        "pickup_note": pickup_note[:200], "booked_by": user["name"], "booked_at": datetime.now(timezone.utc).isoformat(),
    }
    await ship_orders.update_one({"id": req.order_id}, {"$set": {
        "delhivery_shipment": shipment_doc, "courier_name": "Delhivery", "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "shipment": shipment_doc}


@api_router.post("/delhivery/bulk-book")
async def delhivery_bulk_book(req: BulkBookRequest, user=Depends(get_current_user)):
    _dlv_require(user)
    mode = (req.payment_mode or "prepaid").strip().lower()

    async def one(oid):
        ch = (req.choices or {}).get(oid) or {}
        return await delhivery_book(DelhiveryBookRequest(
            order_id=oid, payment_mode=(ch.get("payment_mode") or mode),
            courier_id=int(ch["courier_id"]) if ch.get("courier_id") else None,
            declared_value=(req.declared_values or {}).get(oid)), user=user)

    return await _bulk_book(req.order_ids, one, user, "Delhivery")


async def _dlv_cancel_one(order_id: str, user) -> dict:
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    shp = order.get("delhivery_shipment") or {}
    if not shp.get("awb"):
        raise HTTPException(status_code=400, detail="No Delhivery booking on this order")
    if (order.get("status") or "") == "dispatched":
        raise HTTPException(status_code=400, detail="Order is already dispatched - undo the dispatch before cancelling the label")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{DLV_BASE}/api/p/edit", json={"waybill": shp["awb"], "cancellation": "true"},
                         headers={**_dlv_headers(), "Content-Type": "application/json"})
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:200]}
    if r.status_code != 200 or not (data.get("status") is True or str(data.get("status", "")).lower() == "true"):
        raise HTTPException(status_code=400, detail=f"Delhivery cancel failed: {str(data)[:250]}")
    now = datetime.now(timezone.utc).isoformat()
    await ship_orders.update_one({"id": order_id}, {
        "$push": {"cancelled_shipments": {"courier": "Delhivery", **shp, "cancelled_by": user["name"], "cancelled_at": now}},
        "$unset": {"delhivery_shipment": ""}, "$set": {"updated_at": now}})
    return {"ok": True, "cancelled": shp.get("awb")}


@api_router.post("/delhivery/cancel")
async def delhivery_cancel(req: CancelLabelRequest, user=Depends(get_current_user)):
    _dlv_require(user)
    return await _dlv_cancel_one(req.order_id, user)


@api_router.post("/delhivery/bulk-cancel")
async def delhivery_bulk_cancel(req: BulkBookRequest, user=Depends(get_current_user)):
    _dlv_require(user)

    async def one(oid):
        return await _dlv_cancel_one(oid, user)

    return await _bulk_book(req.order_ids, one, user, "Delhivery cancel")


async def _dlv_label_pdf(awb: str) -> bytes:
    """Delhivery renders the label as a PDF behind a short-lived link."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.get(f"{DLV_BASE}/api/p/packing_slip", params={"wbns": awb, "pdf": "true"}, headers=_dlv_headers())
        data = r.json() if r.status_code == 200 else {}
        pk = ((data or {}).get("packages") or [{}])[0]
        url = pk.get("pdf_download_link") or pk.get("pdf_link") or ""
        if not url:
            raise RuntimeError(f"no label for {awb}: {str(data)[:160]}")
        return (await c.get(url)).content


@api_router.get("/delhivery/labels")
async def delhivery_labels(ids: str, token: str = "", user=None):
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    images, missing = [], []
    for oid in [i for i in (ids or "").split(",") if i][:50]:
        o = await ship_orders.find_one({"id": oid}, {"_id": 0, "order_number": 1, "delhivery_shipment": 1})
        awb = ((o or {}).get("delhivery_shipment") or {}).get("awb")
        if not awb:
            missing.append((o or {}).get("order_number") or oid[:8])
            continue
        try:
            images.extend(_pdf_pages_jpg(await _dlv_label_pdf(awb)) or [])
        except Exception as e:
            logging.warning(f"delhivery label {awb}: {e}")
            missing.append((o or {}).get("order_number") or oid[:8])
    if not images:
        raise HTTPException(status_code=404, detail=f"No labels available for: {', '.join(missing)}")
    return StreamingResponse(_quarter_sheet_pdf(images, per_page=4), media_type="application/pdf",
                             headers={"Content-Disposition": "inline; filename=delhivery-labels.pdf"})


async def _delhivery_mark_dispatched(order: dict, when: str, by: str, docket: str = "") -> dict:
    shp = order.get("delhivery_shipment") or {}
    docket = docket or shp.get("awb") or ""
    dispatch = order.get("dispatch") or {}
    slips = list(dispatch.get("dispatch_slip_images") or [])
    if not slips and shp.get("awb"):
        try:
            jpg = _pdf_first_page_jpg(await _dlv_label_pdf(shp["awb"]))
            if jpg:
                fname = f"{uuid.uuid4()}.jpg"
                async with aiofiles.open(UPLOAD_DIR / fname, "wb") as f:
                    await f.write(jpg)
                slips.append(f"/api/uploads/{fname}")
        except Exception as e:
            logging.warning(f"delhivery slip image failed: {e}")
    dispatch.update({"courier_name": "Delhivery", "courier_partner": shp.get("courier_name") or "",
                     "transporter_name": "", "lr_no": docket, "dispatch_slip_images": slips,
                     "dispatch_type": "courier", "porter_link": "", "dispatched_by": by, "dispatched_at": when})
    await ship_orders.update_one({"id": order["id"]}, {"$set": {
        "dispatch": dispatch, "status": "dispatched", "courier_name": "Delhivery",
        "delhivery_shipment.picked_up_at": when, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "lr_no": docket, "slips": slips}


class DelhiveryDispatchRequest(BaseModel):
    order_id: str
    docket_no: Optional[str] = ""


@api_router.post("/delhivery/dispatch")
async def delhivery_dispatch(req: DelhiveryDispatchRequest, user=Depends(get_current_user)):
    _dlv_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    docket = (req.docket_no or "").strip() or (order.get("delhivery_shipment") or {}).get("awb") or ""
    if not docket:
        raise HTTPException(status_code=400, detail="Tracking / AWB number is required")
    return await _delhivery_mark_dispatched(order, datetime.now(timezone.utc).isoformat(), user["name"], docket)


async def _delhivery_sync_all() -> int:
    """Booked Delhivery orders that the courier has collected become dispatched."""
    orders = await ship_orders.find({"delhivery_shipment.awb": {"$nin": ["", None]},
                                   "status": {"$nin": ["dispatched", "cancelled"]}}, {"_id": 0}).limit(50).to_list(50)
    if not orders:
        return 0
    by_awb = {o["delhivery_shipment"]["awb"]: o for o in orders}
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.get(f"{DLV_BASE}/api/v1/packages/json/", params={"waybill": ",".join(by_awb)}, headers=_dlv_headers())
    if r.status_code != 200:
        logging.warning(f"delhivery track: {r.status_code} {r.text[:120]}")
        return 0
    n = 0
    for row in (r.json() or {}).get("ShipmentData") or []:
        sh = row.get("Shipment") or {}
        o = by_awb.get(str(sh.get("AWB") or ""))
        if not o:
            continue
        status = str((sh.get("Status") or {}).get("Status") or "").lower()
        scans = [str((x.get("ScanDetail") or {}).get("Scan") or "").lower() for x in (sh.get("Scans") or [])]
        gone = (status and not any(w in status for w in DLV_NOT_GONE) and any(w in status for w in DLV_GONE_WORDS)) \
            or any(any(w in sc for w in DLV_GONE_WORDS) for sc in scans)
        if not gone:
            continue
        when = datetime.now(timezone.utc).isoformat()
        for x in sh.get("Scans") or []:
            d = x.get("ScanDetail") or {}
            if "picked" in str(d.get("Scan") or "").lower() and d.get("ScanDateTime"):
                try:
                    when = datetime.fromisoformat(str(d["ScanDateTime"])[:19]).replace(tzinfo=IST).astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
                break
        await _delhivery_mark_dispatched(o, when, "Delhivery (auto)", sh.get("AWB"))
        n += 1
        logging.info(f"Delhivery pickup: {o.get('order_number')} dispatched ({status})")
    return n


async def _delhivery_sync_loop():
    await asyncio.sleep(75)
    while True:
        try:
            await _delhivery_sync_all()
        except Exception as e:
            logging.error(f"Delhivery sync loop error: {e}")
        await asyncio.sleep(DLV_SYNC_INTERVAL)


@app.on_event("startup")
async def _start_delhivery_sync():
    if _dlv_configured():
        asyncio.create_task(_delhivery_sync_loop())
        logging.info(f"Delhivery pickup sync every {DLV_SYNC_INTERVAL}s")


@api_router.post("/delhivery/sync-tracking")
async def delhivery_sync_now(user=Depends(get_current_user)):
    _dlv_require(user)
    return {"count": await _delhivery_sync_all()}


async def _compare_delhivery(pincode: str, weight: float, cod: bool) -> list:
    if not _dlv_configured():
        return [{"carrier": "Delhivery", "service": "", "serviceable": None, "note": "Not configured on the server"}]
    try:
        pin = await _dlv_pin(pincode)
        if not pin:
            return [{"carrier": "Delhivery", "service": "", "serviceable": False, "note": "Delhivery does not serve this pincode"}]
        if cod and str(pin.get("cod", "")).upper() != "Y":
            return [{"carrier": "Delhivery", "service": "", "serviceable": False, "note": "No COD at this pincode"}]
        out = []
        for o in await _dlv_options(pincode, weight, 100.0 if cod else 0.0):
            out.append({"carrier": "Delhivery", "service": o["name"].replace("Delhivery ", ""), "serviceable": True,
                        "total": o["rate"], "gst_note": "GST included", "eta": "",
                        "note": f"zone {o['zone']}" + (f", billed {o['charged_weight_g']} g" if o.get("charged_weight_g") else ""),
                        "cod_charge": o["cod_charges"] if cod else None})
        return out or [{"carrier": "Delhivery", "service": "", "serviceable": False, "note": "No rate returned"}]
    except Exception as e:
        logging.error(f"compare/delhivery: {e}")
        return [{"carrier": "Delhivery", "service": "", "serviceable": None, "note": "Could not reach Delhivery right now"}]


# ═══════════════════════════════════════════════════════════════════════════
# DELHIVERY B2B / LTL ("transport"): heavy consignments booked as an LR.
# Username + password → 24 h JWT. Freight is estimated live; the manifest is an
# async job that returns the LR number. Minimum billed weight is 20 kg.
# ═══════════════════════════════════════════════════════════════════════════
DLVB_BASE = "https://ltl-clients-api.delhivery.com"
DLVB = {
    "username": os.environ.get("DELHIVERY_B2B_USERNAME", "").strip(),
    "password": os.environ.get("DELHIVERY_B2B_PASSWORD", "") or _b64.b64decode(os.environ.get("DELHIVERY_B2B_PASSWORD_B64", "") or b"").decode("utf-8", "ignore"),
    "pickup_name": os.environ.get("DELHIVERY_B2B_PICKUP_NAME", os.environ.get("DELHIVERY_PICKUP_NAME", "MANGALAM AGRO")).strip(),
    "origin_pin": os.environ.get("DELHIVERY_ORIGIN_PINCODE", "440025"),
}
DLVB_COURIER_RE = {"$regex": r"^\s*delhivery\s*b2b", "$options": "i"}
DLVB_SYNC_INTERVAL = int(os.environ.get("DELHIVERY_B2B_SYNC_INTERVAL", "300"))
_dlvb_token = {"jwt": "", "expires": 0.0}


def _dlvb_configured() -> bool:
    return bool(DLVB["username"] and DLVB["password"])


async def _dlvb_auth() -> str:
    """JWT, cached well inside its 24 h life. Never retried in a loop: a wrong
    password locks the user for 10 minutes."""
    import time
    if _dlvb_token["jwt"] and _dlvb_token["expires"] > time.time():
        return _dlvb_token["jwt"]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{DLVB_BASE}/ums/login", json={"username": DLVB["username"], "password": DLVB["password"]})
    jwt_ = ((r.json() if r.status_code == 200 else {}).get("data") or {}).get("jwt")
    if not jwt_:
        raise RuntimeError(f"Delhivery B2B login failed ({r.status_code}): {r.text[:120]}")
    _dlvb_token.update(jwt=jwt_, expires=time.time() + 20 * 3600)
    return jwt_


async def _dlvb_call(method: str, path: str, **kw) -> tuple:
    token = await _dlvb_auth()
    headers = {"Authorization": f"Bearer {token}", **kw.pop("headers", {})}
    if "json" in kw:
        headers.setdefault("Content-Type", "application/json")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.request(method, DLVB_BASE + path, headers=headers, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:400]}


def _dlvb_require(user):
    if user["role"] not in DLV_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not _dlvb_configured():
        raise HTTPException(status_code=400, detail="Delhivery B2B is not configured on the server")


def _dlvb_err(data) -> str:
    e = (data or {}).get("error")
    return (e.get("message") if isinstance(e, dict) else str(e)) or str(data)[:200]


async def _dlvb_pin(pincode: str) -> Optional[dict]:
    code, d = await _dlvb_call("GET", f"/pincode-service/{pincode}", headers={"Content-Type": "application/json"})
    rows = ((d or {}).get("data") or {}).get("pincode_serviceability_data") or [] if code == 200 else []
    return rows[0] if rows else None


def _dlvb_boxes(order: dict) -> tuple:
    """(dimensions list, total weight g, box count) for the estimate / manifest."""
    pkg = order.get("packaging") or {}
    weight = float(str(pkg.get("weight_kg") or 0).strip() or 0)
    try:
        boxes = max(1, int(str(pkg.get("num_boxes") or "1").strip() or 1))
    except ValueError:
        boxes = 1
    per_box = {"packaging": {"weight_kg": max(0.5, weight / boxes)}}
    side = _amazon_box(per_box)
    dims = [{"length_cm": side["length"], "width_cm": side["width"], "height_cm": side["height"], "box_count": boxes}]
    return dims, int(round(weight * 1000)), boxes


async def _dlvb_estimate(dest_pin: str, dims: list, weight_g: int, inv_amount: float, cod_amount: float, rov: bool) -> Optional[dict]:
    body = {"dimensions": dims, "weight_g": max(1, weight_g), "cheque_payment": False,
            "source_pin": DLVB["origin_pin"], "consignee_pin": dest_pin,
            "payment_mode": "cod" if cod_amount > 0 else "prepaid", "inv_amount": max(1, int(round(inv_amount))),
            "freight_mode": "fod", "rov_insurance": bool(rov)}
    if cod_amount > 0:
        body["cod_amount"] = int(round(cod_amount))
    code, d = await _dlvb_call("POST", "/freight/estimate", json=body)
    if code != 200 or not (d or {}).get("success"):
        raise RuntimeError(_dlvb_err(d))
    data = d["data"]
    pb = data.get("price_breakup") or {}
    return {"total": round(float(data.get("total") or 0), 2), "charged_wt_kg": data.get("charged_wt"),
            "min_wt_kg": data.get("min_charged_wt"), "gst": pb.get("gst"), "freight": pb.get("base_freight_charge"),
            "fuel": (pb.get("fuel_surcharge") or 0) + (pb.get("fuel_hike") or 0), "rov": pb.get("insurance_rov"),
            "handling": pb.get("other_handling_charges"), "cod_fee": (pb.get("meta_charges") or {}).get("cod"),
            "to_pay_fee": (pb.get("meta_charges") or {}).get("to_pay")}


@api_router.get("/delhivery-b2b/check/{pincode}")
async def delhivery_b2b_check(pincode: str, weight: float = 20.0, cod: bool = False, user=Depends(get_current_user)):
    pincode = pincode.strip()
    if not pincode.isdigit() or len(pincode) != 6:
        return {"serviceable": False, "configured": True, "message": "Invalid pincode format."}
    if not _dlvb_configured():
        return {"serviceable": None, "configured": False, "message": "Delhivery B2B is not configured on the server."}
    try:
        pin = await _dlvb_pin(pincode)
        if not pin:
            return {"serviceable": False, "configured": True, "message": "Delhivery B2B does not serve this pincode."}
        w = max(1.0, float(weight or 20))
        dims = [{"length_cm": 40, "width_cm": 40, "height_cm": 40, "box_count": 1}]
        est = await _dlvb_estimate(pincode, dims, int(w * 1000), 5000, 5000.0 if cod else 0.0, False)
        code, t = await _dlvb_call("GET", "/tat/estimate", params={"origin_pin": DLVB["origin_pin"], "destination_pin": pincode})
        tat = ((t or {}).get("data") or {}).get("tat") if code == 200 else None
        return {"serviceable": True, "configured": True, "city": pin.get("city") or "", "state": pin.get("state") or "",
                "center": pin.get("center") or "", "oda": bool(pin.get("oda")), "tat_days": tat,
                "couriers": [{"courier_id": 1, "name": "Delhivery B2B Surface (LTL)", "rate": est["total"], "surface": True,
                              "days": tat, "etd": "", "charged_wt_kg": est["charged_wt_kg"], "min_wt_kg": est["min_wt_kg"],
                              "cod_charges": est["cod_fee"], "breakup": est}], "count": 1}
    except Exception as e:
        logging.error(f"delhivery b2b check: {e}")
        return {"serviceable": False, "configured": True, "message": f"Delhivery B2B: {str(e)[:160]}"}


@api_router.get("/delhivery-b2b/bookable")
async def delhivery_b2b_bookable(user=Depends(get_current_user)):
    _dlvb_require(user)
    orders = await ship_orders.find({
        "courier_name": DLVB_COURIER_RE, "status": {"$nin": ["cancelled", "dispatched"]},
        "$or": [{"packaging.weight_kg": {"$nin": ["", None]}}, {"delhivery_b2b_shipment.lrn": {"$nin": ["", None]}}],
    }, {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "grand_total": 1, "shipping_address": 1,
        "packaging": 1, "delhivery_b2b_shipment": 1, "status": 1, "is_cod": 1, "amount_paid": 1, "cod_amount": 1,
        "carrier_risk_applicable": 1}).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        sh = o.get("delhivery_b2b_shipment") or None
        try:
            weight = float(str(pkg.get("weight_kg", "")).strip() or 0)
        except (TypeError, ValueError):
            weight = 0.0
        if weight <= 0 and sh and sh.get("lrn"):
            weight = float(sh.get("weight_kg") or 0)
        if weight <= 0:
            continue
        out.append({"id": o["id"], "order_number": o.get("order_number"), "customer_name": o.get("customer_name"),
                    "grand_total": o.get("grand_total"), "status": o.get("status"),
                    "weight_kg": weight, "num_boxes": pkg.get("num_boxes") or "1",
                    "shipping_address": o.get("shipping_address") or {},
                    "is_cod": bool(o.get("is_cod")), "cod_amount": _amazon_cod_amount(o),
                    "carrier_risk": bool(o.get("carrier_risk_applicable")),
                    "delhivery_b2b_shipment": ({k: v for k, v in sh.items() if k != "raw"} if sh else None)})
    return out


class DelhiveryB2BBookRequest(BaseModel):
    order_id: str
    courier_id: Optional[int] = None
    payment_mode: Optional[str] = None
    declared_value: Optional[float] = None
    insure: Optional[bool] = None            # ROV insurance (carrier risk); default = order's carrier-risk flag
    ewaybill: Optional[str] = ""             # needed when the invoice is above the e-way bill limit


@api_router.post("/delhivery-b2b/quote")
async def delhivery_b2b_quote(req: DelhiveryB2BBookRequest, user=Depends(get_current_user)):
    _dlvb_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    sa = order.get("shipping_address") or {}
    dims, weight_g, boxes = _dlvb_boxes(order)
    if weight_g <= 0:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    cod = _dlv_cod(order, req.payment_mode)
    if (req.payment_mode or "").lower() == "cod" and cod <= 0:
        raise HTTPException(status_code=400, detail="Nothing left to collect - this order is fully paid.")
    rov = bool(order.get("carrier_risk_applicable")) if req.insure is None else bool(req.insure)
    try:
        pin = await _dlvb_pin(str(sa.get("pincode") or ""))
        if not pin:
            return {"ok": False, "message": "Delhivery B2B does not serve this address"}
        est = await _dlvb_estimate(str(sa.get("pincode") or ""), dims, weight_g, _declared_value(order), cod, rov)
        code, t = await _dlvb_call("GET", "/tat/estimate", params={"origin_pin": DLVB["origin_pin"], "destination_pin": str(sa.get("pincode") or "")})
        tat = ((t or {}).get("data") or {}).get("tat") if code == 200 else None
    except Exception as e:
        return {"ok": False, "message": f"Delhivery B2B: {str(e)[:200]}"}
    return {"ok": True, "is_cod": cod > 0, "cod_amount": cod, "weight_kg": weight_g / 1000.0, "boxes": boxes, "rov": rov,
            "oda": bool(pin.get("oda")), "center": pin.get("center") or "",
            "couriers": [{"courier_id": 1, "name": "Delhivery B2B Surface (LTL)", "rate": est["total"], "surface": True,
                          "days": tat, "etd": "", "charged_wt_kg": est["charged_wt_kg"], "min_wt_kg": est["min_wt_kg"],
                          "cod_charges": est["cod_fee"], "breakup": est}]}


@api_router.post("/delhivery-b2b/book")
async def delhivery_b2b_book(req: DelhiveryB2BBookRequest, user=Depends(get_current_user)):
    """BOOKS a real Delhivery B2B LR (manifest job → LR number) and requests a pickup."""
    _dlvb_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("delhivery_b2b_shipment") or {}).get("lrn"):
        raise HTTPException(status_code=400, detail="This order already has a Delhivery B2B LR")
    if req.declared_value and float(req.declared_value) > 0:
        order["declared_value_override"] = float(req.declared_value)
    elif float(order.get("grand_total") or 0) <= 0:
        raise HTTPException(status_code=400, detail="Order total is \u20b90 - enter a declared value for the shipment before booking")
    dims, weight_g, boxes = _dlvb_boxes(order)
    if weight_g <= 0:
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    phone = await _order_recipient_phone(order)
    if not phone:
        raise HTTPException(status_code=400, detail="Customer has no valid phone number. Add one before booking.")
    sa = order.get("shipping_address") or {}
    line1, line2 = _address_lines(sa, cap=150)
    if len((line1 or "").strip()) < 3:
        raise HTTPException(status_code=400, detail="Shipping address is too short for the courier")
    cod = _dlv_cod(order, req.payment_mode)
    if (req.payment_mode or "").lower() == "cod" and cod <= 0:
        raise HTTPException(status_code=400, detail="Nothing left to collect - this order is fully paid.")
    declared = _declared_value(order)
    rov = bool(order.get("carrier_risk_applicable")) if req.insure is None else bool(req.insure)
    try:
        est = await _dlvb_estimate(str(sa.get("pincode") or ""), dims, weight_g, declared, cod, rov)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Delhivery B2B: {str(e)[:200]}")

    rebooks = sum(1 for c in (order.get("cancelled_shipments") or []) if (c.get("courier") or "") == "Delhivery B2B")
    rebooks += int(order.get("delhivery_b2b_failed_attempts") or 0)
    ref = (order.get("order_number") or order["id"][:20]) + (f"-R{rebooks}" if rebooks else "")
    items = [(it.get("product_name") or "").strip() for it in (order.get("items") or []) if it.get("product_name")]
    desc = (", ".join(items) or "Aroma products")[:120]
    name = (sa.get("address_name") or order.get("customer_name") or "Customer").strip()[:60]
    form = {
        "lrn": "", "pickup_location_name": DLVB["pickup_name"],
        "payment_mode": "cod" if cod > 0 else "prepaid", "weight": str(weight_g),
        "dropoff_location": json.dumps({"consignee_name": name, "address": (line1 + (", " + line2 if line2 else ""))[:250],
                                        "city": sa.get("city") or "", "state": sa.get("state") or "",
                                        "zip": str(sa.get("pincode") or ""), "phone": phone,
                                        "email": await _amazon_recipient_email(order) or ""}),
        "rov_insurance": "True" if rov else "False",
        "invoices": json.dumps([{"ewaybill": (req.ewaybill or "").strip(), "inv_num": order.get("order_number") or ref,
                                 "inv_amt": round(declared, 2), "inv_qr_code": ""}]),
        "shipment_details": json.dumps([{"order_id": ref, "box_count": boxes, "description": desc,
                                         "weight": weight_g, "waybills": [], "master": False}]),
        "fm_pickup": "True", "freight_mode": "fod",
        "billing_address": json.dumps({"name": COMPANY["brand"], "company": COMPANY["name"], "consignor": COMPANY["name"],
                                       "address": COMPANY["address"], "city": "Nagpur", "state": "Maharashtra",
                                       "pin": DLVB["origin_pin"], "phone": COMPANY["mobile"], "gst_number": COMPANY["gstin"]}),
    }
    if cod > 0:
        form["cod_amount"] = str(int(round(cod)))
    token = await _dlvb_auth()
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{DLVB_BASE}/manifest", data=form, headers={"Authorization": f"Bearer {token}"})
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:300]}
    job_id = ((data or {}).get("data") or {}).get("job_id") if isinstance((data or {}).get("data"), dict) else (data or {}).get("job_id")
    if r.status_code not in (200, 201, 202) or not job_id:
        await ship_orders.update_one({"id": req.order_id}, {"$inc": {"delhivery_b2b_failed_attempts": 1}})
        logging.error(f"Delhivery B2B manifest failed for {ref}: {r.status_code} {str(data)[:400]}")
        raise HTTPException(status_code=400, detail=f"Delhivery B2B refused the booking: {_dlvb_err(data)}")

    # The manifest is asynchronous: poll the job until the LR number appears.
    lrn, job_status, job_raw = "", "", {}
    for _ in range(12):
        await asyncio.sleep(2.5)
        code, jd = await _dlvb_call("GET", "/manifest", params={"job_id": job_id})
        job_raw = (jd or {}).get("data") or jd or {}
        job_status = str(job_raw.get("status") or job_raw.get("job_status") or "")
        lrn = str(job_raw.get("lrn") or job_raw.get("lr_number") or (job_raw.get("lrnum") or ""))
        if lrn or job_status.lower() in ("failed", "error", "fail"):
            break
    if not lrn:
        await ship_orders.update_one({"id": req.order_id}, {"$set": {"delhivery_b2b_pending_job": {"job_id": job_id, "ref": ref, "at": datetime.now(timezone.utc).isoformat(), "last": str(job_raw)[:300]}}})
        raise HTTPException(status_code=400, detail=f"Delhivery accepted the manifest (job {job_id}) but gave no LR yet: {str(job_raw)[:200]}. Press Refresh in a minute.")

    pickup_note, pickup_date = "", ""
    try:
        now_ist = datetime.now(IST)
        day = now_ist.date() if now_ist.hour < 13 else (now_ist + timedelta(days=1)).date()
        code, pr = await _dlvb_call("POST", "/pickup_requests/", json={
            "client_warehouse": DLVB["pickup_name"], "pickup_date": day.isoformat(), "start_time": "14:00:00", "expected_package_count": boxes})
        pickup_note = f"{code}: {str(pr)[:160]}"
        pickup_date = day.isoformat() if code in (200, 201) else ""
    except Exception as e:
        pickup_note = f"pickup request failed: {e}"
    shipment_doc = {
        "lrn": lrn, "awb": lrn, "tracking_id": lrn, "job_id": job_id, "reference": ref, "courier_name": "Delhivery B2B (LTL)",
        "rate": est["total"], "charged_wt_kg": est["charged_wt_kg"], "boxes": boxes,
        "is_cod": cod > 0, "cod_amount": cod, "declared_value": round(declared, 2), "insured": rov,
        "weight_kg": weight_g / 1000.0, "pickup_date": pickup_date, "pickup_note": pickup_note[:200],
        "booked_by": user["name"], "booked_at": datetime.now(timezone.utc).isoformat(),
    }
    await ship_orders.update_one({"id": req.order_id}, {"$set": {
        "delhivery_b2b_shipment": shipment_doc, "courier_name": "Delhivery B2B", "updated_at": datetime.now(timezone.utc).isoformat()},
        "$unset": {"delhivery_b2b_pending_job": ""}})
    return {"ok": True, "shipment": shipment_doc}


@api_router.post("/delhivery-b2b/bulk-book")
async def delhivery_b2b_bulk_book(req: BulkBookRequest, user=Depends(get_current_user)):
    _dlvb_require(user)
    mode = (req.payment_mode or "prepaid").strip().lower()

    async def one(oid):
        ch = (req.choices or {}).get(oid) or {}
        return await delhivery_b2b_book(DelhiveryB2BBookRequest(
            order_id=oid, payment_mode=(ch.get("payment_mode") or mode), insure=ch.get("insure"),
            declared_value=(req.declared_values or {}).get(oid)), user=user)

    return await _bulk_book(req.order_ids, one, user, "Delhivery B2B")


async def _dlvb_cancel_one(order_id: str, user) -> dict:
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    shp = order.get("delhivery_b2b_shipment") or {}
    if not shp.get("lrn"):
        raise HTTPException(status_code=400, detail="No Delhivery B2B LR on this order")
    if (order.get("status") or "") == "dispatched":
        raise HTTPException(status_code=400, detail="Order is already dispatched - undo the dispatch before cancelling the LR")
    code, data = await _dlvb_call("DELETE", f"/lrn/cancel/{shp['lrn']}")
    if code not in (200, 201, 204) or not (data or {}).get("success", True):
        raise HTTPException(status_code=400, detail=f"Delhivery B2B cancel failed: {_dlvb_err(data)}")
    now = datetime.now(timezone.utc).isoformat()
    await ship_orders.update_one({"id": order_id}, {
        "$push": {"cancelled_shipments": {"courier": "Delhivery B2B", **shp, "cancelled_by": user["name"], "cancelled_at": now}},
        "$unset": {"delhivery_b2b_shipment": ""}, "$set": {"updated_at": now}})
    return {"ok": True, "cancelled": shp.get("lrn"), "response": data}


@api_router.post("/delhivery-b2b/cancel")
async def delhivery_b2b_cancel(req: CancelLabelRequest, user=Depends(get_current_user)):
    _dlvb_require(user)
    return await _dlvb_cancel_one(req.order_id, user)


@api_router.post("/delhivery-b2b/bulk-cancel")
async def delhivery_b2b_bulk_cancel(req: BulkBookRequest, user=Depends(get_current_user)):
    _dlvb_require(user)

    async def one(oid):
        return await _dlvb_cancel_one(oid, user)

    return await _bulk_book(req.order_ids, one, user, "Delhivery B2B cancel")


async def _dlvb_label_pdf(lrn: str) -> bytes:
    """Shipping label (std size, one page per box) as PDF bytes; the LR copy as fallback.
    Both the label links and the LR copy need the login token."""
    token = await _dlvb_auth()
    h = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.get(f"{DLVB_BASE}/label/get_urls/std/{lrn}", headers=h)
        urls = []
        try:
            data = (r.json() or {}).get("data") if r.status_code == 200 else None
        except Exception:
            data = None
        if isinstance(data, list):
            urls = [x for x in data if isinstance(x, str) and x.startswith("http")]
        elif isinstance(data, dict):
            urls = [v for v in data.values() if isinstance(v, str) and v.startswith("http")]
        pdfs = []
        for u in urls[:10]:
            rr = await c.get(u, headers=h)
            if rr.status_code == 200 and rr.content[:4] == b"%PDF":
                pdfs.append(rr.content)
        if len(pdfs) == 1:
            return pdfs[0]
        if pdfs:
            from pypdf import PdfReader, PdfWriter
            w = PdfWriter()
            for b in pdfs:
                for pg in PdfReader(io.BytesIO(b)).pages:
                    w.add_page(pg)
            out = io.BytesIO()
            w.write(out)
            return out.getvalue()
        rr = await c.get(f"{DLVB_BASE}/lr_copy/print/{lrn}", headers=h)
        if rr.status_code == 200 and rr.content[:4] == b"%PDF":
            return rr.content
    raise RuntimeError(f"no label for LR {lrn}")


@api_router.get("/delhivery-b2b/labels")
async def delhivery_b2b_labels(ids: str, token: str = "", user=None):
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    images, missing = [], []
    for oid in [i for i in (ids or "").split(",") if i][:50]:
        o = await ship_orders.find_one({"id": oid}, {"_id": 0, "order_number": 1, "delhivery_b2b_shipment": 1})
        lrn = ((o or {}).get("delhivery_b2b_shipment") or {}).get("lrn")
        if not lrn:
            missing.append((o or {}).get("order_number") or oid[:8])
            continue
        try:
            images.extend(_pdf_pages_jpg(await _dlvb_label_pdf(lrn)) or [])
        except Exception as e:
            logging.warning(f"delhivery b2b label {lrn}: {e}")
            missing.append((o or {}).get("order_number") or oid[:8])
    if not images:
        raise HTTPException(status_code=404, detail=f"No labels available for: {', '.join(missing)}")
    return StreamingResponse(_quarter_sheet_pdf(images, per_page=1), media_type="application/pdf",
                             headers={"Content-Disposition": "inline; filename=delhivery-b2b-labels.pdf"})


async def _delhivery_b2b_mark_dispatched(order: dict, when: str, by: str, docket: str = "") -> dict:
    shp = order.get("delhivery_b2b_shipment") or {}
    docket = docket or shp.get("lrn") or ""
    dispatch = order.get("dispatch") or {}
    slips = list(dispatch.get("dispatch_slip_images") or [])
    if not slips and shp.get("lrn"):
        try:
            jpg = _pdf_first_page_jpg(await _dlvb_label_pdf(shp["lrn"]))
            if jpg:
                fname = f"{uuid.uuid4()}.jpg"
                async with aiofiles.open(UPLOAD_DIR / fname, "wb") as f:
                    await f.write(jpg)
                slips.append(f"/api/uploads/{fname}")
        except Exception as e:
            logging.warning(f"delhivery b2b slip image failed: {e}")
    # An LR is a transport consignment: the WhatsApp tells the customer the LR number.
    dispatch.update({"courier_name": "Delhivery B2B", "courier_partner": "Delhivery B2B (LTL)",
                     "transporter_name": "Delhivery B2B", "lr_no": docket, "dispatch_slip_images": slips,
                     "dispatch_type": "transport", "porter_link": "", "dispatched_by": by, "dispatched_at": when})
    await ship_orders.update_one({"id": order["id"]}, {"$set": {
        "dispatch": dispatch, "status": "dispatched", "courier_name": "Delhivery B2B", "shipping_method": "transport",
        "transporter_name": "Delhivery B2B", "delhivery_b2b_shipment.picked_up_at": when,
        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "lr_no": docket, "slips": slips}


class DelhiveryB2BDispatchRequest(BaseModel):
    order_id: str
    docket_no: Optional[str] = ""


@api_router.post("/delhivery-b2b/dispatch")
async def delhivery_b2b_dispatch(req: DelhiveryB2BDispatchRequest, user=Depends(get_current_user)):
    _dlvb_require(user)
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    docket = (req.docket_no or "").strip() or (order.get("delhivery_b2b_shipment") or {}).get("lrn") or ""
    if not docket:
        raise HTTPException(status_code=400, detail="LR number is required")
    return await _delhivery_b2b_mark_dispatched(order, datetime.now(timezone.utc).isoformat(), user["name"], docket)


# Documented B2B status codes that mean the parcel has left us. MANIFESTED and
# NOT_PICKED never count; anything later in the journey does.
DLVB_GONE_STATUSES = {"PICKED_UP", "LEFT_ORIGIN", "REACH_DESTINATION", "UNDEL_REATTEMPT", "PART_DEL", "OFD", "DELIVERED"}


def _dlvb_statuses(data) -> tuple:
    """(set of status codes found under any *status* key, ISO time of the PICKED_UP event or "")."""
    found, when = set(), ""

    def walk(x):
        nonlocal when
        if isinstance(x, dict):
            st = None
            for k, v in x.items():
                if "status" in k.lower() and isinstance(v, str):
                    st = v.strip().upper().replace(" ", "_")
                    found.add(st)
            # Delhivery puts the pickup moment in `pickup_date` on each waybill.
            if not when and isinstance(x.get("pickup_date"), str) and len(x["pickup_date"]) >= 16:
                try:
                    when = datetime.fromisoformat(x["pickup_date"][:19]).replace(tzinfo=IST).astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
            if st == "PICKED_UP" and not when:
                for k, v in x.items():
                    if isinstance(v, str) and any(t in k.lower() for t in ("time", "date")) and len(v) >= 16:
                        try:
                            dt = datetime.fromisoformat(v.replace("Z", "+00:00")[:25])
                            when = (dt if dt.tzinfo else dt.replace(tzinfo=IST)).astimezone(timezone.utc).isoformat()
                        except ValueError:
                            pass
                        break
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    return found, when


async def _delhivery_b2b_sync_all() -> int:
    n = 0
    async for o in ship_orders.find({"delhivery_b2b_shipment.lrn": {"$nin": ["", None]},
                                   "status": {"$nin": ["dispatched", "cancelled"]}}, {"_id": 0}).limit(50):
        lrn = o["delhivery_b2b_shipment"]["lrn"]
        try:
            code, d = await _dlvb_call("GET", "/lrn/track", params={"lrnum": lrn})
        except Exception as e:
            logging.warning(f"delhivery b2b track {lrn}: {e}")
            continue
        if code != 200:
            continue
        statuses, when = _dlvb_statuses((d or {}).get("data") or d or {})
        if not (statuses & DLVB_GONE_STATUSES):
            continue
        await _delhivery_b2b_mark_dispatched(o, when or datetime.now(timezone.utc).isoformat(), "Delhivery B2B (auto)", lrn)
        n += 1
        logging.info(f"Delhivery B2B pickup: {o.get('order_number')} dispatched")
    return n


async def _delhivery_b2b_sync_loop():
    await asyncio.sleep(90)
    while True:
        try:
            await _delhivery_b2b_sync_all()
        except Exception as e:
            logging.error(f"Delhivery B2B sync loop error: {e}")
        await asyncio.sleep(DLVB_SYNC_INTERVAL)


@app.on_event("startup")
async def _start_delhivery_b2b_sync():
    if _dlvb_configured():
        asyncio.create_task(_delhivery_b2b_sync_loop())
        logging.info(f"Delhivery B2B pickup sync every {DLVB_SYNC_INTERVAL}s")


@api_router.post("/delhivery-b2b/sync-tracking")
async def delhivery_b2b_sync_now(user=Depends(get_current_user)):
    _dlvb_require(user)
    return {"count": await _delhivery_b2b_sync_all()}


class AttachLRRequest(BaseModel):
    order_id: str
    lrn: str


@api_router.post("/delhivery-b2b/attach")
async def delhivery_b2b_attach(req: AttachLRRequest, user=Depends(get_current_user)):
    """Link an LR that was booked directly on the Delhivery portal to an OMS order.
    Books nothing and charges nothing - it only lets the pickup poller dispatch
    the order (and WhatsApp the customer) when Delhivery collects it."""
    _dlvb_require(user)
    lrn = re.sub(r"\D", "", req.lrn or "")
    if not re.fullmatch(r"[1-9][0-9]{8}", lrn):
        raise HTTPException(status_code=400, detail="A Delhivery B2B LR number is 9 digits")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("status") or "") in ("cancelled", "dispatched"):
        raise HTTPException(status_code=400, detail=f"Order is already {order.get('status')}")
    other = await ship_orders.find_one({"delhivery_b2b_shipment.lrn": lrn, "id": {"$ne": req.order_id}}, {"_id": 0, "order_number": 1})
    if other:
        raise HTTPException(status_code=400, detail=f"LR {lrn} is already linked to {other.get('order_number')}")
    code, d = await _dlvb_call("GET", "/lrn/track", params={"lrnum": lrn})
    if code != 200 or not (d or {}).get("success", True):
        raise HTTPException(status_code=400, detail=f"Delhivery does not know LR {lrn} on this account: {_dlvb_err(d)}")
    code2, f = await _dlvb_call("GET", "/lrn/freight-breakup", params={"lrns": lrn})
    now = datetime.now(timezone.utc).isoformat()
    shipment = {"lrn": lrn, "awb": lrn, "tracking_id": lrn, "courier_name": "Delhivery B2B (LTL)", "attached": True,
                "attached_by": user["name"], "attached_at": now, "booked_at": now, "booked_by": "Delhivery portal",
                "freight": (f or {}).get("data") if code2 == 200 else None,
                "weight_kg": float(str((order.get("packaging") or {}).get("weight_kg") or 0).strip() or 0)}
    await ship_orders.update_one({"id": req.order_id}, {"$set": {
        "delhivery_b2b_shipment": shipment, "courier_name": "Delhivery B2B", "transporter_name": "Delhivery B2B",
        "shipping_method": "transport", "updated_at": now}})
    logging.info(f"{user['name']} attached Delhivery B2B LR {lrn} to {order.get('order_number')}")
    return {"ok": True, "lrn": lrn, "track": d}


@api_router.get("/delhivery-b2b/track/{lrn}")
async def delhivery_b2b_track(lrn: str, user=Depends(get_current_user)):
    """Raw Delhivery B2B tracking + freight breakup for one LR (read-only)."""
    _dlvb_require(user)
    code, d = await _dlvb_call("GET", "/lrn/track", params={"lrnum": lrn.strip()})
    code2, f = await _dlvb_call("GET", "/lrn/freight-breakup", params={"lrns": lrn.strip()})
    return {"track": d, "freight": f}


async def _compare_delhivery_b2b(pincode: str, weight: float, cod: bool) -> list:
    if not _dlvb_configured():
        return [{"carrier": "Delhivery B2B", "service": "", "serviceable": None, "note": "Not configured on the server"}]
    try:
        pin = await _dlvb_pin(pincode)
        if not pin:
            return [{"carrier": "Delhivery B2B", "service": "", "serviceable": False, "note": "Not served by Delhivery B2B"}]
        est = await _dlvb_estimate(pincode, [{"length_cm": 40, "width_cm": 40, "height_cm": 40, "box_count": 1}],
                                   int(weight * 1000), 5000, 5000.0 if cod else 0.0, False)
        return [{"carrier": "Delhivery B2B", "service": "Surface LTL (transport)", "serviceable": True, "total": est["total"],
                 "gst_note": "GST included", "eta": "",
                 "note": f"billed at {est['charged_wt_kg']} kg (min {est['min_wt_kg']} kg)" + (" · ODA area" if pin.get("oda") else ""),
                 "cod_charge": est["cod_fee"] if cod else None}]
    except Exception as e:
        logging.error(f"compare/delhivery-b2b: {e}")
        return [{"carrier": "Delhivery B2B", "service": "", "serviceable": None, "note": f"Could not check: {str(e)[:80]}"}]


# ═══════════════════════════════════════════════════════════════════════════
# BOOK SHIPMENTS: one screen for every courier we book by API (DTDC, Amazon
# Shipping, Shiprocket). Booking, cancelling and dispatching still go through
# each courier's own endpoints - this only gathers the orders into one list,
# prints their labels as one PDF, and lets a weighed order be given a courier.
# ═══════════════════════════════════════════════════════════════════════════
SHIP_ROLES = ["admin", "dispatch", "packaging", "accounts"]
SHIP_API_COURIERS = ["DTDC", "Amazon", "Shiprocket", "Delhivery", "Delhivery B2B"]


@api_router.get("/shipments/bookable")
async def shipments_bookable(user=Depends(get_current_user)):
    if user["role"] not in SHIP_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    rows, errors = [], {}
    for courier, fn, key in (("DTDC", dtdc_bookable_orders, "dtdc_shipment"),
                             ("Amazon", amazon_bookable_orders, "amazon_shipment"),
                             ("Shiprocket", shiprocket_bookable, "shiprocket_shipment"),
                             ("Delhivery", delhivery_bookable, "delhivery_shipment"),
                             ("Delhivery B2B", delhivery_b2b_bookable, "delhivery_b2b_shipment")):
        try:
            for o in await fn(user=user):
                sh = o.get(key) or {}
                booked = bool(sh.get("reference_number") or sh.get("shipment_id") or sh.get("awb") or sh.get("lrn"))
                rows.append({**o, "courier": courier, "booked": booked,
                             "tracking": sh.get("awb") or sh.get("lrn") or sh.get("tracking_id") or sh.get("reference_number") or ""})
        except HTTPException as e:
            errors[courier] = str(e.detail)
        except Exception as e:
            logging.error(f"shipments/bookable {courier}: {e}")
            errors[courier] = "Could not load"

    # Weighed courier orders nobody has given a courier yet.
    unassigned = []
    async for o in ship_orders.find({
        "status": {"$nin": ["cancelled", "dispatched"]},
        "packaging.weight_kg": {"$nin": ["", None]},
        "courier_name": {"$in": ["", None]},
        "transporter_name": {"$in": ["", None]},
        "shipping_method": {"$in": ["courier", "", None]},
    }, {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "grand_total": 1, "status": 1,
        "shipping_address": 1, "packaging": 1, "is_cod": 1, "amount_paid": 1, "cod_amount": 1,
        "carrier_risk_applicable": 1}).sort("created_at", -1).limit(200):
        pkg = o.get("packaging") or {}
        try:
            if float(str(pkg.get("weight_kg", "")).strip() or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        sa = o.get("shipping_address") or {}
        unassigned.append({"id": o["id"], "order_number": o.get("order_number"),
                           "customer_name": o.get("customer_name"), "grand_total": o.get("grand_total"),
                           "status": o.get("status"), "weight_kg": pkg.get("weight_kg"),
                           "num_boxes": pkg.get("num_boxes") or "1",
                           "shipping_address": {"city": sa.get("city"), "pincode": sa.get("pincode")},
                           "is_cod": bool(o.get("is_cod")), "cod_amount": _amazon_cod_amount(o),
                           "carrier_risk": bool(o.get("carrier_risk_applicable"))})
    return {"orders": rows, "unassigned": unassigned, "errors": errors}


class SetCourierRequest(BaseModel):
    order_id: str
    courier_name: str


@api_router.post("/shipments/set-courier")
async def shipments_set_courier(req: SetCourierRequest, user=Depends(get_current_user)):
    """Give a weighed order its courier from the Book Shipments screen."""
    if user["role"] not in SHIP_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    courier = (req.courier_name or "").strip()
    if courier not in SHIP_API_COURIERS + ["Anjani"]:
        raise HTTPException(status_code=400, detail="Courier must be DTDC, Amazon, Shiprocket, Delhivery, Delhivery B2B or Anjani")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("status") or "") in ("cancelled", "dispatched"):
        raise HTTPException(status_code=400, detail=f"Order is already {order.get('status')}")
    if ((order.get("dtdc_shipment") or {}).get("reference_number")
            or (order.get("amazon_shipment") or {}).get("shipment_id")
            or (order.get("shiprocket_shipment") or {}).get("awb")
            or (order.get("delhivery_shipment") or {}).get("awb")
            or (order.get("delhivery_b2b_shipment") or {}).get("lrn")):
        raise HTTPException(status_code=400, detail="This order already has a booked label. Cancel the label before changing the courier.")
    # Carrier risk is a DTDC charge the customer has been billed for.
    if order.get("carrier_risk_applicable") and courier != "DTDC":
        raise HTTPException(status_code=400, detail="This order has DTDC carrier risk on its invoice, so it has to go by DTDC. Edit the order to remove carrier risk first.")
    now = datetime.now(timezone.utc).isoformat()
    update = {"shipping_method": "courier", "courier_name": courier, "transporter_name": "", "updated_at": now}
    if isinstance(order.get("dispatch"), dict):
        update["dispatch.courier_name"] = courier
        update["dispatch.transporter_name"] = ""
    await ship_orders.update_one({"id": req.order_id}, {"$set": update})
    return {"ok": True, "courier_name": courier}


async def _sr_label_images(shipment_ids: list) -> list:
    """Shiprocket renders the labels as one PDF; hand back one JPG per label page."""
    if not shipment_ids:
        return []
    code, lb = await _sr_call("POST", "/courier/generate/label", json={"shipment_id": shipment_ids})
    url = (lb or {}).get("label_url")
    if not url:
        return []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        raw = (await c.get(url)).content
    return _pdf_pages_jpg(raw, max_pages=max(8, len(shipment_ids) * 2)) or []


@api_router.get("/shipments/labels")
async def shipments_labels(ids: str, token: str = "", user=None):
    """Labels of every selected order as ONE PDF, whatever the courier.

    DTDC slips come first, each on its own full A4 page (DTDC's slip is an A4
    three-copy sheet). Amazon and Shiprocket labels follow, four to an A4 page.
    """
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    order_ids = [x.strip() for x in (ids or "").split(",") if x.strip()][:60]
    if not order_ids:
        raise HTTPException(status_code=400, detail="No orders given")

    import base64
    full_pages, quarter, sr_ids, missing = [], [], [], []
    for oid in order_ids:
        o = await ship_orders.find_one({"id": oid}, {"_id": 0})
        num = (o or {}).get("order_number") or oid[:8]
        if not o:
            missing.append(num)
        elif (o.get("dtdc_shipment") or {}).get("reference_number"):
            raw, media = await _dtdc_fetch_label_bytes(o["dtdc_shipment"], order=o)
            pages = (_pdf_pages_jpg(raw) if "pdf" in (media or "") else [raw]) if raw else []
            full_pages.extend(pages) if pages else missing.append(num)
        elif (o.get("amazon_shipment") or {}).get("label_base64"):
            try:
                quarter.append(base64.b64decode(o["amazon_shipment"]["label_base64"]))
            except Exception:
                missing.append(num)
        elif (o.get("shiprocket_shipment") or {}).get("shipment_id"):
            sr_ids.append(o["shiprocket_shipment"]["shipment_id"])
        elif (o.get("delhivery_b2b_shipment") or {}).get("lrn"):
            try:
                full_pages.extend(_pdf_pages_jpg(await _dlvb_label_pdf(o["delhivery_b2b_shipment"]["lrn"])) or [])
            except Exception as e:
                logging.warning(f"delhivery b2b label: {e}")
                missing.append(num)
        elif (o.get("delhivery_shipment") or {}).get("awb"):
            try:
                quarter.extend(_pdf_pages_jpg(await _dlv_label_pdf(o["delhivery_shipment"]["awb"])) or [])
            except Exception as e:
                logging.warning(f"delhivery label: {e}")
                missing.append(num)
        else:
            missing.append(num)
    try:
        sr_images = await _sr_label_images(sr_ids)
    except Exception as e:
        logging.error(f"shipments/labels shiprocket: {e}")
        sr_images = []
    if sr_ids and not sr_images:
        missing.append(f"{len(sr_ids)} Shiprocket label(s)")
    quarter.extend(sr_images)
    if not full_pages and not quarter:
        raise HTTPException(status_code=404, detail=f"No labels available for: {', '.join(missing)}")

    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    for images, per_page in ((full_pages, 1), (quarter, 4)):
        if images:
            for page in PdfReader(_quarter_sheet_pdf(images, per_page=per_page)).pages:
                writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    headers = {"Content-Disposition": "inline; filename=shipping-labels.pdf"}
    if missing:
        headers["X-Labels-Missing"] = ", ".join(missing)[:400].encode("ascii", "ignore").decode()
    return StreamingResponse(out, media_type="application/pdf", headers=headers)


@api_router.get("/rates/compare")
async def rates_compare(pincode: str, weight: float = 1.0, cod: bool = False, user=Depends(get_current_user)):
    """Every courier for one pincode and weight, cheapest first, on a GST-inclusive basis."""
    pincode = (pincode or "").strip()
    if not pincode.isdigit() or len(pincode) != 6:
        raise HTTPException(status_code=400, detail="Enter a 6-digit pincode")
    weight = max(0.05, float(weight or 1))
    city, state = await _resolve_pincode_geo(pincode)
    groups = await asyncio.gather(
        _compare_dtdc(pincode, weight), _compare_anjani(pincode, weight, state),
        _compare_amazon(pincode, weight, cod), _compare_shiprocket(pincode, weight, cod),
        _compare_delhivery(pincode, weight, cod), _compare_delhivery_b2b(pincode, weight, cod),
        return_exceptions=True)
    options = []
    for name, g in zip(("DTDC", "Anjani", "Amazon Shipping", "Shiprocket", "Delhivery", "Delhivery B2B"), groups):
        if isinstance(g, Exception):
            logging.error(f"compare/{name}: {g}")
            options.append({"carrier": name, "service": "", "serviceable": None, "note": "Could not check right now"})
        else:
            options += g
    if cod:
        for o in options:
            if o["carrier"] in ("DTDC", "Anjani") and o.get("serviceable"):
                o["serviceable"], o["note"] = False, "COD is not booked through this courier"
                o.pop("total", None)
    priced = sorted([o for o in options if o.get("serviceable") and o.get("total")], key=lambda o: o["total"])
    for i, o in enumerate(priced):
        o["rank"] = i + 1
    if priced:
        priced[0]["cheapest"] = True
    rest = [o for o in options if not (o.get("serviceable") and o.get("total"))]
    return {"pincode": pincode, "city": city, "state": state, "weight_kg": round(weight, 3), "cod": cod,
            "options": priced + rest, "cheapest": priced[0] if priced else None,
            "basis": "What we pay, GST included. Anjani has no GST."}


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
    override = float(order.get("declared_value_override") or 0)
    if override > 0:
        return round(override, 2)       # the booker's explicit figure, as-is
    total = float(order.get("grand_total") or 0)
    if order.get("gst_applicable"):
        return round(total, 2)          # GST invoices already include tax
    return float(math.ceil(total * 1.18))   # e.g. 101 -> 119.18 -> 120


async def _order_phones(order: dict) -> list:
    """All valid contact numbers for the customer, primary first."""
    if order.get("source_collection") == "amazon_orders" and not order.get("ship_to_ready"):
        raise HTTPException(status_code=400, detail=f"{order.get('order_number')}: enter the buyer's name, address and phone "
                                                    "(copy them from Seller Central) on the Amazon order before booking")
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
_ADDRESS_LABEL_WORDS = ("billing", "shipping", "ship to", "deliver", "home",
                        "office", "work", "branch", "warehouse", "godown",
                        "factory", "default", "primary", "secondary",
                        "adress", "address")


def _address_lines(sa: dict, cap: int = 120) -> tuple:
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
    return line1[:cap], line2[:cap]


def _amazon_address_lines(sa: dict) -> dict:
    """The recipient address split across Amazon's three 60-character lines.

    Amazon caps every address line at 60 characters but accepts three of them.
    We used to send a single truncated line, which cost CS-1398 half its
    address on the label. Wraps on word boundaries; anything beyond what three
    lines can hold is squeezed onto the last line and hard-capped, so the
    label degrades from the end rather than mid-address.
    """
    # 180 = three full Amazon lines; the default 120 cap silently ate the tail.
    line1, line2 = _address_lines(sa, cap=180)
    full = re.sub(r"\s+", " ", ", ".join(x for x in (line1, line2) if x)).strip()
    if not full:
        return {"addressLine1": "Address"}
    wrapped, cur = [], ""
    for word in full.split(" "):
        while len(word) > 60:               # pathological unbroken token
            wrapped.append(word[:60])
            word = word[60:]
        cand = f"{cur} {word}".strip()
        if len(cand) <= 60:
            cur = cand
        else:
            wrapped.append(cur)
            cur = word
    if cur:
        wrapped.append(cur)
    if len(wrapped) > 3:                    # squeeze the tail into line 3
        wrapped[2] = (wrapped[2] + " " + " ".join(wrapped[3:]))[:60]
        wrapped = wrapped[:3]
    out = {"addressLine1": wrapped[0]}
    if len(wrapped) > 1:
        out["addressLine2"] = wrapped[1]
    if len(wrapped) > 2:
        out["addressLine3"] = wrapped[2]
    return out


AMAZON_FALLBACK_EMAIL = os.environ.get("AMAZON_FALLBACK_EMAIL", "arnavagrawal22@gmail.com")


async def _amazon_recipient_email(order: dict) -> str:
    """Email to put on the Amazon shipment.

    Amazon sends delivery notifications here. Used at booking time only and
    never written back to the order, so falling back to our own address routes
    the notifications to us rather than losing them - unlike a placeholder
    phone number, which would break the delivery itself.
    """
    email = str(order.get("customer_email") or "").strip()
    if not email and order.get("customer_id"):
        cust = await db.customers.find_one({"id": order["customer_id"]}, {"_id": 0, "email": 1})
        email = str((cust or {}).get("email") or "").strip()
    return email if "@" in email else AMAZON_FALLBACK_EMAIL


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


def _amazon_cod_amount(order: dict) -> float:
    """What Amazon should collect on delivery, or 0 for a prepaid shipment.

    An order is COD when it is still unpaid; the courier collects whatever is
    outstanding rather than the full total, so part-paid orders work too.
    """
    if not order.get("is_cod"):
        return 0.0
    explicit = float(order.get("cod_amount") or 0)
    if explicit > 0:
        return round(explicit, 2)
    due = float(order.get("grand_total") or 0) - float(order.get("amount_paid") or 0)
    return round(max(0.0, due), 2)


# Amazon bills the greater of actual and volumetric weight, where volumetric is
# (L x W x H) / 5000 kg. We do not measure parcels, so rather than send an
# invented box that can silently bill above the real weight, derive a cube whose
# volume sits under the weight — the actual weight then always governs.
AMAZON_VOLUMETRIC_DIVISOR = 5000
AMAZON_BOX_HEADROOM = 0.85          # stay clear of the slab edge
AMAZON_MIN_SIDE_CM = 1


def _amazon_box(order: dict) -> dict:
    """A box whose volumetric weight is below the parcel's actual weight."""
    pkg = order.get("packaging") or {}
    try:
        w = float(str(pkg.get("weight_kg", "")).strip() or 0)
    except ValueError:
        w = 0
    w = max(0.01, w)
    side = (AMAZON_VOLUMETRIC_DIVISOR * w * AMAZON_BOX_HEADROOM) ** (1.0 / 3.0)
    side = max(AMAZON_MIN_SIDE_CM, int(side))       # floor, never round up
    return {"length": side, "width": side, "height": side}


def _amazon_rates_body(ship_to: dict, weight_kg: float, declared_value: float, ref: str,
                       cod_amount: float = 0, box: Optional[dict] = None) -> dict:
    """Shared getRates payload. items + root taxDetails are mandatory for IN accounts.

    COD must sit at the root as valueAddedServices.collectOnDelivery — Amazon
    silently ignores it if placed on the package and quotes the prepaid rate,
    which would book a COD parcel that collects nothing.
    """
    w = max(0.1, float(weight_kg or 1))
    val = max(1, int(round(float(declared_value or 100))))
    body = {
        "shipFrom": _amazon_ship_from(),
        "shipTo": ship_to,
        "packages": [{
            "dimensions": {**(box or _amazon_box({"packaging": {"weight_kg": w}})),
                           "unit": "CENTIMETER"},
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
    if cod_amount and cod_amount > 0:
        body["valueAddedServices"] = {
            "collectOnDelivery": {"amount": {"value": round(float(cod_amount), 2),
                                             "unit": "INR"}}
        }
    return body


class AmazonBookRequest(BaseModel):
    order_id: str
    service_id: Optional[str] = None   # which quoted service to buy; cheapest if omitted
    # Payment mode is chosen explicitly at booking and defaults to prepaid, so a
    # COD shipment is never booked by omission. None falls back to the order flag.
    payment_mode: Optional[str] = None          # "prepaid" | "cod"
    # Declared value entered at booking time; required when the order total is 0
    # (free samples), ignored otherwise.
    declared_value: Optional[float] = None


# Couriers are free text ("Amazon", "Amazon shipping", ...), so match loosely.
AMAZON_COURIER_RE = {"$regex": r"^\s*amazon", "$options": "i"}


@api_router.get("/amazon/bookable")
async def amazon_bookable_orders(user=Depends(get_current_user)):
    """Orders assigned to Amazon courier that packing has weighed and that are not booked yet."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    orders = await ship_orders.find({
        "courier_name": AMAZON_COURIER_RE,
        # Dispatched orders have already shipped, so there is nothing left to book.
        "status": {"$nin": ["cancelled", "dispatched"]},
        "$or": [{"packaging.weight_kg": {"$nin": ["", None]}}, {"amazon_shipment.shipment_id": {"$nin": ["", None]}}],
    }, {
        "_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "grand_total": 1,
        "shipping_address": 1, "packaging": 1, "amazon_shipment": 1, "status": 1,
        "is_cod": 1, "cod_amount": 1, "grand_total": 1, "amount_paid": 1,
    }).sort("created_at", -1).to_list(300)
    out = []
    for o in orders:
        pkg = o.get("packaging") or {}
        # Guard against whitespace-only / zero weights that the query can't catch,
        # but never hide an order whose label is already bought.
        if not (o.get("amazon_shipment") or {}).get("shipment_id"):
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
            "is_cod": bool(o.get("is_cod")),
            "cod_amount": _amazon_cod_amount(o),
        })
    return out


@api_router.post("/amazon/quote")
async def amazon_quote_order(req: AmazonBookRequest, user=Depends(get_current_user)):
    """Live rates for a specific order — read-only, books nothing."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not _amazon_configured():
        raise HTTPException(status_code=400, detail="Amazon Shipping API is not configured")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    pkg = order.get("packaging") or {}
    if not str(pkg.get("weight_kg", "")).strip():
        raise HTTPException(status_code=400, detail="Weight not entered by packing team yet")
    sa = order.get("shipping_address") or {}
    phone = await _order_recipient_phone(order)
    ship_to = {
        "name": sa.get("address_name") or order.get("customer_name") or "Customer",
        **_amazon_address_lines(sa),
        "city": sa.get("city") or "", "stateOrRegion": sa.get("state") or "",
        "postalCode": sa.get("pincode") or "", "countryCode": "IN",
        "phoneNumber": phone or AMAZON_SHIP["origin_phone"],
        "email": await _amazon_recipient_email(order),
    }
    token = await _amazon_access_token()
    mode = (req.payment_mode or "").strip().lower()
    if mode == "prepaid":
        cod = 0.0
    elif mode == "cod":
        cod = _amazon_cod_amount({**order, "is_cod": True})
    else:
        cod = _amazon_cod_amount(order)
    body = _amazon_rates_body(ship_to, pkg.get("weight_kg"), _declared_value(order),
                              order.get("order_number") or "ord", cod, _amazon_box(order))
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
            # Amazon bills the greater of actual and volumetric weight, and
            # itemises the COD charge — both drive the price, so show them.
            "billed_weight": (x.get("billedWeight") or {}).get("value"),
            "billed_weight_unit": (x.get("billedWeight") or {}).get("unit"),
            "charges": [{"id": it.get("rateItemID"),
                         "label": it.get("rateItemNameLocalization"),
                         "amount": (it.get("rateItemCharge") or {}).get("value")}
                        for it in (x.get("rateItemList") or [])],
        })
    if not rates:
        reason = ""
        for ir in payload.get("ineligibleRates") or []:
            rs = (ir.get("ineligibilityReasons") or [{}])[0]
            reason = rs.get("message") or rs.get("code") or ""
            break
        return {"ok": False, "message": "Amazon Shipping does not serve this address.", "detail": reason}
    return {"ok": True, "rates": rates, "request_token": payload.get("requestToken"),
            "cod_amount": cod, "is_cod": bool(cod), "box_cm": _amazon_box(order),
            "box_measured": bool((order.get("packaging") or {}).get("length_cm"))}


@api_router.post("/amazon/book")
async def amazon_book_order(req: AmazonBookRequest, user=Depends(get_current_user)):
    """PURCHASES a real Amazon shipment (this costs money and schedules a pickup)."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized to book shipments")
    if not _amazon_configured():
        raise HTTPException(status_code=400, detail="Amazon Shipping API is not configured")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if (order.get("amazon_shipment") or {}).get("shipment_id"):
        raise HTTPException(status_code=400, detail="This order is already booked with Amazon")
    if req.declared_value and float(req.declared_value) > 0:
        order["declared_value_override"] = float(req.declared_value)
    elif float(order.get("grand_total") or 0) <= 0:
        raise HTTPException(status_code=400,
                            detail="Order total is \u20b90 - enter a declared value for the shipment before booking")
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
        **_amazon_address_lines(sa),
        "city": sa.get("city") or "", "stateOrRegion": sa.get("state") or "",
        "postalCode": sa.get("pincode") or "", "countryCode": "IN",
        "phoneNumber": phone,
        "email": await _amazon_recipient_email(order),
    }
    token = await _amazon_access_token()
    ref = order.get("order_number") or req.order_id[:20]
    headers = {"x-amz-access-token": token, "content-type": "application/json"}

    async with httpx.AsyncClient(timeout=40) as c:
        mode = (req.payment_mode or "").strip().lower()
        if mode == "prepaid":
            cod = 0.0
        elif mode == "cod":
            cod = _amazon_cod_amount({**order, "is_cod": True})
            if cod <= 0:
                raise HTTPException(status_code=400,
                                    detail="Nothing left to collect — this order is fully paid.")
        else:
            cod = _amazon_cod_amount(order)     # no explicit choice: use the order
        rr = await c.post(f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments/rates",
                          headers=headers,
                          json=_amazon_rates_body(ship_to, pkg.get("weight_kg"),
                                                  _declared_value(order), ref, cod,
                                                  _amazon_box(order)))
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

        if cod:
            # Amazon returns the COD group with isRequired true; the purchase is
            # rejected, or silently books prepaid, unless it is echoed back.
            groups = chosen.get("availableValueAddedServiceGroups") or []
            cod_ids = [vas.get("id") for g in groups
                       if (g.get("groupId") or "") == "CollectOnDelivery"
                       for vas in (g.get("valueAddedServices") or []) if vas.get("id")]
            if not cod_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Amazon did not offer Collect on Delivery for this shipment. "
                           "Book it through another courier, or mark the order prepaid.")

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
        if cod:
            purchase["requestedValueAddedServices"] = [{"id": i} for i in cod_ids]
        pr = await c.post(f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments",
                          headers=headers, json=purchase)
    if pr.status_code not in (200, 201):
        logging.error(f"Amazon purchase failed: {pr.status_code} {pr.text[:500]}")
        if re.search(r"A-303|insufficient|low balance", pr.text or "", re.I):
            raise HTTPException(status_code=400, detail="Amazon booking failed: the Amazon Shipping wallet does not have enough balance. Recharge it and book again.")
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
        "is_cod": bool(cod),
        "cod_amount": cod,          # what Amazon collects, to reconcile remittances
        "payment_mode": "cod" if cod else "prepaid",
        "booked_by": user["name"],
        "booked_at": datetime.now(timezone.utc).isoformat(),
    }
    update = {"amazon_shipment": shipment, "updated_at": datetime.now(timezone.utc).isoformat()}
    if tracking_id:
        dispatch = order.get("dispatch") or {}
        dispatch["courier_name"] = "Amazon"
        dispatch.setdefault("lr_no", tracking_id)
        update["dispatch"] = dispatch
    await ship_orders.update_one({"id": req.order_id}, {"$set": update})
    safe = {k: v for k, v in shipment.items() if k != "label_base64"}
    return {"ok": True, "shipment": safe, "has_label": bool(label_b64)}


# ─── Amazon pickup tracking → auto-dispatch ───────────────────────────────
# Amazon emits "PickupDone" when the parcel leaves us; the summary status also
# moves past "ReadyForReceive" once it is in the network.
@api_router.post("/amazon/bulk-book")
async def amazon_bulk_book(req: BulkBookRequest, user=Depends(get_current_user)):
    """PURCHASES real Amazon shipments for several orders.

    payment_mode applies to the whole batch and defaults to prepaid, so a bulk
    run can never turn prepaid orders into COD by accident.
    """
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized to book")
    mode = (req.payment_mode or "prepaid").strip().lower()
    if mode not in ("prepaid", "cod"):
        raise HTTPException(status_code=400, detail="payment_mode must be prepaid or cod")

    async def one(oid):
        ch = (req.choices or {}).get(oid) or {}
        return await amazon_book_order(
            AmazonBookRequest(order_id=oid, payment_mode=(ch.get("payment_mode") or mode),
                              service_id=ch.get("service_id") or None,
                              declared_value=(req.declared_values or {}).get(oid)), user=user)

    return await _bulk_book(req.order_ids, one, user, "Amazon")


async def _amazon_cancel_one(order_id: str, user) -> dict:
    """Cancels a purchased Amazon shipment and clears it off the order."""
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    shp = order.get("amazon_shipment") or {}
    sid = shp.get("shipment_id")
    if not sid:
        raise HTTPException(status_code=400, detail="No Amazon booking on this order")
    if (order.get("status") or "") == "dispatched":
        raise HTTPException(status_code=400,
                            detail="Order is already dispatched - undo the dispatch before cancelling the label")
    token = await _amazon_access_token()
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.put(f"{AMAZON_SHIP['endpoint']}/shipping/v2/shipments/{sid}/cancel",
                        headers={"x-amz-access-token": token, "content-type": "application/json"})
    if r.status_code not in (200, 202, 204):
        # A shipment Amazon calls ineligible after a stale booking is a dead
        # label (expired, never picked up) - clear it locally so the order can
        # be rebooked. A fresh booking that is refused stays put: it may be
        # live at a delivery station already.
        stale = False
        try:
            booked = datetime.fromisoformat(str(shp.get("booked_at")))
            stale = (datetime.now(timezone.utc) - booked).total_seconds() > 48 * 3600
        except (TypeError, ValueError):
            pass
        if not ("ineligible state" in r.text.lower() and stale):
            logging.error(f"Amazon cancel failed for {sid}: {r.status_code} {r.text[:400]}")
            raise HTTPException(status_code=400, detail=f"Amazon cancel failed: {r.text[:300]}")
    now = datetime.now(timezone.utc).isoformat()
    await ship_orders.update_one({"id": order_id}, {
        "$push": {"cancelled_shipments": {"courier": "Amazon", **shp,
                                          "cancelled_by": user["name"], "cancelled_at": now}},
        "$unset": {"amazon_shipment": ""},
        "$set": {"updated_at": now},
    })
    return {"ok": True, "cancelled": shp.get("tracking_id") or sid}


@api_router.post("/amazon/cancel")
async def amazon_cancel(req: CancelLabelRequest, user=Depends(get_current_user)):
    """Cancels one Amazon shipment so the order can be rebooked."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await _amazon_cancel_one(req.order_id, user)


@api_router.post("/amazon/bulk-cancel")
async def amazon_bulk_cancel(req: BulkBookRequest, user=Depends(get_current_user)):
    """Cancels several Amazon shipments, one result line each."""
    if user["role"] not in ["admin", "dispatch", "packaging", "accounts"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    async def one(oid):
        return await _amazon_cancel_one(oid, user)

    return await _bulk_book(req.order_ids, one, user, "Amazon cancel")


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


async def _amazon_mark_dispatched(order: dict, when: str, by: str, docket: str = "", slip_url: str = "") -> dict:
    """Shared dispatch write for both the manual button and the pickup poller."""
    shipment = order.get("amazon_shipment") or {}
    dispatch = order.get("dispatch") or {}
    slips = list(dispatch.get("dispatch_slip_images") or [])
    if slip_url and slip_url not in slips:
        slips.append(slip_url)
    if not slips:
        url = await _save_label_as_slip(shipment)
        if url:
            slips.append(url)
    lr = docket or shipment.get("tracking_id") or ""
    dispatch.update({
        "courier_name": "Amazon",
        "transporter_name": "",
        "lr_no": lr,
        "dispatch_slip_images": slips,
        "dispatch_type": "courier",
        "porter_link": "",
        "dispatched_by": by,
        "dispatched_at": when,
    })
    await ship_orders.update_one({"id": order["id"]}, {"$set": {
        "dispatch": dispatch,
        "status": "dispatched",
        "courier_name": "Amazon",
        "amazon_shipment.picked_up_at": when,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"lr_no": lr, "slips": slips}


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
    await _amazon_mark_dispatched(order, picked_at, "Amazon Shipping (auto)", docket=tracking)
    logging.info(f"Amazon auto-dispatch: {order.get('order_number')} picked up at {picked_at}")
    return f"{order.get('order_number')} dispatched (picked up {picked_at})"


async def _amazon_sync_all() -> list:
    if not _amazon_configured():
        return []
    pending = await ship_orders.find({
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
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
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
    await ship_orders.update_one({"id": req.order_id}, {"$set": {
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


class AmazonDispatchRequest(BaseModel):
    order_id: str
    docket_no: Optional[str] = ""
    slip_image_url: Optional[str] = ""


@api_router.post("/amazon/dispatch")
async def amazon_manual_dispatch(req: AmazonDispatchRequest, user=Depends(get_current_user)):
    """Dispatch now, without waiting for Amazon to report pickup."""
    if user["role"] not in ["admin", "dispatch", "packaging"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await ship_orders.find_one({"id": req.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") == "dispatched":
        raise HTTPException(status_code=400, detail="Order is already dispatched")
    shipment = order.get("amazon_shipment") or {}
    docket = (req.docket_no or "").strip() or shipment.get("tracking_id") or ""
    if not docket:
        raise HTTPException(status_code=400, detail="Tracking / docket number is required")
    res = await _amazon_mark_dispatched(
        order, datetime.now(timezone.utc).isoformat(), user["name"],
        docket=docket, slip_url=(req.slip_image_url or "").strip(),
    )
    return {"ok": True, **res}


# ═══════════════════════════════════════════════════════════════════════════
# AMAZON SELLER ORDERS (SP-API)  - separate from Amazon Shipping above.
# Pulls marketplace orders into the existing Amazon module (amazon_orders),
# keeps Amazon's own status on each, and closes the loop: an order Amazon
# shows as picked up / shipped is dispatched here, a cancelled one is
# cancelled here. Buyer name, street and phone are NOT available to this
# app until the restricted role is granted.
# ═══════════════════════════════════════════════════════════════════════════
SPAPI = {
    "client_id": os.environ.get("AMZ_SP_CLIENT_ID", ""),
    "client_secret": os.environ.get("AMZ_SP_CLIENT_SECRET", ""),
    "refresh_token": os.environ.get("AMZ_SP_REFRESH_TOKEN", ""),
    "endpoint": os.environ.get("AMZ_SP_ENDPOINT", "https://sellingpartnerapi-eu.amazon.com").rstrip("/"),
    "marketplace": os.environ.get("AMZ_SP_MARKETPLACE", "A21TJRUUN4KGV"),   # Amazon.in
}
SPAPI_SYNC_INTERVAL_SECONDS = int(os.environ.get("AMZ_SP_SYNC_SECONDS", "120"))
_spapi_token_cache = {"token": "", "expires": 0.0}
_spapi_sync_lock = asyncio.Lock()

# Easy Ship states at or after the courier's pickup scan. Scheduling a pickup
# is not dispatch - the parcel has to actually leave.
SPAPI_EASYSHIP_GONE = {"PickedUp", "AtOriginFC", "AtDestinationFC", "OutForDelivery", "Delivered",
                       "RejectedByBuyer", "Undeliverable", "ReturningToSeller", "ReturnedToSeller", "Damaged", "Lost"}


def _spapi_configured() -> bool:
    return bool(SPAPI["client_id"] and SPAPI["client_secret"] and SPAPI["refresh_token"])


async def _spapi_token() -> str:
    import time
    if _spapi_token_cache["token"] and _spapi_token_cache["expires"] > time.time() + 60:
        return _spapi_token_cache["token"]
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.amazon.com/auth/o2/token", data={
            "grant_type": "refresh_token", "refresh_token": SPAPI["refresh_token"],
            "client_id": SPAPI["client_id"], "client_secret": SPAPI["client_secret"]})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Amazon login failed: {r.text[:200]}")
    data = r.json()
    _spapi_token_cache.update(token=data["access_token"], expires=time.time() + int(data.get("expires_in", 3600)))
    return data["access_token"]


async def _spapi_get(path: str, params: dict) -> dict:
    """GET with polite retries: the Orders API throttles hard (HTTP 429)."""
    token = await _spapi_token()
    for attempt in range(5):
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.get(f"{SPAPI['endpoint']}{path}", params=params,
                            headers={"x-amz-access-token": token, "accept": "application/json"})
        if r.status_code == 429:
            await asyncio.sleep(3 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Amazon API {path}: {r.status_code} {r.text[:200]}")
        return r.json().get("payload") or {}
    raise HTTPException(status_code=502, detail=f"Amazon API {path}: still throttled")


def _spapi_meta(o: dict) -> dict:
    """Amazon-side facts refreshed on every sync; never touches our own fields."""
    return {
        "amazon_status": o.get("OrderStatus"),
        "easy_ship_status": o.get("EasyShipShipmentStatus") or "",
        "latest_ship_date": o.get("LatestShipDate") or "",
        "purchase_date": o.get("PurchaseDate") or "",
        "is_cod": (o.get("PaymentMethod") or "").upper() == "COD",
        "is_prime": bool(o.get("IsPrime")),
        "amazon_last_update": o.get("LastUpdateDate") or "",
    }


async def _spapi_build_order(o: dict) -> dict:
    items_payload = await _spapi_get(f"/orders/v0/orders/{o['AmazonOrderId']}/orderItems", {})
    items = []
    for it in items_payload.get("OrderItems") or []:
        qty = int(it.get("QuantityOrdered") or 0)
        if qty <= 0:
            continue
        line = float((it.get("ItemPrice") or {}).get("Amount") or 0) + float((it.get("ItemTax") or {}).get("Amount") or 0)
        items.append({"product_name": (it.get("Title") or "").strip(), "quantity": qty, "unit": "pcs",
                      "unit_price": round(line / qty, 2), "amount": round(line, 2),
                      "sku": it.get("SellerSKU") or "", "asin": it.get("ASIN") or "",
                      "order_item_id": it.get("OrderItemId") or ""})
    sa = o.get("ShippingAddress") or {}
    place = ", ".join(x for x in [sa.get("City"), sa.get("StateOrRegion")] if x)
    if sa.get("PostalCode"):
        place = f"{place} - {sa['PostalCode']}" if place else sa["PostalCode"]
    easy = bool(o.get("EasyShipShipmentStatus"))
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "am_order_number": await get_next_am_number(),
        "amazon_order_id": o["AmazonOrderId"],
        "ship_type": "easy_ship" if easy else "self_ship",
        "shipping_method": "amazon" if easy else "courier",
        "courier_name": "",
        # Buyer name / street / phone need the restricted role.
        "customer_name": f"Amazon customer ({sa.get('City') or 'India'})",
        "address": place, "phone": "",
        "items": items,
        "grand_total": float((o.get("OrderTotal") or {}).get("Amount") or sum(i["amount"] for i in items)),
        "status": "new",
        "packaging": {"item_packed_by": [], "box_packed_by": [], "checked_by": [],
                      "item_images": {}, "order_images": [], "packed_box_images": []},
        "dispatch": {},
        "source": "sp_api",
        **_spapi_meta(o),
        "created_at": now, "updated_at": now,
    }


async def _spapi_sync(lookback_hours: Optional[int] = None) -> dict:
    """One pass: new orders in, Amazon status refreshed, shipped -> dispatched, cancelled -> cancelled."""
    if not _spapi_configured():
        raise HTTPException(status_code=400, detail="Amazon seller API is not configured")
    async with _spapi_sync_lock:
        state = await db.settings.find_one({"_id": "spapi_sync"}) or {}
        now = datetime.now(timezone.utc)
        if lookback_hours:
            since = now - timedelta(hours=lookback_hours)
        elif state.get("last_run"):
            since = datetime.fromisoformat(state["last_run"]) - timedelta(minutes=15)   # overlap: never miss one
        else:
            since = now - timedelta(days=7)
        params = {"MarketplaceIds": SPAPI["marketplace"], "MaxResultsPerPage": 100,
                  "LastUpdatedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ")}
        orders, pages = [], 0
        while True:
            payload = await _spapi_get("/orders/v0/orders", params)
            orders += payload.get("Orders") or []
            pages += 1
            nxt = payload.get("NextToken")
            if not nxt or pages >= 10:
                break
            params = {"MarketplaceIds": SPAPI["marketplace"], "NextToken": nxt}
            await asyncio.sleep(2)

        res = {"seen": len(orders), "created": [], "dispatched": [], "cancelled": [], "updated": 0}
        for o in orders:
            aid, st = o.get("AmazonOrderId"), o.get("OrderStatus")
            if not aid or o.get("FulfillmentChannel") == "AFN":          # FBA is not ours to pack
                continue
            existing = await db.amazon_orders.find_one({"amazon_order_id": aid}, {"_id": 0})
            if not existing:
                # Scheduling an Easy Ship pickup flips Amazon's OrderStatus to
                # "Shipped" while the parcel is still on our table. Such an order
                # is still ours to pack, so it is imported as long as the courier
                # has not collected it yet.
                easy = o.get("EasyShipShipmentStatus") or ""
                still_with_us = bool(easy) and easy not in SPAPI_EASYSHIP_GONE and st not in ("Canceled", "Pending")
                if st in ("Unshipped", "PartiallyShipped") or still_with_us:
                    doc = await _spapi_build_order(o)
                    await db.amazon_orders.insert_one(_pii_seal({**doc, "address_public": doc["address"]}))
                    res["created"].append(doc["am_order_number"])
                    await asyncio.sleep(2)                                # orderItems rate limit
                continue
            upd = {**_spapi_meta(o), "updated_at": now.isoformat()}
            gone = (st == "Shipped") if not o.get("EasyShipShipmentStatus") \
                else (o.get("EasyShipShipmentStatus") in SPAPI_EASYSHIP_GONE)
            if st == "Canceled" and existing.get("status") not in ("dispatched", "cancelled"):
                upd["status"] = "cancelled"
                upd["cancelled_at"] = now.isoformat()
                res["cancelled"].append(existing.get("am_order_number"))
            elif gone and existing.get("status") not in ("dispatched", "cancelled"):
                upd["status"] = "dispatched"
                upd["dispatch"] = {**(existing.get("dispatch") or {}), "dispatched_at": now.isoformat(),
                                   "dispatched_by": "Amazon (auto)", "auto": True,
                                   "was_status": existing.get("status")}
                res["dispatched"].append(existing.get("am_order_number"))
            else:
                res["updated"] += 1
            await db.amazon_orders.update_one({"id": existing["id"]}, {"$set": upd})
        res["alerts"] = await _spapi_shipby_alerts(now)
        res["purged"] = await _pii_purge(now)
        await db.settings.update_one({"_id": "spapi_sync"}, {"$set": {
            "last_run": now.isoformat(), "last_result": {k: (v if isinstance(v, int) else len(v)) for k, v in res.items()},
            "last_error": ""}}, upsert=True)
        return res


PII_RETENTION_DAYS = 30


async def _pii_purge(now: datetime) -> int:
    """Amazon's Data Protection Policy: buyer PII goes 30 days after shipment.
    Only the name, street address and phone are blanked; the order, its items,
    city/pincode, photos and history all stay."""
    cutoff = (now - timedelta(days=PII_RETENTION_DAYS)).isoformat()
    stale = await db.amazon_orders.find({
        "has_buyer_pii": True, "pii_purged_at": {"$exists": False},
        "status": {"$in": ["dispatched", "cancelled"]},
        "$or": [{"dispatch.dispatched_at": {"$lte": cutoff}}, {"cancelled_at": {"$lte": cutoff}}],
    }, {"_id": 0, "id": 1, "address_public": 1, "am_order_number": 1}).to_list(500)
    for o in stale:
        await db.amazon_orders.update_one({"id": o["id"]}, {"$set": {
            "customer_name": "Amazon customer", "address": o.get("address_public") or "",
            "phone": "", "ship_to.name": "", "ship_to.line1": "", "ship_to.phone": "",
            "pii_purged_at": now.isoformat(), "has_buyer_pii": False}})
    if stale:
        await _sec_log("pii_purged", count=len(stale), orders=[o["am_order_number"] for o in stale][:50])
    return len(stale)


# Amazon's ship-by deadline is 23:59 IST of the ship-by day, long after the
# office and the pickup slots close, so the warning fires from mid-afternoon
# of that day (deadline minus AMZ_SP_WARN_HOURS), and again once it is missed.
SPAPI_WARN_HOURS = int(os.environ.get("AMZ_SP_WARN_HOURS", "10"))


async def _spapi_shipby_alerts(now: datetime) -> list:
    """One alert per order per stage ('warn', 'overdue') to admin, packaging and dispatch."""
    raised = []
    horizon = (now + timedelta(hours=SPAPI_WARN_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pending = await db.amazon_orders.find({
        "source": "sp_api", "status": {"$in": ["new", "packaging", "packed"]},
        "latest_ship_date": {"$nin": ["", None], "$lte": horizon},
    }, {"_id": 0}).to_list(200)
    if not pending:
        return raised
    recipients = [u["id"] for u in await db.users.find(
        {"role": {"$in": ["admin", "packaging", "dispatch"]}, "active": {"$ne": False}},
        {"_id": 0, "id": 1}).to_list(200)]
    for o in pending:
        try:
            deadline = datetime.fromisoformat(o["latest_ship_date"].replace("Z", "+00:00"))
        except ValueError:
            continue
        unpacked = o.get("status") in ("new", "packaging")
        unscheduled = o.get("easy_ship_status") == "PendingSchedule"
        if not (unpacked or unscheduled):
            continue                       # packed and pickup booked: nothing to chase
        stage = "overdue" if now > deadline else "warn"
        if (o.get("shipby_alerted") or {}).get(stage):
            continue
        todo = " and ".join(x for x in ["not packed" if unpacked else "", "pickup not scheduled" if unscheduled else ""] if x)
        by = deadline.astimezone(IST).strftime("%d %b")
        title = (f"Amazon {o['am_order_number']}: ship-by date MISSED" if stage == "overdue"
                 else f"Amazon {o['am_order_number']}: must ship today ({by})")
        await db.admin_alerts.insert_one({
            "id": str(uuid.uuid4()), "title": title,
            "message": f"{o['am_order_number']} ({o['amazon_order_id']}) is {todo}. Ship-by date: {by}. "
                       f"Items: {', '.join(str(i['quantity']) + ' x ' + i['product_name'][:40] for i in o.get('items') or [])}",
            "sent_by": "System", "sent_by_id": None, "order_id": "", "customer_name": "",
            "recipient_ids": recipients, "recipient_roles": ["admin", "packaging", "dispatch"],
            "acknowledgements": {}, "created_at": now.isoformat(),
            "meta": {"type": "amazon_ship_by", "stage": stage, "amazon_order_id": o["amazon_order_id"]},
        })
        await db.amazon_orders.update_one({"id": o["id"]}, {"$set": {f"shipby_alerted.{stage}": now.isoformat()}})
        raised.append(f"{o['am_order_number']}:{stage}")
    return raised


@api_router.post("/amazon/sp/sync")
async def spapi_sync_now(hours: int = 0, user=Depends(get_current_user)):
    """Pull from Amazon right now. `hours` widens the look-back (admin catch-up)."""
    if user["role"] not in ["admin", "packaging", "dispatch"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await _spapi_sync(min(max(hours, 0), 24 * 30) or None)


@api_router.get("/security/log")
async def security_log(event: str = "", limit: int = 200, admin=Depends(require_admin)):
    q = {"event": event} if event else {}
    rows = await db.security_log.find(q, {"_id": 0, "at_dt": 0}).sort("at_dt", -1).to_list(min(max(limit, 1), 1000))
    return {"rows": rows, "encryption_configured": bool(_PII_KEY)}


@api_router.post("/security/log/reviewed")
async def security_log_reviewed(admin=Depends(require_admin)):
    """Records that the Security Owner reviewed the log (evidence of the bi-weekly review)."""
    await _sec_log("log_reviewed", by=admin.get("username") or admin.get("name"))
    return {"ok": True}


@api_router.get("/amazon/sp/status")
async def spapi_status(user=Depends(get_current_user)):
    state = await db.settings.find_one({"_id": "spapi_sync"}, {"_id": 0}) or {}
    pending = await db.amazon_orders.count_documents({"easy_ship_status": "PendingSchedule",
                                                      "status": {"$nin": ["dispatched", "cancelled"]}})
    return {"configured": _spapi_configured(), "interval_seconds": SPAPI_SYNC_INTERVAL_SECONDS,
            "pending_schedule": pending, **state}


async def _spapi_sync_loop():
    await asyncio.sleep(45)
    while True:
        try:
            await _spapi_sync()
        except Exception as e:
            logging.error(f"Amazon seller sync error: {e}")
            try:
                await db.settings.update_one({"_id": "spapi_sync"}, {"$set": {
                    "last_error": str(getattr(e, "detail", e))[:300],
                    "last_error_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
            except Exception:
                pass
        await asyncio.sleep(SPAPI_SYNC_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_spapi_sync():
    if _spapi_configured():
        asyncio.create_task(_spapi_sync_loop())
        logging.info(f"Amazon seller order sync every {SPAPI_SYNC_INTERVAL_SECONDS}s")


# ═══════════════════════════════════════════════════════════════════════════
# WEBSITE ORDERS → SHOPIFY. When a website order is dispatched, the matching
# Shopify order is fulfilled with the carrier and tracking number, so Shopify
# shows it shipped and mails the customer. A sweep retries every 5 minutes.
# ═══════════════════════════════════════════════════════════════════════════
SHOPIFY = {
    "domain": os.environ.get("SHOPIFY_SHOP_DOMAIN", "").strip().replace("https://", "").rstrip("/"),
    "token": os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip(),
    "api": os.environ.get("SHOPIFY_API_VERSION", "2024-10").strip(),
}
SHOPIFY_FULFIL_SINCE = os.environ.get("SHOPIFY_FULFIL_SINCE", "2026-09-26T00:00:00+00:00")
SHOPIFY_NOTIFY_WITHIN_DAYS = 3          # older dispatches are marked fulfilled quietly


def _shopify_configured() -> bool:
    return bool(SHOPIFY["domain"] and SHOPIFY["token"])


async def _shopify_call(method: str, path: str, **kw) -> tuple:
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.request(method, f"https://{SHOPIFY['domain']}/admin/api/{SHOPIFY['api']}{path}",
                            headers={"X-Shopify-Access-Token": SHOPIFY["token"], "Content-Type": "application/json"}, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


async def _shopify_fulfill(order: dict, by: str = "auto", force: bool = False) -> dict:
    prev = order.get("shopify_fulfillment") or {}
    if prev.get("status") == "fulfilled" and not force:
        return prev
    rec = {"attempts": int(prev.get("attempts") or 0) + 1, "at": datetime.now(timezone.utc).isoformat(), "by": by}
    sid = str(order.get("shopify_order_id") or "").strip()
    d = order.get("dispatch") or {}
    lr = (d.get("lr_no") or "").strip()
    if not _shopify_configured():
        rec.update(status="failed", error="Shopify is not configured on the server (SHOPIFY_SHOP_DOMAIN / SHOPIFY_ADMIN_TOKEN)")
    elif not sid:
        rec.update(status="failed", error="Order has no Shopify order id")
    elif not lr:
        rec.update(status="failed", error="No tracking / LR number on the dispatch yet")
    else:
        try:
            code, fo = await _shopify_call("GET", f"/orders/{sid}/fulfillment_orders.json")
            fos = [x for x in ((fo or {}).get("fulfillment_orders") or []) if x.get("status") in ("open", "in_progress", "scheduled")]
            if code != 200:
                rec.update(status="failed", error=f"Shopify {code}: {str(fo)[:200]}")
            elif not fos:
                already = [x for x in ((fo or {}).get("fulfillment_orders") or []) if x.get("status") == "closed"]
                rec.update(status="fulfilled" if already else "failed",
                           error="" if already else "Shopify has nothing left to fulfil on this order", note="already fulfilled on Shopify" if already else "")
            else:
                courier = _dispatch_courier_label(order) if (d.get("dispatch_type") or order.get("shipping_method")) != "transport" \
                    else (d.get("transporter_name") or order.get("transporter_name") or "Transport")
                url = _dispatch_tracking_url(d.get("courier_name") or order.get("courier_name") or "", lr)
                try:
                    when = datetime.fromisoformat(str(d.get("dispatched_at") or "").replace("Z", "+00:00"))
                except ValueError:
                    when = datetime.now(timezone.utc)
                recent = (datetime.now(timezone.utc) - when) <= timedelta(days=SHOPIFY_NOTIFY_WITHIN_DAYS)
                body = {"fulfillment": {
                    "line_items_by_fulfillment_order": [{"fulfillment_order_id": x["id"]} for x in fos],
                    "tracking_info": {"number": lr, "company": courier, **({"url": url} if url else {})},
                    "notify_customer": bool(recent)}}
                code, res = await _shopify_call("POST", "/fulfillments.json", json=body)
                f = (res or {}).get("fulfillment") or {}
                if code in (200, 201) and f.get("id"):
                    rec.update(status="fulfilled", fulfillment_id=f["id"], carrier=courier, tracking=lr, url=url,
                               notified_customer=bool(recent), error="")
                else:
                    rec.update(status="failed", error=f"Shopify {code}: {str(res)[:240]}")
        except Exception as e:
            rec.update(status="failed", error=str(e)[:240])
    await db.orders.update_one({"id": order["id"]}, {"$set": {"shopify_fulfillment": rec}})
    if rec["status"] != "fulfilled":
        logging.warning(f"shopify fulfil {order.get('order_number')}: {rec.get('error')}")
    return rec


async def _shopify_fulfil_sweep():
    if not _shopify_configured():
        return
    q = {"website_order": True, "status": "dispatched", "dispatch.dispatched_at": {"$gte": SHOPIFY_FULFIL_SINCE},
         "shopify_fulfillment.status": {"$ne": "fulfilled"},
         "$or": [{"shopify_fulfillment.attempts": {"$exists": False}}, {"shopify_fulfillment.attempts": {"$lt": 8}}]}
    async for o in db.orders.find(q, {"_id": 0}).limit(20):
        await _shopify_fulfill(o)


async def _shopify_fulfil_loop():
    await asyncio.sleep(90)
    while True:
        try:
            await _shopify_fulfil_sweep()
        except Exception as e:
            logging.error(f"shopify fulfil sweep: {e}")
        await asyncio.sleep(300)


@app.on_event("startup")
async def _start_shopify_fulfil():
    asyncio.create_task(_shopify_fulfil_loop())
    logging.info("Shopify fulfilment sweep " + ("on" if _shopify_configured() else "idle - not configured"))


@api_router.post("/orders/{order_id}/shopify-fulfill")
async def shopify_fulfill_now(order_id: str, user=Depends(get_current_user)):
    if user["role"] not in ("admin", "dispatch", "accounts"):
        raise HTTPException(status_code=403, detail="Not authorized")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.get("website_order"):
        raise HTTPException(status_code=400, detail="Not a website order")
    if order.get("status") != "dispatched":
        raise HTTPException(status_code=400, detail="Order is not dispatched yet")
    return await _shopify_fulfill(order, by=user["name"], force=True)


# ═══════════════════════════════════════════════════════════════════════════
# DISPATCH → WHATSAPP. Every courier / transport order that becomes "dispatched"
# is announced to the customer through the CRM, which owns the WhatsApp number,
# the 24-hour window logic and the message log. A sweep runs every minute so it
# does not matter which of the many dispatch paths flipped the status.
# ═══════════════════════════════════════════════════════════════════════════
CRM_BASE_URL = os.environ.get("CRM_BASE_URL", "https://crm.mangalamagro.in").rstrip("/")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://oms.mangalamagro.in").rstrip("/")
# Only dispatches from go-live onward are announced; nothing older is sent.
DISPATCH_NOTIFY_SINCE = os.environ.get("DISPATCH_NOTIFY_SINCE", "2026-09-23T11:30:00+00:00")
DISPATCH_NOTIFY_INTERVAL = int(os.environ.get("DISPATCH_NOTIFY_INTERVAL", "60"))
DISPATCH_NOTIFY_MAX_ATTEMPTS = 5
_NOTIFY_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _dispatch_tracking_url(courier: str, lr: str) -> str:
    c, lr = (courier or "").strip().lower(), (lr or "").strip()
    if not lr:
        return ""
    if c.startswith("dtdc"):
        return f"https://txk.dtdc.com/ctbs-tracking/customerInterface.tr?submitName=showCITrackingDetails&cType=Consignment&cnNo={lr}"
    if c.startswith("amazon"):
        return f"https://track.amazon.in/tracking/{lr}"
    if c.startswith("shiprocket"):
        return f"https://shiprocket.co/tracking/{lr}"
    if c.startswith("anjani"):
        return f"https://shreeanjani.co.in/tracking?awb={lr}"
    if c.startswith("delhivery"):
        return f"https://www.delhivery.com/track-v2/package/{lr}"
    return ""


def _dispatch_courier_label(order: dict) -> str:
    d = order.get("dispatch") or {}
    name = (d.get("courier_name") or order.get("courier_name") or "").strip()
    low = name.lower()
    if low.startswith("amazon"):
        return "Amazon Shipping"
    if low.startswith("shiprocket"):
        partner = d.get("courier_partner") or (order.get("shiprocket_shipment") or {}).get("courier_name") or ""
        return f"{partner} (via Shiprocket)" if partner else "Shiprocket"
    if low.startswith("anjani"):
        return "Shree Anjani Courier"
    if low.startswith("delhivery"):
        return d.get("courier_partner") or "Delhivery"
    return name or "our courier"


def _wa_safe_image(upload_path: str) -> str:
    """WhatsApp rejects 1-bit / greyscale / palette images (Meta error 131053), and
    courier labels are usually exactly that. Hand it an RGB JPEG copy instead,
    made once next to the original. Returns the public URL, or "" if unusable."""
    name = str(upload_path or "").rsplit("/", 1)[-1]
    src = UPLOAD_DIR / name
    if not name or not src.exists():
        return ""
    out_name = name.rsplit(".", 1)[0] + ".wa.jpg"
    out = UPLOAD_DIR / out_name
    if not out.exists():
        try:
            from PIL import Image
            im = Image.open(src)
            im.load()
            if im.mode in ("RGBA", "LA", "P") and "A" in im.getbands():
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
                im = bg
            else:
                im = im.convert("RGB")
            if max(im.size) > 1800:
                im.thumbnail((1800, 1800))
            im.save(out, "JPEG", quality=88)
        except Exception as e:
            logging.warning(f"wa image convert {name}: {e}")
            return ""
    return f"{PUBLIC_BASE_URL}/api/uploads/{out_name}"


async def _dispatch_notify_payload(order: dict) -> dict:
    d = order.get("dispatch") or {}
    kind = (d.get("dispatch_type") or order.get("shipping_method") or "").strip().lower()
    slip = ""
    for img in d.get("dispatch_slip_images") or []:
        if str(img).lower().endswith(_NOTIFY_IMAGE_EXT) and not str(img).startswith("http"):
            slip = _wa_safe_image(str(img))
            if slip:
                break
    return {
        "company": order.get("company") or DEFAULT_COMPANY,
        "oms_order_id": order["id"], "order_no": order.get("order_number") or order["id"][:8],
        "customer_name": order.get("customer_name") or "",
        "phones": await _order_phones(order),
        "dispatch_type": "transport" if kind == "transport" else "courier",
        "courier": _dispatch_courier_label(order) if kind != "transport" else "",
        "transporter": (d.get("transporter_name") or order.get("transporter_name") or "").strip(),
        "tracking_no": (d.get("lr_no") or "").strip(),
        "tracking_url": _dispatch_tracking_url(d.get("courier_name") or order.get("courier_name") or "", d.get("lr_no") or "") if kind != "transport" else "",
        "slip_image_url": slip,
        "telecaller_id": order.get("telecaller_id"),
    }


async def _dispatch_notify_send(order: dict, force: bool = False, by: str = "auto") -> dict:
    """Ask the CRM to message the customer; record the outcome on the order."""
    prev = order.get("dispatch_notify") or {}
    rec = {"attempts": int(prev.get("attempts") or 0) + 1, "at": datetime.now(timezone.utc).isoformat(), "by": by}
    payload = await _dispatch_notify_payload(order)
    if not payload["phones"]:
        rec.update(status="skipped", error="customer has no phone number")
    else:
        try:
            token = jwt.encode({"svc": "oms", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, JWT_SECRET, algorithm=JWT_ALGORITHM)
            async with httpx.AsyncClient(timeout=40) as c:
                r = await c.post(f"{CRM_BASE_URL}/api/oms/dispatch-notify", json={**payload, "force": force},
                                 headers={"Authorization": f"Bearer {token}"})
            data = r.json() if r.content else {}
            if r.status_code >= 400:
                rec.update(status="failed", error=f"CRM {r.status_code}: {str(data.get('detail') or data)[:200]}")
            else:
                rec.update(status=data.get("status") or "failed", channel=data.get("channel") or "",
                           template=data.get("template") or "", wamid=data.get("wamid") or "",
                           phone=data.get("phone") or "", lead_id=data.get("lead_id") or "",
                           within_24h=bool(data.get("within_24h")), error=data.get("error") or "")
        except Exception as e:
            rec.update(status="failed", error=str(e)[:200])
    await db.orders.update_one({"id": order["id"]}, {"$set": {"dispatch_notify": rec}})
    if rec["status"] == "failed":
        logging.warning(f"dispatch notify {payload['order_no']}: {rec.get('error')}")
    return rec


async def _dispatch_notify_sweep():
    q = {
        "status": "dispatched",
        "dispatch.dispatch_type": {"$in": ["courier", "transport"]},
        "dispatch.dispatched_at": {"$gte": DISPATCH_NOTIFY_SINCE},
        "dispatch_notify.status": {"$nin": ["sent", "sent_mock", "delivered", "read", "already_sent", "skipped"]},
        "$or": [{"dispatch_notify.attempts": {"$exists": False}}, {"dispatch_notify.attempts": {"$lt": DISPATCH_NOTIFY_MAX_ATTEMPTS}}],
    }
    async for o in db.orders.find(q, {"_id": 0}).sort("dispatch.dispatched_at", 1).limit(20):
        await _dispatch_notify_send(o)


async def _dispatch_notify_loop():
    await asyncio.sleep(45)
    while True:
        try:
            await _dispatch_notify_sweep()
        except Exception as e:
            logging.error(f"dispatch notify sweep: {e}")
        await asyncio.sleep(DISPATCH_NOTIFY_INTERVAL)


@app.on_event("startup")
async def _start_dispatch_notify():
    asyncio.create_task(_dispatch_notify_loop())
    logging.info(f"Dispatch WhatsApp sweep every {DISPATCH_NOTIFY_INTERVAL}s for dispatches since {DISPATCH_NOTIFY_SINCE}")


class NotifyDispatchRequest(BaseModel):
    force: bool = False


@api_router.post("/orders/{order_id}/notify-dispatch")
async def notify_dispatch_now(order_id: str, req: NotifyDispatchRequest = NotifyDispatchRequest(), user=Depends(get_current_user)):
    """Send (or resend) the dispatch WhatsApp for one order right now."""
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if user["role"] not in ("admin", "dispatch", "accounts") and not (user["role"] == "telecaller" and order.get("telecaller_id") == user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized")
    if order.get("status") != "dispatched":
        raise HTTPException(status_code=400, detail="Order is not dispatched yet")
    kind = ((order.get("dispatch") or {}).get("dispatch_type") or order.get("shipping_method") or "").lower()
    if kind not in ("courier", "transport"):
        raise HTTPException(status_code=400, detail="Dispatch messages go only for courier and transport orders")
    return await _dispatch_notify_send(order, force=req.force, by=user["name"])


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


@api_router.get("/amazon/labels-sheet")
async def amazon_labels_sheet(ids: str, token: str = "", user=None):
    """Selected Amazon labels laid out four to an A4 page, one per quarter.

    Filled in selection order: 1 label uses one quarter, 2 the top half, 3
    leave one quarter blank, 4 fill the page; more than 4 continues on the
    next page. Quarters are never stretched — each label keeps its aspect.
    """
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    order_ids = [x.strip() for x in (ids or "").split(",") if x.strip()][:40]
    if not order_ids:
        raise HTTPException(status_code=400, detail="No orders given")

    import base64
    labels = []          # (order_number, PIL-ready bytes)
    missing = []
    for oid in order_ids:
        o = await ship_orders.find_one({"id": oid}, {"_id": 0, "order_number": 1,
                                                   "amazon_shipment": 1})
        sh = (o or {}).get("amazon_shipment") or {}
        if not sh.get("label_base64"):
            missing.append((o or {}).get("order_number") or oid[:8])
            continue
        try:
            labels.append(((o or {}).get("order_number", ""),
                           base64.b64decode(sh["label_base64"])))
        except Exception:
            missing.append((o or {}).get("order_number") or oid[:8])
    if not labels:
        raise HTTPException(status_code=404,
                            detail=f"No stored labels for: {', '.join(missing)}")

    buffer = _quarter_sheet_pdf([raw for _num, raw in labels])
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition":
                                      "inline; filename=amazon-labels-sheet.pdf"})


@api_router.get("/amazon/label/{order_id}")
async def amazon_label_pdf(order_id: str, token: str = "", user=None):
    """Amazon shipping label rendered on a landscape A5 page."""
    if token:
        user = await get_user_from_token_param(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    order = await ship_orders.find_one({"id": order_id}, {"_id": 0})
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


# ─── India Post (Department of Posts / CEPT) ─────────────────────────────
# Two contracts are held: one for small articles (Speed Post) and one for
# heavier ones (Business Parcel). Both are quoted for every shipment and the
# cheaper one wins — that is the whole point of the rate calculator.
#
# Unlike DTDC and Amazon, India Post does NOT allocate the tracking number:
# each customer is allotted a barcode series and generates article numbers
# itself (UPU S10 - 2 letters, 8-digit serial, check digit, "IN").

INDIAPOST_BASE = os.environ.get(
    "INDIAPOST_BASE_URL", "https://test.cept.gov.in/beextcustomer").rstrip("/")
INDIAPOST_MASTER = os.environ.get(
    "INDIAPOST_MASTER_URL", "https://test.cept.gov.in/bemasterdata").rstrip("/")

INDIAPOST_PATH_LOGIN = "/v1/access/login"
INDIAPOST_PATH_OFFICES = "/v1/offices/limited-details"          # on MASTER
INDIAPOST_PATH_TARIFF_SP = "/v1/speed-post/tariffs"
INDIAPOST_PATH_TARIFF_BP = "/v1/business-parcel-tariff/calculate"
INDIAPOST_PATH_TARIFF_LETTER = "/v1/letter-tariff/calculate"
INDIAPOST_PATH_TARIFF_PARCEL = "/v1/parcel-tariff/calculate"
INDIAPOST_PATH_BOOK = "/process-articles"                       # + /{customer_id}
INDIAPOST_PATH_LABEL = "/v1/label/create/domestic"
INDIAPOST_PATH_TRACK = "/v1/tracking/bulk"

# Article types and the envelope each is valid in. Weights are grams, dims cm.
# Straight from the DoP approach document's dimension tables.
INDIAPOST_PRODUCTS = {
    "SP_INLAND_DOC": {
        "label": "Speed Post Document", "service": "SP",
        "w_min": 1, "w_max": 500,
        "l": (1, 42), "b": (1, 29), "h": (1, 2),
        "path": INDIAPOST_PATH_TARIFF_SP, "code": "SP", "shape": "DOC",
    },
    "SP_INLAND_PARCEL": {
        "label": "Speed Post Parcel", "service": "SP",
        "w_min": 501, "w_max": 35000,
        "l": (14, 150), "b": (9, 150), "h": (1, 150),
        "path": INDIAPOST_PATH_TARIFF_SP, "code": "SP", "shape": "NROL",
    },
    "BUSINESS_PARCEL": {
        "label": "Business Parcel", "service": "BP",
        "w_min": 1, "w_max": 35000,
        "l": (14, 150), "b": (9, 150), "h": (1, 150),
        "path": INDIAPOST_PATH_TARIFF_BP, "code": "BP", "shape": "NROL",
    },
    # These two are subscribed on the account but absent from the approach
    # document's booking section, so they are quotable but not (yet) bookable.
    # Envelopes are left wide because DoP publishes no limits for them here;
    # an out-of-range article simply comes back as a refused quote.
    "LETTER": {
        "label": "Registered Letter", "service": "LETTER",
        "w_min": 1, "w_max": 2000,
        "l": (1, 60), "b": (1, 60), "h": (1, 60),
        "path": INDIAPOST_PATH_TARIFF_LETTER, "code": "LETTER", "shape": "DOC",
    },
    "PARCEL": {
        "label": "Parcel", "service": "PARCEL",
        "w_min": 1, "w_max": 35000,
        "l": (1, 150), "b": (1, 150), "h": (1, 150),
        "path": INDIAPOST_PATH_TARIFF_PARCEL, "code": "PARCEL", "shape": "NROL",
    },
}

# Products India Post will actually let us book through process-articles.
INDIAPOST_BOOKABLE_PRODUCTS = {"SP_INLAND_DOC", "SP_INLAND_PARCEL", "BUSINESS_PARCEL"}

# Accounts. "small" and "large" are our names for the two contracts; each may
# serve several product codes, and every eligible product is quoted.
INDIAPOST_ACCOUNTS = {
    "small": {
        "label": os.environ.get("INDIAPOST_SMALL_LABEL", "India Post — Speed Post"),
        "username": os.environ.get("INDIAPOST_SMALL_USERNAME", ""),
        "password": os.environ.get("INDIAPOST_SMALL_PASSWORD", ""),
        "customer_id": os.environ.get("INDIAPOST_SMALL_CUSTOMER_ID", ""),
        "contract_id": os.environ.get("INDIAPOST_SMALL_CONTRACT_ID", ""),
        "products": [p.strip() for p in os.environ.get(
            "INDIAPOST_SMALL_PRODUCTS", "SP_INLAND_DOC,SP_INLAND_PARCEL").split(",") if p.strip()],
        "series_prefix": os.environ.get("INDIAPOST_SMALL_SERIES_PREFIX", ""),
        "series_start": os.environ.get("INDIAPOST_SMALL_SERIES_START", ""),
        "series_end": os.environ.get("INDIAPOST_SMALL_SERIES_END", ""),
    },
    "large": {
        "label": os.environ.get("INDIAPOST_LARGE_LABEL", "India Post — Business Parcel"),
        "username": os.environ.get("INDIAPOST_LARGE_USERNAME", ""),
        "password": os.environ.get("INDIAPOST_LARGE_PASSWORD", ""),
        "customer_id": os.environ.get("INDIAPOST_LARGE_CUSTOMER_ID", ""),
        "contract_id": os.environ.get("INDIAPOST_LARGE_CONTRACT_ID", ""),
        "products": [p.strip() for p in os.environ.get(
            "INDIAPOST_LARGE_PRODUCTS", "BUSINESS_PARCEL").split(",") if p.strip()],
        "series_prefix": os.environ.get("INDIAPOST_LARGE_SERIES_PREFIX", ""),
        "series_start": os.environ.get("INDIAPOST_LARGE_SERIES_START", ""),
        "series_end": os.environ.get("INDIAPOST_LARGE_SERIES_END", ""),
    },
}

INDIAPOST_ORIGIN_PINCODE = os.environ.get("INDIAPOST_ORIGIN_PINCODE", "440025")
INDIAPOST_MAX_WEIGHT_G = 35000


def _indiapost_configured() -> bool:
    return any(a["username"] and a["password"] for a in INDIAPOST_ACCOUNTS.values())


def _s10_check_digit(serial8: str) -> str:
    """UPU S10 check digit — weighting factors 8,6,4,2,3,5,9,7 over modulus 11."""
    weights = (8, 6, 4, 2, 3, 5, 9, 7)
    total = sum(int(d) * w for d, w in zip(serial8, weights))
    remainder = total % 11
    if remainder == 0:
        return "5"
    if remainder == 1:
        return "0"
    return str(11 - remainder)


def indiapost_barcode(prefix: str, serial: int) -> str:
    """e.g. ('ET', 21433001) -> 'ET214330015IN'."""
    s8 = f"{int(serial):08d}"
    return f"{prefix.upper()}{s8}{_s10_check_digit(s8)}IN"


# access_token lives 900s; refresh a minute early rather than racing expiry.
_INDIAPOST_TOKENS: dict = {}


async def _indiapost_token(account_key: str) -> str:
    acct = INDIAPOST_ACCOUNTS.get(account_key) or {}
    if not (acct.get("username") and acct.get("password")):
        raise HTTPException(status_code=503,
                            detail=f"India Post '{account_key}' account is not configured")
    cached = _INDIAPOST_TOKENS.get(account_key)
    now = datetime.now(timezone.utc).timestamp()
    if cached and cached["expires_at"] > now:
        return cached["token"]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{INDIAPOST_BASE}{INDIAPOST_PATH_LOGIN}",
            json={"username": acct["username"], "password": acct["password"]},
            headers={"Content-Type": "application/json", "accept": "application/json"})
    if r.status_code != 200:
        logging.error(f"India Post login failed ({account_key}): {r.status_code} {r.text[:300]}")
        raise HTTPException(status_code=502, detail="India Post login failed")
    data = (r.json() or {}).get("data") or {}
    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="India Post returned no access token")
    _INDIAPOST_TOKENS[account_key] = {
        "token": token,
        "expires_at": now + max(60, int(data.get("expires_in") or 900) - 60),
    }
    return token


async def _indiapost_get(path: str, params: dict, account_key: str, base: str = "") -> dict:
    token = await _indiapost_token(account_key)
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.get(f"{base or INDIAPOST_BASE}{path}", params=params,
                             headers={"Authorization": f"Bearer {token}",
                                      "accept": "application/json"})
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "body": r.text[:400]}
    try:
        return {"ok": True, "data": r.json()}
    except ValueError:
        return {"ok": False, "status": r.status_code, "body": r.text[:400]}


async def indiapost_offices(pincode: str, account_key: str = "") -> list:
    """Post offices under a pincode. Booking needs an 8-digit office_id.

    The masterdata host serves this without a token, so serviceability works
    even before the contract logins are configured. The doc says Bearer is
    required, so fall back to an authenticated call if that ever starts biting.
    """
    params = {"pincode": pincode, "limit": 50, "office-type": "post"}
    url = f"{INDIAPOST_MASTER}{INDIAPOST_PATH_OFFICES}"

    def _unwrap(data):
        return data if isinstance(data, list) else (data.get("data") or [])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, params=params, headers={"accept": "application/json"})
        if r.status_code == 200:
            return _unwrap(r.json())
    except Exception as e:
        logging.warning(f"India Post office lookup (anonymous) failed: {e}")

    key = account_key or next(
        (k for k, a in INDIAPOST_ACCOUNTS.items() if a["username"]), "")
    if not key:
        return []
    res = await _indiapost_get(INDIAPOST_PATH_OFFICES, params, key, base=INDIAPOST_MASTER)
    return _unwrap(res["data"]) if res.get("ok") else []


async def indiapost_delivery_office(pincode: str) -> Optional[dict]:
    """The office a parcel to this pincode would be delivered from.

    Doc rule: delivery_office_flag true and office_type_code not BPO.
    Serviceability is exactly "does such an office exist".
    """
    for o in await indiapost_offices(pincode):
        if o.get("delivery_office_flag") and (o.get("office_type_code") or "").upper() != "BPO":
            return o
    return None


def _indiapost_billing_weight(product: str, weight_g: int) -> int:
    """Weight India Post actually charges on.

    The tariff API answers for the exact grams asked, but the counter bills by
    slab. Verified against a real receipt: consignment CM640588294IN weighed
    1180 g Nagpur->Talcher and was charged the 2 kg rate (base 115, total 135),
    while the API quoted 1180 g at 80. Parcels therefore round up to the next
    whole kilogram; Speed Post steps per 500 g once past its 500 g document
    band. Quoting the raw weight silently under-quotes by a whole slab.
    """
    if product in ("BUSINESS_PARCEL", "PARCEL"):
        return max(1000, int(math.ceil(weight_g / 1000.0) * 1000))
    if product == "SP_INLAND_PARCEL":
        return max(500, int(math.ceil(weight_g / 500.0) * 500))
    return weight_g          # documents and letters are already slab-priced


def _indiapost_eligible(product: str, weight_g: int, dims: dict) -> Optional[str]:
    """None if the article may go by this product, else why not."""
    spec = INDIAPOST_PRODUCTS.get(product)
    if not spec:
        return "unknown product"
    if weight_g < spec["w_min"] or weight_g > spec["w_max"]:
        return f"weight outside {spec['w_min']}–{spec['w_max']} g"
    for axis, key in (("l", "length"), ("b", "breadth"), ("h", "height")):
        val = float(dims.get(key) or 0)
        if val <= 0:
            continue          # dims are optional; tariff then goes on weight alone
        lo, hi = spec[axis]
        if val < lo or val > hi:
            return f"{key} outside {lo}–{hi} cm"
    return None


async def indiapost_quote_product(account_key: str, product: str, weight_g: int,
                                  dst_pin: str, dims: dict, insurance: float = 0,
                                  pod: bool = False) -> dict:
    """One tariff call. Returns a normalised quote or an error dict."""
    spec = INDIAPOST_PRODUCTS[product]
    billed_g = _indiapost_billing_weight(product, int(weight_g))
    params = {
        "product-code": spec["code"],
        "weight": billed_g,                      # grams, whole numbers only
        "source-pincode": INDIAPOST_ORIGIN_PINCODE,
        "destination-pincode": str(dst_pin),
        "length": int(float(dims.get("length") or 0)),
        "width": int(float(dims.get("breadth") or 0)),
        "height": int(float(dims.get("height") or 0)),
    }
    if insurance and insurance > 0:
        params["INS" if spec["code"] == "SP" else "ins"] = int(insurance)
    if pod and spec["code"] == "SP":
        params["POD"] = "YES"

    res = await _indiapost_get(spec["path"], params, account_key)
    if not res.get("ok"):
        return {"ok": False, "product": product, "account": account_key,
                "error": f"HTTP {res.get('status')}", "detail": res.get("body", "")[:200]}
    d = res["data"] or {}
    if not d.get("success"):
        return {"ok": False, "product": product, "account": account_key,
                "error": d.get("message") or "tariff refused"}

    # Speed Post and Business Parcel answer with base_tariff/total_tax/final_amount;
    # Letter and Parcel use basic_charge/cgst+sgst+igst/total_amount. Normalise.
    vas = d.get("vas_charges")
    vas_total = (sum(float(v or 0) for v in vas.values()) if isinstance(vas, dict)
                 else float(vas or 0))
    for extra in ("registration_charge", "acknowledgment_charge", "insurance_charge",
                  "vpp_charge", "otp_charges", "door_delivery_charge", "cod_charge"):
        vas_total += float(d.get(extra) or 0)

    base = d.get("base_tariff")
    if base is None:
        base = d.get("basic_charge", d.get("total_before_tax", 0))
    tax = d.get("total_tax")
    if tax is None:
        tax = sum(float(d.get(k) or 0) for k in ("cgst", "sgst", "igst"))
    total = d.get("final_amount")
    if total is None:
        total = d.get("total_amount", 0)

    return {
        "ok": True,
        "account": account_key,
        "account_label": INDIAPOST_ACCOUNTS[account_key]["label"],
        "requested_product": product,
        "product": d.get("product_code") or product,
        "product_label": spec["label"],
        "service": spec["service"],
        "weight_g": int(weight_g),
        "billed_weight_g": billed_g,
        "rounded_up": billed_g > int(weight_g),
        "chargeable_weight_g": (d.get("chargeable_weight") or d.get("applicable_weight")
                                or billed_g),
        "volumetric_weight_g": d.get("volumetric_weight") or d.get("dimensional_weight"),
        "base_tariff": round(float(base or 0), 2),
        "vas_charges": round(vas_total, 2),
        "tax": round(float(tax or 0), 2),
        "total": round(float(total or 0), 2),            # GST already included
        "distance_km": d.get("distance_km"),
        "zone": d.get("zone_description") or d.get("zone"),
        "weight_slab": d.get("weight_slab"),
        "delivery_type": d.get("delivery_type"),
        "assured_delivery": d.get("assured_delivery_day"),
    }


async def indiapost_compare(weight_g: int, dst_pin: str, dims: dict,
                            insurance: float = 0, pod: bool = False) -> dict:
    """Quote every eligible product on both contracts; cheapest wins."""
    if weight_g <= 0:
        raise HTTPException(status_code=400, detail="Weight must be greater than zero")
    if weight_g > INDIAPOST_MAX_WEIGHT_G:
        return {"ok": False, "serviceable": False,
                "message": f"India Post caps articles at {INDIAPOST_MAX_WEIGHT_G/1000:g} kg"}

    office = await indiapost_delivery_office(str(dst_pin))
    if not office:
        return {"ok": False, "serviceable": False,
                "message": f"No India Post delivery office serves {dst_pin}"}

    # Tariffs are India Post's published rates, identical whichever contract
    # asks — the contract only decides who may *book* the product. So quote
    # every product once on any working login, then label each quote with the
    # contract that would carry it.
    auth_key = next((k for k, a in INDIAPOST_ACCOUNTS.items() if a["username"]), "")
    if not auth_key:
        raise HTTPException(status_code=503, detail="No India Post login is configured")

    tasks, skipped = [], []
    for product in INDIAPOST_PRODUCTS:
        why = _indiapost_eligible(product, weight_g, dims)
        if why:
            skipped.append({"product": product, "reason": why})
            continue
        tasks.append(indiapost_quote_product(auth_key, product, weight_g, dst_pin,
                                             dims, insurance, pod))

    if not tasks:
        return {"ok": False, "serviceable": True, "office": office,
                "message": "No India Post product accepts this weight/size",
                "skipped": skipped}

    results = await asyncio.gather(*tasks, return_exceptions=True)
    quotes = [r for r in results if isinstance(r, dict) and r.get("ok")]
    errors = [r for r in results if isinstance(r, dict) and not r.get("ok")]
    if not quotes:
        return {"ok": False, "serviceable": True, "office": office,
                "message": "India Post returned no usable tariff",
                "errors": errors, "skipped": skipped}

    for q in quotes:
        # The API may resolve a request to a narrower code (SP -> SP_INLAND_DOC),
        # so match a contract on either the returned or the requested product.
        book_key = next((k for k, a in INDIAPOST_ACCOUNTS.items()
                         if q["product"] in a["products"]
                         or q["requested_product"] in a["products"]), "")
        q["book_account"] = book_key
        q["book_account_label"] = INDIAPOST_ACCOUNTS[book_key]["label"] if book_key else ""
        q["bookable"] = bool(book_key and INDIAPOST_ACCOUNTS[book_key]["contract_id"]
                             and q["product"] in INDIAPOST_BOOKABLE_PRODUCTS)

    quotes.sort(key=lambda q: q["total"])
    cheapest = quotes[0]
    # The outright cheapest may be a product India Post won't let us book
    # (Letter and Parcel are quote-only), so surface the cheapest we can
    # actually dispatch as well rather than quoting a rate we cannot use.
    bookable = [q for q in quotes if q["bookable"]]
    cheapest_bookable = bookable[0] if bookable else None
    return {
        "ok": True, "serviceable": True,
        "cheapest": cheapest,
        "cheapest_bookable": cheapest_bookable,
        "quotes": quotes,
        "savings": round(quotes[-1]["total"] - cheapest["total"], 2) if len(quotes) > 1 else 0.0,
        "office": {"office_id": office.get("office_id"), "office_name": office.get("office_name"),
                   "city": office.get("city_name"), "state": office.get("state_name")},
        "errors": errors, "skipped": skipped,
    }


@api_router.get("/indiapost/status")
async def indiapost_status(user=Depends(get_current_user)):
    """Which contracts are wired up — drives the UI's setup hints."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return {
        "configured": _indiapost_configured(),
        "base_url": INDIAPOST_BASE,
        "sandbox": "test.cept.gov.in" in INDIAPOST_BASE,
        "max_weight_kg": INDIAPOST_MAX_WEIGHT_G / 1000,
        "accounts": [{
            "key": k, "label": a["label"], "products": a["products"],
            "ready": bool(a["username"] and a["password"] and a["customer_id"]
                          and a["contract_id"]),
            "can_book": bool(a["series_prefix"] and a["series_start"] and a["series_end"]),
        } for k, a in INDIAPOST_ACCOUNTS.items()],
    }


@api_router.get("/indiapost/check/{pincode}")
async def indiapost_check_pincode(pincode: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if not re.fullmatch(r"\d{6}", str(pincode or "").strip()):
        raise HTTPException(status_code=400, detail="Pincode must be 6 digits")
    office = await indiapost_delivery_office(pincode)
    return {"pincode": pincode, "serviceable": bool(office), "office": office}


class IndiaPostRateRequest(BaseModel):
    pincode: str
    weight_kg: float
    length: Optional[float] = 0
    breadth: Optional[float] = 0
    height: Optional[float] = 0
    insurance: Optional[float] = 0
    pod: Optional[bool] = False


# India Post pushes tracking events here rather than us polling. It cannot
# present a JWT, so the URL carries a secret and we pin the source address.
INDIAPOST_WEBHOOK_TOKEN = os.environ.get("INDIAPOST_WEBHOOK_TOKEN", "")
INDIAPOST_WEBHOOK_IPS = [ip.strip() for ip in
                         os.environ.get("INDIAPOST_WEBHOOK_IPS", "").split(",") if ip.strip()]

# Event codes that mean the article is physically moving, and those that end it.
INDIAPOST_BOOKED_EVENTS = {"ITEM_BOOK"}
INDIAPOST_MOVING_EVENTS = {"BAG_DISPATCH", "ITEM_DISPATCH", "BAG_OPEN",
                           "ITEM_RECEIVE", "BEAT_DISPATCH", "ITEM_INVOICE", "ITEM_TOBO"}
INDIAPOST_RETURN_EVENTS = {"ITEM_RETURN"}
INDIAPOST_DELIVERED_EVENTS = {"ITEM_DELIVERY"}


def _indiapost_event_time(payload: dict) -> str:
    """'2025-11-09' + '08:37:52' -> ISO. Falls back to now on anything odd."""
    d = str(payload.get("event_date") or "").strip()
    t = str(payload.get("event_time") or "00:00:00").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d%m%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(f"{d} {t}", fmt).replace(
                tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


@api_router.post("/indiapost/webhook/{token}")
@api_router.post("/indiapost/webhook/{token}/{stream}")
async def indiapost_webhook(token: str, request: Request, stream: str = "events"):
    """Receives India Post article events. Deliberately unauthenticated except
    for the URL secret and an optional source-IP pin — the sender is their
    server, which has no OMS credentials.

    India Post requires two separate URLs, one for booking events and one for
    everything else, so the stream is carried in the path. Both are handled
    identically here; the tag is kept only so the logs show which fired.
    """
    if stream not in ("booking", "events"):
        raise HTTPException(status_code=404, detail="Not found")
    if not INDIAPOST_WEBHOOK_TOKEN or token != INDIAPOST_WEBHOOK_TOKEN:
        raise HTTPException(status_code=404, detail="Not found")
    if INDIAPOST_WEBHOOK_IPS:
        src = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() \
              or (request.client.host if request.client else "")
        if src not in INDIAPOST_WEBHOOK_IPS:
            logging.warning(f"India Post webhook from unexpected source {src}")
            raise HTTPException(status_code=403, detail="Forbidden")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body must be JSON")
    events = payload if isinstance(payload, list) else [payload]

    accepted = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        article = str(ev.get("article_number") or "").strip().upper()
        if not article:
            continue
        code = str(ev.get("event_code") or "").strip().upper()
        at = _indiapost_event_time(ev)

        # Idempotent: India Post may resend, and duplicates must not pile up.
        await db.indiapost_events.update_one(
            {"article_number": article, "event_code": code, "event_at": at},
            {"$set": {"article_number": article, "event_code": code, "event_at": at,
                      "description": ev.get("event_description"),
                      "office": ev.get("event_office_name"), "stream": stream,
                      "raw": ev, "received_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True)
        accepted += 1

        order = await db.orders.find_one({"indiapost_shipment.barcode": article}, {"_id": 0})
        if not order:
            continue

        update = {
            "indiapost_shipment.last_event": code,
            "indiapost_shipment.last_event_desc": ev.get("event_description"),
            "indiapost_shipment.last_event_at": at,
            "indiapost_shipment.last_office": ev.get("event_office_name"),
        }
        if code in INDIAPOST_DELIVERED_EVENTS:
            update["indiapost_shipment.delivered_at"] = at
        if code in INDIAPOST_RETURN_EVENTS:
            # Same flag the courier-expenses RTO control sets, so returns show
            # up there without anyone having to notice and tick it by hand.
            update["rto"] = True
            update["issue_note"] = (order.get("issue_note")
                                    or f"Returned to sender per India Post on {at[:10]}")
            update["issue_at"] = at
            update["issue_by"] = "India Post"
        if (code in INDIAPOST_BOOKED_EVENTS or code in INDIAPOST_MOVING_EVENTS) \
                and order.get("status") not in ("dispatched", "cancelled"):
            update["status"] = "dispatched"
            update["dispatched_at"] = at
        await db.orders.update_one({"id": order["id"]}, {"$set": update})

    return {"ok": True, "accepted": accepted}


class IndiaPostCardRequest(BaseModel):
    pincodes: Optional[List[str]] = None
    weights_g: Optional[List[int]] = None


# Sensible default grid: our own city plus one destination per broad zone.
INDIAPOST_CARD_PINCODES = ["440001", "400001", "110001", "500051", "781001"]
INDIAPOST_CARD_WEIGHTS = [250, 500, 1000, 2000, 5000, 10000, 20000, 35000]


def _card_dims(weight_g: int) -> dict:
    """Representative box for each weight band, so volumetric weight is realistic."""
    if weight_g <= 1000:
        return {"length": 20, "breadth": 15, "height": 10}
    if weight_g <= 5000:
        return {"length": 30, "breadth": 25, "height": 20}
    return {"length": 45, "breadth": 35, "height": 30}


@api_router.post("/indiapost/rate-card")
async def indiapost_rate_card(req: IndiaPostCardRequest, user=Depends(get_current_user)):
    """Weight x destination grid across both contracts, cheapest marked.

    Quoted live, so it always reflects the contracted rates rather than a
    table that silently goes stale when India Post revises tariffs.
    """
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    pincodes = [p for p in (req.pincodes or INDIAPOST_CARD_PINCODES)
                if re.fullmatch(r"\d{6}", str(p).strip())][:8]
    weights = [int(w) for w in (req.weights_g or INDIAPOST_CARD_WEIGHTS)
               if 0 < int(w) <= INDIAPOST_MAX_WEIGHT_G][:12]
    if not pincodes or not weights:
        raise HTTPException(status_code=400, detail="Give at least one pincode and weight")

    offices = await asyncio.gather(*[indiapost_delivery_office(p) for p in pincodes],
                                   return_exceptions=True)
    columns = [{"pincode": p,
                "office": (o.get("office_name") if isinstance(o, dict) else None),
                "city": (o.get("city_name") if isinstance(o, dict) else None),
                "serviceable": isinstance(o, dict) and bool(o)}
               for p, o in zip(pincodes, offices)]

    # Cap concurrency: this is up to 12 x 8 x 2 upstream calls.
    sem = asyncio.Semaphore(6)

    async def cell(weight_g: int, pincode: str) -> dict:
        async with sem:
            res = await indiapost_compare(weight_g, pincode, _card_dims(weight_g))
        if not res.get("ok"):
            return {"ok": False, "reason": res.get("message")}
        by_product = {q["product_label"]: q["total"] for q in res["quotes"]}
        return {"ok": True, "cheapest": res["cheapest"]["product_label"],
                "cheapest_account": res["cheapest"]["account"],
                "total": res["cheapest"]["total"],
                "savings": res["savings"], "by_product": by_product}

    rows = []
    for w in weights:
        cells = await asyncio.gather(*[cell(w, p) for p in pincodes])
        rows.append({"weight_g": w, "cells": cells})

    return {"ok": True, "origin_pincode": INDIAPOST_ORIGIN_PINCODE,
            "columns": columns, "rows": rows,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sandbox": "test.cept.gov.in" in INDIAPOST_BASE}


@api_router.post("/indiapost/rate")
async def indiapost_rate(req: IndiaPostRateRequest, user=Depends(get_current_user)):
    """Rate calculator — both contracts quoted, cheapest returned."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if not re.fullmatch(r"\d{6}", str(req.pincode or "").strip()):
        raise HTTPException(status_code=400, detail="Pincode must be 6 digits")
    # The API only accepts whole grams; round up so we never under-quote.
    weight_g = int(math.ceil(float(req.weight_kg or 0) * 1000))
    dims = {"length": req.length, "breadth": req.breadth, "height": req.height}
    return await indiapost_compare(weight_g, req.pincode.strip(), dims,
                                   float(req.insurance or 0), bool(req.pod))


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
# pytz zone ONLY for .localize() below. Never rebind IST: a pytz zone used as
# tzinfo= gives the 1880s LMT offset (+05:53), 23 minutes off.
IST_PYTZ = pytz.timezone("Asia/Kolkata")


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
        day = IST_PYTZ.localize(datetime(y, m, d, 0, 0, 0))
    else:
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        day = IST_PYTZ.localize(datetime(now_ist.year, now_ist.month, now_ist.day, 0, 0, 0))
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
