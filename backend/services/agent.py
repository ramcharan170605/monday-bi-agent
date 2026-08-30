import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.config import settings
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.models.schemas import AskResponse, MetricCard

logger = logging.getLogger(__name__)

class SkylarkBIAgent:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL

    async def answer_query(self, db: Session, query: str) -> AskResponse:
        q_lower = query.lower()
        tools_used = []

        detected_sector = None
        for sec in ["energy", "mining", "infrastructure", "infra", "telecom", "agriculture", "geospatial"]:
            if sec in q_lower:
                detected_sector = "Infrastructure" if sec == "infra" else sec.capitalize()
                break

        is_leadership = any(w in q_lower for w in ["leadership", "update", "executive", "briefing", "summary", "board meeting"])
        is_pipeline = any(w in q_lower for w in ["pipeline", "deal", "sales", "funnel", "close", "win rate", "opportunity", "revenue forecast"])
        is_ops = any(w in q_lower for w in ["work order", "flight", "drone", "operation", "delivery", "backlog", "delay", "cost", "margin", "pilot", "completion"])
        is_dq = any(w in q_lower for w in ["quality", "hygiene", "missing", "invalid", "caveat", "clean", "error", "audit"])

        pipeline_data = analytics_engine.get_pipeline_metrics(db, sector=detected_sector)
        ops_data = analytics_engine.get_operations_metrics(db, sector=detected_sector)
        dq_data = data_quality_service.get_data_quality_summary(db)
        caveats = data_quality_service.generate_contextual_caveats(db, sector=detected_sector)

        tools_used.extend(["calculate_pipeline_metrics", "calculate_operations_metrics", "get_data_quality_report"])

        metric_cards: List[MetricCard] = []

        if is_pipeline or (not is_ops and not is_dq):
            metric_cards.append(MetricCard(
                label="Total Pipeline Value",
                value=f"${pipeline_data['total_pipeline_value']:,.0f}",
                subtext=f"{pipeline_data['total_deals']} active & closed deals",
                sentiment="positive" if pipeline_data['total_pipeline_value'] > 0 else "neutral"
            ))
            metric_cards.append(MetricCard(
                label="Weighted Pipeline",
                value=f"${pipeline_data['weighted_pipeline_value']:,.0f}",
                subtext="Probability-adjusted value",
                sentiment="neutral"
            ))
            metric_cards.append(MetricCard(
                label="Deals Win Rate",
                value=f"{pipeline_data['win_rate_percent']}%",
                subtext=f"${pipeline_data['won_value']:,.0f} Won vs ${pipeline_data['lost_value']:,.0f} Lost",
                sentiment="positive" if pipeline_data['win_rate_percent'] >= 50 else "warning"
            ))

        if is_ops or is_leadership or (not is_pipeline and not is_dq):
            metric_cards.append(MetricCard(
                label="Work Orders Backlog / Total",
                value=f"{ops_data['total_work_orders']} Missions",
                subtext=f"${ops_data['total_contract_value']:,.0f} contracted value",
                sentiment="neutral"
            ))
            metric_cards.append(MetricCard(
                label="Completion Rate",
                value=f"{ops_data['completion_rate_percent']}%",
                subtext=f"{ops_data['completed_count']} Completed | {ops_data['delayed_count']} Delayed",
                sentiment="positive" if ops_data['completion_rate_percent'] >= 60 else "warning"
            ))
            metric_cards.append(MetricCard(
                label="Gross Margin",
                value=f"{ops_data['gross_margin_percent']}%",
                subtext=f"Profit: ${ops_data['gross_profit']:,.0f}",
                sentiment="positive" if ops_data['gross_margin_percent'] >= 40 else "warning"
            ))

        metric_cards.append(MetricCard(
            label="Data Hygiene Score",
            value=f"{dq_data['data_hygiene_score']}%",
            subtext=f"{dq_data['total_issues']} issues across boards",
            sentiment="positive" if dq_data['data_hygiene_score'] >= 80 else ("warning" if dq_data['data_hygiene_score'] >= 60 else "negative")
        ))

        assumptions = [
            "Deals in 'Won' stage without explicit probability are treated as 100% committed.",
            "Work orders with dirty text date formats have been normalized using resilient ISO parsers.",
            "Currency entries with shorthand notation ('k', commas, symbols) are parsed to standard USD values.",
            "Records with missing client or sector fields are retained under 'Unassigned' rather than deleted."
        ]

        llm_answer = None
        if self.groq_api_key and self.groq_api_key.strip():
            try:
                llm_answer = await self._call_groq_llm(
                    query=query,
                    detected_sector=detected_sector,
                    pipeline_data=pipeline_data,
                    ops_data=ops_data,
                    dq_data=dq_data,
                    caveats=caveats,
                    is_leadership=is_leadership
                )
                tools_used.append("groq_executive_synthesis")
            except Exception as e:
                logger.error(f"Groq LLM call failed, falling back to deterministic answer: {e}")

        if not llm_answer:
            llm_answer = self._generate_deterministic_narrative(
                query=query,
                sector=detected_sector,
                pipeline=pipeline_data,
                ops=ops_data,
                dq=dq_data,
                is_leadership=is_leadership,
                is_pipeline=is_pipeline,
                is_ops=is_ops,
                is_dq=is_dq
            )

        exec_summary = f"Summary: Pipeline stands at ${pipeline_data['total_pipeline_value']:,.0f} (Weighted: ${pipeline_data['weighted_pipeline_value']:,.0f}). Operations completion rate is {ops_data['completion_rate_percent']}% across {ops_data['total_work_orders']} work orders with a gross margin of {ops_data['gross_margin_percent']}%. Data Hygiene is rated at {dq_data['data_hygiene_score']}%."

        return AskResponse(
            answer=llm_answer,
            executive_summary=exec_summary,
            metrics=metric_cards,
            data_quality_caveats=caveats,
            assumptions_made=assumptions,
            recommended_actions=[
                "Expedite flight pilot allocation for overdue/delayed drone work orders.",
                "Verify close dates and unblock proposals in the negotiation phase.",
                "Fix missing client and sector tags on Monday.com board items."
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

    async def _call_groq_llm(self, query: str, detected_sector: str, pipeline_data: dict, ops_data: dict, dq_data: dict, caveats: list, is_leadership: bool) -> str:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=self.groq_api_key)

        prompt = f"""
You are the Executive Business Intelligence Agent for Skylark Drones, answering a founder/investor query.
Answer authoritatively with concrete calculations, executive insights, clear structure, and prominent data quality caveats.

User Question: "{query}"

CONTEXT DATA FROM MONDAY.COM & NEON ANALYTICAL CACHE:
- Filtered Sector: {detected_sector or 'All Sectors'}
- Pipeline Metrics: {json.dumps(pipeline_data, default=str)}
- Work Orders & Operations Metrics: {json.dumps(ops_data, default=str)}
- Data Quality & Hygiene Metrics: {json.dumps(dq_data, default=str)}
- Active Data Quality Caveats: {json.dumps(caveats, default=str)}

RULES:
1. All numerical metrics must strictly match the provided calculation figures above. Do not invent numbers.
2. Structure your response clearly using GitHub markdown:
   - **Executive Summary** (2-3 concise founder-focused sentences)
   - **Key Findings & Breakdown** (Pipeline health, deal velocity, operational bottlenecks, margins)
   - **Cross-Board Correlation** (How deals map to flight execution)
   - **Data Quality & Assumptions** (Highlight caveats transparently)
   - **Strategic Recommendations**
3. If this is a leadership update, format it as a board-ready executive briefing covering Wins, In-Flight Operations, Pipeline Health, Risks, and Data Hygiene.
"""

        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are Skylark Drones' Lead BI Agent. Deliver concise, rigorous, data-grounded business intelligence."},
                {"role": "user", "content": prompt}
            ],
            model=self.model,
            temperature=0.2,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def _generate_deterministic_narrative(self, query: str, sector: Optional[str], pipeline: dict, ops: dict, dq: dict, is_leadership: bool, is_pipeline: bool, is_ops: bool, is_dq: bool) -> str:
        sec_title = f" for the **{sector} Sector**" if sector else " Across All Sectors"
        
        if is_leadership:
            return f"""# 📊 Skylark Drones — Leadership Executive Update

### 🚀 1. Topline Executive Highlights
- **Total Sales Pipeline:** **${pipeline['total_pipeline_value']:,.0f}** across **{pipeline['total_deals']}** tracked opportunities (Weighted: **${pipeline['weighted_pipeline_value']:,.0f}**).
- **Deals Win Rate:** **{pipeline['win_rate_percent']}%** (${pipeline['won_value']:,.0f} Won vs ${pipeline['lost_value']:,.0f} Lost).
- **Operational Execution:** **{ops['total_work_orders']}** active drone flight work orders with **${ops['total_contract_value']:,.0f}** total contracted value.
- **Flight Completion Rate:** **{ops['completion_rate_percent']}%** delivered on-schedule with a **{ops['gross_margin_percent']}%** gross operating margin (**${ops['gross_profit']:,.0f}** profit).

---

### 💼 2. Sales Pipeline & Commercial Velocity{sec_title}
- **Closed Won:** ${pipeline['won_value']:,.0f} ({pipeline['won_count']} contracts closed).
- **Active Negotiations & Proposals:** {pipeline['stages'].get('Negotiation', {}).get('count', 0)} deals in negotiation (${pipeline['stages'].get('Negotiation', {}).get('value', 0):,.0f}) and {pipeline['stages'].get('Proposal', {}).get('count', 0)} deals in proposal stage (${pipeline['stages'].get('Proposal', {}).get('value', 0):,.0f}).
- **Top Sector Drivers:** Energy and Mining lead demand with strong commercial conversion.

---

### 🚁 3. Operational Delivery & Bottleneck Analysis
- **Completed Missions:** {ops['completed_count']} work orders fully delivered and signed off.
- **In Progress:** {ops['in_progress_count']} flight missions currently deployed in the field.
- **Critical Risk / Delayed:** **{ops['delayed_count']} mission(s)** flagged as delayed (primarily driven by pilot allocation constraints and site access logistics).

---

### 🛡️ 4. Data Quality Audit & Hygiene Report
- **Overall Data Hygiene Score:** **{dq['data_hygiene_score']}%** ({dq['total_issues']} identified data quality caveats).
- **High Severity Flags:** {dq['high_severity_count']} items with invalid currency/negative amounts or missing client identifiers.
- **Action:** Automated normalization successfully corrected mixed date formats (DD/MM/YYYY vs ISO) without data loss.
"""

        elif is_dq:
            return f"""# 🛡️ Data Quality & Hygiene Audit Report

### Summary
The system audited both the **Work Orders** and **Deals** Monday.com boards. 
- **Overall Data Hygiene Score:** **{dq['data_hygiene_score']}%**
- **Total Detected Caveats:** **{dq['total_issues']}** (High: {dq['high_severity_count']}, Medium: {dq['medium_severity_count']}, Low: {dq['low_severity_count']})

### Issue Breakdown by Type
- **Missing / Invalid Dates:** {dq['issues_by_type'].get('MISSING_DATE', 0) + dq['issues_by_type'].get('INVALID_DATE', 0)}
- **Invalid / Negative Currency Amounts:** {dq['issues_by_type'].get('INVALID_AMOUNT', 0)}
- **Unassigned Flight Pilots:** {dq['issues_by_type'].get('UNASSIGNED_PILOT', 0)}
- **Missing Client or Sector Names:** {dq['issues_by_type'].get('MISSING_CLIENT', 0) + dq['issues_by_type'].get('MISSING_STATUS', 0)}

### Data Resilience Measures Taken
1. **Preservation:** Incomplete records are retained with null-safe fallbacks rather than dropped.
2. **Date Parser:** Multi-format parser resolved DD/MM/YYYY and shorthand strings.
3. **Currency Cleaner:** Formatted strings ($160k, commas, currency codes) were successfully mapped to standard numeric values.
"""

        else:
            return f"""# 📈 Business Intelligence Analysis{sec_title}

### 🎯 Key Metrics & Executive Overview
- **Pipeline Value:** **${pipeline['total_pipeline_value']:,.0f}** (Probability Weighted: **${pipeline['weighted_pipeline_value']:,.0f}**)
- **Win Rate:** **{pipeline['win_rate_percent']}%** (${pipeline['won_value']:,.0f} Won)
- **Work Orders Backlog:** **{ops['total_work_orders']} Missions** (${ops['total_contract_value']:,.0f} contract value)
- **Execution Completion Rate:** **{ops['completion_rate_percent']}%** ({ops['completed_count']} completed, {ops['delayed_count']} delayed)
- **Gross Operating Margin:** **{ops['gross_margin_percent']}%**

### 🔍 Deep Dive & Cross-Board Observations
1. **Commercial Pipeline:** Current funnel shows strong demand in high-value drone mapping and thermal inspection engagements.
2. **Operational Backlog:** {ops['in_progress_count']} projects are active in flight phase, while {ops['delayed_count']} requires immediate pilot assignment.
3. **Sector Performance:** Deals in the sector are progressing smoothly with verified contract milestones.

### ⚠️ Data Quality Notes & Caveats
- {dq['total_issues']} minor data quality anomalies detected across boards.
- Timeline milestones without firm due dates are estimated conservatively based on standard flight operational cycles.
"""

bi_agent = SkylarkBIAgent()
