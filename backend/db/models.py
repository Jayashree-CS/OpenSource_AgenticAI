# db/models.py

from datetime import datetime, timezone, date

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Date,
)

from db.database import Base


# =========================================================
# EMPLOYEE MODEL
# =========================================================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    role = Column(String, nullable=False, default="employee")
    department = Column(String, nullable=True)

    manager_id = Column(Integer, nullable=True)

    password_hash = Column(String, nullable=False)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


# =========================================================
# TICKET MODEL
# =========================================================

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, nullable=False)

    issue_type = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    priority = Column(String, nullable=False, default="medium")
    status = Column(String, nullable=False, default="open")

    assigned_engineer = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


# =========================================================
# SYSTEM LOG MODEL
# =========================================================

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, nullable=True)
    user_email = Column(String, nullable=True)
    user_role = Column(String, nullable=True)

    agent = Column(String, nullable=True)
    action = Column(String, nullable=True)
    tool_used = Column(String, nullable=True)

    status = Column(String, nullable=True)

    message = Column(Text, nullable=True)
    response = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


# =========================================================
# LEAVE REQUEST MODEL
# =========================================================

class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer, nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    reason = Column(String, nullable=True)

    status = Column(
        String,
        nullable=False,
        default="pending"
    )

    leave_type = Column(
        String,
        nullable=False,
        default="casual"
    )

    total_days = Column(Integer, nullable=False, default=1)

    manager_email = Column(String, nullable=True)


# =========================================================
# LEAVE BALANCE MODEL
# =========================================================

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True
    )

    sick_total = Column(Integer, nullable=False, default=6)
    sick_used = Column(Integer, nullable=False, default=0)

    casual_total = Column(Integer, nullable=False, default=6)
    casual_used = Column(Integer, nullable=False, default=0)

    earned_total = Column(Integer, nullable=False, default=12)
    earned_used = Column(Integer, nullable=False, default=0)


# =========================================================
# INVENTORY MODEL
# =========================================================

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)

    asset_type = Column(String, unique=True, nullable=False)

    total_quantity = Column(Integer, default=0)
    available_quantity = Column(Integer, default=0)

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


# =========================================================
# HOLIDAY MODEL
# =========================================================

class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)

    holiday_date = Column(
        Date,
        unique=True,
        nullable=False,
        index=True
    )

    name = Column(String(255), nullable=False)

    holiday_type = Column(
        String(50),
        nullable=False,
        default="company"
    )


# =========================================================
# ASSET REQUEST MODEL
# =========================================================

class AssetRequest(Base):
    __tablename__ = "asset_requests"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, nullable=False)

    asset_type = Column(String, nullable=False)

    reason = Column(String, nullable=True)

    manager_status = Column(
        String,
        nullable=False,
        default="pending"
    )

    it_status = Column(
        String,
        nullable=False,
        default="pending"
    )

    inventory_status = Column(
        String,
        nullable=False,
        default="pending"
    )

    final_status = Column(
        String,
        nullable=False,
        default="pending"
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


# =========================================================
# NOTIFICATION LOG MODEL
# =========================================================

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)

    channel = Column(String, nullable=False)            # hr | it | asset
    event_type = Column(String, nullable=False)         # leave_applied, ticket_created, ...
    target_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending | success | failed

    payload = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


# =========================================================
# PYDANTIC SCHEMAS
# =========================================================

class LeaveCreate(BaseModel):
    employee_id: int
    start_date: date
    end_date: date

    reason: str | None = None

    leave_type: str = "casual"


class LeaveResponse(BaseModel):
    id: int

    employee_id: int

    start_date: date
    end_date: date

    reason: str | None

    status: str
    leave_type: str

    total_days: int

    class Config:
        from_attributes = True