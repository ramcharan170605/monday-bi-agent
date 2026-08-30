# Skylark Drones — Monday.com Business Intelligence Agent
## 📄 Technical Decision Log (2-Page Executive Brief)

---

### 1. Executive Context & Core Architecture
Founders and executive leaders at Skylark Drones require immediate, authoritative answers to strategic business questions across sales pipeline and drone flight operations. The data resides in separate Monday.com boards (*Work Orders* and *Deals*), marked by real-world inconsistencies (dirty date formats, shorthand currencies, missing pilots, unassigned sectors).

```
Founder / Executive
        │
        ▼
Hosted React UI (Vercel)
        │
        ▼
FastAPI BI Agent Backend (Render)
        │
        ├──► Monday.com GraphQL API (Source of Truth, Read-Only)
        │
        ├──► Neon Serverless PostgreSQL (Read-Through Analytical Cache)
        │       ├── raw_monday_items
        │       ├── normalized work_orders
        │       ├── normalized deals
        │       └── data_quality_issues
        │
        └──► Groq LLM Engine (Llama 3.3 70B / GPT-OSS)
                ├── Intent Parsing & Tool Dispatch
                └── Executive Narrative & Caveat Synthesis
```

---

### 2. Key Architectural Decisions & Justifications

| Architectural Choice | Decision | Rationale & Why Alternatives Were Rejected |
| :--- | :--- | :--- |
| **Data Source of Truth** | **Monday.com (Direct Read-Only GraphQL API)** | Monday.com remains the live operational database. Direct GraphQL v2 API was chosen over Monday MCP because it delivers predictable cursor-based pagination, schema introspection, rate-limit retry backoff, and zero MCP daemon friction for a hosted deployment. |
| **Analytical Store** | **Neon Serverless PostgreSQL** | Used strictly as a **read-through analytical cache**, not an independent system of record. Relational SQL enables deterministic multi-table joins, exact aggregations, and granular auditability of data quality issues. |
| **RAG vs. Structured SQL Engine** | **Structured Calculations (No Vector-Only RAG)** | **RAG / Vector DB was explicitly rejected for BI math.** Embeddings are inherently fuzzy and cannot calculate revenue, win rates, or operational margins accurately. Structured SQL and Python computations guarantee 100% mathematical precision. |
| **LLM & Tool Orchestration** | **Groq (GPT-OSS / Llama 3.3 70B Versatile)** | Groq provides sub-second inference latency, deterministic tool calling, and low cost. The LLM is used strictly for intent classification and executive synthesis; it never invents numbers. |
| **UI Implementation** | **React + Tailwind + 21st.dev MCP Patterns** | Focused on an executive-grade conversational UI with structured KPI cards, live data quality audit drawer, and board explorer, rather than complex bloated charts. |

---

### 3. Key Assumptions & Data Resilience Engineering

1. **Messy Date Resolution:** Date fields in Monday.com arrive in diverse formats (`YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, shorthand text). Our `DataNormalizer` executes progressive fallback parsing, defaulting unparseable milestone dates to safe approximations while raising transparent data-quality caveats.
2. **Currency & Financial Safety:** Shorthand currency notation (`$160k`, `1.5M`, `210,000 USD`, commas, dirty strings) is cleaned into exact standard numeric decimals. Negative contract values are flagged as `HIGH` severity anomalies rather than dropped.
3. **Canonical Entity & Sector Matching:** Company names (`Adani Green Energy Ltd.`, `Adani`, `Adani Group`) are normalized into canonical keys (`adani`) to enable cross-board correlation between sales deals and flight execution work orders.
4. **Data Quality Transparency:** Incomplete records are preserved (never deleted) and tagged with field-level caveat flags. Every answer explicitly highlights active data-quality risks.

---

### 4. Interpretation of "Leadership Updates"
We interpreted **"The agent should help prepare data for leadership updates"** as an executive-ready operational briefing format. When queried for a leadership update, the agent automatically synthesizes:
- **Topline Commercial Wins:** Total pipeline value, weighted probability value, and win rate.
- **Flight Execution & Operational Velocity:** Total active work orders, delivery completion rate, and gross margin ($ and %).
- **Critical Risks & Blockers:** Overdue/delayed drone missions and unassigned pilot shortages.
- **Data Hygiene Audit:** Active data quality issues on Monday boards with recommended actions for sales and operations managers.

---

### 5. What We Would Do Differently with More Time
- **Monday Webhooks:** Implement real-time Monday.com webhooks (`item_created`, `item_updated`) for instantaneous event-driven cache updates instead of polling sync.
- **Semantic Embeddings for Free-Text:** Add Mistral text embeddings for fuzzy qualitative matching on site descriptions, flight notes, and customer incident logs.
- **Automated Monday Quality Tags:** Add optional write-back capabilities to tag dirty columns in Monday.com with color-coded "Needs Review" status tags.
