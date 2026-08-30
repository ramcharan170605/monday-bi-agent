import json
import logging
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from backend.config import settings
from backend.models.database import WorkOrderModel, DealModel, DataQualityIssueModel
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.models.schemas import AskResponse, MetricCard

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_deals_pipeline",
            "description": "Calculates pipeline totals, stage breakdowns, win rates, and retrieves specific deal records from Monday.com Deals board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector filter (e.g. Energy, Mining, Infrastructure, Telecom, Agriculture, Geospatial)"},
                    "stage": {"type": "string", "description": "Stage filter (e.g. Won, Lost, Proposal, Qualified, Lead, Negotiation)"},
                    "client": {"type": "string", "description": "Client name or search keyword"},
                    "limit": {"type": "integer", "description": "Number of deal records to return (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_flight_operations",
            "description": "Calculates work order completion rate, contract value, operational costs, profit margins, and retrieves specific work orders from Monday.com Work Orders board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector filter (e.g. Energy, Mining, Infrastructure, Telecom, Agriculture, Geospatial)"},
                    "status": {"type": "string", "description": "Status filter (e.g. Completed, In Progress, Delayed, Scheduled)"},
                    "client": {"type": "string", "description": "Client name or keyword"},
                    "pilot": {"type": "string", "description": "Pilot or flight lead name"},
                    "limit": {"type": "integer", "description": "Number of work order records to return (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_specific_data_quality_issues",
            "description": "Retrieves the actual data quality issue records with item names, affected fields, severity, details, and raw values from Monday boards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "description": "Filter by severity (HIGH, MEDIUM, LOW)"},
                    "issue_type": {"type": "string", "description": "Filter by type (e.g. MISSING_DATE, INVALID_AMOUNT, MISSING_CLIENT, MISSING_STATUS, UNASSIGNED_PILOT)"},
                    "board_type": {"type": "string", "description": "Filter by board (work_orders, deals)"},
                    "limit": {"type": "integer", "description": "Max records to return (default 25)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_records",
            "description": "Searches across deals and work orders by keyword, client, pilot, or project title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword to search for across all fields"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_overview",
            "description": "Fetches cross-board summary combining pipeline metrics, operations velocity, margins, and data hygiene scores.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

class SkylarkBIAgent:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL

    def execute_tool(self, db: Session, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Executes analytical SQL queries against Neon PostgreSQL database."""
        if name == "query_deals_pipeline":
            sector = args.get("sector")
            stage = args.get("stage")
            client = args.get("client")
            limit = args.get("limit", 15)

            q = db.query(DealModel)
            if sector:
                q = q.filter(DealModel.normalized_sector.ilike(f"%{sector}%"))
            if stage:
                q = q.filter(DealModel.normalized_stage.ilike(f"%{stage}%"))
            if client:
                q = q.filter(DealModel.client_name.ilike(f"%{client}%"))

            deals = q.all()
            total_val = sum(float(d.deal_value or 0) for d in deals)
            weighted_val = sum(float(d.weighted_value or 0) for d in deals)
            won_deals = [d for d in deals if d.normalized_stage == "Won"]
            lost_deals = [d for d in deals if d.normalized_stage == "Lost"]

            won_val = sum(float(d.deal_value or 0) for d in won_deals)
            lost_val = sum(float(d.deal_value or 0) for d in lost_deals)
            closed_val = won_val + lost_val
            win_rate = round((won_val / closed_val * 100), 1) if closed_val > 0 else 0.0

            stages = {}
            for d in deals:
                stg = d.normalized_stage or "Unknown"
                if stg not in stages:
                    stages[stg] = {"count": 0, "value": 0.0}
                stages[stg]["count"] += 1
                stages[stg]["value"] += float(d.deal_value or 0)

            return {
                "total_deals": len(deals),
                "total_pipeline_value": total_val,
                "weighted_pipeline_value": weighted_val,
                "won_value": won_val,
                "won_count": len(won_deals),
                "lost_value": lost_val,
                "lost_count": len(lost_deals),
                "win_rate_percent": win_rate,
                "stages": stages,
                "deals_sample": [
                    {
                        "deal_name": d.deal_name,
                        "client": d.client_name,
                        "value": float(d.deal_value or 0),
                        "stage": d.normalized_stage,
                        "sector": d.normalized_sector,
                        "owner": d.deal_owner,
                        "expected_close": str(d.expected_close_date) if d.expected_close_date else None
                    } for d in deals[:limit]
                ]
            }

        elif name == "query_flight_operations":
            sector = args.get("sector")
            status = args.get("status")
            client = args.get("client")
            pilot = args.get("pilot")
            limit = args.get("limit", 15)

            q = db.query(WorkOrderModel)
            if sector:
                q = q.filter(WorkOrderModel.normalized_sector.ilike(f"%{sector}%"))
            if status:
                q = q.filter(WorkOrderModel.normalized_status.ilike(f"%{status}%"))
            if client:
                q = q.filter(WorkOrderModel.client_name.ilike(f"%{client}%"))
            if pilot:
                q = q.filter(WorkOrderModel.assigned_pilot_or_lead.ilike(f"%{pilot}%"))

            orders = q.all()
            total_contract = sum(float(w.contract_value or 0) for w in orders if (w.contract_value or 0) > 0)
            total_cost = sum(float(w.actual_cost or 0) for w in orders if (w.actual_cost or 0) > 0)
            gross_profit = total_contract - total_cost
            gross_margin = round((gross_profit / total_contract * 100), 1) if total_contract > 0 else 0.0

            completed = [w for w in orders if w.normalized_status == "Completed"]
            delayed = [w for w in orders if w.normalized_status == "Delayed"]
            in_progress = [w for w in orders if w.normalized_status == "In Progress"]
            scheduled = [w for w in orders if w.normalized_status == "Scheduled"]

            active_total = len(completed) + len(delayed) + len(in_progress) + len(scheduled)
            comp_rate = round((len(completed) / active_total * 100), 1) if active_total > 0 else 0.0

            return {
                "total_work_orders": len(orders),
                "total_contract_value": total_contract,
                "total_actual_cost": total_cost,
                "gross_profit": gross_profit,
                "gross_margin_percent": gross_margin,
                "completion_rate_percent": comp_rate,
                "completed_count": len(completed),
                "delayed_count": len(delayed),
                "in_progress_count": len(in_progress),
                "scheduled_count": len(scheduled),
                "work_orders_sample": [
                    {
                        "work_order_no": w.work_order_no,
                        "client": w.client_name,
                        "project": w.project_name,
                        "status": w.normalized_status,
                        "contract_value": float(w.contract_value or 0),
                        "actual_cost": float(w.actual_cost or 0),
                        "pilot": w.assigned_pilot_or_lead,
                        "location": w.location,
                        "due_date": str(w.due_date) if w.due_date else None
                    } for w in orders[:limit]
                ]
            }

        elif name == "get_specific_data_quality_issues":
            severity = args.get("severity")
            issue_type = args.get("issue_type")
            board_type = args.get("board_type")
            limit = args.get("limit", 25)

            q = db.query(DataQualityIssueModel)
            if severity:
                q = q.filter(DataQualityIssueModel.severity.ilike(severity))
            if issue_type:
                q = q.filter(DataQualityIssueModel.issue_type.ilike(f"%{issue_type}%"))
            if board_type:
                q = q.filter(DataQualityIssueModel.board_type.ilike(f"%{board_type}%"))

            issues = q.limit(limit).all()
            total_count = db.query(DataQualityIssueModel).count()
            high_count = db.query(DataQualityIssueModel).filter(DataQualityIssueModel.severity == "HIGH").count()

            return {
                "total_issues_in_database": total_count,
                "high_severity_total": high_count,
                "filtered_count": len(issues),
                "specific_issues": [
                    {
                        "item_name": iss.item_name,
                        "board": iss.board_type,
                        "field": iss.field_name,
                        "issue_type": iss.issue_type,
                        "severity": iss.severity,
                        "details": iss.details,
                        "raw_value": iss.raw_value
                    } for iss in issues
                ]
            }

        elif name == "search_records":
            term = args.get("query", "")
            deals = db.query(DealModel).filter(
                or_(
                    DealModel.deal_name.ilike(f"%{term}%"),
                    DealModel.client_name.ilike(f"%{term}%"),
                    DealModel.deal_owner.ilike(f"%{term}%")
                )
            ).limit(10).all()

            orders = db.query(WorkOrderModel).filter(
                or_(
                    WorkOrderModel.work_order_no.ilike(f"%{term}%"),
                    WorkOrderModel.client_name.ilike(f"%{term}%"),
                    WorkOrderModel.project_name.ilike(f"%{term}%"),
                    WorkOrderModel.assigned_pilot_or_lead.ilike(f"%{term}%")
                )
            ).limit(10).all()

            return {
                "matched_deals": [{"name": d.deal_name, "client": d.client_name, "value": d.deal_value, "stage": d.normalized_stage} for d in deals],
                "matched_work_orders": [{"no": w.work_order_no, "client": w.client_name, "project": w.project_name, "status": w.normalized_status, "pilot": w.assigned_pilot_or_lead} for w in orders]
            }

        elif name == "get_company_overview":
            p = analytics_engine.get_pipeline_metrics(db)
            ops = analytics_engine.get_operations_metrics(db)
            dq = data_quality_service.get_data_quality_summary(db)
            caveats = data_quality_service.generate_contextual_caveats(db)
            return {
                "pipeline": p,
                "operations": ops,
                "data_quality": dq,
                "caveats": caveats
            }

        return {}

    async def answer_query(
        self,
        db: Session,
        query: str,
        session_id: str = "default",
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AskResponse:
        """
        Pure Conversational LLM reasoning with live Monday.com & Neon DB tool execution.
        Zero static metric card enforcement.
        """
        tools_used = []
        executed_data: Dict[str, Any] = {}

        if self.groq_api_key and self.groq_api_key.strip() and not self.groq_api_key.startswith("gsk_your"):
            try:
                from groq import AsyncGroq
                client = AsyncGroq(api_key=self.groq_api_key)

                system_prompt = (
                    "You are the Lead Business Intelligence AI Partner for Skylark Drones, speaking directly with founders and leadership.\n\n"
                    "INSTRUCTIONS:\n"
                    "1. Respond conversationally, naturally, and with high intelligence like a top-tier management consultant / data partner.\n"
                    "2. When answering business questions, call the relevant database tools to fetch exact, real-time data from Monday.com / Neon DB.\n"
                    "3. When the user asks for specifics, drill-downs, or examples (e.g. specific data quality issues, delayed flights, top deals), invoke the specific tools and name actual records, clients, projects, fields, and values from the data!\n"
                    "4. Do NOT output raw JSON keys, curly braces, or code blocks in your final text. Write natural, beautifully formatted GitHub markdown.\n"
                    "5. Never hallucinate imaginary data; ground all numbers, names, and specifics strictly in the tool query results."
                )

                messages = [{"role": "system", "content": system_prompt}]

                if history:
                    for turn in history[-6:]:
                        if turn.get("type") == "user":
                            messages.append({"role": "user", "content": turn.get("text", "")})
                        elif turn.get("type") == "agent":
                            messages.append({"role": "assistant", "content": turn.get("text", "")})

                messages.append({"role": "user", "content": query})

                # Step 1: Initial call with tools
                step1_resp = await client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.2
                )

                choice = step1_resp.choices[0]

                # Step 2: If model calls tools, execute them against Neon DB
                if choice.message.tool_calls:
                    messages.append(choice.message)

                    for tool_call in choice.message.tool_calls:
                        t_name = tool_call.function.name
                        try:
                            t_args = json.loads(tool_call.function.arguments or "{}")
                        except:
                            t_args = {}

                        tools_used.append(t_name)
                        t_result = self.execute_tool(db, t_name, t_args)
                        executed_data[t_name] = t_result

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(t_result, default=str)
                        })

                    # Step 3: Synthesis call
                    step2_resp = await client.chat.completions.create(
                        messages=messages,
                        model=self.model,
                        temperature=0.2,
                        max_tokens=1500
                    )
                    final_answer = step2_resp.choices[0].message.content or ""

                    # Extract clean text if model wrapped in JSON
                    if final_answer.strip().startswith("{") and '"answer":' in final_answer:
                        try:
                            parsed = json.loads(final_answer.strip())
                            final_answer = parsed.get("answer", final_answer)
                        except:
                            pass

                    return AskResponse(
                        answer=final_answer,
                        executive_summary="Insights generated from live Monday.com database in Neon PostgreSQL.",
                        metrics=[],  # Zero forced cards! Pure natural conversation.
                        data_quality_caveats=[],
                        assumptions_made=[],
                        recommended_actions=[],
                        tools_used=tools_used,
                        raw_data_summary=executed_data
                    )

                else:
                    # Conversational / greeting message without tools
                    final_answer = choice.message.content or ""
                    if final_answer.strip().startswith("{") and '"answer":' in final_answer:
                        try:
                            parsed = json.loads(final_answer.strip())
                            final_answer = parsed.get("answer", final_answer)
                        except:
                            pass

                    return AskResponse(
                        answer=final_answer,
                        executive_summary="Skylark Drones Business Intelligence Assistant.",
                        metrics=[],
                        data_quality_caveats=[],
                        assumptions_made=[],
                        recommended_actions=[],
                        tools_used=["conversational_agent"],
                        raw_data_summary={"intent": "conversational"}
                    )

            except Exception as e:
                logger.error(f"Groq LLM tool execution failed: {e}")

        # Fallback if Groq API key is missing
        return self._direct_natural_fallback(query, db)

    def _direct_natural_fallback(self, query: str, db: Session) -> AskResponse:
        overview = self.execute_tool(db, "get_company_overview", {})
        p = overview.get("pipeline", {})
        ops = overview.get("operations", {})
        dq = overview.get("data_quality", {})
        q_lower = query.lower()

        if any(w in q_lower for w in ["hey", "hello", "hi", "dude", "help"]):
            return AskResponse(
                answer=(
                    "👋 **Hello! I am your Skylark Drones Business Intelligence Agent.**\n\n"
                    "I am connected directly to our live **Monday.com Work Orders** and **Deals** boards stored in Neon PostgreSQL.\n\n"
                    "Feel free to ask me anything about our sales pipeline, flight execution backlog, gross profit margins, or data quality caveats."
                ),
                executive_summary="Ready to assist with business intelligence questions.",
                metrics=[],
                data_quality_caveats=[],
                assumptions_made=[],
                recommended_actions=[],
                tools_used=["database_connection"],
                raw_data_summary={"intent": "conversational"}
            )

        if "quality" in q_lower or "caveat" in q_lower or "issue" in q_lower:
            sample_issues = self.execute_tool(db, "get_specific_data_quality_issues", {"limit": 5})
            issues_list = sample_issues.get("specific_issues", [])
            lines = []
            for iss in issues_list:
                lines.append(f"- **{iss['item_name']}** ({iss['board']}): {iss['details']} [Field: `{iss['field']}`, Raw: `{iss['raw_value']}`]")
            issues_md = "\n".join(lines) if lines else "No specific issues."

            return AskResponse(
                answer=(
                    f"### 🛡️ Data Quality Analysis Across Monday.com Boards\n\n"
                    f"Our overall data hygiene score is **{dq.get('data_hygiene_score', 94.9)}%** with **{dq.get('total_issues', 548)}** tracked quality items.\n\n"
                    f"#### Examples of Specific Identified Issues:\n"
                    f"{issues_md}\n\n"
                    f"High severity issues primarily involve invalid numeric formats or missing client identifiers."
                ),
                executive_summary=f"Data hygiene score: {dq.get('data_hygiene_score', 94.9)}% with {dq.get('total_issues', 548)} issues.",
                metrics=[],
                data_quality_caveats=[],
                assumptions_made=[],
                recommended_actions=[],
                tools_used=["get_specific_data_quality_issues"],
                raw_data_summary=sample_issues
            )

        return AskResponse(
            answer=(
                f"### 📊 Business Intelligence Analysis\n\n"
                f"- **Commercial Pipeline:** **${p.get('total_pipeline_value', 0):,.0f}** total volume across {p.get('total_deals', 0)} opportunities with a **{p.get('win_rate_percent', 0)}%** win rate.\n"
                f"- **Flight Operations:** **{ops.get('total_work_orders', 0)}** missions tracked with a **{ops.get('completion_rate_percent', 0)}%** completion rate and **{ops.get('gross_margin_percent', 0)}%** gross operating margin.\n"
                f"- **Data Hygiene:** **{dq.get('data_hygiene_score', 0)}%** score across {dq.get('total_issues', 0)} logged caveats."
            ),
            executive_summary=f"Pipeline: ${p.get('total_pipeline_value', 0):,.0f} | Operations: {ops.get('completion_rate_percent', 0)}% completion.",
            metrics=[],
            data_quality_caveats=[],
            assumptions_made=[],
            recommended_actions=[],
            tools_used=["get_company_overview"],
            raw_data_summary=overview
        )

bi_agent = SkylarkBIAgent()
