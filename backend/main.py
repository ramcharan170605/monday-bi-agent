import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional

from backend.config import settings
from backend.models.database import (
    Base, engine, get_db, WorkOrderModel, DealModel,
    DataQualityIssueModel, BoardSchemaModel, SyncRunModel
)
from backend.models.schemas import (
    AskRequest, AskResponse, SyncRequest, SyncResponse,
    DataQualityReport, HealthResponse
)
from backend.services.sync_service import sync_service
from backend.services.data_quality import data_quality_service
from backend.services.agent import bi_agent
from backend.services.analytics import analytics_engine
from backend.services.monday_client import monday_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("skylark_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")
    
    # Auto-seed / sync on startup if tables are empty
    with Session(engine) as db:
        wo_count = db.query(WorkOrderModel).count()
        deals_count = db.query(DealModel).count()
        if wo_count == 0 and deals_count == 0 and monday_client.is_configured():
            logger.info("Initial database is empty, performing initial sync from Monday.com...")
            try:
                await sync_service.sync_all_boards(db)
                logger.info("Initial sync completed successfully.")
            except Exception as e:
                logger.error(f"Startup initial sync error: {e}")
    yield

app = FastAPI(
    title="Skylark Drones — Monday.com Business Intelligence Agent",
    description="Founder-level Business Intelligence Agent connecting Monday.com Work Orders and Deals with Neon PostgreSQL analytical cache.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """System health check and connection status."""
    db_ok = False
    try:
        db.execute(Base.metadata.tables["work_orders"].select().limit(1))
        db_ok = True
    except Exception as e:
        logger.error(f"Health DB check failed: {e}")

    wo_count = db.query(WorkOrderModel).count() if db_ok else 0
    deals_count = db.query(DealModel).count() if db_ok else 0
    last_sync_rec = db.query(SyncRunModel).order_by(SyncRunModel.id.desc()).first() if db_ok else None

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        database_connected=db_ok,
        database_host="Neon PostgreSQL Serverless",
        monday_configured=monday_client.is_configured(),
        groq_configured=bool(settings.GROQ_API_KEY and settings.GROQ_API_KEY.strip()),
        total_work_orders=wo_count,
        total_deals=deals_count,
        last_sync=last_sync_rec.completed_at if last_sync_rec else None
    )

@app.post("/sync", response_model=SyncResponse)
async def trigger_sync(req: SyncRequest = SyncRequest(), db: Session = Depends(get_db)):
    """Triggers dynamic read from Monday.com boards, normalizes records, and updates cache."""
    try:
        result = await sync_service.sync_all_boards(db)
        return SyncResponse(**result)
    except Exception as e:
        logger.exception(f"Sync execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask", response_model=AskResponse)
async def ask_agent(req: AskRequest, db: Session = Depends(get_db)):
    """Processes founder natural language queries with structured BI tools and returns insights + caveats."""
    try:
        response = await bi_agent.answer_query(db, req.query, session_id=req.session_id or "default")
        return response
    except Exception as e:
        logger.exception(f"Agent reasoning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data-quality", response_model=DataQualityReport)
def get_data_quality(db: Session = Depends(get_db)):
    """Returns detailed data hygiene report across Monday boards."""
    report = data_quality_service.get_data_quality_summary(db)
    return DataQualityReport(**report)

@app.get("/boards/overview")
def get_boards_overview(db: Session = Depends(get_db)):
    """Returns executive metrics, schema summary, and cross-board correlations."""
    return analytics_engine.get_cross_board_overview(db)

@app.get("/data/work-orders")
def list_work_orders(
    sector: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    """Returns normalized work orders for tabular inspection."""
    q = db.query(WorkOrderModel)
    if sector and sector != "all":
        q = q.filter(WorkOrderModel.normalized_sector.ilike(f"%{sector}%"))
    if status and status != "all":
        q = q.filter(WorkOrderModel.normalized_status.ilike(f"%{status}%"))
    return q.limit(limit).all()

@app.get("/data/deals")
def list_deals(
    sector: Optional[str] = None,
    stage: Optional[str] = None,
    limit: int = 400,
    db: Session = Depends(get_db)
):
    """Returns normalized deals for tabular inspection."""
    q = db.query(DealModel)
    if sector and sector != "all":
        q = q.filter(DealModel.normalized_sector.ilike(f"%{sector}%"))
    if stage and stage != "all":
        q = q.filter(DealModel.normalized_stage.ilike(f"%{stage}%"))
    return q.limit(limit).all()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
