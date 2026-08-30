from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime

class AskRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default"

class MetricCard(BaseModel):
    label: str
    value: str
    change: Optional[str] = None
    subtext: Optional[str] = None
    sentiment: Optional[str] = "neutral"

class AskResponse(BaseModel):
    answer: str
    executive_summary: Optional[str] = None
    metrics: Optional[List[MetricCard]] = None
    data_quality_caveats: List[str] = []
    assumptions_made: List[str] = []
    recommended_actions: List[str] = []
    tools_used: List[str] = []
    raw_data_summary: Optional[Dict[str, Any]] = None

class SyncRequest(BaseModel):
    board_type: Optional[str] = "all"
    force_mock: Optional[bool] = False

class SyncResponse(BaseModel):
    status: str
    synced_boards: List[Dict[str, Any]]
    total_items_fetched: int
    total_items_normalized: int
    total_issues_found: int
    synced_at: datetime

class DataQualityItem(BaseModel):
    id: int
    board_type: str
    monday_item_id: Optional[str]
    item_name: Optional[str]
    field_name: Optional[str]
    issue_type: str
    severity: str
    details: str
    raw_value: Optional[str]

class DataQualityReport(BaseModel):
    total_issues: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    issues_by_type: Dict[str, int]
    issues_by_board: Dict[str, int]
    recent_issues: List[DataQualityItem]
    data_hygiene_score: float

class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    database_host: str
    monday_configured: bool
    groq_configured: bool
    total_work_orders: int
    total_deals: int
    last_sync: Optional[datetime]
