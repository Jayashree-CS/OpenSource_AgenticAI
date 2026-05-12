"""
power_automate_action.py

Microsoft Power Automate notification service for enterprise workflows.

Implements three separate notification flows:
1. HR Notification Flow
2. IT Notification Flow
3. Asset Notification Flow

Power Automate is ONLY a notification layer.
"""

import os
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# LOGGING
# ==========================================

logger = logging.getLogger(__name__)

# ==========================================
# ENV VARIABLES
# ==========================================

POWER_HR_URL = os.getenv("POWER_HR_URL", "").strip()
POWER_IT_URL = os.getenv("POWER_IT_URL", "").strip()
POWER_ASSET_URL = os.getenv("POWER_ASSET_URL", "").strip()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# ==========================================
# SETTINGS
# ==========================================

REQUEST_TIMEOUT = 20
MAX_RETRIES = 3

# Thread pool for async sending
_executor = ThreadPoolExecutor(max_workers=5)

# ==========================================
# HELPERS
# ==========================================

def _is_valid_url(url: str) -> bool:
    return bool(url and url.startswith(("http://", "https://")))


def _do_post(url: str, payload: Dict[str, Any]) -> bool:
    """
    Actual webhook sender.
    """

    try:
        json_data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "EnterpriseAI-Copilot/1.0"
        }

        request = urllib.request.Request(
            url=url,
            data=json_data,
            headers=headers,
            method="POST"
        )

        start = time.time()

        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:

            response_body = response.read().decode("utf-8", errors="ignore")

            duration = round(time.time() - start, 2)

            logger.info(
                f"Webhook success | status={response.status} | time={duration}s"
            )

            logger.info(f"Response: {response_body[:300]}")

            return 200 <= response.status < 300

    except urllib.error.HTTPError as e:

        try:
            error_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            error_body = "Unable to read response body"

        logger.error(
            f"HTTP ERROR | code={e.code} | reason={e.reason} | body={error_body}"
        )

        return False

    except urllib.error.URLError as e:

        logger.error(f"URL ERROR | reason={e.reason}")

        return False

    except Exception as e:

        logger.exception(f"Unexpected webhook failure: {e}")

        return False


def _send_webhook(
    url: str,
    payload: Dict[str, Any],
    async_send: bool = True,
    *,
    channel: str = "",
    event_type: str = "",
) -> bool:

    if not _is_valid_url(url):
        logger.error(f"Invalid webhook URL: {url}")
        try:
            from actions.notification_log_action import record_attempt
            record_attempt(
                channel=channel or "unknown",
                event_type=event_type or "unknown",
                target_url=url,
                payload=payload,
                status="failed",
                error="invalid_url",
                attempts=0,
            )
        except Exception:
            pass
        return False

    def _runner():
        last_error: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):

            success = _do_post(url, payload)

            if success:
                try:
                    from actions.notification_log_action import record_attempt
                    record_attempt(
                        channel=channel or "unknown",
                        event_type=event_type or "unknown",
                        target_url=url,
                        payload=payload,
                        status="success",
                        attempts=attempt,
                    )
                except Exception:
                    pass
                return True

            last_error = f"webhook attempt {attempt} failed"
            logger.warning(f"Retrying webhook ({attempt}/{MAX_RETRIES})")

            time.sleep(2)

        try:
            from actions.notification_log_action import record_attempt
            record_attempt(
                channel=channel or "unknown",
                event_type=event_type or "unknown",
                target_url=url,
                payload=payload,
                status="failed",
                error=last_error or "unknown_failure",
                attempts=MAX_RETRIES,
            )
        except Exception:
            pass

        return False

    # Async mode
    if async_send:
        try:
            _executor.submit(_runner)
            return True
        except Exception as e:
            logger.error(f"Async queue failed: {e}")
            return False

    # Sync mode
    return _runner()

# ==========================================
# HR NOTIFICATIONS
# ==========================================

def send_hr_notification(
    event_type: str,
    title: str,
    message: str,
    status: str = "",
    status_color: str = "",
    employee_name: str = "",
    leave_type: str = "",
    reason: str = "",
    start_date: str = "",
    end_date: str = "",
    leave_id: Optional[int] = None,
    async_send: bool = True,
    metadata: Optional[dict] = None,
) -> bool:
    """Send an HR notification webhook. ``metadata`` accepts an arbitrary dict
    of additional context (employee_id, approver_role, etc.) and is merged
    into the payload so callers can pass enriched data without exhausting
    the positional arg list.
    """

    md = metadata or {}

    def _pick(key, default):
        return md.get(key, default) if md else default

    payload = {
        "event_type": event_type,
        "title": title,
        "message": message,
        "status": status or _pick("status", ""),
        "status_color": status_color or _pick("status_color", ""),
        "employee_name": employee_name or _pick("employee_name", ""),
        "leave_type": leave_type or _pick("leave_type", ""),
        "reason": reason or _pick("reason", "") or "",
        "start_date": start_date or _pick("start_date", ""),
        "end_date": end_date or _pick("end_date", ""),
        "leave_id": leave_id if leave_id is not None else _pick("leave_id", None),
        "cta_text": "Open Dashboard",
        "cta_url": FRONTEND_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "enterprise_ai_copilot",
    }

    # Forward any extra metadata fields under a stable key so consumers
    # (Power Automate flow) get the full context.
    if md:
        payload["metadata"] = md

    return _send_webhook(
        POWER_HR_URL,
        payload,
        async_send,
        channel="hr",
        event_type=event_type,
    )

