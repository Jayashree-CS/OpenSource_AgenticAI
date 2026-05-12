from datetime import date, timedelta

from db.models import Holiday


def is_weekend(value: date) -> bool:
    return value.weekday() >= 5


def get_holidays(db) -> list[Holiday]:
    if db is None:
        return []
    return db.query(Holiday).all()


def is_company_holiday(db, value: date) -> bool:
    if db is None:
        return False
    return db.query(Holiday).filter(Holiday.holiday_date == value).first() is not None


def is_holiday(value: date, db=None) -> bool:
    return is_company_holiday(db, value)


def _daterange(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def get_non_working_days_between(start_date: date, end_date: date, db=None) -> list[dict]:
    days = []
    holidays = {}
    if db is not None:
        holidays = {
            item.holiday_date: item.name
            for item in db.query(Holiday)
            .filter(Holiday.holiday_date >= start_date, Holiday.holiday_date <= end_date)
            .all()
        }

    for current in _daterange(start_date, end_date):
        if is_weekend(current):
            days.append({"date": current, "reason": "weekend"})
        elif current in holidays:
            days.append({"date": current, "reason": holidays[current]})

    return days


def get_working_days(db, start_date: date, end_date: date) -> list[date]:
    non_working = {item["date"] for item in get_non_working_days_between(start_date, end_date, db)}
    return [day for day in _daterange(start_date, end_date) if day not in non_working]


def calculate_working_days(db, start_date: date, end_date: date) -> int:
    return len(get_working_days(db, start_date, end_date))
