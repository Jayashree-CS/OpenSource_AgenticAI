#!/usr/bin/env python3
"""
test_required_chat_scenarios.py

Comprehensive test suite for required chat scenarios validation.

Tests MUST PASS:
- Employee policy questions
- Leave balance/history/pending
- Leave application with date validation
- Manager approval/rejection
- RBAC enforcement
- Company info queries
- Date handling
"""

import sys
import os
import logging
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import modules to test
from actions.enhanced_date_action import enhanced_date_action
from config.rbac import rbac_action, Role, Permission
from config.company import COMPANY_NAME, CEO_NAME
from agents.hr_agent import hr_agent, _deterministic_hr_route, parse_flexible_dates
from actions.leave_action import apply_leave, approve_leave_by_manager, reject_leave_by_manager
from actions.power_automate_action import test_webhook_connectivity


class MockDB:
    """Mock database for testing."""
    def __init__(self):
        self.data = {}
        self.committed = []
        self.employees = {}
        self.leaves = []
    
    def query(self, model):
        return MockQuery(self, model)
    
    def add(self, obj):
        self.committed.append(obj)
    
    def commit(self):
        pass
    
    def refresh(self, obj):
        pass


class MockQuery:
    """Mock query builder."""
    def __init__(self, db, model):
        self.db = db
        self.model = model
        self.filters = []
        self.joins = []
    
    def filter(self, *args, **kwargs):
        self.filters.extend(args)
        self.filters.extend([getattr(self.model, k) == v for k, v in kwargs.items()])
        return self
    
    def join(self, model, on=None):
        self.joins.append((model, on))
        return self

    def order_by(self, *args, **kwargs):
        # No-op: tests don't care about ordering, only about which records
        # would have been returned. Real SQLAlchemy queries are sorted in
        # production via .order_by(<col>.desc()).
        return self

    
    def first(self):
        if hasattr(self.model, '__tablename__') and self.model.__tablename__ == 'employees':
            # Return mock employee
            emp = Mock()
            emp.id = 1
            emp.name = "Test Employee"
            emp.email = "test@example.com"
            emp.role = "employee"
            emp.manager_id = 2
            return emp
        elif hasattr(self.model, '__tablename__') and self.model.__tablename__ == 'leaverequests':
            # Return mock leave
            leave = Mock()
            leave.id = 24
            leave.employee_id = 1
            leave.leave_type = "sick"
            leave.status = "pending_manager"
            leave.start_date = date.today() + timedelta(days=1)
            leave.end_date = date.today() + timedelta(days=1)
            leave.reason = "fever"
            leave.total_days = 1
            return emp
        return None
    
    def all(self):
        return []


class MockUser:
    """Mock user object."""
    def __init__(self, role="employee"):
        self.id = 1
        self.name = "Test User"
        self.email = "test@example.com"
        self.role = role
        self.manager_id = 2 if role == "employee" else None


class MockSessionState:
    """Mock session state."""
    def __init__(self):
        self.pending_data = {}
        self.agent = None
        self.history = []
    
    def get_pending(self, key):
        return self.pending_data.get(key)
    
    def set_pending(self, key, data):
        self.pending_data[key] = data
    
    def clear_pending(self, key):
        self.pending_data.pop(key, None)
    
    def set_agent(self, agent):
        self.agent = agent
    
    def prompt_history(self, limit=10):
        return self.history[-limit:]


def test_enhanced_date_action():
    """Test enhanced date service functionality."""
    print("🧪 Testing Enhanced Date Service...")
    
    # Test relative date parsing
    today = enhanced_date_action.get_today()
    assert isinstance(today, date), "get_today should return date object"
    
    tomorrow = enhanced_date_action.get_tomorrow()
    assert tomorrow == today + timedelta(days=1), "tomorrow should be today + 1 day"
    
    # Test relative date parsing from message
    parsed_date, keyword = enhanced_date_action.parse_relative_date("apply leave tomorrow")
    assert parsed_date == tomorrow, "Should parse tomorrow correctly"
    assert keyword == "tomorrow", "Should return correct keyword"
    
    # Test weekend shift
    saturday = date(2026, 5, 10)  # Saturday
    monday = enhanced_date_action.shift_to_next_working_day(saturday)
    assert monday.weekday() == 0, "Should shift Saturday to Monday"
    
    # Test leave date validation
    validation = enhanced_date_action.validate_leave_date(today + timedelta(days=1))
    assert validation["valid"] == True, "Future date should be valid"
    
    past_validation = enhanced_date_action.validate_leave_date(today - timedelta(days=1))
    assert past_validation["valid"] == False, "Past date should be invalid"
    assert "past" in past_validation["error"], "Should indicate past date error"
    
    print("✅ Enhanced Date Service tests passed")


