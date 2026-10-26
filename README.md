# ReceivIQ: Autonomous Accounts Receivable Agent
> **Enterprise-Grade Autonomous Credit Control, Invoice Collections & Debtor Intelligence Platform**  
> *Powered by AWS Bedrock (Amazon Nova Pro), FastAPI, PostgreSQL, and React 18*

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-336791.svg)](https://www.postgresql.org/)
[![AWS Bedrock](https://img.shields.io/badge/AWS%20Bedrock-Amazon%20Nova%20Pro-FF9900.svg)](https://aws.amazon.com/bedrock/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://reactjs.org/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📌 Project Overview

The **AI Accounts Receivable Agent (ReceivIQ)** is an autonomous agentic AI system designed to eliminate manual friction in corporate credit control and debt recovery.

In commercial enterprises, finance departments spend countless hours tracking overdue aging schedules, calculating contractual interest, formulating reminder notices, and verifying bank remittance proofs. **ReceivIQ** transforms this operational bottleneck into an intelligent, autonomous pipeline:

- **Autonomous Decision Reasoning:** Powered by **AWS Bedrock (Amazon Nova Pro)** to evaluate debtor risk tiers, parse bank transaction UTR receipts, and draft professional collection communications.
- **Fail-Closed Governance:** Consequential financial actions (invoices $\ge$ ₹1,00,000, debt concessions, or legal escalations) are strictly gated behind human approval.
- **Live Reactive Dashboard:** A modern React 18 interface providing real-time Days Sales Outstanding (DSO) metrics, Server-Sent Events (SSE) streaming thought logs, and an interactive ledger.

---

## 👥 Team Members

| Name | PRN | GitHub | Role |
| :--- | :---: | :---: | :--- |
| **Ashish Gokani** | 8025065249 | [@ashishgokani](https://github.com/ashishgokani) | **Team Lead & AI Core Architect (AI Agent Orchestration, AI Model Intergration, Input and Guardrails, etc.)** |
| **Patel Dhairya Aniketan** | 8024064608 | [@dhairya2211](https://github.com/dhairya2211) | **Backend (Tooling & Governance)** |
| **Miyawala Abdulmuizz** | 8024064491 | [@abdulmuizz1409](https://github.com/abdulmuizz1409) | **Backend (Database & Automation)** |
| **Janavi Dadhania** | 8024064714 | [@janavi021](https://github.com/janavi021) | **Backend (Communications & Inbound Intelligence)** |
| **Jaydev Rathava** | 8025064103 | [@jaydev-2006](https://github.com/jaydev-2006) | **Frontend UI/UX** |

---

## 🏗️ System Architecture

```
+----------------------------------------------------------------------------------------------------+
|                                      RECEIVIQ PLATFORM ARCHITECTURE                                |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  +----------------------------------------------------------------------------------------------+  |
|  |                       PRESENTATION TIER (React 18 + Vite + TailwindCSS)                      |  |
|  |  • Financial Dashboard  • Live Invoice Ledger   • Customer Directory  • Governance Approvals|  |
|  |  • Real-Time Audit Feed • AI Copilot Chat (SSE) • Settings Management • Debtor Simulator UI  |  |
|  +----------------------------------------------------------------------------------------------+  |
|                                                │  ▲                                                |
|                   HTTP REST APIs (JSON)        │  │ Server-Sent Events (SSE Live Streams)          |
|                                                ▼  │                                                |
|  +----------------------------------------------------------------------------------------------+  |
|  |                             APPLICATION SERVICES TIER (FastAPI)                              |  |
|  |  • Agent Orchestrator          • Fail-Closed State Machine    • 2.0% Late Penalty Engine     |  |
|  |  • 25 Bedrock Autonomous Tools • APScheduler Background Cron • Debtor Intent Classifier     |  |
|  |  • Inbound IMAP SSL Poller     • SMTP Email Dispatch Engine   • TurnManager State Buffer     |  |
|  +----------------------------------------------------------------------------------------------+  |
|                         │                                              │                           |
|        boto3 Converse   │                               SQLAlchemy ORM │ Pool                      |
|                         ▼                                              ▼                           |
|  +---------------------------------------+   +--------------------------------------------------+  |
|  |       AWS BEDROCK FOUNDATION AI       |   |             RELATIONAL PERSISTENCE               |  |
|  |       (Amazon Nova Pro Model)         |   |                 (PostgreSQL 15+)                 |  |
|  +---------------------------------------+   +--------------------------------------------------+  |
+----------------------------------------------------------------------------------------------------+
```

---

## ✨ Key Feature Capabilities

| Feature | Visual Layout & Highlights | Operational Flow |
| :--- | :--- | :--- |
| **1. Financial Health Dashboard** | • Real-time DSO meter (Days Sales Outstanding)<br>• Overdue Aging Buckets (0–30, 31–60, 61–90, 90+ days)<br>• Collection Velocity Index | Computes rolling 90-day recovery velocity and aggregates gross ledger exposure. |
| **2. Dynamic 2.0% Late Penalty Engine** | • Contractual Simple Interest calculation<br>• Accrues every 30 days overdue<br>• Settled invoice immutability lock | Automatically recalculates accrued late fees while preserving GAAP/IFRS settled records. |
| **3. Autonomous Agent Chat Copilot** | • Interactive conversational credit assistant<br>• Real-time SSE streaming thought accordion<br>• Dual-turn `PendingAction` confirmation | Natural language commands (`Show overdue > 15 days`, `Draft reminder for INV-1004`) with fail-closed safety. |
| **4. Human Governance Approvals** | • ₹1,00,000 High-Value Gating Gate<br>• Dual-action **Approve** or **Reject**<br>• Real-time operator audit log | Stops the AI from firing consequential emails or discounts without explicit supervisor sign-off. |
| **5. Inbound Debtor Email Intelligence** | • Gmail IMAP SSL background poller on port 993<br>• Debtor email verification against registry<br>• Nova Pro bank UTR number extraction | Ingests debtor emails, matches NEFT/RTGS UTR proofs, pauses reminders on dispute, and dispatches receipts. |
| **6. Multi-Scenario Debtor Simulator** | • Sandbox modal for developer/controller testing<br>• 6 Presets: UTR proof, dispute, extension, query<br>• Live AI reasoner response preview | Allows testing edge-case debtor emails directly from the UI without sending external emails. |
| **7. Multi-Commitment Conflict Engine** | • Time-bound settlement discount offers (24–48h)<br>• Revise vs. Stack vs. Cancel conflict matrix<br>• Grace period extension tracking | Prevents overlapping discounts from eroding corporate margins. |
| **8. Scheduled Background Collector** | • APScheduler cron running every 15 minutes<br>• Rest-interval spam suppression (7–14 days)<br>• Dynamic risk-tier reminder cadence | Runs continuous credit audits in the background without requiring user intervention. |

---

## 💻 Technology Stack

| Domain | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend Framework** | **React 18.3 + Vite** | High-performance single page application with fast HMR |
| **Styling & Icons** | **TailwindCSS 3.4 + Lucide React** | Modern glassmorphic dark/light UI with responsive grid |
| **Backend Framework** | **FastAPI (Python 3.12+)** | Asynchronous high-throughput REST APIs and SSE streaming |
| **AI Foundation Model** | **AWS Bedrock (Amazon Nova Pro)** | Multi-turn reasoning, tool execution, and intent classification |
| **Database & ORM** | **PostgreSQL 15+ & SQLAlchemy** | ACID-compliant relational storage with connection pooling |
| **Background Scheduler** | **APScheduler 3.10** | Periodic cron execution of ledger audits and aging sync |
| **Email Protocols** | **IMAP SSL (Port 993) & SMTP TLS** | Bi-directional email communication with Gmail / Enterprise relays |
| **Testing Suite** | **Pytest + AnyIO** | 80+ automated unit, integration, and regression test cases |

---

## 📁 Project Folder Structure

```
ai-accounts-receivable-agent/
├── backend/
│   ├── app/
│   │   ├── api/                     # REST API route controllers
│   │   │   ├── routes_agent.py      # Chat & SSE streaming endpoints
│   │   │   ├── routes_invoices.py   # Invoice ledger operations
│   │   │   ├── routes_customers.py  # Debtor directory operations
│   │   │   ├── routes_approvals.py  # Governance approval endpoints
│   │   │   ├── routes_analytics.py  # Dashboard KPIs & DSO analytics
│   │   │   ├── routes_simulation.py # Debtor reply sandbox endpoints
│   │   │   └── routes_settings.py   # System policy configuration
│   │   ├── core/                    # Security, timezone, and config
│   │   │   ├── config.py            # Pydantic BaseSettings (.env loader)
│   │   │   ├── guardrails.py        # Fail-closed safety validators
│   │   │   └── timezone.py          # Indian Standard Time (IST) utilities
│   │   ├── db/                      # Relational persistence layer
│   │   │   ├── models.py            # 7 SQLAlchemy ORM models
│   │   │   ├── session.py           # Database engine & connection pool
│   │   │   └── seeder.py            # Demo debtor accounts & invoices seeder
│   │   ├── schemas/                 # Pydantic validation schemas
│   │   ├── services/                # Core business & AI services
│   │   │   ├── orchestrator.py      # Central multi-turn AgentOrchestrator
│   │   │   ├── bedrock_service.py   # AWS Bedrock Nova Pro gateway
│   │   │   ├── bedrock_tools.py     # 25 Tool definitions and schemas
│   │   │   ├── tool_dispatcher.py   # Dynamic function execution router
│   │   │   ├── action_state_machine.py # PendingAction two-step confirmation
│   │   │   ├── penalty_engine.py    # 2.0% overdue interest calculator
│   │   │   ├── email_listener_service.py # Gmail IMAP SSL poller
│   │   │   ├── ai_reply_processor.py# Inbound intent classifier & UTR parser
│   │   │   ├── commitments_service.py # Early settlement discount engine
│   │   │   └── scheduler.py         # APScheduler background worker
│   │   └── main.py                  # FastAPI application entrypoint
│   ├── tests/                       # Automated test suite (80+ test cases)
│   ├── requirements.txt             # Backend Python dependencies
│   ├── GMAIL_SETUP_GUIDE.md         # Guide for Gmail App Passwords & IMAP
│   └── .env.example                 # Environment configuration template
│
├── frontend/
│   ├── src/
│   │   ├── api/                     # Axios API client with interceptors
│   │   ├── components/              # 18 Reusable UI components & modals
│   │   │   ├── settings/            # Penalty, Reminders, Bank, Agent tabs
│   │   │   ├── PaymentModal.jsx     # Payment recording modal
│   │   │   ├── ReplySimulatorModal.jsx # Debtor reply sandbox UI
│   │   │   └── MarkdownRenderer.jsx # SSE stream markdown parser
│   │   ├── pages/                   # 7 Full-featured application views
│   │   │   ├── Dashboard.jsx        # Executive KPI dashboard
│   │   │   ├── Invoices.jsx         # Live invoice ledger table
│   │   │   ├── Customers.jsx        # Customer directory & risk scores
│   │   │   ├── Approvals.jsx        # High-value approval portal
│   │   │   ├── AgentChat.jsx        # Real-time conversational AI copilot
│   │   │   ├── AgentActivity.jsx    # Immutable audit trail feed
│   │   │   └── Settings.jsx         # Administration control room
│   │   ├── hooks/                   # Theme context & custom hooks
│   │   └── index.css                # TailwindCSS design system tokens
│   ├── package.json                 # Node dependencies & scripts
│   └── vite.config.js               # Vite build configuration
│
├── README.md                        # Project documentation manual
└── LICENSE                          # MIT License
```

---

## 🗄️ Database Architecture

The platform uses a normalized relational architecture across 7 core PostgreSQL tables:

```
+--------------------+       1:N       +---------------------+       1:N       +---------------------+
|     CUSTOMERS      |---------------->|      INVOICES       |---------------->|      PAYMENTS       |
+--------------------+                 +---------------------+                 +---------------------+
| customer_id (PK)   |                 | invoice_id (PK)     |                 | payment_id (PK)     |
| company_name       |                 | customer_id (FK)    |                 | invoice_id (FK)     |
| email, phone       |                 | principal_amount    |                 | amount_paid         |
| credit_limit       |                 | penalty_amount      |                 | payment_method      |
| risk_tier (Low/Med)|                 | total_amount        |                 | utr_reference       |
| status (ACTIVE)    |                 | status (PENDING/PAID)                 | payment_date        |
+--------------------+                 +---------------------+                 +---------------------+
                                                  │
                                                  │ 1:N
                                                  ▼
+--------------------+                 +---------------------+                 +---------------------+
|   CHAT_SESSIONS    |       1:N       |      APPROVALS      |                 |    AGENT_ACTIONS    |
+--------------------+---------------->+---------------------+                 +---------------------+
| session_id (PK)    |                 | approval_id (PK)    |                 | action_id (PK)      |
| title              |                 | invoice_id (FK)     |                 | session_id          |
| created_at         |                 | threshold_amount    |                 | action_type         |
+--------------------+                 | status (PENDING/OK) |                 | tool_name           |
        │                              | requested_action    |                 | details (JSONB)     |
        │ 1:N                          +---------------------+                 | created_at          |
        ▼                                                                      +---------------------+
+--------------------+
|   CHAT_MESSAGES    |
+--------------------+
| message_id (PK)    |
| session_id (FK)    |
| role (user/ai)     |
| content, thoughts  |
+--------------------+
```

---

## ⚙️ Environment Configuration

### Backend (`backend/.env`)
Copy `backend/.env.example` to `backend/.env` and configure your credentials:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite:///./ar_management.db` | PostgreSQL connection string or SQLite fallback |
| `AWS_REGION` | `us-east-1` | AWS region where Bedrock is provisioned |
| `AWS_ACCESS_KEY_ID` | `your_access_key` | AWS IAM credentials with `bedrock:InvokeModel` access |
| `AWS_SECRET_ACCESS_KEY` | `your_secret_key` | AWS Secret Key |
| `BEDROCK_MODEL_ID` | `us.amazon.nova-pro-v1:0` | Amazon Nova Pro model identifier |
| `EMAIL_PROVIDER` | `simulated` | Set to `smtp` for real email dispatches via Gmail |
| `SMTP_USER` | `your_email@gmail.com` | Google account email |
| `SMTP_PASSWORD` | `your_16_char_app_password` | 16-character Google App Password (not your Gmail password) |
| `PENALTY_RATE_PERCENT` | `2.0` | Contractual late interest percentage |
| `HIGH_VALUE_APPROVAL_THRESHOLD` | `100000.0` | Approval gate threshold in INR (₹) |

### Frontend (`frontend/.env`)
Copy `frontend/.env.example` to `frontend/.env`:
```env
VITE_API_URL=http://127.0.0.1:8000/api
```

---

## 🚀 Installation & Local Setup

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** & npm
- **AWS Account** with Bedrock Nova Pro enabled in `us-east-1`
- (Optional) **PostgreSQL 15+** (SQLite works automatically out of the box for demo/testing)

### 1. Backend Setup
```powershell
cd backend

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate   # On Linux/macOS: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
copy .env.example .env

# Run FastAPI development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation will be live at: `http://127.0.0.1:8000/docs`

### 2. Frontend Setup
In a new terminal window:
```powershell
cd frontend

# Install Node modules
npm install

# Set up frontend environment
copy .env.example .env

# Start Vite dev server
npm run dev
```
Dashboard will be live at: `http://localhost:5173`

---

## 🌐 Core API Endpoints

| Category | Method | Endpoint | Description |
| :--- | :---: | :--- | :--- |
| **Agent Copilot** | `POST` | `/api/agent/chat` | Multi-turn conversational reasoning with tool execution |
| | `GET` | `/api/agent/stream` | Real-time Server-Sent Events (SSE) token and thought streaming |
| | `GET` | `/api/agent/active-turn` | Rehydrates background AI reasoning state upon tab switch |
| **Invoices** | `GET` | `/api/invoices` | List all open and settled debtor invoices with dynamic interest |
| | `POST` | `/api/invoices` | Issue a new commercial tax invoice |
| | `POST` | `/api/invoices/{id}/payment` | Record a payment remittance against an outstanding invoice |
| **Customers** | `GET` | `/api/customers` | Query debtor directory and credit risk scoring tiers |
| | `POST` | `/api/customers` | Register a new debtor account with credit limit checks |
| **Approvals** | `GET` | `/api/approvals` | List tickets exceeding the ₹1,00,000 governance threshold |
| | `POST` | `/api/approvals/{id}/approve` | Executive approval to dispatch pending communication |
| | `POST` | `/api/approvals/{id}/reject` | Reject and cancel proposed action |
| **Simulation** | `POST` | `/api/simulation/customer-reply` | Ingest simulated debtor emails (UTR proofs, disputes, extensions) |
| **Analytics** | `GET` | `/api/analytics/dashboard` | Fetch executive KPIs, DSO meters, and aging distributions |
| **Settings** | `GET` | `/api/settings` | Read runtime late penalty, reminder, and bank coordinates |
| | `PUT` | `/api/settings/penalty` | Hot-reload penalty compounding rate and grace periods |

---

## 🧪 Testing & Verification

The backend includes an automated test suite containing **80+ test cases** covering guardrails, multi-turn reasoning, UTR classification, and scheduler persistence:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests/ -v
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
