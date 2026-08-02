# KAIROS — Autonomous Causal Business Intelligence Agent

<div align="center">

![KAIROS Banner](docs/assets/banner.png)

**An Autonomous Causal Business Intelligence Agent for Proactive Multi-Source Metric Monitoring and Root Cause Analysis**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Deployment](https://img.shields.io/badge/Deployed-Render%20%2B%20Vercel-teal?style=flat-square)](https://kairos-app.vercel.app)
[![Cost](https://img.shields.io/badge/Total%20Cost-₹0-brightgreen?style=flat-square)]()
[![University](https://img.shields.io/badge/Woxsen%20University-Capstone%20Project--I-navy?style=flat-square)]()

> *"Power BI answers questions when you ask. KAIROS asks the questions for you."*

</div>

---

## What is KAIROS?

Every Business Intelligence tool today — Power BI, Tableau, Looker, ThoughtSpot — waits for a human to open it and ask a question. If nobody looks, nobody knows anything is wrong.

**KAIROS** breaks this paradigm. It is a five-agent autonomous pipeline that:

- **Monitors** all connected business metrics every 15 minutes — automatically
- **Detects** anomalies using Prophet and Anomaly Transformer — without being asked
- **Investigates** root causes using DYNOTEARS temporal causal discovery — not just correlations
- **Explains** findings in plain English using a free local LLM (Llama 3.1)
- **Delivers** Telegram alerts within 5 minutes — to any phone

Total deployment cost: **₹0**

---

## The Three Novel Contributions

| Contribution | Description |
|---|---|
| **ProBI** — Proactive Business Intelligence | First formal definition of autonomous business metric monitoring without human initiation |
| **CBMG** — Causal Business Metric Graph | First application of DYNOTEARS temporal causal discovery to business KPI anomaly root cause analysis |
| **SLAC** — Semantic Layer Auto-Construction | First system to automatically infer business meaning from raw heterogeneous schemas using a local LLM |

---

## System Architecture

```
[Google Sheets] [SQL Database] [CSV / REST API]
          ↓            ↓               ↓
       AGENT 1: Data Collector
       SQLAlchemy + Airbyte + APScheduler (every 15 min)
                    ↓
          [DuckDB Time-Series Store]
                    ↓
       AGENT 2: Anomaly Watchman
       Prophet + Anomaly Transformer
                    ↓  (anomaly detected)
       AGENT 3: Causal Investigator  ← Core Research Contribution
       DYNOTEARS + DoWhy + CBMG Builder
                    ↓
       AGENT 4: NL Reporter
       Ollama + Llama 3.1 + LLM-Modulo
                    ↓
       AGENT 5: Messenger
       Telegram Bot API + FastAPI + React
         ↓              ↓            ↓
    Phone Alert    Dashboard      Gmail
```

---

## Tech Stack (100% Free)

| Layer | Tools |
|---|---|
| Agent Orchestration | LangGraph, LangChain |
| LLM (Local) | Ollama + Llama 3.1 8B |
| LLM (Cloud Fallback) | Groq API (14,400 free req/day) |
| Causal Discovery | DYNOTEARS via causal-learn (CMU) |
| Causal Inference | DoWhy (Microsoft Research) |
| Anomaly Detection | Anomaly Transformer, Prophet |
| Data Processing | Pandas, SQLAlchemy, DuckDB, Airbyte |
| Vector Database | ChromaDB |
| Backend | FastAPI, PostgreSQL, APScheduler |
| Frontend | React, Recharts, Tailwind CSS |
| Alert Delivery | Telegram Bot API, Gmail SMTP |
| Deployment | Render.com (free), Vercel (free) |

---

## Repository Structure

```
kairos/
├── backend/
│   ├── agents/
│   │   ├── data_collector.py       # Agent 1
│   │   ├── anomaly_watchman.py     # Agent 2
│   │   ├── causal_investigator.py  # Agent 3
│   │   ├── nl_reporter.py          # Agent 4
│   │   └── messenger.py            # Agent 5
│   ├── connectors/
│   │   ├── sql_connector.py
│   │   ├── sheets_connector.py
│   │   └── csv_connector.py
│   ├── models/
│   │   ├── slac.py                 # Semantic Layer Auto-Construction
│   │   ├── cbmg.py                 # Causal Business Metric Graph
│   │   └── anomaly.py              # Detection pipeline
│   ├── api/
│   │   └── routes.py
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── App.jsx
│   └── package.json
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_anomaly_detection.ipynb
│   └── 03_causal_analysis.ipynb
├── research/
│   ├── literature_review.md
│   └── gap_analysis.md
├── data/
│   └── sample/
├── docs/
│   ├── assets/
│   └── architecture.png
├── tests/
│   └── test_connectors.py
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) installed locally
- Docker (optional)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/kairos.git
cd kairos
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
GROQ_API_KEY=your_groq_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_URL=postgresql://user:password@localhost:5432/kairos
```

### 3. Install backend dependencies

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 4. Pull the LLM model locally (free)

```bash
ollama pull llama3.1:8b
ollama pull sqlcoder
```

### 5. Install frontend dependencies

```bash
cd frontend
npm install
```

### 6. Run with Docker (easiest)

```bash
docker-compose up
```

### 7. Run manually

```bash
# Backend
cd backend && uvicorn main:app --reload

# Frontend
cd frontend && npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## Free API Keys Needed

| Service | How to Get | Cost |
|---|---|---|
| Groq API | [console.groq.com](https://console.groq.com) → Sign up | Free — no card |
| Telegram Bot | Message @BotFather on Telegram → `/newbot` | Free — always |
| Render.com | [render.com](https://render.com) → Sign up | Free tier |
| Vercel | [vercel.com](https://vercel.com) → Sign up | Free tier |

---

## Evaluation Datasets

| Dataset | Source | Use |
|---|---|---|
| Olist Brazil E-Commerce | [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) | End-to-end pipeline evaluation |
| Superstore Sales | [Tableau Public](https://public.tableau.com) | Multi-table analytics benchmark |
| Northwind Database | Microsoft (open) | Classic business analytics |

---

## Research

This project is submitted as Capstone Project-I at Woxsen University, School of Technology.

**Target publication:** KDD 2027 Applied Data Science Track / VLDB 2027 Industrial Track

**Related papers:**
- [ReAct (ICLR 2023)](https://arxiv.org/abs/2210.03629)
- [Anomaly Transformer (ICLR 2022)](https://arxiv.org/abs/2110.02642)
- [AIDA (arXiv 2026)](https://arxiv.org/abs/2605.07202)
- [DYNOTEARS (AISTATS 2020)](https://arxiv.org/abs/2002.00498)

---

## Team

- Palla Chetana Reddy
- Varshini Yadav Nasaram
- Obulagari Nandini

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