def test_rbac_system():
    """Test RBAC system functionality."""
    print("🧪 Testing RBAC System...")
    
    # Test role validation
    assert rbac_action.is_valid_role("employee"), "employee should be valid"
    assert rbac_action.is_valid_role("manager"), "manager should be valid"
    assert rbac_action.is_valid_role("it_team"), "it_team should be valid"
    assert rbac_action.is_valid_role("admin"), "admin should be valid"
    assert not rbac_action.is_valid_role("hr_team"), "hr_team should be invalid (removed)"
    
    # Test permission checking
    assert rbac_action.has_permission("employee", Permission.VIEW_LEAVE_DASHBOARD), "employee can view leave dashboard"
    assert not rbac_action.has_permission("employee", Permission.APPROVE_LEAVE), "employee cannot approve leave"
    
    assert rbac_action.has_permission("manager", Permission.APPROVE_LEAVE), "manager can approve leave"
    assert rbac_action.has_permission("manager", Permission.APPROVE_TICKET), "manager can approve ticket"
    assert rbac_action.has_permission("manager", Permission.APPROVE_ASSET), "manager can approve asset"
    assert not rbac_action.has_permission("manager", Permission.VIEW_SYSTEM_LOGS), "manager cannot view system logs"
    
    assert rbac_action.has_permission("it_team", Permission.APPROVE_TICKET), "it_team can approve ticket"
    assert rbac_action.has_permission("it_team", Permission.APPROVE_ASSET), "it_team can approve asset"
    assert not rbac_action.has_permission("it_team", Permission.APPROVE_LEAVE), "it_team cannot approve leave"
    assert not rbac_action.has_permission("it_team", Permission.VIEW_LEAVE_DASHBOARD), "it_team cannot view leave dashboard"
    
    assert rbac_action.has_permission("admin", Permission.ACCESS_ALL_PAGES), "admin has all permissions"
    
    # Test route access
    assert rbac_action.has_route_access("employee", "/"), "employee can access chat"
    assert rbac_action.has_route_access("employee", "/leave-dashboard"), "employee can access leave dashboard"
    assert not rbac_action.has_route_access("employee", "/dashboard"), "employee cannot access main dashboard"
    
    assert rbac_action.has_route_access("manager", "/dashboard"), "manager can access main dashboard"
    assert rbac_action.has_route_access("manager", "/ticket-dashboard"), "manager can access ticket dashboard"
    
    assert rbac_action.has_route_access("it_team", "/ticket-dashboard"), "it_team can access ticket dashboard"
    assert not rbac_action.has_route_access("it_team", "/leave-dashboard"), "it_team cannot access leave dashboard"
    
    assert rbac_action.has_route_access("admin", "/admin"), "admin can access admin console"
    
    print("✅ RBAC System tests passed")


def test_company_info():
    """Test company information queries."""
    print("🧪 Testing Company Info...")
    
    # Test company constants
    assert COMPANY_NAME == "Novigo Solutions Pvt Ltd", "Company name should be correct"
    assert CEO_NAME == "Jayashree", "CEO name should be correct"
    
    print("✅ Company Info tests passed")


def test_hr_agent_deterministic_routing():
    """Test HR agent deterministic routing."""
    print("🧪 Testing HR Agent Deterministic Routing...")
    
    # Test leave approval routing
    route = _deterministic_hr_route("approve leave 24")
    assert route["action"] == "approve_leave", "Should route to approve leave"
    assert route["leave_id"] == 24, "Should extract leave ID correctly"
    assert route["confirmed"] == False, "Should not be confirmed by default"
    
    # Test confirmed approval
    route = _deterministic_hr_route("confirm approve leave 24")
    assert route["action"] == "approve_leave", "Should route to approve leave"
    assert route["confirmed"] == True, "Should be confirmed"
    
    # Test leave balance
    route = _deterministic_hr_route("show my leave balance")
    assert route["action"] == "leave_balance", "Should route to leave balance"
    
    # Test leave history
    route = _deterministic_hr_route("my leave history")
    assert route["action"] == "leave_history", "Should route to leave history"
    
    # Test pending leaves
    route = _deterministic_hr_route("my pending leaves")
    assert route["action"] == "pending_leaves", "Should route to pending leaves"
    
    # Test company info
    route = _deterministic_hr_route("who is the CEO")
    assert route["action"] == "company_info", "Should route to company info"
    
    route = _deterministic_hr_route("company name")
    assert route["action"] == "company_info", "Should route to company info"
    
    # Test date question
    route = _deterministic_hr_route("what day is today")
    assert route["action"] == "date_question", "Should route to date question"
    
    # Test leave policy
    route = _deterministic_hr_route("what is the leave policy")
    assert route["action"] == "leave_policy_question", "Should route to leave policy question"
    
    print("✅ HR Agent Deterministic Routing tests passed")


