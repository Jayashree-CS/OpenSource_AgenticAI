"""Smoke tests for the out-of-scope guard and RBAC in chat read paths.

These tests are deliberately framework-agnostic (plain ``unittest``) so they
can run without spinning up FastAPI, the LLM, or the vector store.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.scope_guard import evaluate, is_out_of_scope


class ScopeGuardTests(unittest.TestCase):
    """The deterministic guard must decline clearly off-topic prompts and
    let everything HR / IT / policy-related through untouched."""

    OUT_OF_SCOPE = [
        "cook biriyani",
        "give me a chicken curry recipe",
        "what's the weather in Bangalore?",
        "who won the IPL final",
        "tell me a joke",
        "write a python script to sort a list",
        "solve for x: 2x+5=15",
        "should I date my coworker",
        "capital of france",
    ]

    IN_SCOPE = [
        "apply 2 days of casual leave next Monday",
        "my VPN keeps disconnecting",
        "what is the notice period for resignation?",
        "I need a new laptop",
        "show my leave balance",
        "show my tickets",
        "hi",
        "good morning",
        "what is today's date",
        "raise a ticket — outlook is broken",
        "how many casual leaves am I entitled to?",
    ]

    def test_off_topic_messages_are_declined(self):
        for msg in self.OUT_OF_SCOPE:
            with self.subTest(msg=msg):
                self.assertTrue(
                    is_out_of_scope(msg),
                    f"Expected {msg!r} to be flagged off-topic",
                )
                decision = evaluate(msg)
                self.assertFalse(decision.in_scope)
                self.assertIsNotNone(decision.redirect_message)
                # Redirect must include an apology AND list capabilities.
                self.assertIn("CopilotAI", decision.redirect_message)
                self.assertIn("leave", decision.redirect_message.lower())

    def test_in_scope_messages_pass_through(self):
        for msg in self.IN_SCOPE:
            with self.subTest(msg=msg):
                self.assertFalse(
                    is_out_of_scope(msg),
                    f"Expected {msg!r} to be allowed through",
                )

    def test_off_topic_word_inside_in_scope_message_still_in_scope(self):
        """If the message also contains an enterprise keyword, we let it
        through. Example: a question about food allowance policy that
        happens to mention biryani.
        """
        decision = evaluate("the canteen serves biryani — what's the food allowance policy?")
        self.assertTrue(decision.in_scope)


class ChatRBACTests(unittest.TestCase):
    """Read paths used by the chat agent must scope tickets / leaves /
    assets to the calling user unless they are an IT/manager/admin role."""

    def _make_user(self, role: str, user_id: int = 7, email: str = "alice@corp.test"):
        return SimpleNamespace(id=user_id, email=email, role=role, name="Alice")

    def test_employee_asking_for_all_tickets_only_sees_own(self):
        from agents import it_agent

        employee = self._make_user("employee")

        with patch.object(it_agent, "get_all_tickets") as all_tickets, \
             patch.object(it_agent, "get_user_tickets", return_value=[]) as user_tickets:
            it_agent._handle_read_action(
                {"action_type": "all_ticket_status"},
                db=object(),
                user=employee,
            )

        all_tickets.assert_not_called()
        user_tickets.assert_called_once()
        # The second positional arg must be the caller's email.
        called_email = user_tickets.call_args[0][1]
        self.assertEqual(called_email, employee.email)

    def test_it_role_asking_for_all_tickets_sees_everything(self):
        from agents import it_agent

        it_user = self._make_user("it_team", email="it@corp.test")

        with patch.object(it_agent, "get_all_tickets", return_value=[]) as all_tickets, \
             patch.object(it_agent, "get_user_tickets") as user_tickets:
            it_agent._handle_read_action(
                {"action_type": "all_ticket_status"},
                db=object(),
                user=it_user,
            )

        all_tickets.assert_called_once()
        user_tickets.assert_not_called()

    def test_employee_open_tickets_filtered_to_self(self):
        from agents import it_agent

        employee = self._make_user("employee")

        with patch.object(it_agent, "get_open_tickets") as open_all, \
             patch.object(it_agent, "get_user_tickets", return_value=[]) as user_tickets:
            it_agent._handle_read_action(
                {"action_type": "open_tickets"},
                db=object(),
                user=employee,
            )

        open_all.assert_not_called()
        user_tickets.assert_called_once()

    def test_employee_cannot_view_manager_pending_assets(self):
        from agents import it_agent

        employee = self._make_user("employee")
        result = it_agent._handle_read_action(
            {"action_type": "manager_pending_asset_approvals"},
            db=object(),
            user=employee,
        )
        self.assertIsNotNone(result)
        self.assertIn("Access denied", result)

    def test_employee_cannot_view_all_assets(self):
        from agents import it_agent

        employee = self._make_user("employee")
        result = it_agent._handle_read_action(
            {"action_type": "all_asset_status"},
            db=object(),
            user=employee,
        )
        self.assertIsNotNone(result)
        self.assertIn("Access denied", result)


if __name__ == "__main__":
    unittest.main()
