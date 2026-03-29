https://github.com/alyfd/delivery-tracker-backend
2. احذف ملف server.py:

اضغط على ملف server.py
اضغط على أيقونة القلم المنقط (···) فوق يمين
اختر "Delete file"
اضغط "Commit changes"
3. أنشئ server.py من جديد:

اضغط "Add file" → "Create new file"
اسم الملف: server.py
4. انسخ هذا الكود بس (بدون أي شي ثاني!):

ابدأ النسخ من السطر التالي:

from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

load_dotenv()

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'delivery_tracker')]

app = FastAPI()
api_router = APIRouter(prefix="/api")

class Store(BaseModel):
    name: str
    amount: float

class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = ""
    stores: List[Store]
    notes: Optional[str] = ""
    paid: bool = False

class OrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    stores: Optional[List[Store]] = None
    notes: Optional[str] = None
    paid: Optional[bool] = None

class Order(BaseModel):
    id: str
    customer_name: str
    customer_phone: Optional[str] = ""
    stores: List[Store]
    total: float
    paid: bool
    notes: Optional[str] = ""
    created_at: str
    updated_at: str

def order_helper(order) -> dict:
    return {
        "id": str(order["_id"]),
        "customer_name": order["customer_name"],
        "customer_phone": order.get("customer_phone", ""),
        "stores": order["stores"],
        "total": order["total"],
        "paid": order.get("paid", False),
        "notes": order.get("notes", ""),
        "created_at": order["created_at"],
        "updated_at": order["updated_at"]
    }

@api_router.get("/")
async def root():
    return {"message": "Delivery Tracker API"}

@api_router.post("/orders", response_model=Order)
async def create_order(order: OrderCreate):
    total = sum(store.amount for store in order.stores)
    order_dict = {
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "stores": [store.dict() for store in order.stores],
        "total": total,
        "paid": order.paid,
        "notes": order.notes,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    result = await db.orders.insert_one(order_dict)
    new_order = await db.orders.find_one({"_id": result.inserted_id})
    return order_helper(new_order)

@api_router.get("/orders", response_model=List[Order])
async def get_orders(search: Optional[str] = None):
    query = {}
    if search:
        query = {
            "$or": [
                {"customer_name": {"$regex": search, "$options": "i"}},
                {"customer_phone": {"$regex": search, "$options": "i"}}
            ]
        }
    orders = await db.orders.find(query).sort("created_at", -1).to_list(1000)
    return [order_helper(order) for order in orders]

@api_router.get("/orders/stats")
async def get_orders_stats():
    pipeline = [
        {"$match": {"paid": False}},
        {"$group": {"_id": None, "total_pending": {"$sum": "$total"}}}
    ]
    result = await db.orders.aggregate(pipeline).to_list(1)
    total_pending = result[0]["total_pending"] if result else 0
    return {"total_pending": total_pending}

@api_router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    try:
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order_helper(order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.put("/orders/{order_id}", response_model=Order)
async def update_order(order_id: str, order_update: OrderUpdate):
    try:
        existing_order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not existing_order:
            raise HTTPException(status_code=404, detail="Order not found")
        update_dict = {"updated_at": datetime.utcnow().isoformat()}
        if order_update.customer_name is not None:
            update_dict["customer_name"] = order_update.customer_name
        if order_update.customer_phone is not None:
            update_dict["customer_phone"] = order_update.customer_phone
        if order_update.stores is not None:
            update_dict["stores"] = [store.dict() for store in order_update.stores]
            update_dict["total"] = sum(store.amount for store in order_update.stores)
        if order_update.notes is not None:
            update_dict["notes"] = order_update.notes
        if order_update.paid is not None:
            update_dict["paid"] = order_update.paid
        await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": update_dict})
        updated_order = await db.orders.find_one({"_id": ObjectId(order_id)})
        return order_helper(updated_order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.delete("/orders/{order_id}")
async def delete_order(order_id: str):
    try:
        result = await db.orders.delete_one({"_id": ObjectId(order_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        return {"message": "Order deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.patch("/orders/{order_id}/payment")
async def toggle_payment(order_id: str):
    try:
        order = await db.orders.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        new_paid_status = not order.get("paid", False)
        await db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"paid": new_paid_status, "updated_at": datetime.utcnow().isoformat()}})
        updated_order = await db.orders.find_one({"_id": ObjectId(order_id)})
        return order_helper(updated_order)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