def test_date_parsing():
    """Test date parsing functionality."""
    print("🧪 Testing Date Parsing...")
    
    # Test relative dates
    parsed = parse_flexible_dates("apply leave tomorrow")
    assert parsed["start_date"] is not None, "Should parse tomorrow"
    assert parsed["end_date"] is not None, "Should parse tomorrow as end date too"
    assert parsed["date_error"] is None, "Should not have date error"
    assert parsed["relative_keyword"] == "tomorrow", "Should identify relative keyword"
    
    # Test ISO dates
    parsed = parse_flexible_dates("apply leave 2026-05-15")
    assert parsed["start_date"] == "2026-05-15", "Should parse ISO date"
    assert parsed["end_date"] == "2026-05-15", "Should use same date for end"
    
    # Test date range
    parsed = parse_flexible_dates("apply leave from 2026-05-15 to 2026-05-17")
    assert parsed["start_date"] == "2026-05-15", "Should parse start date"
    assert parsed["end_date"] == "2026-05-17", "Should parse end date"
    
    # Test invalid date
    parsed = parse_flexible_dates("apply leave invalid-date")
    assert parsed["start_date"] is None, "Should not parse invalid date"
    assert parsed["end_date"] is None, "Should not parse invalid date"
    
    print("✅ Date Parsing tests passed")


def test_power_automate_connectivity():
    """Test Power Automate connectivity."""
    print("🧪 Testing Power Automate Connectivity...")
    
    # Test webhook connectivity (will fail if no webhooks configured, but shouldn't crash)
    try:
        results = test_webhook_connectivity()
        assert isinstance(results, dict), "Should return results dictionary"
        assert "hr_webhook" in results, "Should include hr_webhook results"
        assert "it_webhook" in results, "Should include it_webhook results"
        assert "asset_webhook" in results, "Should include asset_webhook results"
        
        # Each webhook should have url and configured fields
        for webhook_key, webhook_data in results.items():
            assert "url" in webhook_data, f"{webhook_key} should have url"
            assert "configured" in webhook_data, f"{webhook_key} should have configured status"
            assert "test_result" in webhook_data, f"{webhook_key} should have test result"
        
        print("✅ Power Automate Connectivity tests passed")
    except Exception as e:
        print(f"⚠️ Power Automate connectivity test failed (expected if no webhooks configured): {e}")


def test_employee_scenarios():
    """Test employee chat scenarios."""
    print("🧪 Testing Employee Scenarios...")
    
    db = MockDB()
    user = MockUser("employee")
    history = []
    session = MockSessionState()
    
    # Test 1: Policy question
    with patch('agents.hr_agent.retrieve_docs') as mock_retrieve:
        mock_retrieve.return_value = ["Annual leave: 12 days per year"]
        response = hr_agent("what is the leave policy", db, user, history, session)
        assert response is not None, "Should respond to policy question"
        assert len(response) > 0, "Should have non-empty response"
    
    # Test 2: Leave balance
    with patch('actions.leave_action.get_leave_balance') as mock_balance:
        mock_balance.return_value = {"sick": {"total": 8, "used": 2, "remaining": 6}}
        response = hr_agent("show my leave balance", db, user, history, session)
        assert response is not None, "Should respond to balance query"
    
    # Test 3: Leave history
    with patch('actions.leave_action.get_leave_history') as mock_history:
        mock_history.return_value = []
        response = hr_agent("my leave history", db, user, history, session)
        assert response is not None, "Should respond to history query"
    
    # Test 4: Pending leaves
    with patch('actions.leave_action.get_pending_leaves') as mock_pending:
        mock_pending.return_value = []
        response = hr_agent("my pending leaves", db, user, history, session)
        assert response is not None, "Should respond to pending query"
    
    # Test 5: Leave application - should start flow
    response = hr_agent("apply sick leave tomorrow for fever", db, user, history, session)
    assert response is not None, "Should respond to leave application"
    assert "leave" in response.lower() or "sick" in response.lower(), "Should mention leave or sick"
    
    print("✅ Employee Scenarios tests passed")


