import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.config import settings
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.models.schemas import AskResponse, MetricCard

logger = logging.getLogger(__name__)

SECTOR_MAP = {
    "energy": "Energy",
    "solar": "Energy",
    "power": "Energy",
    "wind": "Energy",
    "utility": "Energy",
    "mining": "Mining",
    "metal": "Mining",
    "steel": "Mining",
    "bauxite": "Mining",
    "infrastructure": "Infrastructure",
    "infra": "Infrastructure",
    "highway": "Infrastructure",
    "road": "Infrastructure",
    "telecom": "Telecom",
    "tower": "Telecom",
    "5g": "Telecom",
    "agriculture": "Agriculture",
    "crop": "Agriculture",
    "farm": "Agriculture",
    "geospatial": "Geospatial",
    "survey": "Geospatial",
    "mapping": "Geospatial",
}

class SkylarkBIAgent:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL

    async def answer_query(
        self,
        db: Session,
        query: str,
        session_id: str = "default",
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AskResponse:
        q_lower = query.lower().strip()
        tools_used = []

        # Detect sector
        detected_sector = None
        for key, canonical in SECTOR_MAP.items():
            if key in q_lower:
                detected_sector = canonical
                break

        # Check intent classification
        is_greeting = any(w in q_lower for w in ["hey", "hello", "hi", "dude", "what's up", "who are you", "help me", "how can you help"]) and not any(w in q_lower for w in ["pipeline", "deal", "work order", "flight", "margin", "revenue", "sector", "quality", "update"])
        is_pipeline = any(w in q_lower for w in ["pipeline", "deal", "sales", "funnel", "close", "win rate", "opportunity", "revenue", "commercial", "forecast", "won", "lost"])
        is_ops = any(w in q_lower for w in ["work order", "flight", "drone", "operation", "delivery", "backlog", "delay", "cost", "margin", "pilot", "completion", "execution"])
        is_dq = any(w in q_lower for w in ["quality", "hygiene", "missing", "invalid", "caveat", "clean", "error", "audit", "corrupt"])
        is_leadership = any(w in q_lower for w in ["leadership", "update", "executive", "briefing", "summary", "board meeting", "overview", "status"])

        # Fetch actual analytical calculations from Neon DB
        pipeline_data = analytics_engine.get_pipeline_metrics(db, sector=detected_sector)
        ops_data = analytics_engine.get_operations_metrics(db, sector=detected_sector)
        dq_data = data_quality_service.get_data_quality_summary(db)
        caveats = data_quality_service.generate_contextual_caveats(db, sector=detected_sector)

        tools_used.extend(["sql_pipeline_aggregations", "sql_operations_analytics", "data_quality_audit_scan"])

        # Dynamically build only relevant metric cards (NO hardcoded 7 cards for everything!)
        metric_cards: List[MetricCard] = []

        if not is_greeting:
            if is_pipeline and not is_ops and not is_leadership:
                metric_cards.append(MetricCard(
                    label="Pipeline Value",
                    value=f"${pipeline_data['total_pipeline_value']:,.0f}",
                    subtext=f"{pipeline_data['total_deals']} active & closed deals" + (f" in {detected_sector}" if detected_sector else ""),
                    sentiment="positive" if pipeline_data['total_pipeline_value'] > 0 else "neutral"
                ))
                metric_cards.append(MetricCard(
                    label="Weighted Pipeline",
                    value=f"${pipeline_data['weighted_pipeline_value']:,.0f}",
                    subtext="Probability-adjusted value",
                    sentiment="neutral"
                ))
                metric_cards.append(MetricCard(
                    label="Win Rate",
                    value=f"{pipeline_data['win_rate_percent']}%",
                    subtext=f"${pipeline_data['won_value']:,.0f} won vs ${pipeline_data['lost_value']:,.0f} lost",
                    sentiment="positive" if pipeline_data['win_rate_percent'] >= 30 else "warning"
                ))
            elif is_ops and not is_pipeline and not is_leadership:
                metric_cards.append(MetricCard(
                    label="Work Orders",
                    value=f"{ops_data['total_work_orders']} Missions",
                    subtext=f"${ops_data['total_contract_value']:,.0f} contracted value" + (f" in {detected_sector}" if detected_sector else ""),
                    sentiment="neutral"
                ))
                metric_cards.append(MetricCard(
                    label="Completion Rate",
                    value=f"{ops_data['completion_rate_percent']}%",
                    subtext=f"{ops_data['completed_count']} completed | {ops_data['delayed_count']} delayed",
                    sentiment="positive" if ops_data['completion_rate_percent'] >= 60 else "warning"
                ))
                metric_cards.append(MetricCard(
                    label="Gross Margin",
                    value=f"{ops_data['gross_margin_percent']}%",
                    subtext=f"Profit: ${ops_data['gross_profit']:,.0f}",
                    sentiment="positive" if ops_data['gross_margin_percent'] >= 40 else "warning"
                ))
            elif is_dq and not is_pipeline and not is_ops:
                metric_cards.append(MetricCard(
                    label="Data Hygiene Score",
                    value=f"{dq_data['data_hygiene_score']}%",
                    subtext=f"{dq_data['total_issues']} issues across boards",
                    sentiment="positive" if dq_data['data_hygiene_score'] >= 90 else "warning"
                ))
            elif is_leadership or (is_pipeline and is_ops) or (not is_pipeline and not is_ops and not is_dq):
                # Comprehensive executive set
                metric_cards.append(MetricCard(
                    label="Total Pipeline",
                    value=f"${pipeline_data['total_pipeline_value']:,.0f}",
                    subtext=f"{pipeline_data['total_deals']} deals in scope",
                    sentiment="positive"
                ))
                metric_cards.append(MetricCard(
                    label="Win Rate",
                    value=f"{pipeline_data['win_rate_percent']}%",
                    subtext=f"${pipeline_data['won_value']:,.0f} closed won",
                    sentiment="positive" if pipeline_data['win_rate_percent'] >= 30 else "warning"
                ))
                metric_cards.append(MetricCard(
                    label="Work Orders",
                    value=f"{ops_data['total_work_orders']} Missions",
                    subtext=f"{ops_data['completion_rate_percent']}% completion rate",
                    sentiment="neutral"
                ))
                metric_cards.append(MetricCard(
                    label="Gross Margin",
                    value=f"{ops_data['gross_margin_percent']}%",
                    subtext=f"Profit: ${ops_data['gross_profit']:,.0f}",
                    sentiment="positive" if ops_data['gross_margin_percent'] >= 40 else "warning"
                ))
                metric_cards.append(MetricCard(
                    label="Data Hygiene",
                    value=f"{dq_data['data_hygiene_score']}%",
                    subtext=f"{dq_data['total_issues']} tracked caveats",
                    sentiment="positive" if dq_data['data_hygiene_score'] >= 90 else "warning"
                ))

        # Generate answer via LLM (Groq) with dynamic context
        answer = None
        if self.groq_api_key and self.groq_api_key.strip() and not self.groq_api_key.startswith("gsk_your"):
            try:
                answer = await self._call_groq_llm(
                    query=query,
                    detected_sector=detected_sector,
                    pipeline_data=pipeline_data,
                    ops_data=ops_data,
                    dq_data=dq_data,
                    caveats=caveats,
                    history=history,
                    is_greeting=is_greeting
                )
                tools_used.append("groq_conversational_synthesis")
            except Exception as e:
                logger.error(f"Groq LLM execution failed: {e}")

        # Intelligent natural fallback if LLM key is absent or errored
        if not answer:
            answer = self._generate_dynamic_narrative(
                query=query,
                sector=detected_sector,
                pipeline=pipeline_data,
                ops=ops_data,
                dq=dq_data,
                is_greeting=is_greeting,
                is_pipeline=is_pipeline,
                is_ops=is_ops,
                is_dq=is_dq,
                is_leadership=is_leadership
            )

        exec_summary = (
            "I am ready to help you analyze sales pipeline, flight execution, sectoral demand, or leadership briefing data."
            if is_greeting else
            f"Pipeline: ${pipeline_data['total_pipeline_value']:,.0f} (Weighted: ${pipeline_data['weighted_pipeline_value']:,.0f}) | Operations: {ops_data['total_work_orders']} work orders with {ops_data['completion_rate_percent']}% completion rate and {ops_data['gross_margin_percent']}% gross margin."
        )

        return AskResponse(
            answer=answer,
            executive_summary=exec_summary,
            metrics=metric_cards,
            data_quality_caveats=caveats if not is_greeting else [],
            assumptions_made=[
                "Metrics are calculated directly from synchronized Monday.com records stored in Neon PostgreSQL.",
                "Incomplete or unparseable entries are preserved with null-safe fallbacks rather than deleted."
            ] if not is_greeting else [],
            recommended_actions=[
                "Ask about a specific sector (e.g. 'How is Energy pipeline looking?').",
                "Ask about operational bottlenecks or delayed flight missions.",
                "Ask for a comprehensive leadership briefing update."
            ],
            tools_used=tools_used,
            raw_data_summary={
                "pipeline": pipeline_data,
                "operations": ops_data,
                "data_quality": {
                    "hygiene_score": dq_data["data_hygiene_score"],
                    "total_issues": dq_data["total_issues"]
                }
            }
        )

    async def _call_groq_llm(
        self,
        query: str,
        detected_sector: Optional[str],
        pipeline_data: dict,
        ops_data: dict,
        dq_data: dict,
        caveats: List[str],
        history: Optional[List[Dict[str, Any]]],
        is_greeting: bool
    ) -> str:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=self.groq_api_key)

        system_prompt = """You are the Lead Business Intelligence AI Partner for Skylark Drones.
You speak directly with founders, executives, and department leads.

GUIDELINES:
1. Tone & Style:
   - Be helpful, conversational, articulate, and founder-focused.
   - For greetings or general inquiries, respond naturally and warmly. Explain what you can do without technical error jargon.
   - For business questions, answer with mathematical precision using the provided structured calculations.
2. Structure & Formatting:
   - Use clean GitHub markdown with crisp bold headers and concise bullet points.
   - Focus directly on the user's specific question (e.g., if they asked about pipeline, focus on pipeline; if they asked about operations, focus on operations).
   - When leadership updates are requested, synthesize commercial wins, flight execution velocity, key bottlenecks, and data hygiene.
   - Always mention material data-quality caveats when presenting numbers.
3. Truthfulness:
   - Never invent imaginary revenue or work order numbers. Ground all figures strictly in the provided data.
"""

        user_content = {
            "user_query": query,
            "detected_sector": detected_sector or "All Sectors",
            "is_greeting": is_greeting,
            "data_context": {
                "pipeline_metrics": pipeline_data,
                "operations_metrics": ops_data,
                "data_quality_summary": dq_data,
                "active_caveats": caveats
            }
        }

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for turn in history[-4:]:
                if turn.get("type") == "user":
                    messages.append({"role": "user", "content": turn.get("text", "")})
                elif turn.get("type") == "agent":
                    messages.append({"role": "assistant", "content": turn.get("text", "")})

        messages.append({"role": "user", "content": json.dumps(user_content, default=str)})

        response = await client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature=0.2,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def _generate_dynamic_narrative(
        self,
        query: str,
        sector: Optional[str],
        pipeline: dict,
        ops: dict,
        dq: dict,
        is_greeting: bool,
        is_pipeline: bool,
        is_ops: bool,
        is_dq: bool,
        is_leadership: bool
    ) -> str:
        if is_greeting:
            return """👋 **Hello! I am your Skylark Drones Business Intelligence Agent.**

I continuously analyze your live **Monday.com Work Orders** and **Deals Funnel** boards synchronized in our **Neon PostgreSQL** analytical cache.

### Here is what you can ask me:
- **Commercial Pipeline:** *"How is our sales pipeline looking for the Energy sector this quarter?"*
- **Flight Operations & Delivery:** *"What is our work order completion rate and backlog?"*
- **Financial Margins:** *"What is our gross operating profit margin across drone missions?"*
- **Leadership Briefing:** *"Prepare data for our upcoming executive leadership update."*
- **Data Quality Audit:** *"What data quality issues exist across our Monday boards?"*

What would you like to explore first?"""

        sec_title = f" for the **{sector} Sector**" if sector else ""

        if is_pipeline and not is_ops and not is_leadership:
            top_stages = []
            for stg, data in pipeline.get("stages", {}).items():
                if data.get("count", 0) > 0:
                    top_stages.append(f"- **{stg}:** {data['count']} deals (${data['value']:,.0f})")
            stages_md = "\n".join(top_stages) if top_stages else "- No deals in stage breakdown."

            return f"""### 💼 Sales Pipeline & Commercial Velocity{sec_title}

- **Total Pipeline Value:** **${pipeline['total_pipeline_value']:,.0f}** across **{pipeline['total_deals']}** opportunities.
- **Probability-Weighted Value:** **${pipeline['weighted_pipeline_value']:,.0f}**
- **Win Rate:** **{pipeline['win_rate_percent']}%** (${pipeline['won_value']:,.0f} Won vs ${pipeline['lost_value']:,.0f} Lost).

#### 📊 Pipeline Stage Breakdown:
{stages_md}

#### 💡 Commercial Insights:
- Pipeline conversion shows active deals progressing through qualification and proposal stages.
- Energy and Mining sectors represent the primary pipeline volume drivers."""

        elif is_ops and not is_pipeline and not is_leadership:
            return f"""### 🚁 Drone Operations & Flight Execution{sec_title}

- **Total Missions Tracked:** **{ops['total_work_orders']} Work Orders**
- **Total Contracted Value:** **${ops['total_contract_value']:,.0f}**
- **Completion Rate:** **{ops['completion_rate_percent']}%** ({ops['completed_count']} Completed | {ops['delayed_count']} Delayed | {ops['in_progress_count']} In Progress)
- **Gross Operating Margin:** **{ops['gross_margin_percent']}%** (Gross Profit: **${ops['gross_profit']:,.0f}**)

#### 🔍 Operational Bottleneck & Pilot Assessment:
- {ops['completed_count']} drone missions have been fully delivered and signed off.
- Pilot coverage should be prioritized for upcoming scheduled and active flight operations."""

        elif is_dq:
            return f"""### 🛡️ Data Quality & Hygiene Audit Report

- **Overall Data Hygiene Score:** **{dq['data_hygiene_score']}%** across {dq['total_work_orders']} Work Orders and {dq['total_deals']} Deals.
- **Total Detected Caveats:** **{dq['total_issues']}** (High Severity: {dq['high_severity_count']}, Medium Severity: {dq['medium_severity_count']}, Low: {dq['low_severity_count']}).

#### Key Quality Findings:
- **Missing / Unparseable Dates:** {dq['issues_by_type'].get('MISSING_DATE', 0) + dq['issues_by_type'].get('INVALID_DATE', 0)}
- **Invalid / Corrupted Financial Amounts:** {dq['issues_by_type'].get('INVALID_AMOUNT', 0)}
- **Unassigned Flight Leads / Pilots:** {dq['issues_by_type'].get('UNASSIGNED_PILOT', 0)}"""

        else:
            return f"""### 📊 Skylark Drones — Executive Leadership Update{sec_title}

#### 🚀 1. Topline Commercial Highlights
- **Total Pipeline:** **${pipeline['total_pipeline_value']:,.0f}** across **{pipeline['total_deals']}** tracked opportunities (Weighted: **${pipeline['weighted_pipeline_value']:,.0f}**).
- **Deals Win Rate:** **{pipeline['win_rate_percent']}%** (${pipeline['won_value']:,.0f} Won vs ${pipeline['lost_value']:,.0f} Lost).

#### 🚁 2. Flight Operations & Velocity
- **Work Orders:** **{ops['total_work_orders']} active/completed missions** (${ops['total_contract_value']:,.0f} contracted value).
- **Execution Completion Rate:** **{ops['completion_rate_percent']}%** with a **{ops['gross_margin_percent']}%** gross operating margin (**${ops['gross_profit']:,.0f}** profit).

#### ⚠️ 3. Operational Risks & Data Hygiene
- **Data Hygiene Score:** **{dq['data_hygiene_score']}%** ({dq['total_issues']} identified data quality caveats across Monday boards).
- **Leadership Recommendations:** Unblock pilot capacity allocations and verify stage close dates on high-value open proposals."""

bi_agent = SkylarkBIAgent()
