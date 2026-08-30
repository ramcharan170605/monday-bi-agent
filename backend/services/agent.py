import json
import logging
import re
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.models.schemas import AskResponse, MetricCard

logger = logging.getLogger(__name__)


SECTORS = {
    "energy": "Energy",
    "mining": "Mining",
    "infrastructure": "Infrastructure",
    "infra": "Infrastructure",
    "telecom": "Telecom",
    "agriculture": "Agriculture",
    "geospatial": "Geospatial",
}

BI_KEYWORDS = {
    "pipeline", "deal", "sales", "funnel", "close", "won", "lost", "win",
    "forecast", "revenue", "sector", "margin", "profit", "cost", "work order",
    "flight", "drone", "operation", "delivery", "backlog", "delay", "pilot",
    "completion", "quality", "hygiene", "missing", "invalid", "audit",
    "leadership", "update", "executive", "briefing", "board meeting",
}

CAPABILITY_PATTERNS = [
    r"\bwhat can (i|we) (ask|do|get)\b",
    r"\bhow (can|do) you help\b",
    r"\bwhat (are you|is this)\b",
    r"\bhelp\b",
]

FOLLOW_UP_PATTERNS = [
    r"^\s*(is that so|really|are you sure|why|how so|explain|tell me more|what do you mean)\??\s*$",
    r"^\s*(yes|no|ok|okay|got it|thanks)\.?\s*$",
    r"\b(summarize|summarise|summary|recap|tl;?dr|few lines|short version|make it concise|condense)\b",
]


