from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import re
import uuid
import jwt
import aiofiles
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from passlib.context import CryptContext

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

# ─── GST State Codes ───
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

# ─── Pydantic Models ───
class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str  # admin, telecaller, packaging, dispatch

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    active: Optional[bool] = None

class AddressModel(BaseModel):
    address: str = ""
    city: str = ""
    state: str = ""
    pincode: str = ""

class CustomerCreate(BaseModel):
    name: str
    gst_no: Optional[str] = ""
    billing_address: AddressModel = AddressModel()
    shipping_address: AddressModel = AddressModel()
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
    show_formulation: bool = False

class OrderCreate(BaseModel):
    customer_id: str
    purpose: str = ""
    items: List[OrderItemModel]
    gst_applicable: bool = False
    shipping_method: str = ""
    courier_name: str = ""
    shipping_charge: float = 0
    shipping_gst: float = 0
    remark: str = ""

class FormulationUpdate(BaseModel):
    items: List[Dict[str, Any]]

class DispatchUpdate(BaseModel):
    courier_name: str = ""
    transporter_name: str = ""
    lr_no: str = ""

# ─── Auth Helpers ───
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

async def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def require_roles(roles: list):
    async def checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker

# ─── Startup ───
@app.on_event("startup")
async def startup():
    # Create indexes
    await db.users.create_index("username", unique=True)
    await db.customers.create_index("name")
    await db.customers.create_index("phone_numbers")
    await db.customers.create_index("gst_no")
    await db.orders.create_index("order_number")
    await db.orders.create_index("customer_id")
    await db.orders.create_index("status")
    await db.orders.create_index("created_at")
    await db.orders.create_index("telecaller_id")

    # Seed admin user
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
        logging.info("Admin user seeded: admin / admin123")

    # Init counter
    existing_counter = await db.counters.find_one({"_id": "order_number"})
    if not existing_counter:
        await db.counters.insert_one({"_id": "order_number", "seq": 0})

# ─── Auth Routes ───
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
    return {
        "id": user["id"], "username": user["username"],
        "name": user["name"], "role": user["role"]
    }

# ─── User Management (Admin) ───
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

# ─── Customer Routes ───
@api_router.post("/customers")
async def create_customer(req: CustomerCreate, user=Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        **req.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.customers.insert_one(doc)
    created = await db.customers.find_one({"id": doc["id"]}, {"_id": 0})
    return created

@api_router.get("/customers")
async def list_customers(
    search: Optional[str] = None,
    user=Depends(get_current_user)
):
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
    update_data = req.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    updated = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    return updated

# ─── Order Routes ───
@api_router.post("/orders")
async def create_order(req: OrderCreate, user=Depends(get_current_user)):
    # Generate order number
    counter = await db.counters.find_one_and_update(
        {"_id": "order_number"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    order_number = f"CS-{counter['seq']:04d}"

    # Get customer name
    customer = await db.customers.find_one({"id": req.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Calculate totals
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

    grand_total = round(subtotal + total_gst + req.shipping_charge + shipping_gst, 2)

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
        "shipping_charge": req.shipping_charge,
        "shipping_gst": shipping_gst,
        "subtotal": round(subtotal, 2),
        "total_gst": round(total_gst + shipping_gst, 2),
        "grand_total": grand_total,
        "remark": req.remark,
        "status": "new",
        "telecaller_id": user["id"],
        "telecaller_name": user["name"],
        "packaging": {
            "item_images": {},
            "order_images": [],
            "packed_box_images": [],
            "packed_by": "",
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
    user=Depends(get_current_user)
):
    query = {}
    # Role-based filtering
    if user["role"] == "telecaller":
        query["telecaller_id"] = user["id"]
    elif user["role"] == "packaging":
        query["status"] = {"$in": ["new", "packaging"]}
    elif user["role"] == "dispatch":
        query["status"] = {"$in": ["packed", "dispatched"]}

    if status:
        query["status"] = status
    if telecaller_id:
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
    return orders

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user=Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@api_router.put("/orders/{order_id}")
async def update_order(order_id: str, updates: dict, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "telecaller"]:
        raise HTTPException(status_code=403, detail="Only admin or telecaller can edit orders")
    updates.pop("id", None)
    updates.pop("order_number", None)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.orders.update_one({"id": order_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# ─── Formulation (Admin) ───
@api_router.put("/orders/{order_id}/formulation")
async def update_formulation(order_id: str, req: FormulationUpdate, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items = order["items"]
    for update_item in req.items:
        idx = update_item.get("index")
        if idx is not None and 0 <= idx < len(items):
            if "formulation" in update_item:
                items[idx]["formulation"] = update_item["formulation"]
            if "show_formulation" in update_item:
                items[idx]["show_formulation"] = update_item["show_formulation"]

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"items": items, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# ─── Packaging ───
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
    if "packed_by" in updates:
        packaging["packed_by"] = updates["packed_by"]

    new_status = updates.get("status", order["status"])
    if new_status == "packed":
        packaging["packed_at"] = datetime.now(timezone.utc).isoformat()

    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "packaging": packaging,
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# ─── Dispatch ───
@api_router.put("/orders/{order_id}/dispatch")
async def update_dispatch(order_id: str, req: DispatchUpdate, user=Depends(get_current_user)):
    if user["role"] not in ["admin", "dispatch"]:
        raise HTTPException(status_code=403, detail="Dispatch or admin only")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    dispatch = {
        "courier_name": req.courier_name,
        "transporter_name": req.transporter_name,
        "lr_no": req.lr_no,
        "dispatched_by": user["name"],
        "dispatched_at": datetime.now(timezone.utc).isoformat()
    }
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "dispatch": dispatch,
            "status": "dispatched",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated

# ─── GST Verification ───
@api_router.get("/gst-verify/{gst_no}")
async def verify_gst(gst_no: str, user=Depends(get_current_user)):
    gst_no = gst_no.upper().strip()
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$'
    if not re.match(pattern, gst_no):
        raise HTTPException(status_code=400, detail="Invalid GSTIN format")

    state_code = gst_no[:2]
    state_name = GST_STATES.get(state_code, "Unknown")

    result = {
        "gstin": gst_no,
        "valid_format": True,
        "state_code": state_code,
        "state_name": state_name,
        "pan": gst_no[2:12],
    }

    # Try external API if configured
    gst_api_key = os.environ.get("GST_API_KEY")
    if gst_api_key:
        try:
            resp = requests.get(
                f"https://sheet.gstincheck.co.in/check/{gst_api_key}/{gst_no}",
                timeout=10
            )
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

# ─── File Upload ───
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

# ─── Reports ───
@api_router.get("/reports/sales")
async def sales_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    admin=Depends(require_admin)
):
    query = {}
    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to + "T23:59:59"

    orders = await db.orders.find(query, {"_id": 0}).to_list(5000)

    # Aggregate by telecaller
    telecaller_stats = {}
    status_counts = {"new": 0, "packaging": 0, "packed": 0, "dispatched": 0}
    total_revenue = 0

    for order in orders:
        tid = order.get("telecaller_id", "unknown")
        tname = order.get("telecaller_name", "Unknown")
        if tid not in telecaller_stats:
            telecaller_stats[tid] = {"name": tname, "order_count": 0, "total_amount": 0}
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

# ─── Static + Mount ───
app.include_router(api_router)

# Mount uploads directory
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
