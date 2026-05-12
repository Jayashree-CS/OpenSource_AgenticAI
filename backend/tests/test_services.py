"""
Unit tests for the new services (normalization + intent classifier).

These tests intentionally avoid LLM calls; they exercise only the rule-based
path of the classifier so they remain hermetic and runnable without API keys.
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.normalization import normalize_message  # noqa: E402
from services.intent_classifier import _rule_classify  # noqa: E402


class NormalizationTests(unittest.TestCase):
    def test_phrase_rewrite_vacation_to_casual(self):
        nq = normalize_message("I need vacation leave next monday")
        self.assertIn("casual leave", nq.normalized)
        self.assertEqual(nq.leave_type, "casual")
        self.assertTrue(any(k.startswith("next_monday") for k in nq.relative_keywords))

    def test_phrase_rewrite_not_feeling_good(self):
        nq = normalize_message("not feeling good today")
        self.assertIn("sick leave", nq.normalized)
        self.assertEqual(nq.leave_type, "sick")
        self.assertIn("today", nq.relative_keywords)

    def test_vpn_issue_rewrites_to_ticket(self):
        nq = normalize_message("vpn issue please help")
        self.assertIn("vpn not working ticket", nq.normalized)
        self.assertEqual(nq.ticket_category, "vpn")

    def test_typo_fix(self):
        nq = normalize_message("apply leav tomorow")
        self.assertIn("leave", nq.normalized)
        self.assertIn("tomorrow", nq.normalized)

    def test_question_flag(self):
        nq = normalize_message("what is the leave policy?")
        self.assertTrue(nq.flags["is_question"])

    def test_confirmation_flag(self):
        nq = normalize_message("yes")
        self.assertTrue(nq.flags["is_confirmation"])


class IntentRuleTests(unittest.TestCase):
    def _intent(self, text: str) -> str:
        nq = normalize_message(text)
        result = _rule_classify(nq)
        return result.intent if result else "unknown"

    def test_apply_leave_routes_to_leave(self):
        self.assertEqual(self._intent("I want to apply for sick leave"), "leave")

    def test_vpn_routes_to_ticket(self):
        self.assertEqual(self._intent("vpn not working"), "ticket")

    def test_request_laptop_routes_to_asset(self):
        self.assertEqual(self._intent("I need a new laptop"), "asset")

    def test_pending_approvals_routes_to_approval(self):
        self.assertEqual(self._intent("show pending approvals"), "approval")

    def test_inventory_keywords(self):
        self.assertEqual(self._intent("show inventory low stock"), "inventory")

    def test_greeting_routes_to_conversational(self):
        self.assertEqual(self._intent("hi there"), "conversational")

    def test_question_routes_to_informational(self):
        self.assertEqual(self._intent("what is the leave policy?"), "informational")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
