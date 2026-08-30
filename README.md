# Skylark Drones — Monday.com Business Intelligence Agent

> **A hosted, founder-level Business Intelligence Agent that connects dynamically to Monday.com boards (*Work Orders* & *Deals*), syncs and normalizes messy data into a Neon PostgreSQL analytical cache, and answers strategic business queries with mathematical precision and explicit data-quality caveats.**

---

## 🏛️ System Architecture

```
                      ┌────────────────────────────┐
                      │   Founder / Evaluator UI   │
                      │  (Hosted React + Tailwind) │
                      └─────────────┬──────────────┘
                                    │ HTTP / JSON
                                    ▼
                      ┌────────────────────────────┐
                      │   FastAPI Agent Backend    │
                      │      (Hosted on Render)    │
                      └──────┬──────────────┬──────┘
                             │              │
       Direct GraphQL API v2 │              │ Analytical SQL Queries
                             ▼              ▼
     ┌────────────────────────────┐   ┌──────────────────────────────┐
     │        Monday.com          │   │      Neon PostgreSQL         │
     │  (Canonical Source Truth)  │   │  (Read-Through Analytical)   │
     │  • Work Orders Board       │   │  • raw_monday_items          │
     │  • Deals Funnel Board      │   │  • normalized work_orders    │
     └────────────────────────────┘   │  • normalized deals          │
                                      │  • data_quality_issues       │
                                      └──────────────┬───────────────┘
                                                     │
                                                     ▼
                                      ┌──────────────────────────────┐
                                      │       Groq LLM Engine        │
                                      │  (Llama 3.3 70B / GPT-OSS)   │
                                      │  • Intent Routing            │
                                      │  • Executive Briefing Format │
                                      └──────────────────────────────┘
```

---

## 💡 Core Highlights

- **Deterministic BI Computations:** Numerical answers (revenue, pipeline volume, win rate, gross margin, completion percentage) are computed strictly via SQL/Python logic — **never hallucinated via embeddings**.
- **Resilient Data Normalization:** Automatically parses mixed date formats (`DD/MM/YYYY`, `YYYY-MM-DD`, text dates), formats messy currency strings (`$160k`, `1.5M`, dirty commas), and normalizes client company aliases.
- **Automated Data Quality Audit:** Scans for missing milestone dates, negative contract values, unassigned drone pilots, and cross-board orphaned records with a live **Data Hygiene Score (0-100%)**.
- **Founder Executive Chat:** Features suggested founder questions, interactive KPI cards, markdown briefings, and expandable caveat drawers.
- **Dual Mode (Live & Fallback):** Connects to live Monday.com boards via GraphQL API v2 with automatic fallback dataset generation for offline evaluation.

---

## ⚙️ Environment Configuration

Copy `.env.example` to `.env` and configure:

```env
# Neon PostgreSQL Database URL
DATABASE_URL=postgresql://neondb_owner:...@ep-little-pond-a6sl2gzf.us-west-2.aws.neon.tech/neondb?sslmode=require

# Monday.com API Access
MONDAY_API_TOKEN=your_monday_personal_api_token
WORK_ORDERS_BOARD_ID=your_work_orders_board_id
DEALS_BOARD_ID=your_deals_board_id

# Groq LLM API Key
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Server Port
PORT=8000

# Frontend API URL (for hosted React app)
VITE_API_URL=https://your-backend-service.onrender.com
```

---

## 🚀 Quickstart (Local Run)

### 1. Backend (FastAPI)
```bash
# Activate virtual environment
.\venv\Scripts\activate  # Windows
source venv/bin/activate # Linux/Mac

# Run server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend (React + Vite + Tailwind)
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:3000`** in your browser.

---

## 🌐 Hosted Deployment Guide

### Deploy Backend to Render:
1. Create a **New Web Service** connected to this repository.
2. Settings:
   - **Environment:** `Python`
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
3. Add Environment Variables (`DATABASE_URL`, `MONDAY_API_TOKEN`, `WORK_ORDERS_BOARD_ID`, `DEALS_BOARD_ID`, `GROQ_API_KEY`).

### Deploy Frontend to Vercel:
1. Create a **New Project** in Vercel connected to this repository.
2. Set **Root Directory** to `frontend`.
3. Add Environment Variable:
   - `VITE_API_URL` = `https://<your-render-backend-url>.onrender.com`
4. Click **Deploy**.

---

## 📄 Decision Log

See [**`DECISION_LOG.md`**](./DECISION_LOG.md) for the 2-page executive summary covering architectural trade-offs, rejection of vector-only RAG for BI math, and our interpretation of leadership updates.
