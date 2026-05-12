import os
from fastapi import FastAPI
from db.database import engine, Base
# Import ORM classes so metadata.create_all knows all tables
from db.models import (  # noqa: F401
    Employee,
    LeaveRequest,
    Ticket,
    AssetRequest,
    LeaveBalance,
    Holiday,
    SystemLog,
    Inventory,
    NotificationLog,
)
from fastapi.middleware.cors import CORSMiddleware
from routes import leave  # import routes
from routes import chat
from routes import dashboard
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
from fastapi import HTTPException, Request

from routes.api_employee import router as api_employee_router
from routes.api_manager import router as api_manager_router
from routes.api_it import router as api_it_router
from routes.api_admin import router as api_admin_router

load_dotenv()

def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    # Dev defaults (Vite + older React dev server)
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_payload(message: str, *, error: str = "error", data=None, success: bool = False):
    return {"success": success, "message": message, "data": data, "error": error}


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            str(exc.detail),
            error="http_error",
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            "Internal server error",
            error="internal_error",
            data={"type": type(exc).__name__},
        ),
    )

# Create tables

Base.metadata.create_all(bind=engine)


# One-time data migration: legacy seed used role="it" but RBAC canonical
# value is "it_team". Existing rows must be upgraded so action-layer RBAC
# (which re-reads role from the DB) accepts IT users.
def _migrate_legacy_roles() -> None:
    try:
        from db.database import SessionLocal
        from db.models import Employee
        db = SessionLocal()
        try:
            updated = (
                db.query(Employee)
                .filter(Employee.role.in_(["it", "itteam", "it-team", "it team"]))
                .update({Employee.role: "it_team"}, synchronize_session=False)
            )
            if updated:
                db.commit()
                print(f"[startup] migrated {updated} legacy IT role row(s) -> 'it_team'")
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - migration is best-effort
        print(f"[startup] role migration skipped: {exc}")


_migrate_legacy_roles()

# Include routes

app.include_router(leave.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
app.include_router(dashboard.admin_router)

app.include_router(api_employee_router)
app.include_router(api_manager_router)
app.include_router(api_it_router)
app.include_router(api_admin_router)


# Startup diagnostics: surface which Power Automate channels are
# configured so missing env vars (POWER_HR_URL / POWER_IT_URL /
# POWER_ASSET_URL) are obvious at boot instead of silently swallowing
# notification failures.
@app.on_event("startup")
def _log_notification_channels() -> None:
    try:
        from actions.power_automate_action import test_webhook_connectivity
        cfg = test_webhook_connectivity()
    except Exception as exc:
        print(f"[startup] could not read webhook config: {exc}")
        return
    print("[startup] Power Automate channels:")
    for key, info in cfg.items():
        state = "OK" if info.get("configured") else "NOT CONFIGURED"
        url = info.get("url") or "<empty>"
        # Mask everything after the host for a touch of privacy in logs.
        safe_url = url.split("?")[0] if url else "<empty>"
        print(f"  - {key}: {state} ({safe_url})")
