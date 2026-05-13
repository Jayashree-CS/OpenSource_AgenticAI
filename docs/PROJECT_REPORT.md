# CopilotAI — Enterprise HR & IT Agentic Assistant

**Project Report (for SharePoint Submission)**
Stack: FastAPI · React · LangChain · LangGraph · Chroma · Groq · Gemini · Microsoft Power Automate

---

## 1. PROJECT TITLE

**CopilotAI — A Multi-Agent Enterprise Assistant for HR Policy, Leave, IT Support, and Asset Lifecycle Management with Role-Based Access Control and Power Automate Notification Orchestration.**

---

## 2. PROJECT ABSTRACT

Enterprises operate fragmented HR and IT service desks: leave applications in HRMS portals, IT issues in ticketing tools, asset procurement in spreadsheets, and policies buried in PDFs. Each interaction costs employees minutes and managers hours of approval triage every week.

**CopilotAI** consolidates all four workflows behind a single conversational interface. A user can apply for leave, raise an IT ticket, request an asset, ask "what is the notice period?", or check pending approvals — all in plain English. Behind the chat surface, a deterministic intent classifier and a LangGraph multi-agent router decide whether the message is a knowledge query (answered via Retrieval-Augmented Generation over the company's ingested policy PDFs) or an actionable workflow (executed against a SQLAlchemy / SQLite domain model). All state-changing events emit Microsoft Power Automate webhooks so managers, IT engineers, and admins receive Teams / email notifications.

Four departments are first-class citizens: **HR** (leave + policy), **IT** (tickets + asset procurement), **Operations / Management** (approval workflows), and **Admin** (audit logs, system health, webhook diagnostics). The stack is built around `LangChain 1.2`, `LangGraph 1.1`, `Groq Llama 3.1 / 3.3`, `Gemini 2.0 Flash`, `Chroma 1.5` with HuggingFace `all-MiniLM-L6-v2` embeddings, `FastAPI 0.136`, and a `React 18 + Vite 8` SPA. RBAC is enforced at the route, action, RAG, and UI layers.

**Business value:** a single chat channel that reduces approval turnaround from days to minutes, eliminates duplicate IT tickets, gives managers a live pending-approval widget, and gives admins a complete audit trail of every agent action, webhook attempt, and policy citation.

---

## 3. OBJECTIVE

### 3.1 Original assignment objective
Build an internal enterprise AI assistant demonstrating: agentic AI via **LangGraph**, **RAG** over company documents, **RBAC** across HR/IT use cases, **workflow automation** via Power Automate, **conversation memory**, and a **modern web UI** with role-aware dashboards.

### 3.2 What the system needed to achieve
1. Accept natural-language requests, classify intent, and dispatch to the correct domain agent.
2. Execute deterministic workflows (apply leave, raise ticket, request asset) with persistence and approval chains.
3. Answer policy questions only from the official ingested corpus — never hallucinate company facts.
4. Enforce RBAC so an employee cannot approve their own leave or read confidential HR documents.
5. Notify the correct stakeholder (manager / IT team / asset desk) on every state change.
6. Maintain conversation continuity so follow-ups like "yes, confirm" do not require restating context.

### 3.3 Enterprise use case (concrete walkthrough)
> *07:55* — Employee `Jayashree`: *"apply 2 days casual leave next Monday and Tuesday, reason: family function"*. The bot extracts dates, validates balance, persists `LeaveRequest(status=pending_manager)`, fires HR webhook, Manager `Poorna` gets a Teams card.
> *08:10* — Manager opens CopilotAI, the **ApprovalWidget** shows the new request, she types *"approve leave 7"*. RBAC validates, status flips to `approved`, balance decremented, employee gets a confirmation webhook.
> *10:30* — Employee: *"my VPN keeps disconnecting"*. Intent classifier returns `ticket`, duplicate-detection finds none, IT ticket #14 is created, IT team gets a webhook + ApprovalWidget entry.
> *14:00* — Admin `Srinivasa` opens **AdminConsole**, hits `/admin/notifications/test`, validates all three channels, downloads system logs.

### 3.4 Fulfillment
Every step above maps to concrete files in §4.

---

## 4. ORIGINAL REQUIREMENTS ANALYSIS

| # | Requirement | Implemented in my project | Status |
|---|---|---|---|
| 1 | **HR module** — leave + policy Q&A | `agents/hr_agent.py`, `actions/leave_action.py`, `routes/leave.py` | ✅ |
| 2 | **IT module** — tickets + assets + lifecycle | `agents/it_agent.py`, `actions/it_action.py`, `actions/asset_action.py` | ✅ |
| 3 | **RAG over policy docs** with citations | `rag/ingest.py`, `rag/retriever.py`, 8 PDFs in `data/documents/` | ✅ |
| 4 | **RBAC** at multiple layers | `config/rbac.py` (4 roles × 13 permissions), `frontend/src/utils/rbac.js`, `App.jsx` | ✅ |
| 5 | **Approval workflows** — multi-stage | leave (manager-final), asset (manager → IT → inventory → final), ticket state machine | ✅ |
| 6 | **Tracing / logging** — audit trail | `db/models.py::SystemLog`, `actions/log_action.py`, `utils/logging_config.py` | ✅ |
| 7 | **Conversation memory** — multi-turn | `graph_structure/state.py::AgentSessionState` (max 40 turns + pending workflow slot) | ✅ |
| 8 | **Power Automate integration** | `actions/power_automate_action.py` (3 channels + retries + audit) | ✅ |
| 9 | **LangGraph orchestration** | `graph_structure/graph.py` (router → hr / it / end) | ✅ |
| 10 | **FastMCP** | Not used — direct LangChain + LangGraph instead. `langchain-protocol` present but unwired. | ⚪ Deliberate de-scope |
| 11 | **Audit logging** | `SystemLog` + `NotificationLog` tables, `/dashboard/logs`, `SystemLogs.jsx` | ✅ |
| 12 | **Web search fallback** | Not used — bot is hard-scoped to internal corpus by `services/scope_guard.py` | ⚪ Deliberate de-scope |
| 13 | **Hybrid models** | `llm.py` exposes Groq Llama 3.1 8B, Llama 3.3 70B, Gemini 2.0 Flash | ✅ |
| 14 | **Role-aware frontend** | 17 pages, 4 layouts (`EmployeeLayout`, `ManagerLayout`, `ITLayout`, `AdminLayout`) | ✅ |

12 of 14 capability lines are implemented end-to-end; FastMCP and external web search were de-scoped because the bot is intentionally a closed-corpus assistant.

---

## 5. SYSTEM OVERVIEW

End-to-end flow of a single chat message:

1. **Authentication** — `POST /login` (`routes/chat.py`) issues a JWT; `actions/auth_dependency.get_current_user` decodes it on every subsequent request.
2. **Chat ingress** — `POST /chat` loads the user's `AgentSessionState` from the in-memory store.
3. **Scope guard** — `services/scope_guard.evaluate(msg)` runs a deterministic regex check; out-of-scope queries (recipes, weather, sports, jokes) are short-circuited with a friendly redirect. No LLM call is made.
4. **Orchestration** — `services/orchestrator.orchestrate` calls `services.intent_classifier.classify`, which runs:
   1. `services/normalization.normalize_message` (phrase rewrites, synonyms, date parsing, entity extraction).
   2. Deterministic regex for the 7 canonical intents (`leave`, `ticket`, `asset`, `approval`, `inventory`, `informational`, `conversational`).
   3. **Gemini 2.0 Flash** fallback for ambiguous messages; **Groq Llama 3.1 8B** second-line fallback.
   4. Session's `pending_workflow` is honoured — bare "yes" routes back into the waiting flow.
5. **LangGraph dispatch** — `graph_structure/graph.py` produces a compiled `StateGraph`; the `router` node calls `agents/router_agent.route_query`; conditional edges send state to `hr`, `it`, or `__end__`.
6. **Agent execution** — `hr_agent` or `it_agent` parses intent, consults DB, applies RBAC, returns either an answer or a "needs confirmation" prompt.
7. **Action layer** — On confirmation, agents call `actions/*` (`leave_action`, `it_action`, `asset_action`). Each action: schema validation → DB transaction → email → Power Automate webhook → `SystemLog`.
8. **Power Automate** — Webhooks pushed through `ThreadPoolExecutor(max_workers=5)`, 3 retries, 20s timeout. Every attempt persisted in `notification_logs`.
9. **Response** — Reply appended to `AgentSessionState.history` and returned to the React SPA. Managers and IT users see live items in the **ApprovalWidget** sidebar (polls `/api/manager/pending` or `/api/it/tickets/open`).
10. **Audit** — Every chat, approval, and webhook is queryable via `/dashboard/logs` (admin-only).

---

## 6. ARCHITECTURE

### 6.1 Component layers

| Layer | Technologies | Key files |
|---|---|---|
| **Frontend** | React 18, Vite 8, react-router-dom 6, axios, lucide-react | `frontend/src/App.jsx`, `frontend/src/pages/*` |
| **API gateway** | FastAPI 0.136, JWT, bcrypt | `backend/main.py`, `backend/routes/*` |
| **Orchestration** | LangGraph 1.1 StateGraph | `backend/graph_structure/graph.py` |
| **Intent / NLP** | Regex + Gemini Flash + Groq fallback | `backend/services/{normalization,intent_classifier,orchestrator,scope_guard}.py` |
| **Agents** | LangChain 1.2 wrappers | `backend/agents/{router_agent,hr_agent,it_agent}.py` |
| **Actions** | SQLAlchemy + Python | `backend/actions/*.py` |
| **RAG** | Chroma 1.5, MiniLM-L6-v2, Groq Llama 3.3 70B | `backend/rag/{ingest,retriever,cli}.py` |
| **Database** | SQLAlchemy 2.0 + SQLite (`hr_copilot.db`) | `backend/db/{database,models}.py` |
| **Memory** | In-process `AgentSessionState`, max 40 turns | `backend/graph_structure/state.py` |
| **Notifications** | Microsoft Power Automate webhooks | `backend/actions/power_automate_action.py` |
| **Tracing** | `SystemLog` + structured JSON | `backend/db/models.py`, `backend/utils/logging_config.py` |

### 6.2 Architecture diagram (text)

```
                ┌──────────────────────────────────────────────────────────┐
                │                React SPA  (Vite, port 5173)              │
                │ AuthContext · 4 role layouts · ApprovalWidget · Toast    │
                └──────────────┬───────────────────────────────────────────┘
                               │ axios / JWT
                ┌──────────────▼───────────────────────────────────────────┐
                │            FastAPI 0.136   (uvicorn, port 8000)          │
                │   /chat · /leave · /dashboard · /api/{employee, manager, │
                │   it, admin}                                             │
                └──────┬───────────────┬────────────────────────┬──────────┘
                       │               │                        │
              ┌────────▼────────┐  ┌───▼─────────────────┐  ┌───▼──────────┐
              │  scope_guard    │  │  orchestrator       │  │  RBAC        │
              │  (regex only)   │  │  + intent_classifier│  │  4 roles ×   │
              └────────┬────────┘  │  (regex → Gemini →  │  │  13 perms    │
                       │           │   Groq fallback)    │  └──────────────┘
                       │           └────┬────────────────┘
                       │                │
                       │       ┌────────▼────────────┐
                       │       │   LangGraph         │
                       │       │   router_node       │
                       │       │   ├─ hr_node ───────┼──► hr_agent.py
                       │       │   └─ it_node ───────┼──► it_agent.py
                       │       └────────┬────────────┘
                       │                │
                       │       ┌────────▼─────────────────────────────────┐
                       │       │  actions/ (leave, it, asset, inventory)  │
                       │       └────────┬───────────────┬────────────┬────┘
                       │                │               │            │
              ┌────────▼─────┐  ┌───────▼──────┐ ┌─────▼─────┐  ┌────▼──────────┐
              │  RAG         │  │  SQLite      │ │  Email    │  │ Power Automate│
              │  Chroma +    │  │  hr_copilot  │ │ (SMTP)    │  │ HR / IT /     │
              │  MiniLM-L6   │  │  9 tables    │ └───────────┘  │ Asset webhooks│
              └──────────────┘  └──────────────┘                └─────┬─────────┘
                                                                      │
                                                                      ▼
                                                               Teams / Outlook
```

### 6.3 Per-concern breakdown

- **Frontend** — Vite SPA. `App.jsx` declares 4 protected layouts; each route wrapped in `<RequireAuth roles={...}>`. Role normalisation in `utils/rbac.js`.
- **Backend** — FastAPI in `main.py` with CORS, global `HTTPException` handler returning uniform `{success, message, data, error}`, startup hooks for table creation, legacy-role migration (`it` → `it_team`), and Power Automate channel diagnostics.
- **Database** — SQLite via SQLAlchemy. 9 tables (§9). All timestamps timezone-aware.
- **RAG** — Persisted Chroma at `chroma_db/hr_policies/`. Local embeddings (CPU). Chunks 500/100. Metadata: `source`, `access_level`, `category`, `chunk_id`.
- **Power Automate** — Three URLs from `.env`. Structured JSON payload with `event_type`, `cta_url`, timestamp.
- **LangGraph** — 3 nodes (`router`, `hr`, `it`). Router defensively coerces unknown values to `"general"`.
- **LLM** — `llm.get_llm()` factory; temperature 0 everywhere.
- **Approvals** — Leave: 1-stage. Asset: 4-stage. Ticket: state-machine.
- **Memory** — Per-user `AgentSessionState` with rolling 40-turn history + `pending_workflow` slot.
- **Tracing** — `system_logs` + `notification_logs` + structured JSON stdout.

---

## 7. FOLDER STRUCTURE

```
FinalAgenticAi/
├── .gitignore                            # root ignore (OS, IDE, archives)
├── .vscode/
├── backend/
│   ├── .env                              # secrets (gitignored)
│   ├── .gitignore
│   ├── main.py                           # FastAPI app + CORS + startup hooks
│   ├── llm.py                            # hybrid LLM factory (Groq + Gemini)
│   ├── requirements.txt
│   ├── hr_copilot.db                     # SQLite app DB (runtime, gitignored)
│   ├── graph.mmd                         # exported Mermaid graph (generated)
│   ├── actions/                          # tool/action layer — pure logic
│   │   ├── auth_action.py · auth_dependency.py
│   │   ├── leave_action.py               # leave lifecycle + balance + overlap
│   │   ├── it_action.py                  # ticket state machine + duplicates
│   │   ├── asset_action.py               # 4-stage asset approval workflow
│   │   ├── inventory_action.py
│   │   ├── calendar_action.py · enhanced_date_action.py
│   │   ├── email_action.py
│   │   ├── power_automate_action.py      # 3-channel webhook sender
│   │   ├── notification_log_action.py
│   │   ├── log_action.py · hr_ai_action.py
│   ├── agents/                           # LLM agents
│   │   ├── router_agent.py               # regex + LLM intent router
│   │   ├── hr_agent.py                   # leave + RAG
│   │   └── it_agent.py                   # ticket + asset
│   ├── auth/
│   │   ├── seed_employees.py             # seeds 4 demo users
│   │   └── set_passwords.py
│   ├── config/
│   │   ├── rbac.py                       # Roles, Permissions, RBACService
│   │   └── dateTime.py
│   ├── db/
│   │   ├── database.py                   # SQLAlchemy engine + SessionLocal
│   │   └── models.py                     # 9 ORM tables + Pydantic schemas
│   ├── graph_structure/
│   │   ├── graph.py                      # LangGraph StateGraph builder
│   │   └── state.py                      # AgentSessionState + store
│   ├── rag/
│   │   ├── ingest.py                     # PDF ingest pipeline
│   │   ├── retriever.py                  # RBAC-aware retrieval
│   │   └── cli.py                        # `python -m rag.cli` reindex
│   ├── routes/                           # FastAPI routers
│   │   ├── chat.py                       # /chat + /login + /register
│   │   ├── leave.py                      # /leave/*
│   │   ├── dashboard.py                  # /dashboard/* + /admin/*
│   │   ├── api_employee.py · api_manager.py · api_it.py · api_admin.py
│   ├── services/
│   │   ├── normalization.py              # phrase rewrites + entity extraction
│   │   ├── intent_classifier.py          # rules → Gemini → Groq
│   │   ├── orchestrator.py               # OrchestrationDecision builder
│   │   └── scope_guard.py                # out-of-scope refusal layer
│   ├── utils/
│   │   ├── logging_config.py             # structured JSON logger
│   │   └── retry_utils.py                # retry decorators (exp backoff)
│   ├── data/documents/                   # 8 ingested PDFs (gitignored)
│   ├── chroma_db/, rag_db/               # persisted vector stores (gitignored)
│   ├── tests/                            # pytest suites
│   └── venv/                             # local virtualenv (gitignored)
└── frontend/
    ├── .env                              # VITE_API_BASE (gitignored)
    ├── .gitignore
    ├── package.json · vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx · App.jsx
        ├── api/                          # axios clients per domain
        ├── components/                   # ApprovalWidget, AdminConsole, ...
        ├── config/                       # ROUTES + ROLES configuration
        ├── context/                      # AuthContext
        ├── layouts/                      # CommonLayout + 4 role layouts
        ├── pages/                        # 17 pages (see §8)
        ├── hooks/
        └── utils/                        # rbac.js + helpers
```

### 7.1 Purpose of every important folder

| Folder | Purpose |
|---|---|
| `backend/actions/` | The "tool" tier: pure functions an agent or route handler can call. No HTTP, no LLM — just DB + side effects. |
| `backend/agents/` | LLM-driven agents that combine prompt construction, action calls, and response shaping. |
| `backend/services/` | Pre-agent NLP plumbing: normalisation, intent, scope, orchestration. |
| `backend/routes/` | FastAPI routers — one per persona (employee, manager, IT, admin) plus `chat`, `leave`, `dashboard`. |
| `backend/rag/` | RAG concerns isolated: ingest pipeline, retriever, CLI re-index. |
| `backend/graph_structure/` | LangGraph wiring + session-memory store. |
| `backend/config/` | Cross-cutting config: RBAC matrix, date helpers. |
| `backend/db/` | SQLAlchemy engine and 9-table schema. |
| `backend/utils/` | Logging + retry decorators. |
| `backend/auth/` | One-shot seed scripts for users + passwords. |
| `backend/data/documents/` | The ingested PDF corpus (gitignored). |
| `frontend/src/pages/` | One page per role-specific dashboard. |
| `frontend/src/components/` | Reusable widgets including the role-aware `ApprovalWidget`. |
| `frontend/src/layouts/` | Four role-specific shells (sidebar + header + outlet). |
| `frontend/src/api/` | Thin axios wrappers grouped by backend persona. |
| `frontend/src/config/` | Centralised `ROUTES` map + role enum. |

---

## 8. FILE STRUCTURE SUMMARY

### Backend — entry & wiring
- **`backend/main.py`** — FastAPI app. Configures CORS, mounts 8 routers, runs `Base.metadata.create_all`, runs legacy-role migration, prints Power Automate channel status on startup. Global `HTTPException` handler standardises error envelopes.
- **`backend/llm.py`** — `get_llm(model_type)` factory returning `ChatGroq` / `ChatGoogleGenerativeAI` keyed by `"groq_fast"`, `"groq_versatile"`, `"gemini_flash"`. Default temperature 0.

### Backend — agents
- **`agents/router_agent.py`** — `route_query(msg) → "hr" | "it" | "general"`. Layer 1 regex (~25 keywords), layer 2 Gemini Flash, layer 3 Groq fallback. Includes `SEMANTIC_MAP` keyword normalisation.
- **`agents/hr_agent.py`** — Leave application, cancellation, balance, status. Calls `leave_action` for state changes and `rag.retriever.retrieve_docs_with_sources` for policy questions with citations.
- **`agents/it_agent.py`** — Ticket and asset workflows. Performs duplicate detection, state-machine enforcement, manager-email composition.

### Backend — services
- **`services/normalization.py`** — `NormalizedQuery` dataclass with `original`, `normalized`, `dates`, `leave_type`, `asset_type`, `ticket_category`, `flags`. Phrase rewrites first ("not feeling good" → "sick leave"), then single-word synonyms.
- **`services/intent_classifier.py`** — 7-intent classifier with rule layer + LLM fallback. Returns `IntentResult(intent, agent, confidence, source, reason, normalized)`.
- **`services/orchestrator.py`** — `orchestrate(message, session_state)` returns `OrchestrationDecision` with `requires_confirmation` and `pending_workflow`.
- **`services/scope_guard.py`** — LLM-free guard. Refuses recipes, weather, sports, jokes, etc.

### Backend — actions
- **`actions/leave_action.py`** — `apply_leave`, `cancel_leave`, `approve_leave`, `reject_leave`, `get_leave_balance`. Working-day calc, overlap validation, balance decrement.
- **`actions/it_action.py`** — `create_ticket`, `check_duplicate_ticket`, `update_ticket_status`. Strict `TICKET_TRANSITIONS` graph.
- **`actions/asset_action.py`** — Four-stage lifecycle (`create_asset_request`, `approve_asset_by_manager`, `approve_asset_by_it`, `reject_asset_*`, `cancel_asset_request`).
- **`actions/power_automate_action.py`** — `send_hr_notification`, `send_it_notification`, `send_asset_notification`. Async via `ThreadPoolExecutor`, 3 retries.
- **`actions/auth_action.py` / `auth_dependency.py`** — bcrypt password hashing, JWT issuance, FastAPI dependencies.
- **`actions/enhanced_date_action.py`** — Natural-language date parsing.
- **`actions/email_action.py`** — SMTP stub with channel tagging.
- **`actions/log_action.py` / `notification_log_action.py`** — Persist into audit tables.

### Backend — RAG
- **`rag/ingest.py`** — Walks `./data/`, loads PDFs via `PyPDFLoader`, classifies access level + category by filename, splits with `RecursiveCharacterTextSplitter(chunk_size=500, overlap=100)`, persists to Chroma. Idempotent.
- **`rag/retriever.py`** — `_get_vectorstore()` `lru_cache`'d. `build_retriever(role)` constructs `RetrievalQA` with Groq Llama 3.3 70B and role-scoped `where` filter. `retrieve_docs_with_sources` returns `(text, source, page)` triples.
- **`rag/cli.py`** — `python -m rag.cli ingest` entry point.

### Backend — routes
- **`routes/chat.py`** — `/login`, `/register`, `/chat`. Orchestrates scope guard → orchestrator → LangGraph → agent.
- **`routes/leave.py`** — REST: apply, cancel, balance, list.
- **`routes/dashboard.py`** — `/dashboard/summary`, `/dashboard/logs`.
- **`routes/api_employee.py`** — Employee self-service.
- **`routes/api_manager.py`** — Pending approvals, approve/reject endpoints.
- **`routes/api_it.py`** — Open tickets, IT-stage assets.
- **`routes/api_admin.py`** — User management, system logs, **`/admin/notifications/config`** + **`/admin/notifications/test`**.

### Backend — config & db
- **`config/rbac.py`** — `Role` enum (4), `Permission` enum (13), `ROLE_PERMISSIONS`, `ROUTE_ACCESS`, `SIDEBAR_VISIBILITY`, `API_PERMISSIONS`, `RBACService`, helpers (`is_admin`, `is_manager`, `can_approve_*`).
- **`db/database.py`** — SQLite engine + `SessionLocal` + declarative `Base`.
- **`db/models.py`** — 9 ORM tables + Pydantic schemas.

### Backend — graph & memory
- **`graph_structure/graph.py`** — Compiles 3-node LangGraph.
- **`graph_structure/state.py`** — `AgentSessionState` + `InMemoryAgentStateStore` (thread-safe `RLock`).

### Backend — utilities
- **`utils/logging_config.py`** — Structured JSON formatter + `contextvars` for per-request user tracking.
- **`utils/retry_utils.py`** — `@retry` decorator with `EXPONENTIAL_BACKOFF` / `LINEAR_BACKOFF` / `FIXED_INTERVAL` and jitter.

### Frontend
| File | Purpose |
|---|---|
| `frontend/src/App.jsx` | Routes table + 4 role-protected layouts |
| `frontend/src/context/AuthContext.jsx` | JWT persistence + user state |
| `frontend/src/utils/rbac.js` | Mirror of backend role enum |
| `frontend/src/config/routesConfig.js` | `ROUTES` map per role |
| `frontend/src/pages/ChatPage.jsx` | Conversational UI + ApprovalWidget mount |
| `frontend/src/pages/AuthPage.jsx` | Login / register |
| `frontend/src/pages/{Employee,Manager,IT,Admin}Dashboard.jsx` | Role-specific summaries |
| `frontend/src/pages/{MyLeaves,MyTickets,MyAssets}.jsx` | Self-service history |
| `frontend/src/pages/{ApprovalHistory,TicketResolution,InventoryDashboard}.jsx` | Workflow pages |
| `frontend/src/pages/{SystemLogs,UserManagement,Analytics}.jsx` | Admin pages |
| `frontend/src/components/ApprovalWidget.jsx` | Role-aware pending list (manager → leaves+assets; IT → tickets+IT-stage assets) |
| `frontend/src/components/AdminConsole.jsx` | Webhook config + test buttons |
| `frontend/src/components/AppSidebar.jsx` | Role-filtered nav |
| `frontend/src/components/Toast.jsx` | Toast context |
| `frontend/src/api/client.js` | axios instance with JWT interceptor + base URL from `VITE_API_BASE` |

---

## 9. DATABASE DESIGN

Schema in `backend/db/models.py`, materialised by `Base.metadata.create_all` into `hr_copilot.db`.

### 9.1 Tables overview

| # | Table | Purpose | Used by |
|---|---|---|---|
| 1 | `employees` | Master user table | auth, RBAC, all agents |
| 2 | `leave_requests` | Per-application leave records | `hr_agent`, `leave_action`, `api_manager` |
| 3 | `leave_balances` | Per-employee balances for 3 leave types | `leave_action` |
| 4 | `tickets` | IT support tickets | `it_agent`, `it_action`, `api_it` |
| 5 | `asset_requests` | 4-stage asset procurement records | `it_agent`, `asset_action`, `api_manager`, `api_it` |
| 6 | `inventory` | Asset stock levels | `inventory_action`, `asset_action` |
| 7 | `holidays` | Company / public holidays | `calendar_action`, `leave_action` |
| 8 | `system_logs` | Per-action audit trail | `log_action`, `/dashboard/logs` |
| 9 | `notification_logs` | Per-webhook delivery audit | `power_automate_action`, `/admin/notifications/*` |

### 9.2 Column-level detail

**`employees`** — `id PK · name · email UNIQUE · role · department · manager_id · password_hash · created_at`

**`leave_requests`** — `id PK · employee_id · start_date · end_date · reason · status (pending_manager|approved|rejected|cancelled) · leave_type (sick|casual|earned) · total_days · manager_email`

**`leave_balances`** — `id PK · employee_id UNIQUE · sick_total/used · casual_total/used · earned_total/used` (defaults 6/6/12)

**`tickets`** — `id PK · user_id (email) · issue_type · description · priority · status (open|in_progress|resolved|closed|rejected) · assigned_engineer · created_at · updated_at`

**`asset_requests`** — `id PK · user_id (email) · asset_type · reason · manager_status · it_status · inventory_status · final_status · created_at · updated_at`  (four independent status columns enable a true 4-stage pipeline)

**`inventory`** — `id PK · asset_type UNIQUE · total_quantity · available_quantity · updated_at`

**`holidays`** — `id PK · holiday_date UNIQUE · name · holiday_type (company|public)`

**`system_logs`** — `id PK · user_id · user_email · user_role · agent · action · tool_used · status · message · response · created_at`

**`notification_logs`** — `id PK · channel (hr|it|asset) · event_type · target_url · status (pending|success|failed) · payload (JSON text) · error · attempts · created_at · updated_at`

### 9.3 Relationships

```
employees (1) ──< (N) leave_requests           via employee_id
employees (1) ──< (N) tickets                  via user_id = email
employees (1) ──< (N) asset_requests           via user_id = email
employees (1) ──< (1) leave_balances           via employee_id (unique)
employees (1) ──< (N) employees                self-ref via manager_id
asset_requests (N) >── (1) inventory           via asset_type
employees (1) ──< (N) system_logs              via user_id / user_email
notification_logs · holidays                   independent reference tables
```

Relationships are enforced at the application layer (no `ForeignKey` constraints declared in the ORM) because the cross-domain join on `user_id = email` historically simplified early migrations.

---

## 10. MODULE IMPLEMENTATION

### A. HR Module

**A.1 Policy assistant** — `hr_agent._answer_policy_question` calls `rag.retriever.retrieve_docs_with_sources(query, k=4, role=user.role)`, assembles context with `[1] source (p.X)` citation tags, invokes Groq Llama 3.3 70B with strict instruction: *"Answer using ONLY the provided context. If not present, reply exactly: 'I couldn't find this in our company documents. Please contact HR for clarification.'"* RBAC filtering applied at retriever level.

**A.2 Leave management** — Five operations: `apply`, `cancel`, `approve`, `reject`, `balance`. Dates extracted via `enhanced_date_action.parse_relative_date_safe`. The agent enforces a non-empty, non-placeholder `reason` (explicit user requirement), validates against `BLOCKING_LEAVE_STATUSES` for overlap, and checks the relevant balance column before persisting.

**A.3 Approval workflow** — Single-stage manager-only. `can_approve_leave` rejects employees/IT. On approval: status → `approved`, `*_used` column incremented, HR webhook with `status_color="#22c55e"`. On rejection: status → `rejected`, no balance change, webhook with `status_color="#ef4444"`.

### B. IT Module

**B.1 Support tickets** — `create_ticket` first calls `check_duplicate_ticket` (same `user_id` + `issue_type` + open status). Duplicates return a friendly "ticket #N is still open" instead of a new row. State transitions constrained by `TICKET_TRANSITIONS`; illegal jumps raise `TicketTransitionError`.

**B.2 Asset requests** — Four sequential stages:

```
employee → manager_status=approved → it_status=approved
                                  → inventory_status=reserved
                                  → final_status=fulfilled
```

Each stage fires its own Power Automate notification. Manager rejection short-circuits to `final_status=rejected`; IT rejection skips inventory. `reserve_inventory` decrements `available_quantity` atomically inside the same transaction.

**B.3 Issue validation** — `services/normalization.py` rewrites colloquial phrases ("VPN down", "wifi issue", "system slow") into canonical tokens before the IT agent reads them, dramatically improving classification accuracy on noisy input.

**B.4 Assignment flow** — `assigned_engineer` populated when an IT user accepts a ticket via the IT dashboard; transition `open → in_progress` is the trigger.

### C. Admin features

- **AdminConsole** (`frontend/src/components/AdminConsole.jsx`) drives **`/admin/notifications/config`** + **`/admin/notifications/test`**.
- **UserManagement** page exposes every `Employee` row with role editing.
- **SystemLogs** reads `/dashboard/logs` — admin-only — backed by `system_logs`.
- **Webhook diagnostics on startup** — `main.py::_log_notification_channels` prints all three channels' status at boot.

### D. Analytics features

- **ManagerDashboard** + **Analytics** surface counts from `/dashboard/summary` filtered by manager's team.
- **InventoryDashboard** shows stock levels with low-stock highlighting.
- **ApprovalHistory** reads `/api/manager/history`.

---

## 11. LANGGRAPH IMPLEMENTATION

### 11.1 State

```python
class GraphState(TypedDict):
    message: str
    agent: str
    response: str
    db: object
    user: object
    history: list
    session_state: object
```

`session_state` is the `AgentSessionState` fetched from `agent_state_store.get(user_id)`. The graph never mutates the DB directly — it forwards `db` and `user` into the agent nodes.

### 11.2 Nodes

| Node | Function | Output |
|---|---|---|
| `router` | `route_query(message)` | `{"agent": "hr" \| "it" \| "general"}` |
| `hr` | `hr_agent(message, db, user, history, session_state)` | `{"response": str, "agent": "hr"}` |
| `it` | `it_agent(...)` | `{"response": str, "agent": "it"}` |

### 11.3 Conditional routing

```python
builder.add_conditional_edges(
    "router",
    lambda s: s["agent"] if s["agent"] in {"hr", "it"} else "general",
    {"hr": "hr", "it": "it", "general": "__end__"},
)
```

`general` queries skip the LangGraph agent nodes entirely and are handled by `routes/chat.py::_answer_general_question`, which performs RAG against the policy corpus with a strict refusal prompt.

### 11.4 Approvals, memory, tools

- **Approvals** are deterministic inside `hr_agent` / `it_agent` (RBAC + DB + webhook); they are not separate graph nodes.
- **Memory** injected via `state["session_state"]`. After each successful exchange, `routes/chat.py` calls `session_state.record_exchange(user_msg, assistant_reply)`.
- **Tools** are direct function calls into `backend/actions/*` rather than LangChain `Tool` wrappers — simpler tracing, lower latency.

### 11.5 Final response

```python
{"reply": "<assistant text>", "agent": "hr" | "it" | "general"}
```

A Mermaid export lives at `backend/graph.mmd`.

---

## 12. MULTI-AGENT SYSTEM

### 12.1 Router Agent · `agents/router_agent.py`
- **Role:** Classifier at LangGraph entry (hr / it / general).
- **Responsibility:** Deterministic regex priority routing + LLM fallback.
- **Tools:** `get_llm("gemini_flash")` primary, `get_llm("groq_fast")` fallback.
- **Invocation:** `router` node, every chat request.

### 12.2 HR Agent · `agents/hr_agent.py`
- **Role:** Leave + policy specialist.
- **Tools:** `leave_action.*`, `enhanced_date_action.parse_relative_date_safe`, `rag.retriever.retrieve_docs_with_sources`, `email_action.send_email`, `power_automate_action.send_hr_notification`.
- **Invocation:** LangGraph `hr` node.

### 12.3 IT Agent · `agents/it_agent.py`
- **Role:** Ticket + asset specialist.
- **Tools:** `it_action.*`, `asset_action.*`, `inventory_action.reserve_inventory`, `email_action.send_email`, `power_automate_action.send_it_notification`, `power_automate_action.send_asset_notification`.
- **Invocation:** LangGraph `it` node.

### 12.4 RAG Agent (functional) · `rag/retriever.py`
- **Role:** RBAC-aware retrieval + Groq Llama 3.3 70B answer composition.
- **Tools:** Chroma vector store, MiniLM-L6-v2 embeddings, `RetrievalQA` chain.
- **Invocation:** Called by HR agent for policy questions and by `chat.py::_answer_general_question`.

### 12.5 Approval Agent (functional)
- **Role:** RBAC gatekeeper for state transitions.
- **Implementation:** Action-layer functions `approve_leave`, `update_ticket_status`, `approve_asset_by_*`.
- **Tools:** `rbac.can_approve_*`, `power_automate_action.send_*`, `notification_log_action.record_attempt`.

### 12.6 Email Agent (functional) · `actions/email_action.py`
- **Role:** SMTP delivery with channel tagging.

The brief also mentioned a hypothetical **Analytics Agent**; this build serves analytics via `/dashboard/summary` + frontend dashboards rather than an LLM agent, because the queries are deterministic aggregations.

---

## 13. RAG IMPLEMENTATION

### 13.1 Document source
Eight PDFs in `backend/data/documents/`: `Novigo Leave Policy.pdf`, `Novigo-Policy-SalaryAdvance V1.4.pdf`, `CSR policy_Novigo.pdf`, `employee_handbook.pdf` (~48 MB), `novigo_company_knowledge.pdf`, `policy.pdf`, `salary.pdf`, `code.pdf`.

### 13.2 Ingestion · `rag/ingest.py`
- Walks `./data/`, loads each PDF via `langchain_community.document_loaders.PyPDFLoader`.
- Classifies access level by filename markers:
  - `admin` ← `admin`, `confidential`, `compensation`, `salary-advance`
  - `manager` ← `manager`, `leadership`, `approval`
  - `employee` ← everything else
- Classifies category: `leave`, `salary`, `code`, `csr`, `handbook`, `policy`, `general`.
- Splits with `RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)`.
- Stamps each chunk: `source`, `access_level`, `category`, `page`, stable `chunk_id = "{source}#p{page}#c{i}"`.
- Clears existing Chroma directory before re-ingest — idempotent.

### 13.3 Chunking
- **Size:** 500 chars (`RAG_CHUNK_SIZE`).
- **Overlap:** 100 chars (`RAG_CHUNK_OVERLAP`).
- Fits small policy paragraphs while keeping context-window costs low.

### 13.4 Embeddings
- `sentence-transformers/all-MiniLM-L6-v2` running on CPU.
- `normalize_embeddings=True` so cosine similarity behaves predictably.
- Zero external API cost.

### 13.5 Vector store
- `chromadb 1.5.8` via `langchain-chroma 1.1.0`.
- Persisted at `./chroma_db/hr_policies/` (secondary `rag_db/` holds an experimental larger collection).
- Singleton via `lru_cache(maxsize=1)` — embedding model loaded once per process.

### 13.6 Retrieval
- `top_k = 4` (`RETRIEVER_TOP_K`).
- Role-driven Chroma `where` filter:
  - `admin` → no filter.
  - `manager` → `{"access_level": {"$in": ["employee", "manager"]}}`.
  - everyone else → `{"access_level": "employee"}`.

### 13.7 Citation-aware response
`retrieve_docs_with_sources` returns `(text, source, page)` triples. HR agent prompt instructs LLM to cite as `[1] [2]` mapped to the numbered sources. Front-end renders bracketed citations as clickable badges.

### 13.8 Integration points
- **`agents/hr_agent.py`** — policy intent.
- **`routes/chat.py::_answer_general_question`** — `general` route (company name, CEO, mission).

---

## 14. POWER AUTOMATE INTEGRATION

### 14.1 Channels

| ENV var | Channel | Triggers |
|---|---|---|
| `POWER_HR_URL` | HR / Leave | `leave_applied`, `leave_approved`, `leave_rejected`, `leave_cancelled` |
| `POWER_IT_URL` | IT / Ticket | `ticket_created`, `ticket_updated`, `ticket_resolved`, `ticket_rejected` |
| `POWER_ASSET_URL` | Asset | `asset_requested`, `asset_manager_approved`, `asset_it_approved`, `asset_rejected`, `asset_fulfilled` |

### 14.2 Payload contract

```jsonc
{
  "event_type": "leave_applied",
  "title": "Leave Applied: Casual",
  "message": "Jayashree has applied for 2 days of casual leave",
  "status": "PENDING_MANAGER",
  "status_color": "#facc15",
  "employee_name": "Jayashree",
  "leave_type": "casual",
  "reason": "family function",
  "start_date": "2026-05-18",
  "end_date": "2026-05-19",
  "leave_id": 7,
  "cta_text": "Open Dashboard",
  "cta_url": "http://localhost:5173",
  "timestamp": "2026-05-12T07:55:23.118Z",
  "source": "enterprise_ai_copilot",
  "metadata": { /* arbitrary context */ }
}
```

### 14.3 HTTP flow

```
action_function (e.g. apply_leave)
        │
        ▼
send_hr_notification(...)        ←─── builds payload, picks POWER_HR_URL
        │
        ▼
_send_webhook(url, payload, async_send=True)
        │   submits to ThreadPoolExecutor(max_workers=5)
        ▼
_runner() loop:
  for attempt in 1..3:
      _do_post(url, payload)            ← urllib, 20s timeout
      if 2xx: record_attempt(status=success); return True
      sleep(2)
  record_attempt(status=failed, error=last_error)
```

### 14.4 Audit + diagnostics

Every attempt — success or failure — writes a `notification_logs` row with channel, event, URL, payload, status, attempt count, error. Admins query that table directly, or hit `/admin/notifications/config` (introspection) and `/admin/notifications/test` (synchronous test fire). On boot, `main.py` prints configured/unconfigured status of every channel.

### 14.5 Downstream

Power Automate flows fan out to Outlook (manager / IT mailbox) and Teams adaptive cards. The bot owns the webhook contract; routing inside Microsoft 365 is the customer's concern.

---

## 15. SECURITY

### 15.1 RBAC matrix

| Role | View Leave | View Ticket | View Asset | Approve Leave | Approve Ticket | Approve Asset | View Sys Logs | Admin Console |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `employee` | ✅ (own) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `manager` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `it_team` | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### 15.2 Enforcement layers

1. **Authentication middleware** — `actions/auth_dependency.get_current_user` decodes JWT, looks up `Employee`, returns 401 on invalid token.
2. **Role guards** — `require_roles({...})` FastAPI dependency returns 403 on mismatch; used on every manager / IT / admin route.
3. **Action-layer re-checks** — `approve_leave`, `update_ticket_status`, `approve_asset_by_*` all call `rbac.can_approve_*` again, so a stolen JWT for an employee cannot approve their own leave by hitting the API directly.
4. **Frontend route protection** — `App.jsx` wraps every layout in `<RequireAuth roles={[...]}>`; role mismatch redirects to that role's default route.
5. **Sidebar visibility** — `rbac.py::SIDEBAR_VISIBILITY` mirrored in `frontend/src/utils/rbac.js`; nav items invisible to a role are unmounted, not hidden.
6. **RAG filter** — `rag/retriever.py::_role_filter` injects a Chroma `where` clause; an employee literally cannot retrieve admin-classified text.
7. **Role normalisation** — `_canonical_role` collapses legacy `"it"`, `"itteam"`, `"it-team"` to `"it_team"`; `main.py::_migrate_legacy_roles` upgrades old DB rows on startup.

### 15.3 Other measures

- bcrypt-hashed passwords (`actions/auth_action.hash_password`).
- JWT signing key in `.env`, never hardcoded.
- CORS restricted to `CORS_ORIGINS` env var (defaults only to localhost dev ports).
- `.env` gitignored at root, backend, and frontend.
- Power Automate URLs treated as secrets.
- `system_logs` audit trail admin-readable only.

---

## 16. MEMORY SYSTEM

### 16.1 Short-term — `AgentSessionState`

Per-user, in-process, in `graph_structure/state.py::InMemoryAgentStateStore`:

- **Rolling history** — `history: list[ChatTurn]` with `trim_history()` enforcing `max_history=40`. Older turns dropped to bound prompt size.
- **Pending workflow slot** — `pending_workflow: {type, data, timestamp}`. Enables multi-step confirmation: bot stores `{"type": "hr_leave", "data": {dates, reason}}`; user replies "yes"; orchestrator detects `is_confirmation`, reads pending slot, routes back to HR agent with full context.
- **Active / last agent tracking** — `active_agent`, `last_agent`. Tie-breakers like "show status" after a ticket conversation are treated as IT follow-ups.
- **Thread safety** — `RLock` around the store.

### 16.2 Long-term — DB persistence

- `system_logs` and `notification_logs` survive restarts (long-term audit memory).
- `leave_requests`, `tickets`, `asset_requests` are themselves long-term memory — "show my leaves" reads directly from these tables.

### 16.3 Continuity guarantees

- A page refresh keeps memory (user_id is the key).
- A backend restart clears short-term state but long-term DB intact, so "show my pending leaves" still works.
- Store designed to be swapped for Redis with a one-class change.

---

## 17. HYBRID MODEL USAGE

### 17.1 Models in play

| Alias | Provider | Model | Purpose |
|---|---|---|---|
| `groq_fast` | Groq | `llama-3.1-8b-instant` | Chit-chat, fallback classification |
| `groq_versatile` | Groq | `llama-3.3-70b-versatile` | RAG answering with citations |
| `gemini_flash` | Google | `gemini-2.0-flash` | Primary intent classification |

All wrapped behind `llm.get_llm(alias)`. Temperature 0 for determinism.

### 17.2 Routing logic

- **Router agent** — Gemini Flash classifies; Groq Llama 3.1 8B is rate-limit fallback.
- **Intent classifier** — Regex first, Gemini Flash second, Groq third.
- **RAG answers** — Always Groq Llama 3.3 70B (best reasoning over multiple citations).
- **General chat** — Groq Llama 3.1 8B (low latency).

### 17.3 Why hybrid

| Concern | Single-model risk | Hybrid mitigation |
|---|---|---|
| **Latency** | 70B on every message is slow | Cheap classifier first, 70B only for final answers |
| **Cost** | Calling 70B for "hi" wastes tokens | Tiny classifier picks lane, 70B only when needed |
| **Reliability** | One provider outage blocks everything | Two providers + regex underneath both |
| **Determinism** | Pure LLM routing drifts run-to-run | Regex layer at every decision gives reproducibility |

### 17.4 Concrete benefit

"apply 2 days casual leave next Monday":

1. Scope guard (regex, 0 ms, 0 tokens) — in scope.
2. Normaliser (regex, 1 ms, 0 tokens) — extracts `casual`, `next Monday`, `2 days`.
3. Intent classifier (regex hit, confidence 0.9, no LLM call).
4. Router (regex hit, no LLM call) — `hr`.
5. HR agent (Groq 8B, ~300 ms) — composes confirmation prompt.

**One** small-model call for the whole round trip. Only ambiguous messages incur Gemini Flash. Only policy questions incur the 70B call.

---

## 18. EXTRA FEATURES IMPLEMENTED BEYOND THE ASSIGNMENT

1. **Deterministic scope-guard layer** (`services/scope_guard.py`) — LLM-free refusal of out-of-domain queries.
2. **Hybrid intent classifier** with rule-first + Gemini-second + Groq-third — 7 canonical intents with confidence scores and reason strings.
3. **Phrase-level normaliser** — rewrites colloquial input ("not feeling good" → "sick leave") before LLM sees it.
4. **Role-aware ApprovalWidget** — managers see leaves + assets; IT team sees open tickets + IT-stage assets.
5. **IT team approval parity with managers** — IT approves both **asset requests** (IT stage) and IT tickets with full notification popups.
6. **Power Automate diagnostics endpoints** — `/admin/notifications/config` + `/admin/notifications/test`.
7. **Boot-time webhook channel report** — `_log_notification_channels` prints status of all three channels.
8. **Async webhook delivery + 3-attempt retry** — `ThreadPoolExecutor`; webhooks never block the chat reply.
9. **`notification_logs` audit table** — every webhook attempt persisted with status, error, attempt count, and payload.
10. **Legacy-role auto-migration on startup** — upgrades `"it"` rows to `"it_team"` without manual SQL.
11. **RBAC-aware retrieval** — `access_level` metadata stamped during ingest, applied at query time.
12. **Citation-aware policy answers** — bracketed `[1] [2]` tags rendered as clickable badges.
13. **Asset 4-stage lifecycle with independent status columns** — explicit pipeline state.
14. **Ticket state machine with explicit transition graph** — `TICKET_TRANSITIONS` rejects illegal jumps.
15. **Duplicate-ticket detection** — prevents users spamming the same issue.
16. **Multi-turn workflow continuation** — `pending_workflow` slot carries intent forward through bare confirmations.
17. **Structured JSON logging with context vars** — every log line carries user id, role, request id.
18. **Retry decorator library** — three strategies with jitter, usable across the action layer.
19. **Unified error envelope** — `{success, message, data, error}` everywhere.
20. **Branding consistency pass** — every prompt, notification footer, and test now says "CopilotAI".
21. **Admin webhook test from UI** — `AdminConsole.jsx` exposes the test endpoints with one click.
22. **Manager + IT pending widgets unified** — same component, role-aware data source.
23. **Frontend role layouts** — `EmployeeLayout`, `ManagerLayout`, `ITLayout`, `AdminLayout` instead of in-component role checks.

---

## 19. KEY ACHIEVEMENTS

### Enterprise concepts demonstrated
- Multi-agent orchestration via LangGraph.
- Closed-corpus RAG with role-aware retrieval and citations.
- Four-role RBAC enforced at five layers (UI / route / API / action / retrieval).
- Multi-stage approval workflows with idempotent state machines.
- Outbound webhook fan-out to Microsoft Power Automate with retries + audit.
- Conversation memory across multi-step workflows.
- Hybrid LLM cost / latency / reliability strategy.
- Per-action audit log queryable by admins.

### Technical concepts demonstrated
- LangChain 1.x tool chaining and `RetrievalQA` composition.
- LangGraph `StateGraph` with conditional edges and typed state.
- Chroma vector store with persisted embeddings and metadata filtering.
- SQLAlchemy 2.0 declarative models with timezone-aware timestamps.
- FastAPI dependency injection for auth, DB, role guards.
- React 18 + Vite 8 SPA with protected routes and role-aware layouts.
- JWT + bcrypt authentication.
- Thread-pool async side effects without blocking the request thread.
- Structured logging via `contextvars`.

### Production-readiness features
- Deterministic scope guard prevents off-brand behaviour.
- Three-layer fallback (regex → Gemini → Groq) keeps bot up during single-provider outage.
- Durable webhook delivery: 3 retries + full audit + admin replay endpoint.
- One-time DB migrations on startup for legacy data.
- All secrets behind `.env`; multi-level `.gitignore` enforces no-leak.
- Uniform error envelope across every endpoint.
- Health-style boot logging for webhook channels.

### Learning outcomes
- Composing deterministic rules with LLM fallbacks is more reliable and cheaper than pure-LLM pipelines.
- RBAC must be enforced at every layer, not just the UI.
- Notification systems need first-class audit storage from day one.
- Asset and approval lifecycles deserve separate status columns rather than overloaded enums.
- Memory is best modelled as `(history, pending_workflow)` rather than a single conversation log.

---

## 20. FUTURE IMPROVEMENTS

### Scalability
- **Postgres** instead of SQLite — single env var change.
- **Redis-backed `AgentSessionState`** — store class designed to be swappable.
- **Off-CPU embeddings** — HuggingFace Inference Endpoints or hosted embeddings for throughput.
- **Externalise Chroma** — managed `chromadb` cluster instead of local persist directory.

### Cloud deployment
- Containerise backend (FastAPI + uvicorn) and frontend (multi-stage Vite + nginx).
- Deploy backend on **Azure App Service** or **AKS**; frontend on **Azure Static Web Apps**.
- Secrets in **Azure Key Vault**, surfaced via App Service config.
- **Application Insights** for distributed tracing.

### Production improvements
- **Alembic migrations** instead of `create_all`.
- Strict Pydantic v2 request validation on every endpoint.
- **CI** running the existing pytest suites on every push.
- **Rate limiting** via `slowapi` on `/chat` and `/login`.
- **Refresh tokens** to complement short-lived JWT.
- **Webhook signature verification** so Power Automate callbacks can authenticate.
- **Sentry / Loki** sink for the structured JSON logger.

### Additional enterprise modules
- **Expense / reimbursement** — same 4-stage pattern as assets.
- **Onboarding bot** — checklist workflow for new hires.
- **Performance review** — calendar + form + approval pipeline.
- **Controlled web search** for explicitly-flagged questions outside the corpus.
- **FastMCP server** — expose `apply_leave`, `create_ticket`, `request_asset` as MCP tools.
- **Multilingual support** — translation pre-step for non-English prompts.

---

## 21. CONCLUSION

CopilotAI demonstrates that a tightly-scoped, well-instrumented enterprise assistant can deliver real business value without the brittleness usually associated with pure-LLM systems. By interleaving deterministic regex layers with hybrid LLM fallbacks, enforcing RBAC at every tier from UI to retrieval, and making every state-changing action observable through both an audit table and a Microsoft Power Automate webhook, the project meets the original assignment objectives — multi-agent orchestration, RAG, RBAC, approvals, memory, and Power Automate integration — and substantially extends them with scope guards, retry-and-audit webhook delivery, asset 4-stage lifecycle, ticket state machines, role-aware approval widgets, admin webhook diagnostics, and a uniform error envelope. The codebase is organised so each concern lives in its own module (services / actions / agents / routes / graph) and so swapping any one piece — SQLite for Postgres, in-memory store for Redis, Groq for OpenAI — is a single-file change. The result is a credible reference architecture for an HR + IT copilot that an enterprise could realistically extend toward production.

---

## 22. APPENDIX

### 22.1 Technologies

| Layer | Technology / Version |
|---|---|
| Language | Python 3.11+, JavaScript (ES2022) |
| Backend framework | FastAPI 0.136.1, uvicorn 0.46.0 |
| ORM | SQLAlchemy 2.0.49 |
| Database | SQLite (`hr_copilot.db`) |
| Auth | python-jose 3.5.0 (JWT), passlib 1.7.4 + bcrypt 4.3.0 |
| LLM SDKs | langchain 1.2.16, langchain-groq 1.1.2, langchain-google-genai 4.2.2, langchain-chroma 1.1.0, langchain-huggingface 1.2.2, langchain-text-splitters 1.1.2 |
| Orchestration | langgraph 1.1.10, langgraph-checkpoint 4.0.3 |
| Models | Groq Llama 3.1 8B (`llama-3.1-8b-instant`), Groq Llama 3.3 70B (`llama-3.3-70b-versatile`), Google Gemini 2.0 Flash (`gemini-2.0-flash`) |
| Embeddings | sentence-transformers 5.4.1 (`all-MiniLM-L6-v2`) |
| Vector store | chromadb 1.5.8 |
| Validation | pydantic 2.13.3 |
| Frontend framework | React 18.2, Vite 8.0 |
| Frontend libs | react-router-dom 6.22, axios 1.6.7, lucide-react 0.344, date-fns 3.3.1 |
| Workflow / Notifications | Microsoft Power Automate (HTTP-trigger flows) |
| PDF ingestion | langchain_community PyPDFLoader |

### 22.2 Backend APIs (selected)

| Method | Path | Purpose | Roles |
|---|---|---|---|
| POST | `/login` | JWT issuance | public |
| POST | `/register` | self-signup | public |
| POST | `/chat` | conversational entry | authenticated |
| POST | `/leave/apply` | apply leave | employee+ |
| POST | `/leave/cancel` | cancel leave | employee (own) |
| GET  | `/leave/balance` | balance | authenticated |
| GET  | `/dashboard/summary` | role-filtered counts | authenticated |
| GET  | `/dashboard/logs` | system audit log | admin |
| GET  | `/api/employee/leaves` | my leaves | employee+ |
| GET  | `/api/employee/tickets` | my tickets | employee+ |
| GET  | `/api/employee/assets` | my assets | employee+ |
| GET  | `/api/manager/pending` | pending leaves + assets | manager / admin |
| POST | `/api/manager/leaves/{id}/approve` | approve leave | manager / admin |
| POST | `/api/manager/leaves/{id}/reject` | reject leave | manager / admin |
| GET  | `/api/it/tickets/open` | open IT tickets | it_team / admin |
| POST | `/api/it/tickets/{id}/update` | update ticket status | it_team / admin |
| POST | `/api/it/assets/{id}/approve` | IT-stage asset approve | it_team / admin |
| POST | `/api/it/assets/{id}/reject` | IT-stage asset reject | it_team / admin |
| GET  | `/admin/users` | user list | admin |
| GET  | `/admin/notifications/config` | webhook channel introspection | admin |
| POST | `/admin/notifications/test` | fire test webhook | admin |

### 22.3 Frameworks & tools

- **LangChain** — LLM + retrieval chains.
- **LangGraph** — graph-based agent orchestration.
- **Chroma** — persisted vector store.
- **HuggingFace Sentence Transformers** — local embeddings.
- **FastAPI** — HTTP layer.
- **SQLAlchemy** — ORM.
- **React + Vite** — SPA.
- **Microsoft Power Automate** — workflow / notification engine.
- **Groq + Google Generative AI** — LLM providers.

### 22.4 Key dependencies — backend

```
fastapi==0.136.1            uvicorn==0.46.0
sqlalchemy==2.0.49          pydantic==2.13.3
python-jose==3.5.0          passlib==1.7.4         bcrypt==4.3.0
langchain==1.2.16           langgraph==1.1.10
langchain-groq==1.1.2       langchain-google-genai==4.2.2
langchain-chroma==1.1.0     langchain-huggingface==1.2.2
sentence-transformers==5.4.1
chromadb==1.5.8
google-generativeai==0.8.6  groq==0.37.1
```

### 22.5 Key dependencies — frontend

```
react ^18.2.0               react-dom ^18.2.0
react-router-dom ^6.22.0    axios ^1.6.7
lucide-react ^0.344.0       date-fns ^3.3.1
vite ^8.0.11                @vitejs/plugin-react ^6.0.1
```

### 22.6 Deployment notes (local)

1. **Backend**
   ```powershell
   cd backend
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   # populate .env: GROQ_API_KEY, GOOGLE_API_KEY, JWT_SECRET,
   #   POWER_HR_URL, POWER_IT_URL, POWER_ASSET_URL, CORS_ORIGINS
   python -m auth.seed_employees       # seeds 4 demo users
   python -m rag.cli                   # ingest PDFs into Chroma
   uvicorn main:app --reload --port 8000
   ```

2. **Frontend**
   ```powershell
   cd frontend
   npm install
   # populate .env: VITE_API_BASE=http://localhost:8000
   npm run dev                         # http://localhost:5173
   ```

3. **Seed users** (default password `password123`):
   - Employee — `Jemp@novigo.com`
   - Manager — `Jman@novigo.com`
   - IT Team — `Jit@novigo.com`
   - Admin — `Jadmin@novigo.com`

4. **Power Automate**: create three HTTP-trigger flows in Microsoft Power Automate; copy each trigger URL into the matching env var (`POWER_HR_URL`, `POWER_IT_URL`, `POWER_ASSET_URL`). Verify with `GET /admin/notifications/config` and test with `POST /admin/notifications/test`.

---

**End of report.**
