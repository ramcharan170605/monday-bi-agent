from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models.database import WorkOrderModel, DealModel, DataQualityIssueModel
from typing import Dict, Any, List, Optional
import pandas as pd

class AnalyticsEngine:
    @staticmethod
    def get_pipeline_metrics(db: Session, sector: Optional[str] = None) -> Dict[str, Any]:
        query = db.query(DealModel)
        if sector and sector.lower() != "all":
            query = query.filter(DealModel.normalized_sector.ilike(f"%{sector}%"))

        deals = query.all()
        if not deals:
            return {
                "total_deals": 0,
                "total_pipeline_value": 0.0,
                "weighted_pipeline_value": 0.0,
                "won_value": 0.0,
                "lost_value": 0.0,
                "win_rate_percent": 0.0,
                "stages": {},
                "sectors": {}
            }

        total_value = sum(float(d.deal_value or 0) for d in deals)
        weighted_val = sum(float(d.weighted_value or 0) for d in deals)
        
        stages: Dict[str, Dict[str, Any]] = {}
        sectors: Dict[str, Dict[str, Any]] = {}

        won_val = 0.0
        lost_val = 0.0
        won_count = 0
        lost_count = 0

        for d in deals:
            val = float(d.deal_value or 0)
            stage = d.normalized_stage or "Unknown"
            sec = d.normalized_sector or "Unassigned"

            if stage not in stages:
                stages[stage] = {"count": 0, "value": 0.0}
            stages[stage]["count"] += 1
            stages[stage]["value"] += val

            if sec not in sectors:
                sectors[sec] = {"count": 0, "value": 0.0}
            sectors[sec]["count"] += 1
            sectors[sec]["value"] += val

            if stage == "Won":
                won_val += val
                won_count += 1
            elif stage == "Lost":
                lost_val += val
                lost_count += 1

        closed_total_val = won_val + lost_val
        win_rate = round((won_val / closed_total_val * 100), 1) if closed_total_val > 0 else 0.0

        return {
            "total_deals": len(deals),
            "total_pipeline_value": round(total_value, 2),
            "weighted_pipeline_value": round(weighted_val, 2),
            "won_value": round(won_val, 2),
            "won_count": won_count,
            "lost_value": round(lost_val, 2),
            "lost_count": lost_count,
            "win_rate_percent": win_rate,
            "stages": stages,
            "sectors": sectors
        }

    @staticmethod
    def get_operations_metrics(db: Session, sector: Optional[str] = None) -> Dict[str, Any]:
        query = db.query(WorkOrderModel)
        if sector and sector.lower() != "all":
            query = query.filter(WorkOrderModel.normalized_sector.ilike(f"%{sector}%"))

        orders = query.all()
        if not orders:
            return {
                "total_work_orders": 0,
                "total_contract_value": 0.0,
                "total_actual_cost": 0.0,
                "gross_margin_percent": 0.0,
                "completion_rate_percent": 0.0,
                "statuses": {},
                "delayed_count": 0,
                "in_progress_count": 0,
                "completed_count": 0
            }

        total_contract = sum(float(w.contract_value or 0) for w in orders if (w.contract_value or 0) > 0)
        total_cost = sum(float(w.actual_cost or 0) for w in orders if (w.actual_cost or 0) > 0)
        
        statuses: Dict[str, Dict[str, Any]] = {}
        sectors: Dict[str, Dict[str, Any]] = {}
        completed_count = 0
        delayed_count = 0
        in_progress_count = 0
        scheduled_count = 0

        for w in orders:
            c_val = float(w.contract_value or 0)
            status = w.normalized_status or "Unknown"
            sec = w.normalized_sector or "Unassigned"

            if status not in statuses:
                statuses[status] = {"count": 0, "contract_value": 0.0}
            statuses[status]["count"] += 1
            statuses[status]["contract_value"] += max(0.0, c_val)

            if sec not in sectors:
                sectors[sec] = {"count": 0, "contract_value": 0.0}
            sectors[sec]["count"] += 1
            sectors[sec]["contract_value"] += max(0.0, c_val)

            if status == "Completed":
                completed_count += 1
            elif status == "Delayed":
                delayed_count += 1
            elif status == "In Progress":
                in_progress_count += 1
            elif status == "Scheduled":
                scheduled_count += 1

        active_or_done = completed_count + in_progress_count + delayed_count + scheduled_count
        comp_rate = round((completed_count / active_or_done * 100), 1) if active_or_done > 0 else 0.0
        
        gross_profit = total_contract - total_cost
        gross_margin = round((gross_profit / total_contract * 100), 1) if total_contract > 0 else 0.0

        return {
            "total_work_orders": len(orders),
            "total_contract_value": round(total_contract, 2),
            "total_actual_cost": round(total_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_percent": gross_margin,
            "completion_rate_percent": comp_rate,
            "completed_count": completed_count,
            "delayed_count": delayed_count,
            "in_progress_count": in_progress_count,
            "scheduled_count": scheduled_count,
            "statuses": statuses,
            "sectors": sectors
        }

    @staticmethod
    def get_cross_board_overview(db: Session) -> Dict[str, Any]:
        pipeline = AnalyticsEngine.get_pipeline_metrics(db)
        ops = AnalyticsEngine.get_operations_metrics(db)

        deals = db.query(DealModel).all()
        wos = db.query(WorkOrderModel).all()

        deal_clients = {d.normalized_client for d in deals if d.normalized_client}
        wo_clients = {w.normalized_client for w in wos if w.normalized_client}

        matched_clients = deal_clients.intersection(wo_clients)
        deals_without_wo = deal_clients - wo_clients

        return {
            "pipeline": pipeline,
            "operations": ops,
            "matched_client_count": len(matched_clients),
            "unmatched_client_count": len(deals_without_wo),
            "top_clients": list(matched_clients)
        }

analytics_engine = AnalyticsEngine()
