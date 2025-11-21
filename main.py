import os
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, Masjid, Project, Participant, Contribution, Expense

app = FastAPI(title="Masjid Fund Collection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helpers
class Obj(BaseModel):
    id: str

def oid(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def collection(name: str):
    return db[name]


@app.get("/")
def root():
    return {"message": "Masjid Fund Collection API Running"}


@app.get("/test")
def test_database():
    try:
        collections = db.list_collection_names()
        return {
            "backend": "✅ Running",
            "database": "✅ Connected & Working",
            "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
            "database_name": db.name,
            "connection_status": "Connected",
            "collections": collections,
        }
    except Exception as e:
        return {
            "backend": "✅ Running",
            "database": f"❌ Error: {str(e)[:80]}",
            "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
            "database_name": os.getenv("DATABASE_NAME"),
            "connection_status": "Error",
            "collections": [],
        }


# Auth: mobile + OTP (default = mobile)
class LoginRequest(BaseModel):
    mobile: str
    otp: str


@app.post("/auth/login")
def login(req: LoginRequest):
    u = collection("user").find_one({"mobile": req.mobile})
    if not u:
        # auto create user with default otp=mobile
        user = User(mobile=req.mobile, otp=req.mobile)
        uid = create_document("user", user)
        u = collection("user").find_one({"_id": ObjectId(uid)})
    otp = u.get("otp") or u.get("mobile")
    if req.otp != otp:
        raise HTTPException(status_code=401, detail="Invalid OTP")
    u["id"] = str(u.pop("_id"))
    return {"user": u}


class UpdateOtpRequest(BaseModel):
    new_otp: str


@app.post("/auth/update-otp/{user_id}")
def update_otp(user_id: str, body: UpdateOtpRequest):
    res = collection("user").update_one({"_id": oid(user_id)}, {"$set": {"otp": body.new_otp}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# Masjid management
class CreateMasjid(BaseModel):
    name: str
    address: Optional[str] = None
    support_whatsapp: Optional[str] = None
    owner_user_id: str


@app.post("/masjids")
def create_masjid(body: CreateMasjid):
    masjid = Masjid(
        name=body.name,
        address=body.address,
        created_by_user_id=body.owner_user_id,
        support_whatsapp=body.support_whatsapp,
    )
    mid = create_document("masjid", masjid)
    # grant admin role
    collection("user").update_one(
        {"_id": oid(body.owner_user_id)},
        {"$set": {f"roles.{mid}": "admin"}},
    )
    return {"id": mid}


@app.get("/masjids")
def list_masjids():
    items = []
    for m in collection("masjid").find().sort("created_at", -1):
        m["id"] = str(m.pop("_id"))
        items.append(m)
    return {"items": items}


# Projects
class CreateProject(BaseModel):
    masjid_id: str
    title: str
    description: Optional[str] = None
    is_public: bool = True
    landing_slug: Optional[str] = None
    gpay_url: Optional[str] = None
    gpay_upi: Optional[str] = None
    gpay_qr_image: Optional[str] = None
    allowed_frequencies: Optional[List[str]] = None


@app.post("/projects")
def create_project(body: CreateProject):
    project = Project(**body.model_dump())
    pid = create_document("project", project)
    return {"id": pid}


@app.get("/projects/{masjid_id}")
def list_projects(masjid_id: str):
    items = []
    for p in collection("project").find({"masjid_id": masjid_id}).sort("created_at", -1):
        p["id"] = str(p.pop("_id"))
        items.append(p)
    return {"items": items}


# Join project (pledge)
class JoinProject(BaseModel):
    project_id: str
    user_id: str
    pledge_amount: Optional[float] = None
    frequency: Optional[str] = None
    preferred_mode: Optional[str] = None


@app.post("/projects/join")
def join_project(body: JoinProject):
    # upsert participant
    collection("participant").update_one(
        {"project_id": body.project_id, "user_id": body.user_id},
        {"$set": body.model_dump()},
        upsert=True,
    )
    return {"ok": True}


@app.get("/projects/{project_id}/participants")
def list_participants(project_id: str):
    items = []
    for r in collection("participant").find({"project_id": project_id}):
        r["id"] = str(r.pop("_id"))
        items.append(r)
    return {"items": items}


# Contributions
class AddContribution(BaseModel):
    project_id: str
    user_id: Optional[str] = None
    mobile: Optional[str] = None
    name: Optional[str] = None
    amount: float
    mode: str
    note: Optional[str] = None
    proof_url: Optional[str] = None
    paid_at: Optional[datetime] = None


@app.post("/contributions")
def add_contribution(body: AddContribution):
    c = Contribution(**body.model_dump())
    cid = create_document("contribution", c)
    return {"id": cid}


@app.get("/projects/{project_id}/contributions")
def list_contributions(project_id: str):
    items = []
    total = 0.0
    for r in collection("contribution").find({"project_id": project_id, "approved": True}).sort("created_at", -1):
        r["id"] = str(r.pop("_id"))
        total += float(r.get("amount", 0))
        items.append(r)
    return {"items": items, "total": total}


# Expenses (by accountant)
class AddExpense(BaseModel):
    masjid_id: str
    project_id: str
    amount: float
    description: str
    spent_at: Optional[datetime] = None
    added_by_user_id: Optional[str] = None
    attachment_url: Optional[str] = None


@app.post("/expenses")
def add_expense(body: AddExpense):
    e = Expense(**body.model_dump())
    eid = create_document("expense", e)
    return {"id": eid}


@app.get("/projects/{project_id}/expenses")
def list_expenses(project_id: str):
    items = []
    total = 0.0
    for r in collection("expense").find({"project_id": project_id}).sort("created_at", -1):
        r["id"] = str(r.pop("_id"))
        total += float(r.get("amount", 0))
        items.append(r)
    return {"items": items, "total": total}


# Aggregated transparency per project
@app.get("/projects/{project_id}/ledger")
def project_ledger(project_id: str):
    contrib_total = 0.0
    expense_total = 0.0
    for c in collection("contribution").find({"project_id": project_id, "approved": True}):
        contrib_total += float(c.get("amount", 0))
    for e in collection("expense").find({"project_id": project_id}):
        expense_total += float(e.get("amount", 0))
    balance = contrib_total - expense_total
    return {
        "contributed": contrib_total,
        "spent": expense_total,
        "balance": balance,
    }


# Public landing: show project, contributions (names/amounts), totals
@app.get("/public/projects/{landing_slug}")
def public_project(landing_slug: str):
    p = collection("project").find_one({"landing_slug": landing_slug, "is_public": True})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p["id"] = str(p.pop("_id"))
    # last 50 contributions
    contribs = []
    total = 0.0
    for c in collection("contribution").find({"project_id": p["id"], "approved": True}).sort("created_at", -1).limit(50):
        c["id"] = str(c.pop("_id"))
        total += float(c.get("amount", 0))
        contribs.append({"name": c.get("name") or c.get("mobile", "Guest"), "amount": c.get("amount"), "paid_at": c.get("paid_at") or c.get("created_at")})
    ledger = app.router.routes  # dummy to avoid lint warning
    return {
        "project": p,
        "recent_contributions": contribs,
        "total": total,
    }


# Admin dashboards
@app.get("/admin/{masjid_id}/summary")
def masjid_summary(masjid_id: str):
    # totals per masjid across projects
    projects = list(collection("project").find({"masjid_id": masjid_id}))
    pids = [str(p["_id"]) for p in projects]
    contrib_total = 0.0
    expense_total = 0.0
    for pid in pids:
        for c in collection("contribution").find({"project_id": pid, "approved": True}):
            contrib_total += float(c.get("amount", 0))
        for e in collection("expense").find({"project_id": pid}):
            expense_total += float(e.get("amount", 0))
    return {
        "projects": len(projects),
        "contributed": contrib_total,
        "spent": expense_total,
        "balance": contrib_total - expense_total,
    }


@app.get("/super/summary")
def super_summary():
    # across all masjids
    contrib_total = 0.0
    expense_total = 0.0
    for c in collection("contribution").find({"approved": True}):
        contrib_total += float(c.get("amount", 0))
    for e in collection("expense").find({}):
        expense_total += float(e.get("amount", 0))
    masjids = collection("masjid").count_documents({})
    projects = collection("project").count_documents({})
    return {
        "masjids": masjids,
        "projects": projects,
        "contributed": contrib_total,
        "spent": expense_total,
        "balance": contrib_total - expense_total,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
