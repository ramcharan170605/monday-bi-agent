import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from backend.config import settings
from backend.models.database import WorkOrderModel, DealModel, DataQualityIssueModel
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.models.schemas import AskResponse, MetricCard

logger = logging.getLogger(__name__)

# Available database tools for the LLM
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_deals_pipeline",
            "description": "Calculates pipeline volume, weighted revenue, win rates, stage breakdowns, and top opportunities from Monday.com Deals board in Neon DB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter (e.g. Energy, Mining, Infrastructure, Telecom, Agriculture, Geospatial)"},
                    "stage": {"type": "string", "description": "Optional stage filter (e.g. Won, Lost, Proposal, Qualified, Lead, Negotiation)"},
                    "client": {"type": "string", "description": "Optional client name or keyword"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_flight_operations",
            "description": "Calculates work order completion rate, contract value, operational cost, gross profit margins, delayed flights, and pilot assignments from Monday.com Work Orders board in Neon DB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter (e.g. Energy, Mining, Infrastructure, Telecom, Agriculture, Geospatial)"},
                    "status": {"type": "string", "description": "Optional status filter (e.g. Completed, In Progress, Delayed, Scheduled)"},
                    "client": {"type": "string", "description": "Optional client name or keyword"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_data_quality_audit",
            "description": "Fetches data hygiene score and specific caveats (missing dates, invalid financial amounts, unassigned pilots) across Monday boards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "description": "Optional severity filter (HIGH, MEDIUM, LOW)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_full_leadership_overview",
            "description": "Fetches high-level executive overview combining pipeline, operations, gross margins, and cross-board client alignment.",
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
        """Executes analytical SQL calculations directly against Neon PostgreSQL database."""
        if name == "query_deals_pipeline":
            sector = args.get("sector")
            stage = args.get("stage")
            client = args.get("client")

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

            # Stage summary
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
                "sample_deals": [{"name": d.deal_name, "client": d.client_name, "value": d.deal_value, "stage": d.normalized_stage, "sector": d.normalized_sector} for d in deals[:10]]
            }

        elif name == "query_flight_operations":
            sector = args.get("sector")
            status = args.get("status")
            client = args.get("client")

            q = db.query(WorkOrderModel)
            if sector:
                q = q.filter(WorkOrderModel.normalized_sector.ilike(f"%{sector}%"))
            if status:
                q = q.filter(WorkOrderModel.normalized_status.ilike(f"%{status}%"))
            if client:
                q = q.filter(WorkOrderModel.client_name.ilike(f"%{client}%"))

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
                "sample_orders": [{"id": w.work_order_no, "client": w.client_name, "project": w.project_name, "status": w.normalized_status, "contract": w.contract_value, "pilot": w.assigned_pilot_or_lead} for w in orders[:10]]
            }

        elif name == "query_data_quality_audit":
            dq = data_quality_service.get_data_quality_summary(db)
            caveats = data_quality_service.generate_contextual_caveats(db)
            return {
                "data_hygiene_score": dq["data_hygiene_score"],
                "total_issues": dq["total_issues"],
                "high_severity_count": dq["high_severity_count"],
                "medium_severity_count": dq["medium_severity_count"],
                "low_severity_count": dq["low_severity_count"],
                "issues_by_type": dq["issues_by_type"],
                "caveats": caveats
            }

        elif name == "get_full_leadership_overview":
            pipeline = analytics_engine.get_pipeline_metrics(db)
            ops = analytics_engine.get_operations_metrics(db)
            dq = data_quality_service.get_data_quality_summary(db)
            caveats = data_quality_service.generate_contextual_caveats(db)
            return {
                "pipeline": pipeline,
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
        Pure LLM reasoning with live Neon DB tool execution.
        Zero hardcoded lexical rules, zero static metric templates.
        """
        tools_used = []
        executed_data: Dict[str, Any] = {}

        if self.groq_api_key and self.groq_api_key.strip() and not self.groq_api_key.startswith("gsk_your"):
            try:
                from groq import AsyncGroq
                client = AsyncGroq(api_key=self.groq_api_key)

                system_prompt = (
                    "You are Skylark Drones' Lead Business Intelligence Agent. "
                    "You answer questions from founders, executives, and department leads by querying live Monday.com Work Orders and Deals data in Neon PostgreSQL.\n\n"
                    "INSTRUCTIONS:\n"
                    "1. For greetings or general questions, respond warmly and conversationally without calling tools or generating unnecessary cards.\n"
                    "2. For business questions (pipeline, flight operations, backlog, margins, sectors, data quality, leadership updates), call the appropriate database tool(s) to fetch the exact numbers.\n"
                    "3. Format your final response strictly as a JSON object with this structure:\n"
                    "{\n"
                    '  "answer": "Detailed markdown response answering the question directly and articulately",\n'
                    '  "executive_summary": "1-line executive takeaway",\n'
                    '  "metrics": [{"label": "Metric Name", "value": "$X / Y%", "subtext": "context", "sentiment": "positive|negative|warning|neutral"}],\n'
                    '  "data_quality_caveats": ["caveat 1", "caveat 2"],\n'
                    '  "recommended_actions": ["action 1", "action 2"]\n'
                    "}\n"
                    "4. If a question doesn't need metric cards (e.g. greetings, simple explanations), set 'metrics': []. Only include relevant metric badges.\n"
                    "5. Never invent numbers. Always ground figures in tool outputs."
                )

                messages = [{"role": "system", "content": system_prompt}]

                if history:
                    for turn in history[-4:]:
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
                    temperature=0.1
                )

                choice = step1_resp.choices[0]

                # Step 2: Handle tool calls if invoked by LLM
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
                        response_format={"type": "json_object"}
                    )
                    content = step2_resp.choices[0].message.content
                    parsed = json.loads(content)

                    # Build metric cards
                    metric_cards = []
                    for m in parsed.get("metrics", []):
                        if isinstance(m, dict) and "label" in m and "value" in m:
                            metric_cards.append(MetricCard(
                                label=str(m.get("label")),
                                value=str(m.get("value")),
                                subtext=m.get("subtext"),
                                sentiment=m.get("sentiment", "neutral")
                            ))

                    return AskResponse(
                        answer=parsed.get("answer", "Here are the requested insights from our Monday.com database."),
                        executive_summary=parsed.get("executive_summary", "Insights processed from live Monday.com records."),
                        metrics=metric_cards,
                        data_quality_caveats=parsed.get("data_quality_caveats", []),
                        assumptions_made=parsed.get("assumptions_made", []),
                        recommended_actions=parsed.get("recommended_actions", []),
                        tools_used=tools_used or ["groq_llm_reasoning"],
                        raw_data_summary=executed_data
                    )

                else:
                    # No tools needed (e.g. greeting or conversation)
                    content = choice.message.content or ""
                    try:
                        parsed = json.loads(content)
                        return AskResponse(
                            answer=parsed.get("answer", content),
                            executive_summary=parsed.get("executive_summary", "Welcome to Skylark Drones BI Assistant."),
                            metrics=[],
                            data_quality_caveats=[],
                            assumptions_made=[],
                            recommended_actions=[],
                            tools_used=["groq_conversational_response"],
                            raw_data_summary={"intent": "conversational"}
                        )
                    except:
                        return AskResponse(
                            answer=content,
                            executive_summary="Skylark Drones Business Intelligence Assistant.",
                            metrics=[],
                            data_quality_caveats=[],
                            assumptions_made=[],
                            recommended_actions=[],
                            tools_used=["groq_conversational_response"],
                            raw_data_summary={"intent": "conversational"}
                        )

            except Exception as e:
                logger.error(f"Groq tool-calling flow failed, falling back to direct context: {e}")

        # Fallback if Groq API key is missing
        overview = self.execute_tool(db, "get_full_leadership_overview", {})
        return self._direct_database_response(query, overview)

    def _direct_database_response(self, query: str, overview: Dict[str, Any]) -> AskResponse:
        p = overview.get("pipeline", {})
        ops = overview.get("operations", {})
        dq = overview.get("data_quality", {})
        q_lower = query.lower()

        if any(w in q_lower for w in ["hey", "hello", "hi", "dude", "help"]):
            return AskResponse(
                answer=(
                    "👋 **Hello! I am your Skylark Drones Business Intelligence Agent.**\n\n"
                    "I continuously query live **Monday.com Work Orders** and **Deals** cached in our **Neon PostgreSQL** database.\n\n"
                    "You can ask me about:\n"
                    "- Sales pipeline & win rates by sector\n"
                    "- Drone flight work orders & execution completion\n"
                    "- Gross profit margins & operational costs\n"
                    "- Executive leadership updates & data hygiene audits"
                ),
                executive_summary="Skylark Drones BI Assistant ready.",
                metrics=[],
                data_quality_caveats=[],
                assumptions_made=[],
                recommended_actions=["Ask a question about sales pipeline, work orders, or flight margins."],
                tools_used=["database_overview_scan"],
                raw_data_summary={"intent": "conversational"}
            )

        return AskResponse(
            answer=(
                f"### 📊 Business Intelligence Analysis\n\n"
                f"- **Pipeline:** Total volume is **${p.get('total_pipeline_value', 0):,.0f}** (Weighted: **${p.get('weighted_pipeline_value', 0):,.0f}**) across {p.get('total_deals', 0)} deals with a **{p.get('win_rate_percent', 0)}%** win rate.\n"
                f"- **Operations:** **{ops.get('total_work_orders', 0)}** missions tracked with **{ops.get('completion_rate_percent', 0)}%** delivery completion and **{ops.get('gross_margin_percent', 0)}%** gross margin (**${ops.get('gross_profit', 0):,.0f}** gross profit).\n"
                f"- **Data Quality:** Hygiene score is **{dq.get('data_hygiene_score', 0)}%** across {dq.get('total_issues', 0)} logged caveats."
            ),
            executive_summary=f"Pipeline: ${p.get('total_pipeline_value', 0):,.0f} | Operations: {ops.get('completion_rate_percent', 0)}% completion across {ops.get('total_work_orders', 0)} missions.",
            metrics=[
                MetricCard(label="Pipeline Value", value=f"${p.get('total_pipeline_value', 0):,.0f}", subtext=f"{p.get('total_deals', 0)} deals in scope", sentiment="positive"),
                MetricCard(label="Win Rate", value=f"{p.get('win_rate_percent', 0)}%", subtext=f"${p.get('won_value', 0):,.0f} won", sentiment="neutral"),
                MetricCard(label="Work Orders", value=f"{ops.get('total_work_orders', 0)} Missions", subtext=f"{ops.get('completion_rate_percent', 0)}% completion rate", sentiment="neutral"),
                MetricCard(label="Gross Margin", value=f"{ops.get('gross_margin_percent', 0)}%", subtext=f"Profit: ${ops.get('gross_profit', 0):,.0f}", sentiment="positive")
            ],
            data_quality_caveats=overview.get("caveats", []),
            assumptions_made=["Data calculated from live Monday.com records in Neon PostgreSQL."],
            recommended_actions=["Review high-value open deals and pilot allocations."],
            tools_used=["neon_database_analytics"],
            raw_data_summary=overview
        )

bi_agent = SkylarkBIAgent()
