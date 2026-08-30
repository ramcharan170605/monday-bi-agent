import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import (
    BoardSchemaModel, RawMondayItemModel, WorkOrderModel, DealModel,
    DataQualityIssueModel, SyncRunModel
)
from backend.services.monday_client import monday_client
from backend.services.normalizer import normalizer

logger = logging.getLogger(__name__)

class SyncService:
    async def sync_all_boards(self, db: Session, force_mock: bool = False) -> Dict[str, Any]:
        wo_result = await self.sync_board(db, "work_orders", settings.WORK_ORDERS_BOARD_ID, force_mock)
        deals_result = await self.sync_board(db, "deals", settings.DEALS_BOARD_ID, force_mock)

        return {
            "status": "SUCCESS" if wo_result["status"] == "SUCCESS" and deals_result["status"] == "SUCCESS" else "PARTIAL",
            "synced_boards": [wo_result, deals_result],
            "total_items_fetched": wo_result["items_fetched"] + deals_result["items_fetched"],
            "total_items_normalized": wo_result["items_normalized"] + deals_result["items_normalized"],
            "total_issues_found": wo_result["issues_found"] + deals_result["issues_found"],
            "synced_at": datetime.now(timezone.utc)
        }

    async def sync_board(self, db: Session, board_type: str, board_id: str, force_mock: bool = False) -> Dict[str, Any]:
        sync_run = SyncRunModel(
            board_type=board_type,
            status="IN_PROGRESS",
            started_at=datetime.now(timezone.utc)
        )
        db.add(sync_run)
        db.flush()

        try:
            schema_data = await monday_client.get_board_schema(board_id or board_type)
            existing_schema = db.query(BoardSchemaModel).filter(BoardSchemaModel.board_type == board_type).first()
            if existing_schema:
                existing_schema.board_id = str(schema_data.get("id", board_id))
                existing_schema.title = schema_data.get("name", board_type)
                existing_schema.columns_json = schema_data.get("columns", [])
                existing_schema.updated_at = datetime.now(timezone.utc)
            else:
                new_schema = BoardSchemaModel(
                    board_id=str(schema_data.get("id", board_id or board_type)),
                    board_type=board_type,
                    title=schema_data.get("name", board_type),
                    columns_json=schema_data.get("columns", [])
                )
                db.add(new_schema)

            raw_items = await monday_client.fetch_board_items(board_id or board_type)
            sync_run.items_fetched = len(raw_items)

            db.query(DataQualityIssueModel).filter(DataQualityIssueModel.board_type == board_type).delete()
            db.query(RawMondayItemModel).filter(RawMondayItemModel.board_type == board_type).delete()
            if board_type == "deals":
                db.query(DealModel).delete()
            else:
                db.query(WorkOrderModel).delete()
            db.flush()

            normalized_count = 0
            issues_count = 0

            for item in raw_items:
                item_id = str(item.get("id"))
                item_name = item.get("name", "")

                db.add(RawMondayItemModel(
                    board_type=board_type,
                    monday_item_id=item_id,
                    item_name=item_name,
                    raw_json=item,
                    fetched_at=datetime.now(timezone.utc)
                ))

                col_text = {c.get("id"): c.get("text") for c in item.get("column_values", [])}
                item_issues = []

                if board_type == "deals":
                    client_val = self._find_val(col_text, ["client", "customer", "account", "company", "text"])
                    sector_val = self._find_val(col_text, ["sector", "industry", "status", "category"])
                    stage_val = self._find_val(col_text, ["stage", "deal_stage", "phase", "status_1"])
                    deal_val = self._find_val(col_text, ["value", "deal_value", "amount", "numbers"])
                    prob_val = self._find_val(col_text, ["prob", "probability", "win_rate", "numbers_1"])
                    exp_close_val = self._find_val(col_text, ["exp_close", "expected_close", "date", "close_date"])
                    act_close_val = self._find_val(col_text, ["act_close", "actual_close", "date_1"])
                    owner_val = self._find_val(col_text, ["owner", "deal_owner", "person", "people"])

                    client_disp, client_key, c_flag = normalizer.normalize_client_name(client_val or item_name)
                    if c_flag:
                        item_issues.append({"field": "client", "type": "MISSING_CLIENT", "severity": "MEDIUM", "msg": c_flag, "raw": client_val})

                    sec_disp, sec_flag = normalizer.normalize_sector(sector_val)
                    if sec_flag:
                        item_issues.append({"field": "sector", "type": sec_flag, "severity": "LOW", "msg": f"Sector issue: {sec_flag}", "raw": sector_val})

                    stg_disp, stg_flag = normalizer.normalize_deal_stage(stage_val)
                    if stg_flag:
                        item_issues.append({"field": "stage", "type": stg_flag, "severity": "MEDIUM", "msg": f"Stage issue: {stg_flag}", "raw": stage_val})

                    val_num, val_flag = normalizer.parse_amount(deal_val)
                    if val_flag:
                        sev = "HIGH" if "NEGATIVE" in val_flag or "INVALID" in val_flag else "MEDIUM"
                        item_issues.append({"field": "deal_value", "type": "INVALID_AMOUNT", "severity": sev, "msg": val_flag, "raw": str(deal_val)})

                    prob_num, _ = normalizer.parse_amount(prob_val)
                    if prob_num is None:
                        prob_num = 100.0 if stg_disp == "Won" else (0.0 if stg_disp == "Lost" else 50.0)

                    weighted_num = round((val_num or 0.0) * (prob_num / 100.0), 2) if val_num is not None else 0.0

                    exp_dt, dt_flag = normalizer.parse_date(exp_close_val)
                    if dt_flag and stg_disp not in ["Won", "Lost"]:
                        item_issues.append({"field": "expected_close_date", "type": "MISSING_DATE", "severity": "MEDIUM", "msg": dt_flag, "raw": str(exp_close_val)})

                    act_dt, _ = normalizer.parse_date(act_close_val)

                    db.add(DealModel(
                        monday_item_id=item_id,
                        deal_name=item_name,
                        client_name=client_disp,
                        normalized_client=client_key,
                        sector=sector_val,
                        normalized_sector=sec_disp,
                        deal_stage=stage_val,
                        normalized_stage=stg_disp,
                        deal_value=val_num,
                        probability=prob_num,
                        weighted_value=weighted_num,
                        expected_close_date=exp_dt,
                        actual_close_date=act_dt,
                        deal_owner=owner_val,
                        data_quality_flags=item_issues
                    ))

                else:
                    client_val = self._find_val(col_text, ["client", "customer", "enterprise", "text"])
                    project_val = self._find_val(col_text, ["project", "project_name", "title", "text_1"])
                    sector_val = self._find_val(col_text, ["sector", "industry", "status", "category"])
                    status_val = self._find_val(col_text, ["status", "execution_status", "state", "status_1"])
                    start_dt_val = self._find_val(col_text, ["start_date", "flight_date", "date"])
                    due_dt_val = self._find_val(col_text, ["due_date", "target_date", "date_1", "delivery_date"])
                    comp_dt_val = self._find_val(col_text, ["comp_date", "completed_date", "date_2"])
                    val_num_val = self._find_val(col_text, ["contract_val", "contract_value", "amount", "numbers"])
                    cost_val = self._find_val(col_text, ["actual_cost", "flight_cost", "cost", "numbers_1"])
                    pilot_val = self._find_val(col_text, ["pilot", "flight_lead", "lead", "person", "people"])
                    loc_val = self._find_val(col_text, ["location", "site", "operational_site", "text_2"])

                    client_disp, client_key, c_flag = normalizer.normalize_client_name(client_val)
                    if c_flag:
                        item_issues.append({"field": "client", "type": "MISSING_CLIENT", "severity": "HIGH", "msg": c_flag, "raw": client_val})

                    sec_disp, sec_flag = normalizer.normalize_sector(sector_val)
                    if sec_flag:
                        item_issues.append({"field": "sector", "type": sec_flag, "severity": "LOW", "msg": f"Sector issue: {sec_flag}", "raw": sector_val})

                    stat_disp, stat_flag = normalizer.normalize_work_order_status(status_val)
                    if stat_flag:
                        item_issues.append({"field": "status", "type": "MISSING_STATUS", "severity": "HIGH", "msg": stat_flag, "raw": status_val})

                    start_dt, _ = normalizer.parse_date(start_dt_val)
                    due_dt, due_flag = normalizer.parse_date(due_dt_val)
                    comp_dt, _ = normalizer.parse_date(comp_dt_val)

                    if due_flag and stat_disp not in ["Completed", "Cancelled"]:
                        item_issues.append({"field": "due_date", "type": "MISSING_DATE", "severity": "MEDIUM", "msg": due_flag, "raw": str(due_dt_val)})

                    contract_num, c_val_flag = normalizer.parse_amount(val_num_val)
                    if c_val_flag:
                        sev = "HIGH" if "NEGATIVE" in c_val_flag or "INVALID" in c_val_flag else "MEDIUM"
                        item_issues.append({"field": "contract_value", "type": "INVALID_AMOUNT", "severity": sev, "msg": c_val_flag, "raw": str(val_num_val)})

                    cost_num, _ = normalizer.parse_amount(cost_val)

                    if not pilot_val or "unassigned" in str(pilot_val).lower():
                        item_issues.append({"field": "pilot", "type": "UNASSIGNED_PILOT", "severity": "MEDIUM", "msg": "Pilot unassigned or unavailable", "raw": str(pilot_val)})

                    db.add(WorkOrderModel(
                        monday_item_id=item_id,
                        work_order_no=item_name,
                        client_name=client_disp,
                        normalized_client=client_key,
                        project_name=project_val or item_name,
                        sector=sector_val,
                        normalized_sector=sec_disp,
                        status=status_val,
                        normalized_status=stat_disp,
                        start_date=start_dt,
                        due_date=due_dt,
                        completed_date=comp_dt,
                        contract_value=contract_num,
                        actual_cost=cost_num,
                        assigned_pilot_or_lead=pilot_val,
                        location=loc_val,
                        data_quality_flags=item_issues
                    ))

                for iss in item_issues:
                    db.add(DataQualityIssueModel(
                        board_type=board_type,
                        monday_item_id=item_id,
                        item_name=item_name,
                        field_name=iss["field"],
                        issue_type=iss["type"],
                        severity=iss["severity"],
                        details=iss["msg"],
                        raw_value=str(iss.get("raw", ""))
                    ))
                    issues_count += 1

                normalized_count += 1

            sync_run.status = "SUCCESS"
            sync_run.items_normalized = normalized_count
            sync_run.issues_found = issues_count
            sync_run.completed_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "board_type": board_type,
                "status": "SUCCESS",
                "items_fetched": len(raw_items),
                "items_normalized": normalized_count,
                "issues_found": issues_count
            }

        except Exception as e:
            logger.exception(f"Sync error for {board_type}: {e}")
            db.rollback()
            sync_run.status = "FAILED"
            sync_run.error_message = str(e)
            sync_run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "board_type": board_type,
                "status": "FAILED",
                "error": str(e),
                "items_fetched": 0,
                "items_normalized": 0,
                "issues_found": 0
            }

    def _find_val(self, col_text: Dict[str, Any], candidate_keys: List[str]) -> Optional[str]:
        for k in candidate_keys:
            if k in col_text and col_text[k] is not None:
                return col_text[k]
        for col_id, val in col_text.items():
            for k in candidate_keys:
                if k in col_id.lower() and val is not None:
                    return val
        return None

sync_service = SyncService()
