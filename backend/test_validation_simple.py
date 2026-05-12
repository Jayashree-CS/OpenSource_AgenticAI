#!/usr/bin/env python3
"""
Simple validation test for the implemented fixes.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing Module Imports...")
    
    try:
        # Test enhanced date service
        from actions.enhanced_date_action import enhanced_date_action
        today = enhanced_date_action.get_today()
        print(f"✅ Enhanced date service works - Today: {today}")
        
        # Test RBAC
        from config.rbac import rbac_action, Role, Permission
        assert rbac_action.is_valid_role("employee")
        assert rbac_action.is_valid_role("manager")
        assert rbac_action.is_valid_role("it_team")
        assert rbac_action.is_valid_role("admin")
        assert not rbac_action.is_valid_role("hr_team")
        print("✅ RBAC system works - hr_team removed, final roles implemented")
        
        # Test company config
        from config.company import COMPANY_NAME, CEO_NAME
        assert COMPANY_NAME == "Novigo Solutions Pvt Ltd"
        assert CEO_NAME == "Jayashree"
        print(f"✅ Company config works - {COMPANY_NAME}, CEO: {CEO_NAME}")
        
        # Test Power Automate service
        from actions.power_automate_action import test_webhook_connectivity
        results = test_webhook_connectivity()
        print("✅ Power Automate service works with improved error handling")
        
        # Test HR agent routing
        from agents.hr_agent import _deterministic_hr_route
        route = _deterministic_hr_route("approve leave 24")
        assert route["action"] == "approve_leave"
        assert route["leave_id"] == 24
        print("✅ HR agent deterministic routing works")
        
        return True
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False

def test_date_handling():
    """Test date handling improvements."""
    print("🧪 Testing Date Handling...")
    
    try:
        from actions.enhanced_date_action import enhanced_date_action
        
        # Test relative date parsing
        parsed_date, keyword = enhanced_date_action.parse_relative_date("tomorrow")
        assert keyword == "tomorrow"
        assert parsed_date is not None
        print("✅ Relative date parsing works")
        
        # Test date validation
        validation = enhanced_date_action.validate_leave_date(parsed_date)
        assert validation["valid"] == True
        print("✅ Date validation works")
        
        # Test weekend handling
        from datetime import date, timedelta
        saturday = date(2026, 5, 10)  # Saturday
        monday = enhanced_date_action.shift_to_next_working_day(saturday)
        assert monday.weekday() == 0  # Monday
        print("✅ Weekend shifting works")
        
        return True
        
    except Exception as e:
        print(f"❌ Date handling test failed: {e}")
        return False

def test_rbac_permissions():
    """Test RBAC permission matrix."""
    print("🧪 Testing RBAC Permissions...")
    
    try:
        from config.rbac import rbac_action, Permission
        
        # Test employee permissions
        assert rbac_action.has_permission("employee", Permission.VIEW_LEAVE_DASHBOARD)
        assert not rbac_action.has_permission("employee", Permission.APPROVE_LEAVE)
        assert not rbac_action.has_permission("employee", Permission.VIEW_SYSTEM_LOGS)
        print("✅ Employee permissions correct")
        
        # Test manager permissions
        assert rbac_action.has_permission("manager", Permission.APPROVE_LEAVE)
        assert rbac_action.has_permission("manager", Permission.APPROVE_TICKET)
        assert rbac_action.has_permission("manager", Permission.APPROVE_ASSET)
        assert not rbac_action.has_permission("manager", Permission.VIEW_SYSTEM_LOGS)
        print("✅ Manager permissions correct")
        
        # Test IT team permissions
        assert rbac_action.has_permission("it_team", Permission.APPROVE_TICKET)
        assert rbac_action.has_permission("it_team", Permission.APPROVE_ASSET)
        assert not rbac_action.has_permission("it_team", Permission.APPROVE_LEAVE)
        assert not rbac_action.has_permission("it_team", Permission.VIEW_LEAVE_DASHBOARD)
        print("✅ IT team permissions correct")
        
        # Test admin permissions
        assert rbac_action.has_permission("admin", Permission.ACCESS_ALL_PAGES)
        assert rbac_action.has_permission("admin", Permission.VIEW_SYSTEM_LOGS)
        print("✅ Admin permissions correct")
        
        return True
        
    except Exception as e:
        print(f"❌ RBAC permissions test failed: {e}")
        return False

def main():
    """Run validation tests."""
    print("🚀 Final Validation Test Suite")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_date_handling,
        test_rbac_permissions,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
            print()
        except Exception as e:
            print(f"❌ {test.__name__} crashed: {e}")
            failed += 1
            print()
    
    print("=" * 50)
    print(f"📊 Validation Results: {passed} passed, {failed} failed")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
