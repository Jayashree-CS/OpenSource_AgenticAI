from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable, Literal, TypedDict


Role = Literal["user", "assistant", "system"]


class ChatTurn(TypedDict):
    role: Role
    content: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_history(turns: Iterable[dict[str, Any]] | None) -> list[ChatTurn]:
    """Keep only prompt-safe chat turns in the standard role/content format."""
    normalized: list[ChatTurn] = []

    for turn in turns or []:
        role = turn.get("role")
        content = turn.get("content")

        if role not in ("user", "assistant", "system"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue

        normalized.append({"role": role, "content": content.strip()})

    return normalized


@dataclass
class AgentSessionState:
    user_id: str
    history: list[ChatTurn] = field(default_factory=list)
    active_agent: str | None = None
    last_agent: str | None = None
    pending_workflow: dict[str, Any] = field(default_factory=dict) # To store multi-step states
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    max_history: int = 40

    def touch(self) -> None:
        self.updated_at = _now()

    def set_pending_step(self, workflow_type: str, data: dict[str, Any]) -> None:
        """Store state for a multi-step workflow (e.g., waiting for confirmation)."""
        self.pending_workflow = {"type": workflow_type, "data": data, "timestamp": _now().isoformat()}
        self.touch()

    def get_pending_step(self) -> dict[str, Any]:
        return self.pending_workflow

    def clear_pending_step(self) -> None:
        self.pending_workflow = {}
        self.touch()

    # ------------------------------------------------------------------
    # Backwards-compatible key-based pending helpers used by chat router.
    # Each workflow type ("hr_leave", "it_action", ...) maps onto its own
    # bucket inside ``pending_workflow``.
    # ------------------------------------------------------------------

    def set_pending(self, workflow_type: str, data: dict[str, Any]) -> None:
        self.pending_workflow = {
            "type": workflow_type,
            "data": data,
            "timestamp": _now().isoformat(),
        }
        self.touch()

    def get_pending(self, workflow_type: str) -> dict[str, Any] | None:
        if not self.pending_workflow:
            return None
        if self.pending_workflow.get("type") != workflow_type:
            return None
        return self.pending_workflow.get("data") or {}

    def clear_pending(self, workflow_type: str | None = None) -> None:
        if workflow_type is None or self.pending_workflow.get("type") == workflow_type:
            self.pending_workflow = {}
            self.touch()

    def append_turn(self, role: Role, content: str) -> None:
        if not content or not content.strip():
            return

        self.history.append({"role": role, "content": content.strip()})
        self.trim_history()
        self.touch()

    def record_exchange(self, user_message: str, assistant_reply: str) -> None:
        self.append_turn("user", user_message)
        self.append_turn("assistant", assistant_reply)

    def prompt_history(self, current_message: str | None = None, limit: int = 10) -> list[ChatTurn]:
        turns = normalize_history(self.history)

        if current_message and current_message.strip():
            turns.append({"role": "user", "content": current_message.strip()})

        return turns[-limit:]

    def history_text(self, current_message: str | None = None, limit: int = 10) -> str:
        turns = self.prompt_history(current_message=current_message, limit=limit)

        if not turns:
            return "(no prior turns)"

        return "\n".join(
            f"{turn['role'].capitalize()}: {turn['content']}"
            for turn in turns
        )

    def set_agent(self, agent: str | None) -> None:
        self.active_agent = agent
        if agent:
            self.last_agent = agent
        self.touch()

    def trim_history(self) -> None:
        if len(self.history) > self.max_history:
            self.history[:] = self.history[-self.max_history:]


class InMemoryAgentStateStore:
    """Per-user agent state store. Swap this class for Redis/DB persistence later."""

    def __init__(self, max_history: int = 40):
        self.max_history = max_history
        self._states: dict[str, AgentSessionState] = {}
        self._lock = RLock()

    def get(self, user_id: str) -> AgentSessionState:
        with self._lock:
            state = self._states.get(user_id)
            if state is None:
                state = AgentSessionState(user_id=user_id, max_history=self.max_history)
                self._states[user_id] = state
            return state

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._states.pop(user_id, None)


agent_state_store = InMemoryAgentStateStore()
