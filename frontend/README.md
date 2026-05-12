# Enterprise AI Copilot — Frontend

React frontend for the Multi-Agent AI Copilot. Connects to a FastAPI backend.

## Stack

- React 18 + React Router v6
- Axios (API calls with auto-token injection)
- DM Sans + DM Serif Display (Google Fonts)
- CSS Variables for theming (Rama Green `#006D5B`)

## Project Structure

```
src/
├── App.jsx                    # Root router with protected/public routes
├── index.js                   # React entry point
├── index.css                  # Global CSS variables & reset
├── context/
│   └── AuthContext.jsx        # Global auth state (user, token, login/logout)
├── utils/
│   └── api.js                 # All API calls (authAPI, chatAPI, leaveAPI, ticketAPI, assetAPI, adminAPI)
├── pages/
│   ├── AuthPage.jsx/css       # Login + Register (split-screen)
│   └── ChatPage.jsx/css       # Main chat interface
└── components/
    ├── Sidebar.jsx/css        # Rama Green sidebar with session history
    ├── MessageBubble.jsx/css  # Chat bubbles with agent personas + RAG sources
    ├── QuickActions.jsx/css   # Role-specific quick action chips
    ├── ApprovalWidget.jsx/css # Manager inline approval widget
    ├── TicketDashboard.jsx/css # IT team ticket management overlay
    └── AdminConsole.jsx/css   # System logs + usage stats
```

## Setup

```bash
cd frontend
cp .env.example .env.local
npm install
npm start
```

Ensure your FastAPI backend is running at `http://localhost:8000`.

## Backend API Contract

### Auth (FastAPI OAuth2)
| Endpoint | Method | Body | Response |
|---|---|---|---|
| `/auth/token` | POST | `username`, `password` (form) | `{ access_token, token_type, user }` |
| `/auth/register` | POST | `{ email, password, full_name, role, department }` | `{ access_token, user }` |
| `/auth/me` | GET | — | user object |

The `user` object must include: `{ id, email, full_name, role, department }`.

### Chat
| Endpoint | Method | Body | Response |
|---|---|---|---|
| `/agent/chat` | POST | `{ message, session_id, history[] }` | `{ reply, agent, sources[], session_id, requires_approval }` |
| `/agent/sessions` | GET | — | `[{ id, title, agent, created_at }]` |
| `/agent/sessions` | POST | — | `{ id, title }` |
| `/agent/sessions/:id` | GET | — | `{ messages[] }` |
| `/agent/sessions/:id` | DELETE | — | — |

### Leave
| Endpoint | Method | Notes |
|---|---|---|
| `/leave/apply` | POST | `{ leave_type, start_date, end_date, reason }` |
| `/leave/balance` | GET | Returns balances by type |
| `/leave/history` | GET | User's own history |
| `/leave/pending-approvals` | GET | Manager-scoped |
| `/leave/:id/approve` | POST | Manager only |
| `/leave/:id/reject` | POST | Manager only |
| `/leave/:id/cancel` | POST | Own requests only |

### Tickets
| Endpoint | Method | Notes |
|---|---|---|
| `/tickets/create` | POST | `{ subject, description, category, priority }` |
| `/tickets/my` | GET | Own tickets |
| `/tickets/all` | GET | IT team / admin only |
| `/tickets/:id` | PATCH | Update status, assignment |

### Assets
| Endpoint | Method | Notes |
|---|---|---|
| `/assets/request` | POST | `{ asset_type, asset_name, justification }` |
| `/assets/my` | GET | Own requests |
| `/assets/pending-approvals` | GET | Manager / IT scoped |
| `/assets/:id/approve` | POST | — |
| `/assets/:id/reject` | POST | — |

### Admin (Admin role only)
| Endpoint | Method | Notes |
|---|---|---|
| `/admin/logs` | GET | `?limit=50` |
| `/admin/stats` | GET | Aggregated usage stats |
| `/admin/users` | GET | All users |

## RBAC Matrix

| Role | Chat | Leave Apply | Leave Approve | Tickets | Asset Request | Asset Approve | Admin Console |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| employee | ✓ | ✓ | — | ✓ | ✓ | — | — |
| manager | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (team) | — |
| hr_team | ✓ | ✓ | ✓ (HR) | — | — | — | ✓ |
| it_team | ✓ | — | — | ✓ (all) | — | ✓ (IT step) | ✓ |
| admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (full) |

## Leave Threshold — Human-in-the-Loop

The backend should mark `requires_approval: true` in chat replies and set `above_threshold: true` on leave records when leave exceeds the configured threshold (default: 5 days). The frontend:
1. Shows a yellow warning banner in the message bubble
2. Shows the `⚠ Above threshold` flag in the ApprovalWidget
3. Routes these to HR Team for secondary approval

## Agent Detection

The backend returns `agent: "hr" | "it" | "router"` in chat responses. The frontend:
- Updates the sidebar agent status indicator
- Shows the correct avatar persona (HR Assistant / IT Support Pro / AI Copilot)
- Filters quick action chips to the relevant agent

## Color Palette

| Variable | Hex | Usage |
|---|---|---|
| `--rama-green` | `#006D5B` | Sidebar, buttons, user bubbles |
| `--mint-mist` | `#E6F0EE` | Hover states, secondary bg |
| `--white` | `#FFFFFF` | Chat bg, cards |
| `--charcoal` | `#1A1A1A` | Body text |
| `--success` | `#28A745` | Approved status |