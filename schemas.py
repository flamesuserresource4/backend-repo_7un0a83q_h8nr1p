"""
Masjid Fund Collection Schemas

Each Pydantic model here maps to a MongoDB collection (lowercase of class name).
We model a multi-tenant system supporting multiple masjids, projects, pledges,
contributions (with payment proofs), and expenses logged by accountants.

Authentication is OTP-like via mobile; default OTP is the mobile number itself
until the user changes it. Roles: super_admin (global), admin/accountant per masjid.
"""
from typing import Optional, List, Literal, Dict
from pydantic import BaseModel, Field
from datetime import datetime

Frequency = Literal["one_time", "weekly", "monthly", "yearly"]
PaymentMode = Literal["direct", "online", "gpay"]
Role = Literal["super_admin", "admin", "accountant", "member"]


class User(BaseModel):
    mobile: str = Field(..., description="Unique mobile number, also default OTP")
    name: Optional[str] = Field(None)
    otp: Optional[str] = Field(None, description="If None, defaults to mobile")
    # roles per masjid: masjid_id -> role (admin/accountant/member). super_admin via is_super_admin
    roles: Dict[str, Role] = Field(default_factory=dict)
    is_super_admin: bool = Field(False)


class Masjid(BaseModel):
    name: str
    address: Optional[str] = None
    created_by_user_id: Optional[str] = None
    support_whatsapp: Optional[str] = Field(None, description="WhatsApp support number for OTP help")


class Project(BaseModel):
    masjid_id: str
    title: str
    description: Optional[str] = None
    is_public: bool = Field(True)
    landing_slug: Optional[str] = Field(None, description="Public slug for sharing")
    # payment presentation
    gpay_url: Optional[str] = None
    gpay_upi: Optional[str] = None
    gpay_qr_image: Optional[str] = Field(None, description="QR image URL")
    # allowed frequencies to suggest on UI
    allowed_frequencies: List[Frequency] = Field(default_factory=lambda: ["one_time", "weekly", "monthly", "yearly"])


class Participant(BaseModel):
    project_id: str
    user_id: str
    pledge_amount: Optional[float] = Field(None, ge=0)
    frequency: Optional[Frequency] = None
    preferred_mode: Optional[PaymentMode] = None


class Contribution(BaseModel):
    project_id: str
    user_id: Optional[str] = None
    mobile: Optional[str] = Field(None, description="Mobile of contributor (for guest)")
    name: Optional[str] = None
    amount: float = Field(..., gt=0)
    mode: PaymentMode
    paid_at: Optional[datetime] = None
    note: Optional[str] = None
    proof_url: Optional[str] = Field(None, description="Screenshot/receipt URL if online")
    approved: bool = Field(True, description="Visible to all; could be moderated later")


class Expense(BaseModel):
    masjid_id: str
    project_id: str
    amount: float = Field(..., gt=0)
    description: str
    spent_at: Optional[datetime] = None
    added_by_user_id: Optional[str] = None
    attachment_url: Optional[str] = None

