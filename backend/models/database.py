from sqlalchemy import create_engine, Column, Integer, String, Text, Numeric, Date, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=60,
    connect_args={"sslmode": "require", "connect_timeout": 15}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class BoardSchemaModel(Base):
    __tablename__ = "board_schemas"
    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(String(100), nullable=False)
    board_type = Column(String(50), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    columns_json = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class RawMondayItemModel(Base):
    __tablename__ = "raw_monday_items"
    id = Column(Integer, primary_key=True, index=True)
    board_type = Column(String(50), nullable=False)
    monday_item_id = Column(String(100), nullable=False)
    item_name = Column(String(500))
    raw_json = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("board_type", "monday_item_id", name="uq_raw_board_item"),)

class WorkOrderModel(Base):
    __tablename__ = "work_orders"
    id = Column(Integer, primary_key=True, index=True)
    monday_item_id = Column(String(100), unique=True, index=True)
    work_order_no = Column(String(100))
    client_name = Column(String(255))
    normalized_client = Column(String(255), index=True)
    project_name = Column(String(255))
    sector = Column(String(100))
    normalized_sector = Column(String(100), index=True)
    status = Column(String(100))
    normalized_status = Column(String(100), index=True)
    start_date = Column(Date)
    due_date = Column(Date)
    completed_date = Column(Date)
    contract_value = Column(Numeric(15, 2))
    actual_cost = Column(Numeric(15, 2))
    currency = Column(String(10), default="USD")
    assigned_pilot_or_lead = Column(String(255))
    location = Column(String(255))
    data_quality_flags = Column(JSONB, default=list)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class DealModel(Base):
    __tablename__ = "deals"
    id = Column(Integer, primary_key=True, index=True)
    monday_item_id = Column(String(100), unique=True, index=True)
    deal_name = Column(String(255))
    client_name = Column(String(255))
    normalized_client = Column(String(255), index=True)
    sector = Column(String(100))
    normalized_sector = Column(String(100), index=True)
    deal_stage = Column(String(100))
    normalized_stage = Column(String(100), index=True)
    deal_value = Column(Numeric(15, 2))
    probability = Column(Numeric(5, 2))
    weighted_value = Column(Numeric(15, 2))
    expected_close_date = Column(Date)
    actual_close_date = Column(Date)
    deal_owner = Column(String(255))
    currency = Column(String(10), default="USD")
    data_quality_flags = Column(JSONB, default=list)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class DataQualityIssueModel(Base):
    __tablename__ = "data_quality_issues"
    id = Column(Integer, primary_key=True, index=True)
    board_type = Column(String(50), nullable=False, index=True)
    monday_item_id = Column(String(100))
    item_name = Column(String(500))
    field_name = Column(String(100))
    issue_type = Column(String(100))
    severity = Column(String(20))
    details = Column(Text)
    raw_value = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SyncRunModel(Base):
    __tablename__ = "sync_runs"
    id = Column(Integer, primary_key=True, index=True)
    board_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    items_fetched = Column(Integer, default=0)
    items_normalized = Column(Integer, default=0)
    issues_found = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
