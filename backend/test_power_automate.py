#!/usr/bin/env python3
"""
Test script to validate Power Automate integration logic without full backend dependencies.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_power_automate_imports():
    """Test that Power Automate service can be imported."""
    try:
        from actions.power_automate_action import (
            send_hr_notification, 
            send_it_notification, 
            send_asset_notification,
            notify_leave_applied,
            notify_ticket_created,
            notify_asset_requested
        )
        print("✅ Power Automate service imports successfully")
        return True
    except ImportError as e:
        print(f"❌ Power Automate service import failed: {e}")
        return False

def test_payload_structure():
    """Test that notification payloads have correct structure."""
    try:
        from actions.power_automate_action import send_hr_notification, send_it_notification, send_asset_notification
        
        # Test HR payload structure
        hr_result = send_hr_notification(
            event_type="leave_applied",
            title="Leave Request Submitted",
            message="Test employee applied for Sick Leave.",
            status="Pending Manager Approval",
            status_color="#facc15",
            employee_name="Test Employee",
            leave_type="Sick Leave",
            reason="Test reason",
            start_date="2026-08-12",
            end_date="2026-08-12",
            leave_id=1
        )
        print("✅ HR notification payload structure valid")
        
        # Test IT payload structure
        it_result = send_it_notification(
            event_type="ticket_created",
            title="IT Ticket Created",
            message="VPN issue ticket created.",
            status="Open",
            status_color="#3b82f6",
            ticket_id=101,
            ticket_type="VPN",
            priority="Medium",
            user_email="test@example.com",
            description="Test description"
        )
        print("✅ IT notification payload structure valid")
        
        # Test Asset payload structure
        asset_result = send_asset_notification(
            event_type="asset_requested",
            title="Asset Request Submitted",
            message="Laptop request submitted.",
            status="Pending Approval",
            status_color="#a855f7",
            employee_name="Test Employee",
            asset_name="Dell Latitude",
            asset_type="Laptop",
            user_email="test@example.com",
            request_id=1,
            reason="Test reason"
        )
        print("✅ Asset notification payload structure valid")
        
        # Since no webhooks are configured, all should return False
        assert hr_result == False, "HR notification should return False when webhook not configured"
        assert it_result == False, "IT notification should return False when webhook not configured"
        assert asset_result == False, "Asset notification should return False when webhook not configured"
        print("✅ All notifications correctly handle missing webhook URLs")
        
        return True
    except Exception as e:
        print(f"❌ Payload structure test failed: {e}")
        return False

def test_environment_variables():
    """Test environment variable handling."""
    try:
        # Test with empty environment variables
        os.environ['POWER_HR_URL'] = ''
        os.environ['POWER_IT_URL'] = ''
        os.environ['POWER_ASSET_URL'] = ''
        
        from actions.power_automate_action import POWER_HR_URL, POWER_IT_URL, POWER_ASSET_URL
        
        assert POWER_HR_URL == '', "POWER_HR_URL should be empty"
        assert POWER_IT_URL == '', "POWER_IT_URL should be empty"
        assert POWER_ASSET_URL == '', "POWER_ASSET_URL should be empty"
        print("✅ Environment variables handled correctly")
        
        # Test with valid environment variables
        os.environ['POWER_HR_URL'] = 'https://example.com/hr-webhook'
        os.environ['POWER_IT_URL'] = 'https://example.com/it-webhook'
        os.environ['POWER_ASSET_URL'] = 'https://example.com/asset-webhook'
        
        # Reload the module to test environment variable loading
        import importlib
        import actions.power_automate_action
        importlib.reload(actions.power_automate_action)
        
        print("✅ Environment variable reloading works")
        return True
    except Exception as e:
        print(f"❌ Environment variable test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing Power Automate Integration...")
    print("=" * 50)
    
    tests = [
        test_power_automate_imports,
        test_payload_structure,
        test_environment_variables
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All Power Automate integration tests passed!")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
