# Skylark Drones — Monday.com Business Intelligence Agent

<div align="center">

**An AI-powered, founder-level Business Intelligence Agent that connects to live Monday.com boards, syncs data into Neon PostgreSQL, and answers strategic business queries with mathematical precision and data-quality caveats.**

[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-React_18-61DAFB?style=for-the-badge&logo=react)](https://reactjs.org)
[![Database](https://img.shields.io/badge/Database-Neon_PostgreSQL-4169E1?style=for-the-badge&logo=postgresql)](https://neon.tech)
[![LLM](https://img.shields.io/badge/LLM-Groq_API-F55036?style=for-the-badge)](https://groq.com)
[![Deployed](https://img.shields.io/badge/Live-Render_+_Vercel-000?style=for-the-badge&logo=vercel)](https://vercel.com)

</div>

---

## 🏛️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Founder / Executive UI                       │
│              React 18 + Tailwind CSS (Vercel)                  │
│  ┌──────────┐  ┌────────────┐  ┌────────────────────────────┐  │
│  │ AI Chat  │  │  Data      │  │  Data Quality              │  │
│  │ Console  │  │  Explorer  │  │  Dashboard                 │  │
│  └──────────┘  └────────────┘  └────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /ask { query, history }
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI Agent Backend (Render)                  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  LLM-Driven BI Agent                       │ │
│  │                                                            │ │
│  │  1. User question → LLM interprets intent                 │ │
│  │  2. LLM selects tool(s) → executes against DB / API       │ │
│  │  3. Tool results → LLM synthesises executive answer        │ │
│  │                                                            │ │
│  │  Tools: query_deals │ query_work_orders │ pipeline_metrics │ │
│  │         operations_metrics │ data_quality │ cross_board    │ │
│  │         fetch_monday_live                                  │ │
│  └──────────┬─────────────────────────────────┬───────────────┘ │
│             │                                 │                 │
│      Analytical SQL                    GraphQL API v2           │
│             │                                 │                 │
└─────────────┼─────────────────────────────────┼─────────────────┘
              ▼                                 ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│     Neon PostgreSQL          │  │        Monday.com            │
│  (Analytical Cache)          │  │   (Source of Truth)          │
│                              │  │                              │
│  • normalized deals (346)    │  │  • Deal Funnel Board         │
│  • normalized work_orders    │  │  • Work Order Tracker Board  │
│    (176)                     │  │                              │
│  • data_quality_issues (548) │  │                              │
│  • raw_monday_items          │  │                              │
│  • board_schemas             │  │                              │
└──────────────────────────────┘  └──────────────────────────────┘
              │
              ▼
┌──────────────────────────────┐
│      Groq LLM Engine         │
│   (openai/gpt-oss-20b)       │
│                              │
│  • Tool-calling agent        │
│  • Multi-round reasoning     │
│  • Executive synthesis       │
└──────────────────────────────┘
```

---

## 🤖 How the Agent Works

The agent uses an **LLM-driven agentic architecture** — the language model is the decision-maker, not hardcoded keyword matching.

### Agent Flow

1. **User asks a question** → _"How is our energy pipeline looking this quarter?"_
2. **LLM interprets intent** → identifies: sector = Energy, metric = pipeline health
3. **LLM selects tool(s)** → calls `get_pipeline_metrics(sector="Energy")`
4. **Backend executes** → queries Neon PostgreSQL for Energy deals, computes win rate, stage distribution
5. **Results returned to LLM** → model receives structured data (137 deals, ₹922M pipeline, 1.1% win rate…)
6. **LLM generates answer** → produces a sector-specific executive briefing with insights and caveats

### Available Tools

| Tool | Purpose | Example Trigger |
|------|---------|----------------|
| `query_deals` | Filter & retrieve specific deal records | _"Show me won deals in mining"_ |
| `query_work_orders` | Filter & retrieve work order records | _"List delayed flights"_ |
| `get_pipeline_metrics` | Aggregated pipeline KPIs | _"What's our overall win rate?"_ |
| `get_operations_metrics` | Aggregated operations KPIs | _"What's our gross margin?"_ |
| `get_data_quality_report` | Hygiene score + flagged records | _"What data issues exist?"_ |
| `compare_pipeline_vs_execution` | Cross-board deals ↔ work orders | _"Compare sales with delivery"_ |
| `fetch_monday_board_live` | Fresh data from Monday.com API | _"Pull latest Monday data"_ |

### Multi-Round Reasoning

The model can **chain tool calls** across up to 4 rounds. For example:
- Round 1: `get_pipeline_metrics(sector="Energy")` → gets pipeline numbers
- Round 2: `get_data_quality_report(board_type="deals")` → checks data integrity
- Round 3: Synthesises a complete answer incorporating both datasets

---

## ✨ Key Features

### 🎯 Intelligent Query Understanding
- Natural language questions routed to the right data source by the LLM
- Cross-board analysis when questions span both Deals and Work Orders
- Sector, status, client, and pilot filters applied automatically
- Conversation history tracking for natural multi-turn drill-downs

### 📊 Deterministic BI Computations
- Revenue, pipeline volume, win rates, and gross margins computed via **SQL/Python** — never hallucinated
- Aggregations done server-side before the LLM sees results

### 🛡️ Automated Data Quality Audit
- Scans for missing dates, invalid financial values, unassigned pilots, and cross-board orphans
- Live **Data Hygiene Score (0–100%)** with severity-weighted penalties
- Contextual caveats attached to every agent response

### 🔄 Live Monday.com Sync
- Full cursor-based pagination via Monday.com GraphQL API v2
- Resilient normalisation of messy dates (`DD/MM/YYYY`, `YYYY-MM-DD`, `TBD`), currency strings (`$160k`, `1.5M`), and client aliases
- One-click re-sync from the UI

### 💬 Executive Chat Interface
- Suggested founder-level questions for quick access
- Markdown-rendered responses with data quality caveat badges
- Tool dispatch indicators showing which data sources were queried
- Conversation history for follow-up questions

---

## ⚙️ Environment Configuration

Copy `.env.example` to `.env` and configure:

```env
# Neon PostgreSQL
DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require

# Monday.com API
MONDAY_API_TOKEN=your_monday_personal_api_token
WORK_ORDERS_BOARD_ID=5030966911
DEALS_BOARD_ID=5030966948

# Groq LLM
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

# Server
PORT=8000

# Frontend (Vite)
VITE_API_URL=https://your-backend.onrender.com
```

---

## 🚀 Quickstart

### Backend (FastAPI)

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
.\venv\Scripts\activate         # Windows

# Install dependencies
pip install -r backend/requirements.txt

# Run server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## 🌐 Production Deployment

### Backend → Render

| Setting | Value |
|---------|-------|
| Environment | Python |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Env Variables | `DATABASE_URL`, `MONDAY_API_TOKEN`, `WORK_ORDERS_BOARD_ID`, `DEALS_BOARD_ID`, `GROQ_API_KEY`, `GROQ_MODEL` |

### Frontend → Vercel

| Setting | Value |
|---------|-------|
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Env Variables | `VITE_API_URL` = `https://your-backend.onrender.com` |

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | System health check (DB, Monday.com, Groq status) |
| `POST` | `/sync` | Trigger Monday.com → Neon data sync |
| `POST` | `/ask` | AI agent question answering |
| `GET` | `/data-quality` | Data quality report with hygiene score |
| `GET` | `/boards/overview` | High-level board metrics |
| `GET` | `/data/work-orders` | Filterable work order records |
| `GET` | `/data/deals` | Filterable deal records |

### `/ask` Request / Response

```json
// Request
{
  "query": "How is our energy pipeline looking?",
  "session_id": "default",
  "history": []
}

// Response
{
  "answer": "## Energy Pipeline Snapshot\n\n...",
  "executive_summary": "Analysis via get_pipeline_metrics.",
  "metrics": [],
  "data_quality_caveats": ["⚠️ 28 high-severity issues detected..."],
  "tools_used": ["get_pipeline_metrics"],
  "raw_data_summary": {}
}
```

---

## 🗂️ Project Structure

```
├── backend/
│   ├── main.py                 # FastAPI app, routes, lifespan
│   ├── config.py               # Pydantic settings
│   ├── models/
│   │   ├── database.py         # SQLAlchemy ORM models
│   │   └── schemas.py          # Pydantic request/response schemas
│   └── services/
│       ├── agent.py            # LLM-driven BI agent with tool calling
│       ├── analytics.py        # Deterministic SQL aggregation engine
│       ├── data_quality.py     # Hygiene scoring and caveats
│       ├── monday_client.py    # Monday.com GraphQL API client
│       ├── normalizer.py       # Data parsing and normalization
│       └── sync_service.py     # Monday.com → Neon sync pipeline
├── frontend/
│   └── src/
│       ├── App.jsx             # Main chat UI
│       ├── components/
│       │   ├── Header.jsx      # Navigation, sync button
│       │   ├── MetricCards.jsx  # KPI card grid
│       │   ├── DataExplorer.jsx # Record browser with search/filter
│       │   └── DataQualityDrawer.jsx  # Hygiene dashboard
│       └── services/
│           └── api.js          # Backend API client
├── DECISION_LOG.md             # Architectural decision log
└── README.md
```

---

## 🏗️ Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LLM tool-calling** over keyword routing | The model dynamically selects what data to fetch based on intent, eliminating brittle if/else chains |
| **Neon PostgreSQL** as analytical cache | Fast structured queries; Monday.com API is too slow for real-time aggregation |
| **Monday.com API** as source of truth | Always available for fresh data when the cache might be stale |
| **SQL/Python** for BI math | Win rates, margins, and pipeline values are computed deterministically — never hallucinated by the LLM |
| **Multi-round tool loop** (max 4) | Handles models that chain tool calls (e.g., fetch pipeline → then fetch data quality) |
| **Context-injection fallback** | If the model doesn't support tool calling, injects a data snapshot and still generates a useful answer |

See [**`DECISION_LOG.md`**](./DECISION_LOG.md) for the full executive summary.

---

## 📄 License

Built for the Skylark Drones technical assessment.
