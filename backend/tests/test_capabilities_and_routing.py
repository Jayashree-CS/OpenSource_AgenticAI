"""Regression tests for the user-reported issues:

1. Bot must ask for missing date/type/reason when the user just types
   "apply leave" — never silently confirm with hallucinated defaults.
2. Reason is now a required leave slot.
3. ``send_it_notification`` accepts a ``metadata=`` kwarg.
4. Router no longer sends ``who is the CEO`` to the IT agent.
5. Capability dispatcher answers documented employee phrases without
   hitting the LLM.
"""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.hr_agent import _missing_leave_slots, _merge_leave_slots
from agents.router_agent import route_query
from actions.power_automate_action import send_it_notification


class LeaveSlotRequirementTests(unittest.TestCase):
    """The previous bug: bot showed a confirmation dialog with reason=null
    or used "Applied via AI" silently. Reason must now be required, and
    the LLM extractor must not invent dates / leave_type / reason out of
    thin air when the user message has no evidence for them.
    """

    def test_reason_is_required_slot(self):
        wf = {
            "leave_type": "sick",
            "start_date": "2026-05-12",
            "end_date": "2026-05-12",
            "reason": None,
        }
        missing = _missing_leave_slots(wf)
        self.assertIn("reason", missing)

    def test_blank_reason_is_treated_as_missing(self):
        wf = {
            "leave_type": "sick",
            "start_date": "2026-05-12",
            "end_date": "2026-05-12",
            "reason": "   ",
        }
        self.assertIn("reason", _missing_leave_slots(wf))

    def test_full_slots_are_not_missing(self):
        wf = {
            "leave_type": "sick",
            "start_date": "2026-05-12",
            "end_date": "2026-05-12",
            "reason": "fever",
        }
        self.assertEqual(_missing_leave_slots(wf), [])

    def test_apply_leave_does_not_hallucinate_slots(self):
        """If the user types JUST "apply leave" the LLM extractor's
        hallucinated values must be ignored — only slots with textual
        evidence in the message survive into the workflow data.
        """
        user = SimpleNamespace(id=1, name="A", email="a@x.com", role="employee")

        hallucinated = {
            "action": "apply_leave",
            "leave_type": "sick",
            "start_date": "2026-05-12",
            "end_date": "2026-05-12",
            "reason": "fever",
        }
        with patch("agents.hr_agent.extract_hr_action", return_value=hallucinated):
            merged = _merge_leave_slots({}, "apply leave", history=[], user=user)
        # None of the four slots should have been accepted from the LLM.
        self.assertIsNone(merged.get("leave_type"))
        self.assertIsNone(merged.get("start_date"))
        self.assertIsNone(merged.get("end_date"))
        self.assertIsNone(merged.get("reason"))

    def test_extractor_slots_accepted_when_message_has_evidence(self):
        user = SimpleNamespace(id=1, name="A", email="a@x.com", role="employee")
        extracted = {
            "action": "apply_leave",
            "leave_type": "sick",
            "start_date": "2026-05-12",
            "end_date": "2026-05-12",
            "reason": "fever",
        }
        with patch("agents.hr_agent.extract_hr_action", return_value=extracted):
            merged = _merge_leave_slots(
                {}, "apply sick leave on 2026-05-12 because of fever",
                history=[], user=user,
            )
        self.assertEqual(merged.get("leave_type"), "sick")
        self.assertEqual(merged.get("start_date"), "2026-05-12")
        self.assertEqual(merged.get("end_date"), "2026-05-12")
        self.assertEqual(merged.get("reason"), "fever")


class ItNotificationMetadataTests(unittest.TestCase):
    def test_send_it_notification_accepts_metadata_kwarg(self):
        sig = inspect.signature(send_it_notification)
        self.assertIn("metadata", sig.parameters)

    def test_send_it_notification_call_with_metadata_does_not_raise(self):
        with patch("actions.power_automate_action._send_webhook", return_value=True) as wh:
            ok = send_it_notification(
                event_type="ticket_updated",
                title="t",
                message="m",
                metadata={
                    "employee_id": 1,
                    "ticket_id": 42,
                    "issue_type": "vpn",
                    "status": "in_progress",
                },
            )
        self.assertTrue(ok)
        wh.assert_called_once()
        payload = wh.call_args[0][1]
        # Metadata shorthand must be unpacked into the payload AND retained
        # under the ``metadata`` key for downstream Power Automate flows.
        self.assertEqual(payload["ticket_id"], "IT-42")
        self.assertEqual(payload["ticket_type"], "vpn")
        self.assertEqual(payload["status"], "in_progress")
        self.assertEqual(payload["metadata"]["employee_id"], 1)


class RouterRegexTests(unittest.TestCase):
    """The old IT regex had a trailing ``software|)`` empty alternative
    that matched every message → every query was sent to the IT agent,
    breaking ``who is the CEO`` and other company / HR questions.
    """

    def test_company_info_does_not_route_to_it(self):
        for msg in (
            "who is the CEO",
            "who is the ceo of the company",
            "tell me about the company",
            "tell me about my company",
            "what is the organization name",
            "where is the company headquartered",
        ):
            with self.subTest(msg=msg):
                self.assertNotEqual(route_query(msg), "it")

    def test_hr_routes_unaffected(self):
        for msg in (
            "apply leave tomorrow",
            "show my leave balance",
            "leave history",
        ):
            with self.subTest(msg=msg):
                self.assertEqual(route_query(msg), "hr")

    def test_it_routes_still_work(self):
        for msg in (
            "my vpn is broken",
            "i need a new laptop",
            "raise a ticket for outlook",
        ):
            with self.subTest(msg=msg):
                self.assertEqual(route_query(msg), "it")


if __name__ == "__main__":
    unittest.main()
