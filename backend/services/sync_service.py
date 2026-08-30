import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
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
    async def sync_all_boards(self, db: Session) -> Dict[str, Any]:
        if not settings.WORK_ORDERS_BOARD_ID or not settings.DEALS_BOARD_ID:
            raise RuntimeError("Both WORK_ORDERS_BOARD_ID and DEALS_BOARD_ID must be configured in environment variables.")

        wo_result = await self.sync_board(db, "work_orders", settings.WORK_ORDERS_BOARD_ID)
        deals_result = await self.sync_board(db, "deals", settings.DEALS_BOARD_ID)

        return {
            "status": "SUCCESS" if wo_result["status"] == "SUCCESS" and deals_result["status"] == "SUCCESS" else "PARTIAL",
            "synced_boards": [wo_result, deals_result],
            "total_items_fetched": wo_result["items_fetched"] + deals_result["items_fetched"],
            "total_items_normalized": wo_result["items_normalized"] + deals_result["items_normalized"],
            "total_issues_found": wo_result["issues_found"] + deals_result["issues_found"],
            "synced_at": datetime.now(timezone.utc)
        }

    async def sync_board(self, db: Session, board_type: str, board_id: str) -> Dict[str, Any]:
        if not board_id or not str(board_id).strip():
            raise ValueError(f"Board ID for {board_type} is not configured.")

        sync_run = SyncRunModel(
            board_type=board_type,
            status="IN_PROGRESS",
            started_at=datetime.now(timezone.utc)
        )
        db.add(sync_run)
        db.flush()

        try:
            schema_data = await monday_client.get_board_schema(board_id)
            columns_list = schema_data.get("columns", [])
            col_id_to_title = {c["id"]: c["title"] for c in columns_list if "id" in c and "title" in c}

            existing_schema = db.query(BoardSchemaModel).filter(BoardSchemaModel.board_type == board_type).first()
            if existing_schema:
                existing_schema.board_id = str(schema_data.get("id", board_id))
                existing_schema.title = schema_data.get("name", board_type)
                existing_schema.columns_json = columns_list
                existing_schema.updated_at = datetime.now(timezone.utc)
            else:
                new_schema = BoardSchemaModel(
                    board_id=str(schema_data.get("id", board_id)),
                    board_type=board_type,
                    title=schema_data.get("name", board_type),
                    columns_json=columns_list
                )
                db.add(new_schema)

            raw_items = await monday_client.fetch_board_items(board_id)
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

                # Map column values by ID, title, and lower-case title
                val_map: Dict[str, Any] = {}
                for c in item.get("column_values", []):
                    cid = c.get("id")
                    ctext = c.get("text")
                    if cid:
                        val_map[cid] = ctext
                        val_map[cid.lower()] = ctext
                        title = col_id_to_title.get(cid)
                        if title:
                            val_map[title] = ctext
                            val_map[title.lower()] = ctext

                item_issues = []

                if board_type == "deals":
                    client_val = self._get_best_val(val_map, ["client code", "client", "customer", "account", "company"])
                    owner_val = self._get_best_val(val_map, ["owner code", "deal owner", "owner", "person"])
                    sector_val = self._get_best_val(val_map, ["sector/service", "sector", "industry", "category"])
                    stage_val = self._get_best_val(val_map, ["deal stage", "deal status", "stage", "phase"])
                    deal_val = self._get_best_val(val_map, ["masked deal value", "deal value", "value", "amount"])
                    prob_val = self._get_best_val(val_map, ["closure probability", "win probability", "prob", "probability"])
                    exp_close_val = self._get_best_val(val_map, ["tentative close date", "expected close date", "exp_close", "close date (a)"])
                    act_close_val = self._get_best_val(val_map, ["close date (a)", "actual close date", "act_close"])

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
                    client_val = self._get_best_val(val_map, ["customer name code", "client", "customer", "enterprise"])
                    project_val = self._get_best_val(val_map, ["nature of work", "project title", "project", "title"])
                    sector_val = self._get_best_val(val_map, ["sector", "industry", "category"])
                    status_val = self._get_best_val(val_map, ["execution status", "status", "state"])
                    start_dt_val = self._get_best_val(val_map, ["probable start date", "flight start date", "start_date"])
                    due_dt_val = self._get_best_val(val_map, ["data delivery date", "target delivery date", "due_date", "probable end date"])
                    comp_dt_val = self._get_best_val(val_map, ["collection date", "completion date", "comp_date"])
                    val_num_val = self._get_best_val(val_map, ["amount in rupees (excl of gst) (masked)", "contract amount (masked)", "contract value", "contract_val", "amount"])
                    billed_val = self._get_best_val(val_map, ["billed value in rupees (excl of gst.) (masked)", "billed value", "actual cost", "actual_cost"])
                    pilot_val = self._get_best_val(val_map, ["bd/kam personnel code", "bd/kam lead code", "flight lead", "pilot", "person"])
                    loc_val = self._get_best_val(val_map, ["operational site location", "location", "site"])

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

                    cost_num, _ = normalizer.parse_amount(billed_val)

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

    def _get_best_val(self, val_map: Dict[str, Any], candidate_keys: List[str]) -> Optional[str]:
        for k in candidate_keys:
            if k in val_map and val_map[k] is not None and str(val_map[k]).strip():
                return str(val_map[k]).strip()
        for k in candidate_keys:
            for map_k, map_v in val_map.items():
                if k in map_k and map_v is not None and str(map_v).strip():
                    return str(map_v).strip()
        return None

sync_service = SyncService()
