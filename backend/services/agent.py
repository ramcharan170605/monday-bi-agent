"""
Skylark Drones BI Agent — LLM-driven agentic architecture.

The LLM is the decision-maker.  It receives the user's natural-language
question, decides which database / API tools to invoke, executes them
against the Neon PostgreSQL cache and (optionally) the live Monday.com
GraphQL API, then synthesises a question-specific executive answer.

No lexical routing.  No keyword matching.  No hardcoded response templates.
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.database import (
    DataQualityIssueModel,
    DealModel,
    WorkOrderModel,
)
from backend.models.schemas import AskResponse
from backend.services.analytics import analytics_engine
from backend.services.data_quality import data_quality_service
from backend.services.monday_client import MondayClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serial(obj: Any) -> Any:
    """JSON fallback serialiser for Decimal / date / datetime."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI-compatible function-calling schema)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "query_deals",
            "description": (
                "Search and retrieve individual deal records from the sales "
                "pipeline stored in the Neon database.  Returns matching records "
                "together with aggregated totals (count, pipeline value, weighted "
                "value, won/lost split, win rate, stage breakdown).  "
                "Use this when the user asks about specific deals, clients in the "
                "pipeline, deal owners, or needs record-level detail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": (
                            "Sector filter.  Known values: Energy, Mining, "
                            "Infrastructure, Telecom, Agriculture, Geospatial, "
                            "Railways, Aviation, Manufacturing, "
                            "Security And Surveillance, DSP, Others"
                        ),
                    },
                    "stage": {
                        "type": "string",
                        "description": (
                            "Deal stage filter.  Known values: Won, Lost, "
                            "Proposal, Discovery, Negotiation, On Hold, "
                            "Project Completed"
                        ),
                    },
                    "client": {
                        "type": "string",
                        "description": "Client name search (partial match)",
                    },
                    "owner": {
                        "type": "string",
                        "description": "Deal owner name filter",
                    },
                    "min_value": {
                        "type": "number",
                        "description": "Minimum deal value threshold",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max sample records to return (default 12)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_work_orders",
            "description": (
                "Search and retrieve individual flight work-order / mission "
                "records from the Neon database.  Returns matching records with "
                "aggregated totals (count, contract value, actual cost, gross "
                "margin, completion rate, status breakdown).  "
                "Use this when the user asks about flight operations, project "
                "delivery, pilots, delayed missions, or record-level detail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Sector filter",
                    },
                    "status": {
                        "type": "string",
                        "description": (
                            "Status filter.  Known values: Completed, "
                            "In Progress, Delayed, Scheduled, Cancelled, On Hold"
                        ),
                    },
                    "client": {
                        "type": "string",
                        "description": "Client name search (partial match)",
                    },
                    "pilot": {
                        "type": "string",
                        "description": "Pilot / flight-lead name filter",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location filter",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max sample records to return (default 12)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_metrics",
            "description": (
                "Compute aggregated pipeline KPIs from all deals: total "
                "pipeline value, weighted pipeline value, win rate %, won/lost "
                "value split, stage-by-stage distribution, and sector-by-sector "
                "distribution.  Use for high-level pipeline health questions or "
                "sector-specific pipeline analysis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Optional sector to narrow the analysis",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_operations_metrics",
            "description": (
                "Compute aggregated operations KPIs from all work orders: "
                "total work-order count, total contract value vs actual cost, "
                "gross profit and margin %, completion rate, delay count, "
                "and status / sector breakdowns.  Use for operations health, "
                "efficiency, or profitability questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Optional sector to narrow the analysis",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_quality_report",
            "description": (
                "Retrieve data-quality / hygiene analysis: overall hygiene "
                "score, issue counts by severity (HIGH / MEDIUM / LOW), "
                "breakdown by issue type, contextual caveat strings, and "
                "specific flagged records with item names, fields, and raw "
                "values.  Use when the user asks about data issues, integrity, "
                "missing fields, corrupted values, or data health."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "board_type": {
                        "type": "string",
                        "description": "Filter issues by board: work_orders or deals",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Filter by severity: HIGH, MEDIUM, or LOW",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max flagged records (default 15)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_pipeline_vs_execution",
            "description": (
                "Cross-board analysis that compares the sales pipeline (deals) "
                "with project execution (work orders).  Returns pipeline "
                "volume vs delivery contract value, client overlap between "
                "the two boards, and margin analysis.  Use when the user asks "
                "to compare sales with delivery, or wants a holistic view of "
                "how the pipeline translates into operations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Optional sector filter for the comparison",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_monday_board_live",
            "description": (
                "Pull the freshest items directly from the Monday.com GraphQL "
                "API (source of truth), bypassing the Neon cache.  Use ONLY "
                "when the user explicitly asks for the latest / live data from "
                "Monday.com, or suspects the cached data might be stale."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "board_type": {
                        "type": "string",
                        "enum": ["deals", "work_orders"],
                        "description": "Which Monday.com board to query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max items to fetch (default 10)",
                    },
                },
                "required": ["board_type"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the lead Business Intelligence analyst for **Skylark Drones**, a
commercial drone-services company headquartered in India.  You speak
directly with the founders and C-suite.

You have access to tools that query two data stores in real time:

1. **Neon PostgreSQL** – a normalised analytical cache of two Monday.com
   boards:
   • Deals pipeline (≈ 346 deals): client, sector, deal stage, deal value,
     probability, weighted value, owner, expected / actual close dates.
   • Flight Work Orders (≈ 176 missions): client, sector, status, contract
     value, actual cost, pilot, location, start / due / completed dates.
   • Data-quality issues tracked per record.

2. **Monday.com GraphQL API** – the source of truth.  Use this only when
   freshness matters or the user explicitly asks for live data.

**Sectors in the data:** Energy, Mining, Infrastructure, Telecom,
Agriculture, Geospatial, Railways, Aviation, Manufacturing,
Security And Surveillance, DSP, Others.

---

### Your workflow

1. **Read the question carefully.**  Identify what the user actually wants
   to know (sector? status? comparison? client lookup? data quality?).
2. **Select and call the right tool(s).**  You may call *multiple* tools
   when the question spans both deals and operations.  Pass relevant
   filters (sector, status, client …) so results are focused.
3. **Analyse the returned data.**  Do the reasoning – don't just dump
   numbers.
4. **Compose a clear, insightful answer** in clean GitHub-flavoured
   Markdown.

### Tool-selection cheat sheet

| User intent | Tool(s) to call |
|---|---|
| Pipeline health / deals / win rate | `get_pipeline_metrics` and/or `query_deals` |
| Sector-specific pipeline | `get_pipeline_metrics(sector=…)` and `query_deals(sector=…)` |
| Operations / flights / margins | `get_operations_metrics` and/or `query_work_orders` |
| Delayed / in-progress missions | `query_work_orders(status=…)` |
| Compare sales vs delivery | `compare_pipeline_vs_execution` |
| Data quality / integrity | `get_data_quality_report` |
| Specific client lookup | `query_deals(client=…)` + `query_work_orders(client=…)` |
| Live Monday.com data | `fetch_monday_board_live` |
| Greeting / meta question | *no tool needed – reply conversationally* |

### Response rules

- Write clean Markdown with headers and bullet points where appropriate.
- Reference **specific** numbers, client names, deal names, and project
   names from the tool results.
- Note any data-quality caveats that could affect the analysis.
- Provide actionable insight, not a raw data dump.
- **Never** output raw JSON, code blocks, or tool-call syntax in the
  final answer.
- Keep the answer focused on what the user asked — do NOT append
  unrelated KPIs.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SkylarkBIAgent:
    """LLM-driven agentic BI – the model decides, the tools execute."""

    def __init__(self) -> None:
        self.groq_api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.monday = MondayClient()

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_query_deals(
        self, db: Session, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        sector = args.get("sector")
        stage = args.get("stage")
        client = args.get("client")
        owner = args.get("owner")
        min_value = args.get("min_value")
        limit = args.get("limit", 12)

        q = db.query(DealModel)
        if sector:
            q = q.filter(DealModel.normalized_sector.ilike(f"%{sector}%"))
        if stage:
            q = q.filter(DealModel.normalized_stage.ilike(f"%{stage}%"))
        if client:
            q = q.filter(
                or_(
                    DealModel.client_name.ilike(f"%{client}%"),
                    DealModel.normalized_client.ilike(f"%{client}%"),
                )
            )
        if owner:
            q = q.filter(DealModel.deal_owner.ilike(f"%{owner}%"))
        if min_value is not None:
            q = q.filter(DealModel.deal_value >= min_value)

        deals = q.all()

        total_val = sum(float(d.deal_value or 0) for d in deals)
        weighted_val = sum(float(d.weighted_value or 0) for d in deals)
        won = [d for d in deals if d.normalized_stage == "Won"]
        lost = [d for d in deals if d.normalized_stage == "Lost"]
        won_val = sum(float(d.deal_value or 0) for d in won)
        lost_val = sum(float(d.deal_value or 0) for d in lost)
        closed = won_val + lost_val
        win_rate = round(won_val / closed * 100, 1) if closed > 0 else 0.0

        stages: Dict[str, Dict[str, Any]] = {}
        for d in deals:
            s = d.normalized_stage or "Unknown"
            if s not in stages:
                stages[s] = {"count": 0, "value": 0.0}
            stages[s]["count"] += 1
            stages[s]["value"] += float(d.deal_value or 0)

        sample = [
            {
                "deal_name": d.deal_name,
                "client": d.client_name,
                "sector": d.normalized_sector,
                "stage": d.normalized_stage,
                "value": float(d.deal_value or 0),
                "weighted_value": float(d.weighted_value or 0),
                "owner": d.deal_owner,
                "expected_close": (
                    str(d.expected_close_date) if d.expected_close_date else None
                ),
            }
            for d in deals[:limit]
        ]

        return {
            "total_matching_deals": len(deals),
            "total_pipeline_value": total_val,
            "weighted_pipeline_value": weighted_val,
            "won_count": len(won),
            "won_value": won_val,
            "lost_count": len(lost),
            "lost_value": lost_val,
            "win_rate_percent": win_rate,
            "stage_breakdown": stages,
            "sample_deals": sample,
        }

    def _tool_query_work_orders(
        self, db: Session, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        sector = args.get("sector")
        status = args.get("status")
        client = args.get("client")
        pilot = args.get("pilot")
        location = args.get("location")
        limit = args.get("limit", 12)

        q = db.query(WorkOrderModel)
        if sector:
            q = q.filter(
                WorkOrderModel.normalized_sector.ilike(f"%{sector}%")
            )
        if status:
            q = q.filter(
                WorkOrderModel.normalized_status.ilike(f"%{status}%")
            )
        if client:
            q = q.filter(
                or_(
                    WorkOrderModel.client_name.ilike(f"%{client}%"),
                    WorkOrderModel.normalized_client.ilike(f"%{client}%"),
                )
            )
        if pilot:
            q = q.filter(
                WorkOrderModel.assigned_pilot_or_lead.ilike(f"%{pilot}%")
            )
        if location:
            q = q.filter(WorkOrderModel.location.ilike(f"%{location}%"))

        orders = q.all()

        total_contract = sum(
            float(w.contract_value or 0)
            for w in orders
            if (w.contract_value or 0) > 0
        )
        total_cost = sum(
            float(w.actual_cost or 0)
            for w in orders
            if (w.actual_cost or 0) > 0
        )
        gross_profit = total_contract - total_cost
        gross_margin = (
            round(gross_profit / total_contract * 100, 1)
            if total_contract > 0
            else 0.0
        )

        by_status: Dict[str, int] = {}
        for w in orders:
            s = w.normalized_status or "Unknown"
            by_status[s] = by_status.get(s, 0) + 1

        active = sum(
            by_status.get(s, 0)
            for s in ["Completed", "In Progress", "Delayed", "Scheduled"]
        )
        comp_rate = (
            round(by_status.get("Completed", 0) / active * 100, 1)
            if active > 0
            else 0.0
        )

        sample = [
            {
                "work_order_no": w.work_order_no,
                "client": w.client_name,
                "project": w.project_name,
                "sector": w.normalized_sector,
                "status": w.normalized_status,
                "contract_value": float(w.contract_value or 0),
                "actual_cost": float(w.actual_cost or 0),
                "pilot": w.assigned_pilot_or_lead,
                "location": w.location,
                "due_date": str(w.due_date) if w.due_date else None,
            }
            for w in orders[:limit]
        ]

        return {
            "total_matching_work_orders": len(orders),
            "total_contract_value": total_contract,
            "total_actual_cost": total_cost,
            "gross_profit": gross_profit,
            "gross_margin_percent": gross_margin,
            "completion_rate_percent": comp_rate,
            "status_breakdown": by_status,
            "sample_work_orders": sample,
        }

    def _tool_pipeline_metrics(
        self, db: Session, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        return analytics_engine.get_pipeline_metrics(
            db, sector=args.get("sector")
        )

    def _tool_operations_metrics(
        self, db: Session, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        return analytics_engine.get_operations_metrics(
            db, sector=args.get("sector")
        )

    def _tool_data_quality(
        self, db: Session, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        board_type = args.get("board_type")
        severity = args.get("severity")
        limit = args.get("limit", 15)

        summary = data_quality_service.get_data_quality_summary(db)
        caveats = data_quality_service.generate_contextual_caveats(db)

        q = db.query(DataQualityIssueModel)
        if board_type:
            q = q.filter(
                DataQualityIssueModel.board_type.ilike(f"%{board_type}%")
            )
        if severity:
            q = q.filter(DataQualityIssueModel.severity.ilike(severity))

        issues = q.limit(limit).all()

        return {
            "hygiene_score_percent": summary.get("data_hygiene_score"),
            "total_issues": summary.get("total_issues"),
            "high_severity": summary.get("high_severity_count"),
            "medium_severity": summary.get("medium_severity_count"),
            "low_severity": summary.get("low_severity_count"),
            "issues_by_type": summary.get("issues_by_type", {}),
            "issues_by_board": summary.get("issues_by_board", {}),
            "contextual_caveats": caveats,
            "flagged_records": [
                {
                    "item_name": i.item_name,
                    "board": i.board_type,
                    "field": i.field_name,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "details": i.details,
                    "raw_value": i.raw_value,
                }
                for i in issues
            ],
        }

    def _tool_compare(
        self, db: Session, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        sector = args.get("sector")
        pipeline = analytics_engine.get_pipeline_metrics(db, sector=sector)
        operations = analytics_engine.get_operations_metrics(db, sector=sector)

        deal_q = db.query(DealModel.normalized_client).distinct()
        wo_q = db.query(WorkOrderModel.normalized_client).distinct()
        if sector:
            deal_q = deal_q.filter(
                DealModel.normalized_sector.ilike(f"%{sector}%")
            )
            wo_q = wo_q.filter(
                WorkOrderModel.normalized_sector.ilike(f"%{sector}%")
            )

        deal_clients = {r[0] for r in deal_q.all() if r[0]}
        wo_clients = {r[0] for r in wo_q.all() if r[0]}
        shared = deal_clients & wo_clients

        return {
            "pipeline_summary": pipeline,
            "operations_summary": operations,
            "client_overlap": {
                "deals_only_count": len(deal_clients - wo_clients),
                "work_orders_only_count": len(wo_clients - deal_clients),
                "shared_count": len(shared),
                "shared_client_names": sorted(list(shared))[:20],
            },
        }

    async def _tool_monday_live(
        self, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        board_type = args.get("board_type", "deals")
        limit = args.get("limit", 10)
        board_id = (
            settings.DEALS_BOARD_ID
            if board_type == "deals"
            else settings.WORK_ORDERS_BOARD_ID
        )
        try:
            items = await self.monday.fetch_board_items(board_id, limit=limit)
            # Trim each item to avoid token bloat
            trimmed = []
            for item in items[:limit]:
                trimmed.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "columns": {
                        cv.get("id", ""): cv.get("text", "")
                        for cv in item.get("column_values", [])
                        if cv.get("text")
                    },
                })
            return {
                "source": "Monday.com API (live)",
                "board_type": board_type,
                "items_fetched": len(trimmed),
                "items": trimmed,
            }
        except Exception as exc:
            return {"error": f"Monday.com API call failed: {exc}"}

    # ------------------------------------------------------------------
    # Tool router
    # ------------------------------------------------------------------

    _TOOL_MAP: Dict[str, str] = {
        "query_deals": "_tool_query_deals",
        "query_work_orders": "_tool_query_work_orders",
        "get_pipeline_metrics": "_tool_pipeline_metrics",
        "get_operations_metrics": "_tool_operations_metrics",
        "get_data_quality_report": "_tool_data_quality",
        "compare_pipeline_vs_execution": "_tool_compare",
        "fetch_monday_board_live": "_tool_monday_live",
    }

    async def _execute_tool(
        self, db: Session, name: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        method_name = self._TOOL_MAP.get(name)
        if not method_name:
            return {"error": f"Unknown tool: {name}"}
        method = getattr(self, method_name)
        try:
            # Monday live tool is async; the rest are sync
            if name == "fetch_monday_board_live":
                return await method(args)
            return method(db, args)
        except Exception as exc:
            logger.error(f"Tool {name} failed: {exc}", exc_info=True)
            return {"error": f"Tool execution failed: {exc}"}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def answer_query(
        self,
        db: Session,
        query: str,
        session_id: str = "default",
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AskResponse:
        """LLM-driven agentic answering with tool calling."""

        # Guard: no API key → immediate fallback
        if not (
            self.groq_api_key
            and self.groq_api_key.strip()
            and not self.groq_api_key.startswith("gsk_your")
        ):
            return self._llm_unavailable_response()

        try:
            from groq import AsyncGroq

            client = AsyncGroq(api_key=self.groq_api_key)

            # ---- Build message list ----
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
            if history:
                for turn in history[-6:]:
                    role = (
                        "user" if turn.get("type") == "user" else "assistant"
                    )
                    text = turn.get("text", "")
                    if text:
                        messages.append({"role": role, "content": text})
            messages.append({"role": "user", "content": query})

            # ---- Multi-round tool-calling loop ----
            # The model may call tools across multiple rounds (e.g.
            # first fetch pipeline data, then decide it also needs
            # data-quality info).  We keep looping until the model
            # produces a plain text answer or we hit the round cap.

            MAX_ROUNDS = 4
            tools_used: List[str] = []
            tool_results: Dict[str, Any] = {}
            final_answer: Optional[str] = None

            try:
                first_resp = await client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=1024,
                )
            except Exception as tool_err:
                logger.warning(
                    "Tool-calling request failed (%s); falling back to "
                    "context-injection mode.",
                    tool_err,
                )
                return await self._context_injection_fallback(
                    client, messages, db
                )

            choice = first_resp.choices[0]

            # ---- No tool calls → conversational reply ----
            if not choice.message.tool_calls:
                answer = (
                    choice.message.content
                    or "I'm ready to help.  Ask me anything about our "
                    "pipeline, operations, or data quality."
                )
                return AskResponse(
                    answer=answer,
                    executive_summary="Conversational response.",
                    metrics=[],
                    data_quality_caveats=[],
                    assumptions_made=[],
                    recommended_actions=[],
                    tools_used=["conversational"],
                    raw_data_summary={},
                )

            # ---- Execute tools in a loop ----
            messages.append(choice.message)

            for tc in choice.message.tool_calls:
                t_name = tc.function.name
                try:
                    t_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    t_args = {}
                tools_used.append(t_name)
                logger.info("Tool call [round 1]: %s(%s)", t_name, t_args)
                result = await self._execute_tool(db, t_name, t_args)
                tool_results[t_name] = result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=_serial),
                })

            # Subsequent rounds (model may call more tools or answer)
            for round_idx in range(2, MAX_ROUNDS + 1):
                resp = await client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=2000,
                )
                choice = resp.choices[0]

                if not choice.message.tool_calls:
                    # Model is done — this is the final answer
                    final_answer = choice.message.content or ""
                    break

                # Model wants more tools — execute them
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    t_name = tc.function.name
                    try:
                        t_args = json.loads(
                            tc.function.arguments or "{}"
                        )
                    except json.JSONDecodeError:
                        t_args = {}
                    tools_used.append(t_name)
                    logger.info(
                        "Tool call [round %d]: %s(%s)",
                        round_idx, t_name, t_args,
                    )
                    result = await self._execute_tool(db, t_name, t_args)
                    tool_results[t_name] = result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=_serial),
                    })
            else:
                # Hit max rounds without a text answer — force one
                final_answer = (
                    choice.message.content
                    or "I gathered the data but ran into a processing "
                    "limit.  Please try a more specific question."
                )

            # Unwrap if model accidentally wrapped in JSON
            if final_answer and final_answer.strip().startswith("{"):
                try:
                    parsed = json.loads(final_answer.strip())
                    if isinstance(parsed, dict) and "answer" in parsed:
                        final_answer = parsed["answer"]
                except json.JSONDecodeError:
                    pass

            # ---- Collect contextual data-quality caveats ----
            caveats = self._collect_caveats(db, tools_used, tool_results)

            return AskResponse(
                answer=final_answer,
                executive_summary=(
                    f"Analysis via {', '.join(tools_used)}."
                ),
                metrics=[],
                data_quality_caveats=caveats,
                assumptions_made=[],
                recommended_actions=[],
                tools_used=tools_used,
                raw_data_summary={},
            )

        except Exception as exc:
            logger.error("Agent execution failed: %s", exc, exc_info=True)
            return self._llm_unavailable_response()

    # ------------------------------------------------------------------
    # Context-injection fallback (if model doesn't support tool calling)
    # ------------------------------------------------------------------

    async def _context_injection_fallback(
        self,
        client: Any,  # AsyncGroq instance
        base_messages: List[Dict[str, Any]],
        db: Session,
    ) -> AskResponse:
        """
        Fallback: inject a focused data snapshot into the prompt and let
        the LLM answer without formal tool calls.
        """
        pipeline = analytics_engine.get_pipeline_metrics(db)
        operations = analytics_engine.get_operations_metrics(db)
        dq_summary = data_quality_service.get_data_quality_summary(db)
        caveats = data_quality_service.generate_contextual_caveats(db)

        context = {
            "pipeline_metrics": pipeline,
            "operations_metrics": operations,
            "data_quality": {
                "hygiene_score": dq_summary.get("data_hygiene_score"),
                "total_issues": dq_summary.get("total_issues"),
                "high_severity": dq_summary.get("high_severity_count"),
            },
            "caveats": caveats,
        }

        base_messages.append(
            {
                "role": "user",
                "content": (
                    "[SYSTEM NOTE: Tool calling is unavailable.  Here is "
                    "a data snapshot from the Neon database for reference.  "
                    "Use it to answer the user's question.]\n\n"
                    + json.dumps(context, default=_serial)
                ),
            }
        )

        resp = await client.chat.completions.create(
            messages=base_messages,
            model=self.model,
            temperature=0.2,
            max_tokens=1800,
        )

        answer = resp.choices[0].message.content or ""

        return AskResponse(
            answer=answer,
            executive_summary="Analysis via context injection (fallback).",
            metrics=[],
            data_quality_caveats=caveats[:3],
            assumptions_made=[],
            recommended_actions=[],
            tools_used=["context_injection_fallback"],
            raw_data_summary={},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_caveats(
        self,
        db: Session,
        tools_used: List[str],
        tool_results: Dict[str, Any],
    ) -> List[str]:
        """
        Auto-generate data-quality caveats relevant to whatever the
        agent just analysed.
        """
        # If the DQ report tool was already called, pull caveats from it
        dq_result = tool_results.get("get_data_quality_report")
        if dq_result and "contextual_caveats" in dq_result:
            return dq_result["contextual_caveats"][:4]

        try:
            return data_quality_service.generate_contextual_caveats(db)[:3]
        except Exception:
            return []

    @staticmethod
    def _llm_unavailable_response() -> AskResponse:
        return AskResponse(
            answer=(
                "⚠️ **The AI model is currently unavailable.**\n\n"
                "I cannot analyse your question because the LLM endpoint "
                "is not responding or the API key is misconfigured.  "
                "Please try again shortly, or check the `/health` endpoint "
                "for system status.\n\n"
                "In the meantime you can explore the **Data Explorer** tab "
                "for raw records or the **Data Quality** tab for integrity "
                "reports."
            ),
            executive_summary="LLM unavailable.",
            metrics=[],
            data_quality_caveats=[],
            assumptions_made=[],
            recommended_actions=[
                "Check GROQ_API_KEY configuration",
                "Verify model endpoint availability",
            ],
            tools_used=[],
            raw_data_summary={},
        )


bi_agent = SkylarkBIAgent()
