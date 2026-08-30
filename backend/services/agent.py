import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.config import settings
from backend.models.database import WorkOrderModel, DealModel, DataQualityIssueModel
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.models.schemas import AskResponse, MetricCard

logger = logging.getLogger(__name__)

class SkylarkBIAgent:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL

    def _build_comprehensive_database_context(self, db: Session) -> Dict[str, Any]:
        """Extracts complete live state from Neon PostgreSQL analytical cache."""
        deals = db.query(DealModel).all()
        wos = db.query(WorkOrderModel).all()
        dqs = db.query(DataQualityIssueModel).limit(40).all()

        # 1. Pipeline aggregations by sector and stage
        deals_by_sector: Dict[str, Dict[str, Any]] = {}
        for d in deals:
            sec = d.normalized_sector or "Unassigned"
            stg = d.normalized_stage or "Unknown"
            val = float(d.deal_value or 0)
            w_val = float(d.weighted_value or 0)

            if sec not in deals_by_sector:
                deals_by_sector[sec] = {
                    "total_deals": 0,
                    "total_value": 0.0,
                    "weighted_value": 0.0,
                    "won_value": 0.0,
                    "lost_value": 0.0,
                    "won_count": 0,
                    "lost_count": 0,
                    "stages": {},
                    "sample_deals": []
                }
            deals_by_sector[sec]["total_deals"] += 1
            deals_by_sector[sec]["total_value"] += val
            deals_by_sector[sec]["weighted_value"] += w_val

            if stg not in deals_by_sector[sec]["stages"]:
                deals_by_sector[sec]["stages"][stg] = {"count": 0, "value": 0.0}
            deals_by_sector[sec]["stages"][stg]["count"] += 1
            deals_by_sector[sec]["stages"][stg]["value"] += val

            if stg == "Won":
                deals_by_sector[sec]["won_value"] += val
                deals_by_sector[sec]["won_count"] += 1
            elif stg == "Lost":
                deals_by_sector[sec]["lost_value"] += val
                deals_by_sector[sec]["lost_count"] += 1

            if len(deals_by_sector[sec]["sample_deals"]) < 8:
                deals_by_sector[sec]["sample_deals"].append({
                    "deal_name": d.deal_name,
                    "client": d.client_name,
                    "value": val,
                    "stage": stg,
                    "probability": d.probability,
                    "expected_close": str(d.expected_close_date) if d.expected_close_date else None
                })

        # 2. Operations aggregations by sector and status
        ops_by_sector: Dict[str, Dict[str, Any]] = {}
        for w in wos:
            sec = w.normalized_sector or "Unassigned"
            status = w.normalized_status or "Unknown"
            c_val = float(w.contract_value or 0)
            cost = float(w.actual_cost or 0)

            if sec not in ops_by_sector:
                ops_by_sector[sec] = {
                    "total_work_orders": 0,
                    "total_contract_value": 0.0,
                    "total_actual_cost": 0.0,
                    "completed_count": 0,
                    "delayed_count": 0,
                    "in_progress_count": 0,
                    "scheduled_count": 0,
                    "sample_missions": []
                }
            ops_by_sector[sec]["total_work_orders"] += 1
            ops_by_sector[sec]["total_contract_value"] += max(0.0, c_val)
            ops_by_sector[sec]["total_actual_cost"] += max(0.0, cost)

            if status == "Completed":
                ops_by_sector[sec]["completed_count"] += 1
            elif status == "Delayed":
                ops_by_sector[sec]["delayed_count"] += 1
            elif status == "In Progress":
                ops_by_sector[sec]["in_progress_count"] += 1
            elif status == "Scheduled":
                ops_by_sector[sec]["scheduled_count"] += 1

            if len(ops_by_sector[sec]["sample_missions"]) < 8:
                ops_by_sector[sec]["sample_missions"].append({
                    "wo_no": w.work_order_no,
                    "client": w.client_name,
                    "project": w.project_name,
                    "status": status,
                    "contract_value": c_val,
                    "cost": cost,
                    "pilot": w.assigned_pilot_or_lead,
                    "due_date": str(w.due_date) if w.due_date else None
                })

        # 3. Overall KPI totals
        total_pipeline = sum(d["total_value"] for d in deals_by_sector.values())
        weighted_pipeline = sum(d["weighted_value"] for d in deals_by_sector.values())
        total_won = sum(d["won_value"] for d in deals_by_sector.values())
        total_lost = sum(d["lost_value"] for d in deals_by_sector.values())
        closed_total = total_won + total_lost
        overall_win_rate = round((total_won / closed_total * 100), 1) if closed_total > 0 else 0.0

        total_contracts = sum(o["total_contract_value"] for o in ops_by_sector.values())
        total_costs = sum(o["total_actual_cost"] for o in ops_by_sector.values())
        gross_profit = total_contracts - total_costs
        overall_gross_margin = round((gross_profit / total_contracts * 100), 1) if total_contracts > 0 else 0.0

        total_wos = len(wos)
        total_completed = sum(o["completed_count"] for o in ops_by_sector.values())
        total_delayed = sum(o["delayed_count"] for o in ops_by_sector.values())
        overall_comp_rate = round((total_completed / total_wos * 100), 1) if total_wos > 0 else 0.0

        # 4. Data Quality
        dq_summary = data_quality_service.get_data_quality_summary(db)
        sample_issues = [
            {
                "item": iss.item_name,
                "board": iss.board_type,
                "field": iss.field_name,
                "type": iss.issue_type,
                "severity": iss.severity,
                "details": iss.details,
                "raw": iss.raw_value
            } for iss in dqs
        ]

        return {
            "company_kpis": {
                "total_pipeline_value": total_pipeline,
                "weighted_pipeline_value": weighted_pipeline,
                "total_deals_count": len(deals),
                "total_won_value": total_won,
                "total_lost_value": total_lost,
                "overall_win_rate_percent": overall_win_rate,
                "total_work_orders_count": total_wos,
                "total_contract_value": total_contracts,
                "total_actual_cost": total_costs,
                "gross_profit": gross_profit,
                "overall_gross_margin_percent": overall_gross_margin,
                "overall_completion_rate_percent": overall_comp_rate,
                "total_completed_missions": total_completed,
                "total_delayed_missions": total_delayed,
                "data_hygiene_score": dq_summary["data_hygiene_score"],
                "total_issues_count": dq_summary["total_issues"],
                "high_severity_issues_count": dq_summary["high_severity_count"]
            },
            "deals_by_sector": deals_by_sector,
            "operations_by_sector": ops_by_sector,
            "data_quality_audit": {
                "summary": dq_summary,
                "sample_flagged_records": sample_issues
            }
        }

    async def answer_query(
        self,
        db: Session,
        query: str,
        session_id: str = "default",
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AskResponse:
        """
        Direct, unrestricted LLM intelligence over live Monday.com & Neon PostgreSQL database state.
        Zero rigid tool-call failure modes. Zero static templates.
        """
        context = self._build_comprehensive_database_context(db)
        answer = None

        if self.groq_api_key and self.groq_api_key.strip() and not self.groq_api_key.startswith("gsk_your"):
            try:
                from groq import AsyncGroq
                client = AsyncGroq(api_key=self.groq_api_key)

                system_prompt = """You are the Lead Business Intelligence AI Partner for Skylark Drones, communicating directly with company founders and executives.

You have direct, real-time access to the entire analytical database synchronized from Monday.com (Deals Funnel and Flight Work Orders boards).

GUIDELINES FOR ANSWERING:
1. Speak naturally, articulately, and conversationally like a world-class VP of Strategy / Chief Data Officer.
2. Address the user's specific question directly with high analytical precision:
   - If they ask about a sector (e.g. "renewables" or "energy" or "mining"), drill into that sector's pipeline volume, weighted value, win rate, stage distribution, and specific customer accounts/deal names from the data.
   - If they ask about work orders, delivery completion, or costs, break down the flight operations, gross margins, pilot coverage, and delayed missions.
   - If they ask for specifics on data quality or caveats, name actual flagged records, corrupted fields, and operational discrepancies.
   - If they ask for a leadership update, synthesize top commercial wins, flight execution velocity, key bottlenecks, and data hygiene notes.
   - For greetings or conversational questions, respond warmly and helpfully.
3. Formatting:
   - Use clean, elegant GitHub markdown with clear section headers and concise bullet points.
   - NEVER output raw JSON or code blocks. Always output pure, articulate markdown text.
4. Accuracy:
   - All numbers, values, customer names, and project references must come strictly from the provided database context."""

                messages = [{"role": "system", "content": system_prompt}]

                # Include recent conversation turns
                if history:
                    for turn in history[-6:]:
                        if turn.get("type") == "user":
                            messages.append({"role": "user", "content": turn.get("text", "")})
                        elif turn.get("type") == "agent":
                            messages.append({"role": "assistant", "content": turn.get("text", "")})

                # Inject query + comprehensive live database state
                user_message = {
                    "question": query,
                    "live_database_state": context
                }

                messages.append({"role": "user", "content": json.dumps(user_message, default=str)})

                response = await client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    temperature=0.2,
                    max_tokens=1800
                )
                answer = response.choices[0].message.content or ""

            except Exception as e:
                logger.error(f"Groq LLM call failed: {e}")

        # Intelligent natural fallback if LLM is unavailable
        if not answer:
            answer = self._generate_intelligent_direct_answer(query, context)

        return AskResponse(
            answer=answer,
            executive_summary="Direct analytical intelligence over live Monday.com database in Neon PostgreSQL.",
            metrics=[],  # Zero forced metric cards
            data_quality_caveats=[],
            assumptions_made=[],
            recommended_actions=[],
            tools_used=["neon_database_direct_intelligence"],
            raw_data_summary={"database_kpis": context["company_kpis"]}
        )

    def _generate_intelligent_direct_answer(self, query: str, context: Dict[str, Any]) -> str:
        q_lower = query.lower()
        kpis = context["company_kpis"]
        deals_by_sec = context["deals_by_sector"]
        ops_by_sec = context["operations_by_sector"]

        # Check for sector match (e.g. renewables, energy, solar, wind)
        target_sec = None
        for sec in deals_by_sec.keys():
            if sec.lower() in q_lower or (sec.lower() == "energy" and any(w in q_lower for w in ["renewable", "solar", "wind", "power", "energy"])):
                target_sec = sec
                break

        if target_sec and target_sec in deals_by_sec:
            d_sec = deals_by_sec[target_sec]
            stages_list = [f"- **{stg}:** {info['count']} deals (${info['value']:,.0f})" for stg, info in d_sec["stages"].items()]
            sample_list = [f"- **{s['deal_name']}** ({s['client']}): ${s['value']:,.0f} — *Stage: {s['stage']}*" for s in d_sec["sample_deals"][:5]]

            return f"""### ⚡ {target_sec} / Renewables Sector Pipeline Analysis

Our **{target_sec}** pipeline represents a significant commercial opportunity across **{d_sec['total_deals']}** tracked deals:

- **Total Pipeline Volume:** **${d_sec['total_value']:,.0f}**
- **Probability-Weighted Value:** **${d_sec['weighted_value']:,.0f}**
- **Closed Deals:** **${d_sec['won_value']:,.0f}** Won ({d_sec['won_count']} deals) vs **${d_sec['lost_value']:,.0f}** Lost ({d_sec['lost_count']} deals).

#### 📊 Pipeline Stage Distribution:
{chr(10).join(stages_list) if stages_list else "- No stage data available."}

#### 💼 Key Opportunities in this Sector:
{chr(10).join(sample_list) if sample_list else "- No sample deals available."}"""

        elif any(w in q_lower for w in ["quality", "caveat", "issue", "error", "hygiene"]):
            dq = context["data_quality_audit"]["summary"]
            issues = context["data_quality_audit"]["sample_flagged_records"][:6]
            issues_md = "\n".join([f"- **{iss['item']}** ({iss['board']}): {iss['details']} [Field: `{iss['field']}`, Raw: `{iss['raw']}`]" for iss in issues])

            return f"""### 🛡️ Data Quality & Integrity Audit

Our overall board hygiene score is **{dq['data_hygiene_score']}%** across {kpis['total_work_orders_count']} Work Orders and {kpis['total_deals_count']} Deals.

- **Total Identified Issues:** **{dq['total_issues']}**
- **High Severity Issues:** **{dq['high_severity_count']}** (primarily corrupted monetary amounts and missing client names)

#### Specific Examples of Flagged Records:
{issues_md}"""

        elif any(w in q_lower for w in ["hey", "hello", "hi", "dude", "help"]):
            return """👋 **Hello! I am your Skylark Drones Business Intelligence Agent.**

I have direct access to our live **Monday.com Work Orders** and **Deals Pipeline** database in Neon PostgreSQL. 

Feel free to ask me anything regarding:
- Sectoral pipeline health (e.g. Energy/Renewables, Mining, Infrastructure)
- Drone flight execution, completion rates, and profit margins
- Specific data quality caveats and flagged records
- Leadership updates for board briefings"""

        else:
            return f"""### 📊 Skylark Drones — Executive Leadership Overview

- **Commercial Sales Pipeline:** Total volume is **${kpis['total_pipeline_value']:,.0f}** (Weighted: **${kpis['weighted_pipeline_value']:,.0f}**) across {kpis['total_deals_count']} deals with a **{kpis['overall_win_rate_percent']}%** win rate.
- **Flight Operations & Execution:** **{kpis['total_work_orders_count']}** missions tracked with a **{kpis['overall_completion_rate_percent']}%** completion rate and **{kpis['overall_gross_margin_percent']}%** gross operating margin (**${kpis['gross_profit']:,.0f}** profit).
- **Data Hygiene Audit:** Rated at **{kpis['data_hygiene_score']}%** across {kpis['total_issues_count']} tracked data quality caveats."""

bi_agent = SkylarkBIAgent()