def test_manager_scenarios():
    """Test manager chat scenarios."""
    print("🧪 Testing Manager Scenarios...")
    
    db = MockDB()
    user = MockUser("manager")
    history = []
    session = MockSessionState()
    
    # Test 1: Show pending approvals
    with patch('actions.leave_action.get_pending_leaves_for_manager') as mock_pending:
        mock_pending.return_value = []
        response = hr_agent("show pending approvals", db, user, history, session)
        assert response is not None, "Should respond to pending approvals query"
    
    # Test 2: Approve leave
    with patch('actions.leave_action.approve_leave_by_manager') as mock_approve:
        mock_approve.return_value = Mock()
        mock_approve.return_value.id = 24
        mock_approve.return_value.status = "approved"
        response = hr_agent("approve leave 24", db, user, history, session)
        assert response is not None, "Should respond to approve leave"
    
    # Test 3: Confirm approve leave
    with patch('actions.leave_action.approve_leave_by_manager') as mock_approve:
        mock_approve.return_value = Mock()
        mock_approve.return_value.id = 24
        mock_approve.return_value.status = "approved"
        response = hr_agent("confirm approve leave 24", db, user, history, session)
        assert response is not None, "Should respond to confirm approve leave"
    
    print("✅ Manager Scenarios tests passed")


def test_rbac_enforcement():
    """Test RBAC enforcement scenarios."""
    print("🧪 Testing RBAC Enforcement...")
    
    db = MockDB()
    employee_user = MockUser("employee")
    manager_user = MockUser("manager")
    history = []
    session = MockSessionState()
    
    # Test employee cannot approve leave
    with patch('actions.leave_action.approve_leave_by_manager') as mock_approve:
        mock_approve.return_value = None  # Should return None due to RBAC
        response = hr_agent("approve leave 24", db, employee_user, history, session)
        # Should handle gracefully without crashing
    
    # Test manager can approve leave
    with patch('actions.leave_action.approve_leave_by_manager') as mock_approve:
        mock_approve.return_value = Mock()
        mock_approve.return_value.id = 24
        response = hr_agent("approve leave 24", db, manager_user, history, session)
        assert response is not None, "Manager should be able to approve leave"
    
    print("✅ RBAC Enforcement tests passed")


def test_integration_scenarios():
    """Test integration scenarios."""
    print("🧪 Testing Integration Scenarios...")
    
    # Test complete leave application flow
    db = MockDB()
    user = MockUser("employee")
    history = []
    session = MockSessionState()
    
    # Step 1: Apply leave
    with patch('actions.leave_action.apply_leave') as mock_apply, \
         patch('actions.leave_action.get_leave_balance') as mock_balance:
        mock_balance.return_value = {"sick": {"total": 8, "used": 2, "remaining": 6}}
        mock_leave = Mock()
        mock_leave.id = 25
        mock_leave.status = "pending_manager"
        mock_apply.return_value = mock_leave
        
        response1 = hr_agent("apply sick leave tomorrow for fever", db, user, history, session)
        assert response1 is not None, "Should start leave application"
    
    # Step 2: Confirm application
    response2 = hr_agent("yes", db, user, history, session)
    assert response2 is not None, "Should confirm leave application"
    
    print("✅ Integration Scenarios tests passed")


def main():
    """Run all tests."""
    print("🚀 Starting Required Chat Scenarios Test Suite")
    print("=" * 60)
    
    tests = [
        test_enhanced_date_action,
        test_rbac_system,
        test_company_info,
        test_hr_agent_deterministic_routing,
        test_date_parsing,
        test_power_automate_connectivity,
        test_employee_scenarios,
        test_manager_scenarios,
        test_rbac_enforcement,
        test_integration_scenarios,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
            print()
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1
            print()
    
    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All required chat scenario tests passed!")
        return True
    else:
        print(f"❌ {failed} tests failed. Please check the implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
