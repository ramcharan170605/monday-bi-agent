from sqlalchemy.orm import Session
from backend.models.database import WorkOrderModel, DealModel, DataQualityIssueModel
from typing import Dict, Any, List

class DataQualityService:
    @staticmethod
    def get_data_quality_summary(db: Session) -> Dict[str, Any]:
        issues = db.query(DataQualityIssueModel).all()
        total_wo = db.query(WorkOrderModel).count()
        total_deals = db.query(DealModel).count()
        total_records = total_wo + total_deals

        high = sum(1 for i in issues if i.severity == "HIGH")
        medium = sum(1 for i in issues if i.severity == "MEDIUM")
        low = sum(1 for i in issues if i.severity == "LOW")

        if total_records == 0:
            score = 100.0
        else:
            penalty = (high * 15.0 + medium * 5.0 + low * 2.0) / total_records
            score = max(0.0, round(100.0 - penalty, 1))

        by_type: Dict[str, int] = {}
        for i in issues:
            by_type[i.issue_type] = by_type.get(i.issue_type, 0) + 1

        by_board: Dict[str, int] = {}
        for i in issues:
            by_board[i.board_type] = by_board.get(i.board_type, 0) + 1

        recent = [
            {
                "id": i.id,
                "board_type": i.board_type,
                "monday_item_id": i.monday_item_id,
                "item_name": i.item_name,
                "field_name": i.field_name,
                "issue_type": i.issue_type,
                "severity": i.severity,
                "details": i.details,
                "raw_value": i.raw_value
            }
            for i in issues[:25]
        ]

        return {
            "total_issues": len(issues),
            "high_severity_count": high,
            "medium_severity_count": medium,
            "low_severity_count": low,
            "issues_by_type": by_type,
            "issues_by_board": by_board,
            "data_hygiene_score": score,
            "total_work_orders": total_wo,
            "total_deals": total_deals,
            "recent_issues": recent
        }

    @staticmethod
    def generate_contextual_caveats(db: Session, sector: str = None) -> List[str]:
        caveats = []
        issues_query = db.query(DataQualityIssueModel)
        if sector and sector != "all":
            issues = issues_query.filter(DataQualityIssueModel.details.ilike(f"%{sector}%")).all()
        else:
            issues = issues_query.all()

        high_issues = [i for i in issues if i.severity == "HIGH"]
        if high_issues:
            caveats.append(f"⚠️ {len(high_issues)} high-severity data quality issues detected (e.g. invalid financial values or missing client identities).")

        null_dates = [i for i in issues if i.issue_type in ["MISSING_DATE", "INVALID_DATE"]]
        if null_dates:
            caveats.append(f"📅 {len(null_dates)} records have missing or unparseable target dates; timeline projections are conservative estimates.")

        unassigned_pilots = db.query(WorkOrderModel).filter(
            (WorkOrderModel.assigned_pilot_or_lead.is_(None)) | 
            (WorkOrderModel.assigned_pilot_or_lead.ilike("%unassigned%"))
        ).count()
        if unassigned_pilots > 0:
            caveats.append(f"🚁 {unassigned_pilots} active/delayed work orders currently have unassigned pilots or pilot shortages.")

        deals_won = db.query(DealModel).filter(DealModel.normalized_stage == "Won").all()
        wo_clients = {w.normalized_client for w in db.query(WorkOrderModel).all() if w.normalized_client}
        unmatched_won = [d for d in deals_won if d.normalized_client not in wo_clients]
        if unmatched_won:
            caveats.append(f"🔄 Cross-board caveat: {len(unmatched_won)} 'Won' deal(s) (e.g. {unmatched_won[0].deal_name}) do not yet have a matching operational Work Order.")

        if not caveats:
            caveats.append("✅ Data hygiene is high across active boards with no blocking anomalies.")

        return caveats

data_quality_service = DataQualityService()