# ==========================================
# IT NOTIFICATIONS
# ==========================================

def send_it_notification(
    event_type: str,
    title: str,
    message: str,
    status: str = "",
    status_color: str = "",
    ticket_id: Optional[int] = None,
    ticket_type: str = "",
    priority: str = "",
    user_email: str = "",
    description: str = "",
    async_send: bool = True,
    metadata: Optional[dict] = None,
) -> bool:
    """Send an IT notification webhook. Accepts a ``metadata`` dict so
    callers can pass enriched context (employee_id, issue_type, etc.)
    without exhausting the positional arg list — same shape as
    ``send_hr_notification`` and ``send_asset_notification``.
    """
    md = metadata or {} 

    def _pick(key, default):
        return md.get(key, default) if md else default

    resolved_ticket_id = ticket_id if ticket_id is not None else _pick("ticket_id", None)
    resolved_ticket_type = ticket_type or _pick("issue_type", "") or _pick("ticket_type", "")
    resolved_priority = priority or _pick("priority", "")
    resolved_email = user_email or _pick("employee_email", "") or _pick("user_email", "")
    resolved_description = description or _pick("issue_description", "") or _pick("description", "")
    resolved_status = status or _pick("status", "")

    payload = {
        "event_type": event_type,
        "title": title,
        "message": message,
        "status": resolved_status,
        "status_color": status_color or _pick("status_color", ""),
        "ticket_id": f"IT-{resolved_ticket_id}" if resolved_ticket_id is not None else "",
        "ticket_type": resolved_ticket_type,
        "priority": resolved_priority,
        "user_email": resolved_email,
        "description": resolved_description,
        "cta_text": "Open  Dashboard",
        "cta_url": FRONTEND_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "enterprise_ai_copilot",
    }

    if md:
        payload["metadata"] = md

    return _send_webhook(
        POWER_IT_URL,
        payload,
        async_send,
        channel="it",
        event_type=event_type,
    )

# ==========================================
# ASSET NOTIFICATIONS
# ==========================================

def send_asset_notification(
    event_type: str,
    title: str,
    message: str,
    status: str = "",
    status_color: str = "",
    employee_name: str = "",
    asset_name: str = "",
    asset_type: str = "",
    user_email: str = "",
    request_id: Optional[int] = None,
    reason: str = "",
    async_send: bool = True,
    metadata: Optional[dict] = None,
) -> bool:
    """Send an asset notification webhook. Accepts a single ``metadata`` dict
    to keep callers uniform across HR / IT / asset channels.
    """
    md = metadata or {}

    def _pick(key, default):
        return md.get(key, default) if md else default

    resolved_request_id = request_id if request_id is not None else _pick("request_id", None)

    payload = {
        "event_type": event_type,
        "title": title,
        "message": message,
        "status": status or _pick("status", ""),
        "status_color": status_color or _pick("status_color", ""),
        "employee_name": employee_name or _pick("employee_name", ""),
        "asset_name": asset_name or _pick("asset_name", "") or _pick("asset_type", ""),
        "asset_type": asset_type or _pick("asset_type", ""),
        "user_email": user_email or _pick("employee_email", "") or _pick("user_email", ""),
        "request_id": resolved_request_id,
        "reason": reason or _pick("reason", "") or "",
        "cta_text": "Open Dashboard",
        "cta_url": FRONTEND_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "enterprise_ai_copilot",
    }

    if md:
        payload["metadata"] = md

    return _send_webhook(
        POWER_ASSET_URL,
        payload,
        async_send,
        channel="asset",
        event_type=event_type,
    )

# ==========================================
# TEST ALL WEBHOOKS
# ==========================================

def test_webhook_connectivity() -> Dict[str, Dict[str, Any]]:
    """
    Lightweight introspection of the configured Power Automate webhook URLs.

    Returns a dict keyed by ``hr_webhook|it_webhook|asset_webhook``; each
    entry contains the configured URL, a boolean ``configured`` flag, and a
    ``test_result`` field. ``test_result`` is intentionally non-blocking
    here so unit tests never trigger real outbound HTTP calls.
    """
    channels = {
        "hr_webhook": POWER_HR_URL,
        "it_webhook": POWER_IT_URL,
        "asset_webhook": POWER_ASSET_URL,
    }

    return {
        key: {
            "url": url,
            "configured": _is_valid_url(url),
            "test_result": "configured" if _is_valid_url(url) else "not_configured",
        }
        for key, url in channels.items()
    }


def test_all_webhooks():

    payload = {
        "event_type": "test",
        "title": "Test Notification",
        "message": "Webhook connectivity test",
        "status": "TEST",
        "status_color": "#808080",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "test"
    }

    results = {
        "hr": False,
        "it": False,
        "asset": False
    }

    print("\nTesting HR webhook...")
    results["hr"] = _send_webhook(
        POWER_HR_URL,
        payload,
        async_send=False
    )

    print("\nTesting IT webhook...")
    results["it"] = _send_webhook(
        POWER_IT_URL,
        payload,
        async_send=False
    )

    print("\nTesting Asset webhook...")
    results["asset"] = _send_webhook(
        POWER_ASSET_URL,
        payload,
        async_send=False
    )

    print("\nRESULTS")
    print(results)

    return results