class SkylarkBIAgent:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self._conversation_state: Dict[str, Dict[str, Any]] = {}

    async def answer_query(self, db: Session, query: str, session_id: str = "default") -> AskResponse:
        """
        Uses a query-planning step before any BI calculations are selected.

        The LLM is allowed to classify intent and synthesize the final response,
        but SQL/Python tools remain the only source for numerical BI metrics.
        """
        session_key = session_id or "default"
        previous = self._conversation_state.get(session_key)
        plan = await self._build_query_plan(query, previous)
        tools_used = plan.pop("tools_used", [])

        if plan["intent"] == "capability":
            response = self._capability_response()
            self._remember(session_key, query, response, plan, response.raw_data_summary or {})
            return response

        if plan["intent"] == "follow_up" and previous:
            response = await self._answer_follow_up(query, previous)
            self._remember(session_key, query, response, plan, previous.get("raw_data_summary") or {})
            return response

        if plan["intent"] == "clarify":
            response = self._clarifying_response(query)
            self._remember(session_key, query, response, plan, response.raw_data_summary or {})
            return response

        sector = plan.get("sector")
        needs_pipeline = bool(plan.get("needs_pipeline"))
        needs_ops = bool(plan.get("needs_operations"))
        needs_dq = bool(plan.get("needs_data_quality"))
        is_leadership = bool(plan.get("wants_leadership_update"))

        if is_leadership:
            needs_pipeline = needs_ops = needs_dq = True

        pipeline_data = None
        ops_data = None
        dq_data = None
        caveats: List[str] = []

        if needs_pipeline:
            pipeline_data = analytics_engine.get_pipeline_metrics(db, sector=sector)
            tools_used.append("calculate_pipeline_metrics")

        if needs_ops:
            ops_data = analytics_engine.get_operations_metrics(db, sector=sector)
            tools_used.append("calculate_operations_metrics")

        if needs_dq or needs_pipeline or needs_ops:
            dq_data = data_quality_service.get_data_quality_summary(db)
            caveats = data_quality_service.generate_contextual_caveats(db, sector=sector)
            tools_used.append("get_data_quality_report")

        metric_cards = self._build_metric_cards(pipeline_data, ops_data, dq_data, needs_pipeline, needs_ops, needs_dq)
        assumptions = self._build_assumptions(sector)

        raw_data_summary = {
            "plan": plan,
            "pipeline": pipeline_data,
            "operations": ops_data,
            "data_quality": {
                "hygiene_score": dq_data["data_hygiene_score"],
                "total_issues": dq_data["total_issues"],
            } if dq_data else None,
        }

        answer = None
        if self.groq_api_key and self.groq_api_key.strip():
            try:
                answer = await self._call_groq_llm(
                    query=query,
                    plan=plan,
                    pipeline_data=pipeline_data,
                    ops_data=ops_data,
                    dq_data=dq_data,
                    caveats=caveats,
                    previous=previous,
                )
                tools_used.append("groq_executive_synthesis")
            except Exception as e:
                logger.error(f"Groq LLM call failed, falling back to deterministic answer: {e}")

        if not answer:
            answer = self._generate_deterministic_narrative(query, plan, pipeline_data, ops_data, dq_data)

        exec_summary = self._executive_summary(pipeline_data, ops_data, dq_data)
        response = AskResponse(
            answer=answer,
            executive_summary=exec_summary,
            metrics=metric_cards,
            data_quality_caveats=caveats,
            assumptions_made=assumptions,
            recommended_actions=self._recommended_actions(plan),
            tools_used=self._dedupe(tools_used),
            raw_data_summary=raw_data_summary,
        )
        self._remember(session_key, query, response, plan, raw_data_summary)
        return response

    async def _build_query_plan(self, query: str, previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        q_lower = query.lower().strip()
        heuristic = self._heuristic_plan(query, previous)

        if not self.groq_api_key or not self.groq_api_key.strip():
            return heuristic

        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=self.groq_api_key)
            system = (
                "Classify the user's query for a BI agent over Monday.com Deals and Work Orders. "
                "Return only compact JSON. Do not calculate metrics. "
                "Valid intent values: capability, follow_up, clarify, bi. "
                "If the user asks to summarize, recap, shorten, verify, explain, or continue a previous answer, "
                "classify it as follow_up when previous context exists. "
                "Set booleans for needs_pipeline, needs_operations, needs_data_quality, "
                "wants_leadership_update. sector may be Energy, Mining, Infrastructure, "
                "Telecom, Agriculture, Geospatial, or null."
            )
            previous_hint = None
            if previous:
                previous_hint = {
                    "last_user_query": previous.get("query"),
                    "last_intent": previous.get("plan", {}).get("intent"),
                    "last_summary": previous.get("response", {}).get("executive_summary"),
                }
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"query": query, "previous": previous_hint})},
            ]
            result = await client.chat.completions.create(
                messages=messages,
                model=self.model,
                temperature=0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(result.choices[0].message.content)
            plan = self._coerce_plan(parsed, heuristic)
            plan["tools_used"] = ["groq_intent_planner"]
            return plan
        except Exception as e:
            logger.warning(f"Groq intent planning failed; using heuristic plan: {e}")
            heuristic["tools_used"] = ["heuristic_intent_planner"]
            return heuristic

    def _heuristic_plan(self, query: str, previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        q_lower = query.lower().strip()
        sector = next((canonical for token, canonical in SECTORS.items() if token in q_lower), None)

        if any(re.search(pattern, q_lower) for pattern in CAPABILITY_PATTERNS):
            intent = "capability"
        elif previous and any(re.search(pattern, q_lower) for pattern in FOLLOW_UP_PATTERNS):
            intent = "follow_up"
        elif not any(keyword in q_lower for keyword in BI_KEYWORDS):
            intent = "clarify"
        else:
            intent = "bi"

        is_leadership = any(w in q_lower for w in ["leadership", "update", "executive", "briefing", "summary", "board meeting"])
        wants_pipeline = any(w in q_lower for w in ["pipeline", "deal", "sales", "funnel", "close", "won", "lost", "win", "forecast", "revenue", "sector"])
        wants_ops = any(w in q_lower for w in ["work order", "flight", "drone", "operation", "delivery", "backlog", "delay", "cost", "margin", "pilot", "completion"])
        wants_dq = any(w in q_lower for w in ["quality", "hygiene", "missing", "invalid", "caveat", "clean", "error", "audit"])

        if intent == "bi" and not (wants_pipeline or wants_ops or wants_dq or is_leadership):
            wants_pipeline = wants_ops = True

        return {
            "intent": intent,
            "sector": sector,
            "needs_pipeline": intent == "bi" and (wants_pipeline or is_leadership),
            "needs_operations": intent == "bi" and (wants_ops or is_leadership),
            "needs_data_quality": intent == "bi" and (wants_dq or is_leadership),
            "wants_leadership_update": intent == "bi" and is_leadership,
            "confidence": 0.65,
            "reason": "Heuristic keyword and conversation-context planner.",
            "tools_used": ["heuristic_intent_planner"],
        }

    def _coerce_plan(self, parsed: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        intent = parsed.get("intent")
        if intent not in {"capability", "follow_up", "clarify", "bi"}:
            intent = fallback["intent"]
        if fallback.get("intent") == "follow_up" and intent in {"clarify", "bi"}:
            intent = "follow_up"

        sector = parsed.get("sector")
        if sector not in set(SECTORS.values()):
            sector = fallback.get("sector")

        if intent in {"capability", "clarify", "follow_up"}:
            return {
                "intent": intent,
                "sector": sector,
                "needs_pipeline": False,
                "needs_operations": False,
                "needs_data_quality": False,
                "wants_leadership_update": False,
                "confidence": float(parsed.get("confidence") or fallback.get("confidence") or 0.7),
                "reason": parsed.get("reason") or fallback.get("reason"),
            }

        needs_pipeline = bool(parsed.get("needs_pipeline"))
        needs_operations = bool(parsed.get("needs_operations"))
        needs_data_quality = bool(parsed.get("needs_data_quality"))
        wants_leadership = bool(parsed.get("wants_leadership_update"))

        if wants_leadership:
            needs_pipeline = needs_operations = needs_data_quality = True
        if not (needs_pipeline or needs_operations or needs_data_quality):
            needs_pipeline = fallback.get("needs_pipeline", False)
            needs_operations = fallback.get("needs_operations", False)
            needs_data_quality = fallback.get("needs_data_quality", False)

        return {
            "intent": "bi",
            "sector": sector,
            "needs_pipeline": needs_pipeline,
            "needs_operations": needs_operations,
            "needs_data_quality": needs_data_quality,
            "wants_leadership_update": wants_leadership,
            "confidence": float(parsed.get("confidence") or 0.8),
            "reason": parsed.get("reason") or "Groq model classified the analytical intent.",
        }

    def _capability_response(self) -> AskResponse:
        return AskResponse(
            answer=(
                "I can answer founder-level questions over the live Monday.com Deals and Work Orders boards, "
                "then ground the numbers in Neon/PostgreSQL calculations before I summarize them.\n\n"
                "**Good questions to ask:**\n"
                "- How is our Energy sector pipeline this quarter?\n"
                "- What is our work order backlog and completion rate?\n"
                "- Which sectors have strong pipeline but weak execution coverage?\n"
                "- What data quality issues could distort leadership reporting?\n"
                "- Prepare a leadership update for the board.\n\n"
                "For numerical answers, I use structured metrics instead of lexical matching or embeddings. "
                "When the data is incomplete, I will call that out rather than pretending the numbers are cleaner than they are."
            ),
            executive_summary="Ask about pipeline, revenue, sectors, operations, backlog, margins, data quality, or leadership updates.",
            metrics=[],
            data_quality_caveats=[],
            assumptions_made=[],
            recommended_actions=[
                "Try a sector-specific pipeline question.",
                "Ask for an operational backlog or data-quality audit.",
                "Request a leadership update when you need an executive-ready summary.",
            ],
            tools_used=["groq_intent_planner" if self.groq_api_key else "heuristic_intent_planner"],
            raw_data_summary={"intent": "capability"},
        )

    async def _answer_follow_up(self, query: str, previous: Dict[str, Any]) -> AskResponse:
        previous_response = previous.get("response") or {}
        previous_answer = previous_response.get("answer") or ""
        last_summary = previous_response.get("executive_summary") or "the previous answer"
        q_lower = query.lower()
        raw_data_summary = previous.get("raw_data_summary") or {}

        if any(token in q_lower for token in ["summarize", "summarise", "summary", "recap", "tl;dr", "tldr", "few lines", "short version", "condense"]):
            answer = await self._summarize_previous_answer(query, previous_answer, raw_data_summary, last_summary)
        elif any(token in q_lower for token in ["why", "how so", "explain", "tell me more", "what do you mean"]):
            answer = await self._explain_previous_answer(query, previous_answer, raw_data_summary, last_summary)
        else:
            answer = (
                f"Yes. The short version is: {last_summary}\n\n"
                "That response came from the agent's structured calculation tools and was then synthesized by the LLM. "
                "The caveat is that the underlying Monday data still has quality issues, so client matching, dates, and sector labels should be treated as decision-support signals rather than perfectly audited finance numbers.\n\n"
                "I can drill into any one part next: pipeline risk, sector demand, work-order execution, margin, or data hygiene."
            )

        return AskResponse(
            answer=answer,
            executive_summary=last_summary,
            metrics=[],
            data_quality_caveats=previous_response.get("data_quality_caveats", [])[:4],
            assumptions_made=previous_response.get("assumptions_made", [])[:4],
            recommended_actions=["Ask a more specific follow-up to run a fresh metric calculation."],
            tools_used=["conversation_follow_up"],
            raw_data_summary=previous.get("raw_data_summary"),
        )

    async def _summarize_previous_answer(
        self,
        query: str,
        previous_answer: str,
        raw_data_summary: Dict[str, Any],
        last_summary: str,
    ) -> str:
        if self.groq_api_key and self.groq_api_key.strip() and previous_answer:
            try:
                from groq import AsyncGroq

                client = AsyncGroq(api_key=self.groq_api_key)
                response = await client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Summarize the previous BI answer in 3-5 crisp executive lines. "
                                "Keep the most important computed numbers exactly as provided. "
                                "Include one caveat if material. Do not ask a clarifying question."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps({
                                "user_follow_up": query,
                                "previous_answer": previous_answer,
                                "previous_computed_context": raw_data_summary,
                            }, default=str),
                        },
                    ],
                    model=self.model,
                    temperature=0.1,
                    max_tokens=450,
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Groq follow-up summary failed; using deterministic summary: {e}")

        return self._deterministic_previous_summary(raw_data_summary, last_summary, previous_answer)

    async def _explain_previous_answer(
        self,
        query: str,
        previous_answer: str,
        raw_data_summary: Dict[str, Any],
        last_summary: str,
    ) -> str:
        if self.groq_api_key and self.groq_api_key.strip() and previous_answer:
            try:
                from groq import AsyncGroq

                client = AsyncGroq(api_key=self.groq_api_key)
                response = await client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Explain the previous BI answer like a practical founder briefing. "
                                "Connect the metrics to business meaning. Keep numbers grounded in the provided context. "
                                "Do not introduce new calculations."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps({
                                "user_follow_up": query,
                                "previous_answer": previous_answer,
                                "previous_computed_context": raw_data_summary,
                            }, default=str),
                        },
                    ],
                    model=self.model,
                    temperature=0.15,
                    max_tokens=700,
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Groq follow-up explanation failed; using deterministic explanation: {e}")

        return (
            f"The previous answer means: {last_summary}\n\n"
            "The agent first selected the relevant BI tools, then calculated metrics from the normalized Monday.com cache. "
            "The LLM's job was to explain the implications, not to make up the numbers."
        )

    def _deterministic_previous_summary(self, raw_data_summary: Dict[str, Any], last_summary: str, previous_answer: str = "") -> str:
        pipeline = raw_data_summary.get("pipeline")
        ops = raw_data_summary.get("operations")
        dq = raw_data_summary.get("data_quality")
        lines = []
        if pipeline:
            lines.append(
                f"- Pipeline is ${pipeline['total_pipeline_value']:,.0f} total and ${pipeline['weighted_pipeline_value']:,.0f} weighted, with a {pipeline['win_rate_percent']}% win rate."
            )
        if ops:
            lines.append(
                f"- Operations show {ops['total_work_orders']} work orders, {ops['completion_rate_percent']}% completion, and {ops['gross_margin_percent']}% gross margin."
            )
        if dq:
            lines.append(
                f"- Data hygiene is {dq['hygiene_score']}%, with {dq['total_issues']} tracked caveats that should be disclosed in leadership reporting."
            )
        if not lines:
            if raw_data_summary.get("intent") == "capability":
                return (
                    "- I can answer questions about pipeline, revenue, sectors, operations, backlog, margins, and data quality.\n"
                    "- I calculate numbers from Monday.com data cached in Neon/PostgreSQL, then use the LLM to explain the business meaning.\n"
                    "- I will flag caveats when dates, client names, sectors, or operational records are incomplete."
                )
            clean_answer = re.sub(r"\s+", " ", previous_answer or "").strip()
            if clean_answer:
                lines.append(f"- {clean_answer[:320].rstrip()}")
            else:
                lines.append(f"- {last_summary}")
        return "\n".join(lines)

    def _clarifying_response(self, query: str) -> AskResponse:
        return AskResponse(
            answer=(
                "I do not want to force a BI dashboard answer onto that prompt. "
                "Can you point me at the business slice you want: pipeline, revenue, sector performance, work orders, backlog, margin, or data quality?\n\n"
                "For example: **How is the Energy sector pipeline this quarter?** or "
                "**What operational blockers should leadership know about?**"
            ),
            executive_summary="Clarification needed before running BI calculations.",
            metrics=[],
            data_quality_caveats=[],
            assumptions_made=[],
            recommended_actions=["Rephrase with a BI topic such as pipeline, operations, sector, revenue, or data quality."],
            tools_used=["intent_clarification"],
            raw_data_summary={"intent": "clarify", "query": query},
        )

    async def _call_groq_llm(
        self,
        query: str,
        plan: Dict[str, Any],
        pipeline_data: Optional[dict],
        ops_data: Optional[dict],
        dq_data: Optional[dict],
        caveats: List[str],
        previous: Optional[Dict[str, Any]],
    ) -> str:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=self.groq_api_key)
        prompt = {
            "user_question": query,
            "intent_plan": plan,
            "assignment_interpretation": (
                "In this Skylark Drones assignment, 'leadership update', 'board update', "
                "or 'updates for leadership' means an executive BI briefing about sales pipeline, "
                "operations, risks, and data quality. It does not mean corporate leadership changes, "
                "board-member announcements, appointments, resignations, or governance news unless the user explicitly asks for those."
            ),
            "computed_pipeline_metrics": pipeline_data,
            "computed_operations_metrics": ops_data,
            "computed_data_quality_metrics": dq_data,
            "active_caveats": caveats,
            "previous_summary": (previous or {}).get("response", {}).get("executive_summary"),
        }

        response = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Skylark Drones' production BI agent. "
                        "Use only the provided computed metrics for numbers. "
                        "Do not repeat a generic executive briefing unless the user asked for one. "
                        "If the question is narrow, answer narrowly. Always mention material caveats. "
                        "Do not use markdown tables; the hosted UI renders compact bullets and headings more reliably. "
                        "Use short labeled bullet groups for metrics, stage breakdowns, caveats, and recommendations. "
                        "For leadership updates, do not just list metrics. Produce a board-ready decision brief with: "
                        "1) headline judgment, 2) what changed or matters, 3) risks/blockers, 4) decisions or asks for leadership, "
                        "5) data-quality caveats. Tie pipeline and operations together when both are provided. "
                        "Never interpret 'leadership update' or 'board update' as personnel, governance, or board-member news in this app; "
                        "it is an executive business update over the Monday.com Work Orders and Deals data."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, default=str)},
            ],
            model=self.model,
            temperature=0.15,
            max_tokens=1200,
        )
        return response.choices[0].message.content

    def _generate_deterministic_narrative(
        self,
        query: str,
        plan: Dict[str, Any],
        pipeline: Optional[dict],
        ops: Optional[dict],
        dq: Optional[dict],
    ) -> str:
        sector = plan.get("sector")
        title = f" for the **{sector} Sector**" if sector else ""

        if plan.get("wants_leadership_update"):
            ops_risk = (
                f"{ops['delayed_count']} delayed missions need review"
                if ops["delayed_count"] > 0
                else "execution delay count is currently zero, but pilot coverage and handoffs still need monitoring"
            )
            leadership_ask = (
                "unblock delayed missions"
                if ops["delayed_count"] > 0
                else "protect pilot capacity for active and upcoming work orders"
            )
            return (
                f"## Leadership Update{title}\n\n"
                f"**Headline judgment:** Demand is large, but conversion quality needs attention: "
                f"${pipeline['total_pipeline_value']:,.0f} total pipeline is carrying only "
                f"${pipeline['weighted_pipeline_value']:,.0f} weighted value and a {pipeline['win_rate_percent']}% win rate.\n\n"
                f"**Commercial picture:** {pipeline['total_deals']} deals are in scope, with "
                f"${pipeline['won_value']:,.0f} won versus ${pipeline['lost_value']:,.0f} lost. "
                f"Leadership should focus on whether large early-stage opportunities are real near-term revenue or inflated pipeline.\n\n"
                f"**Operational readiness:** {ops['total_work_orders']} work orders represent "
                f"${ops['total_contract_value']:,.0f} contracted value. Execution is healthy at "
                f"{ops['completion_rate_percent']}% completion and {ops['gross_margin_percent']}% gross margin, "
                f"and {ops_risk}.\n\n"
                f"**Leadership asks:** Confirm owners and next actions for high-value open deals, {leadership_ask}, "
                f"and clean the records most likely to distort board reporting.\n\n"
                f"**Data caveat:** {dq['total_issues']} quality issues are tracked with a "
                f"{dq['data_hygiene_score']}% hygiene score, so this should be treated as operational BI, not audited finance."
            )

        sections = [f"## Business Intelligence Answer{title}"]
        if pipeline:
            sections.append(
                f"**Pipeline:** ${pipeline['total_pipeline_value']:,.0f} total value, "
                f"${pipeline['weighted_pipeline_value']:,.0f} weighted value, "
                f"{pipeline['win_rate_percent']}% win rate."
            )
        if ops:
            sections.append(
                f"**Operations:** {ops['total_work_orders']} work orders, "
                f"{ops['completion_rate_percent']}% completion, "
                f"{ops['delayed_count']} delayed, {ops['gross_margin_percent']}% gross margin."
            )
        if dq:
            sections.append(
                f"**Data quality:** {dq['total_issues']} issues detected; hygiene score is {dq['data_hygiene_score']}%."
            )
        sections.append("Numbers above come from structured calculations over the synchronized Monday.com cache.")
        return "\n\n".join(sections)

    def _build_metric_cards(
        self,
        pipeline: Optional[dict],
        ops: Optional[dict],
        dq: Optional[dict],
        include_pipeline: bool,
        include_ops: bool,
        include_dq: bool,
    ) -> List[MetricCard]:
        cards: List[MetricCard] = []
        if include_pipeline and pipeline:
            cards.extend([
                MetricCard(
                    label="Total Pipeline Value",
                    value=f"${pipeline['total_pipeline_value']:,.0f}",
                    subtext=f"{pipeline['total_deals']} deals in scope",
                    sentiment="positive" if pipeline["total_pipeline_value"] > 0 else "neutral",
                ),
                MetricCard(
                    label="Weighted Pipeline",
                    value=f"${pipeline['weighted_pipeline_value']:,.0f}",
                    subtext="Probability-adjusted value",
                    sentiment="neutral",
                ),
                MetricCard(
                    label="Deals Win Rate",
                    value=f"{pipeline['win_rate_percent']}%",
                    subtext=f"${pipeline['won_value']:,.0f} won vs ${pipeline['lost_value']:,.0f} lost",
                    sentiment="positive" if pipeline["win_rate_percent"] >= 50 else "warning",
                ),
            ])

        if include_ops and ops:
            cards.extend([
                MetricCard(
                    label="Work Orders",
                    value=f"{ops['total_work_orders']} Missions",
                    subtext=f"${ops['total_contract_value']:,.0f} contracted value",
                    sentiment="neutral",
                ),
                MetricCard(
                    label="Completion Rate",
                    value=f"{ops['completion_rate_percent']}%",
                    subtext=f"{ops['completed_count']} completed | {ops['delayed_count']} delayed",
                    sentiment="positive" if ops["completion_rate_percent"] >= 60 else "warning",
                ),
                MetricCard(
                    label="Gross Margin",
                    value=f"{ops['gross_margin_percent']}%",
                    subtext=f"Profit: ${ops['gross_profit']:,.0f}",
                    sentiment="positive" if ops["gross_margin_percent"] >= 40 else "warning",
                ),
            ])

        if include_dq and dq:
            cards.append(MetricCard(
                label="Data Hygiene Score",
                value=f"{dq['data_hygiene_score']}%",
                subtext=f"{dq['total_issues']} issues across boards",
                sentiment="positive" if dq["data_hygiene_score"] >= 80 else "warning",
            ))
        return cards

    def _build_assumptions(self, sector: Optional[str]) -> List[str]:
        assumptions = [
            "Numerical metrics are calculated from normalized Monday.com records stored in Neon PostgreSQL.",
            "Incomplete records are retained with null-safe fallbacks rather than deleted.",
            "Currency strings and mixed date formats are normalized before calculation.",
        ]
        if sector:
            assumptions.append(f"Sector filtering uses normalized sector labels matching '{sector}'.")
        return assumptions

    def _recommended_actions(self, plan: Dict[str, Any]) -> List[str]:
        if plan.get("needs_data_quality") and not (plan.get("needs_pipeline") or plan.get("needs_operations")):
            return [
                "Fix high-severity records first: invalid values, missing clients, and unparseable dates.",
                "Re-sync Monday.com after cleanup to refresh the analytical cache.",
            ]
        if plan.get("needs_operations"):
            return [
                "Review delayed or unassigned work orders before the next leadership review.",
                "Prioritize work orders tied to high-value won deals where client matching is strong.",
            ]
        return [
            "Inspect high-value open deals by stage and sector.",
            "Confirm close dates and probabilities for large opportunities before using the forecast externally.",
        ]

    def _executive_summary(self, pipeline: Optional[dict], ops: Optional[dict], dq: Optional[dict]) -> str:
        parts = []
        if pipeline:
            parts.append(
                f"Pipeline: ${pipeline['total_pipeline_value']:,.0f} total, ${pipeline['weighted_pipeline_value']:,.0f} weighted."
            )
        if ops:
            parts.append(
                f"Operations: {ops['completion_rate_percent']}% completion across {ops['total_work_orders']} work orders."
            )
        if dq:
            parts.append(f"Data hygiene: {dq['data_hygiene_score']}% with {dq['total_issues']} tracked issues.")
        return " ".join(parts) if parts else "No BI calculation was run for this prompt."

    def _remember(self, session_id: str, query: str, response: AskResponse, plan: Dict[str, Any], raw_data_summary: Dict[str, Any]) -> None:
        self._conversation_state[session_id] = {
            "query": query,
            "plan": plan,
            "response": response.model_dump(),
            "raw_data_summary": raw_data_summary,
        }

    @staticmethod
    def _dedupe(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out


bi_agent = SkylarkBIAgent()
