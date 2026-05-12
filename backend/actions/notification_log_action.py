"""
actions/notification_log_action.py

Persistence helpers for ``NotificationLog`` rows. Power Automate webhook
results are recorded here so that admins can audit every outbound flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from db.database import SessionLocal
from db.models import NotificationLog

logger = logging.getLogger(__name__)


def _serialize(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, default=str)[:8000]
    except Exception:
        return str(payload)[:8000]


def record_attempt(
    *,
    channel: str,
    event_type: str,
    target_url: Optional[str],
    payload: Dict[str, Any],
    status: str,
    error: Optional[str] = None,
    attempts: int = 1,
) -> Optional[int]:
    """
    Insert (or update by event_type+channel for retries) a notification log
    row. Returns the row id when persisted.
    """
    db = SessionLocal()
    try:
        row = NotificationLog(
            channel=(channel or "").lower(),
            event_type=event_type,
            target_url=target_url,
            payload=_serialize(payload),
            status=status,
            error=(error or "")[:2000],
            attempts=attempts,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to record notification log: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


__all__ = ["record_attempt"]
