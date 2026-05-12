"""
enhanced_date_action.py

Centralized timezone-aware date utility service to fix date + holiday logic bugs.

Provides deterministic date resolution for:
- today, tomorrow, day after tomorrow
- next weekdays (next monday, etc.)
- safe weekend handling
- timezone-safe current date
- relative date validation
"""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Optional, Tuple, List

from config.dateTime import DEFAULT_TIMEZONE


class EnhancedDateService:
    """Centralized timezone-aware date service with deterministic logic."""
    
    def __init__(self):
        self.timezone = ZoneInfo(DEFAULT_TIMEZONE)
    
    def get_today(self) -> date:
        """Get today's date in the configured timezone."""
        return datetime.now(self.timezone).date()
    
    def get_tomorrow(self) -> date:
        """Get tomorrow's date in the configured timezone."""
        return self.get_today() + timedelta(days=1)
    
    def get_day_after_tomorrow(self) -> date:
        """Get day after tomorrow's date in the configured timezone."""
        return self.get_today() + timedelta(days=2)
    
    def get_next_weekday(self, target_weekday: int) -> date:
        """
        Get the next occurrence of a specific weekday.
        
        Args:
            target_weekday: Monday=0, Tuesday=1, ..., Sunday=6
            
        Returns:
            Date of next target weekday
        """
        today = self.get_today()
        days_ahead = (target_weekday - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # If today is the target day, get next week's
        return today + timedelta(days=days_ahead)
    
    def parse_relative_date(self, message: str) -> Tuple[Optional[date], Optional[str]]:
        """
        Parse relative dates from message with deterministic logic.
        
        Args:
            message: User message containing relative date
            
        Returns:
            Tuple of (parsed_date, relative_keyword)
        """
        msg_lower = (message or "").lower().strip()
        today = self.get_today()
        
        # Check for specific relative patterns
        if "day after tomorrow" in msg_lower:
            return self.get_day_after_tomorrow(), "day_after_tomorrow"
        elif re.search(r"\btomorrow\b", msg_lower):
            return self.get_tomorrow(), "tomorrow"
        elif re.search(r"\btoday\b", msg_lower):
            return today, "today"
        
        # Check for weekday patterns
        weekday_patterns = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6
        }
        
        for weekday_name, weekday_num in weekday_patterns.items():
            if re.search(rf"\b(?:next\s+)?{weekday_name}\b", msg_lower):
                return self.get_next_weekday(weekday_num), f"next_{weekday_name}"
        
        return None, None
    
    def shift_to_next_working_day(self, target_date: date) -> date:
        """
        Shift date to next working day if it falls on weekend.
        
        Args:
            target_date: Date to check/shift
            
        Returns:
            Working day date (same if already working day)
        """
        if target_date.weekday() >= 5:  # Saturday (5) or Sunday (6)
            # Shift to next Monday
            days_to_monday = 7 - target_date.weekday()
            return target_date + timedelta(days=days_to_monday)
        return target_date
    
    def is_weekend(self, target_date: date) -> bool:
        """Check if date falls on weekend."""
        return target_date.weekday() >= 5
    
    def get_date_info(self, target_date: date) -> Dict[str, any]:
        """
        Get comprehensive date information.
        
        Args:
            target_date: Date to analyze
            
        Returns:
            Dictionary with date information
        """
        today = self.get_today()
        is_past = target_date < today
        is_today = target_date == today
        is_future = target_date > today
        is_weekend = self.is_weekend(target_date)
        
        return {
            "date": target_date,
            "is_past": is_past,
            "is_today": is_today,
            "is_future": is_future,
            "is_weekend": is_weekend,
            "day_name": target_date.strftime("%A"),
            "formatted": target_date.strftime("%Y-%m-%d"),
            "relative_to_today": (target_date - today).days
        }
    
    def validate_leave_date(self, target_date: date) -> Dict[str, any]:
        """
        Validate date for leave application with comprehensive checks.
        
        Args:
            target_date: Date to validate for leave
            
        Returns:
            Validation result with recommendations
        """
        date_info = self.get_date_info(target_date)
        
        if date_info["is_past"]:
            return {
                "valid": False,
                "error": "past_date",
                "message": "You cannot apply leave for a past date. Please choose today or a future date.",
                "suggestion": self.get_tomorrow().isoformat() if not self.is_weekend(self.get_tomorrow()) else self.shift_to_next_working_day(self.get_tomorrow()).isoformat()
            }
        
        if date_info["is_weekend"]:
            working_day = self.shift_to_next_working_day(target_date)
            return {
                "valid": False,
                "error": "weekend",
                "message": f"{date_info['day_name']} falls on a weekend, so leave is not required.",
                "suggestion": working_day.isoformat(),
                "shifted_date": working_day.isoformat()
            }
        
        return {
            "valid": True,
            "error": None,
            "message": "Date is valid for leave application.",
            "date_info": date_info
        }
    
    def get_date_range_info(self, start_date: date, end_date: date) -> Dict[str, any]:
        """
        Get comprehensive date range information.
        
        Args:
            start_date: Range start date
            end_date: Range end date
            
        Returns:
            Dictionary with range information
        """
        if end_date < start_date:
            return {
                "valid": False,
                "error": "end_before_start",
                "message": "End date cannot be before start date."
            }
        
        total_days = (end_date - start_date).days + 1
        weekend_days = 0
        
        current = start_date
        while current <= end_date:
            if self.is_weekend(current):
                weekend_days += 1
            current += timedelta(days=1)
        
        working_days = total_days - weekend_days
        
        return {
            "valid": True,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_days": total_days,
            "working_days": working_days,
            "weekend_days": weekend_days,
            "duration_days": (end_date - start_date).days + 1
        }


# Global instance for centralized access
enhanced_date_action = EnhancedDateService()


# Backward compatibility functions
def get_today() -> date:
    """Get today's date in the configured timezone."""
    return enhanced_date_action.get_today()


def get_tomorrow() -> date:
    """Get tomorrow's date in the configured timezone."""
    return enhanced_date_action.get_tomorrow()


def get_day_after_tomorrow() -> date:
    """Get day after tomorrow's date in the configured timezone."""
    return enhanced_date_action.get_day_after_tomorrow()


def parse_relative_date_safe(message: str) -> Tuple[Optional[date], Optional[str]]:
    """
    Safe relative date parsing with deterministic logic.
    
    Args:
        message: User message
        
    Returns:
        Tuple of (parsed_date, relative_keyword)
    """
    return enhanced_date_action.parse_relative_date(message)


def validate_leave_date_safe(target_date: date) -> Dict[str, any]:
    """
    Safe leave date validation with comprehensive checks.
    
    Args:
        target_date: Date to validate
        
    Returns:
        Validation result
    """
    return enhanced_date_action.validate_leave_date(target_date)


def get_date_info_safe(target_date: date) -> Dict[str, any]:
    """
    Safe date information retrieval.
    
    Args:
        target_date: Date to analyze
        
    Returns:
        Date information dictionary
    """
    return enhanced_date_action.get_date_info(target_date)


def get_today_text() -> str:
    """Get formatted today text."""
    today = get_today()
    return f"Today is {today.strftime('%A')}, {today.day} {today.strftime('%B')} {today.year}"


def get_day_name(value: date) -> str:
    """Get day name for date."""
    return value.strftime("%A")
