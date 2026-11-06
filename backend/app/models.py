import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, Text, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())

class Profile(Base):
    __tablename__ = 'profiles'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # Supabase auth user UUID
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default='analyst')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Customer(Base):
    __tablename__ = 'customers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    segment: Mapped[str] = mapped_column(String(30), default='PERSONA')
    region: Mapped[str] = mapped_column(String(80), default='PERU')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    currency: Mapped[str] = mapped_column(String(3), default='PEN')
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE')

class Transaction(Base):
    __tablename__ = 'transactions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    source_account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    destination_account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default='PEN')
    channel: Mapped[str] = mapped_column(String(30), default='TRANSFER')
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(12), default='LOW')
    flags: Mapped[list] = mapped_column(JSON, default=list)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    transaction_id: Mapped[str] = mapped_column(ForeignKey('transactions.id'), unique=True)
    severity: Mapped[str] = mapped_column(String(12))
    score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default='OPEN', index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Case(Base):
    __tablename__ = 'cases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    alert_id: Mapped[str] = mapped_column(ForeignKey('alerts.id'), unique=True)
    title: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(24), default='OPEN')
    priority: Mapped[str] = mapped_column(String(12), default='HIGH')
    owner_id: Mapped[str] = mapped_column(String(36))
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class CaseNote(Base):
    __tablename__ = 'case_notes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'), index=True)
    author_id: Mapped[str] = mapped_column(String(36))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

Index('ix_transaction_source_time', Transaction.source_account_id, Transaction.occurred_at)
