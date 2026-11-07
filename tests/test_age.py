from datetime import date

import pytest

from app.models import User, calculate_age


@pytest.mark.parametrize("date_of_birth,today,expected", [
    (None, date(2026, 11, 7), None),
    (date(2000, 11, 8), date(2026, 11, 7), 25),
    (date(2000, 11, 7), date(2026, 11, 7), 26),
    (date(2000, 11, 6), date(2026, 11, 7), 26),
    (date(2000, 2, 29), date(2024, 2, 28), 23),
    (date(2000, 2, 29), date(2024, 2, 29), 24),
    (date(2000, 2, 29), date(2025, 2, 28), 24),
    (date(2000, 2, 29), date(2025, 3, 1), 25),
])
def test_calculate_age_counts_completed_years(date_of_birth, today, expected):
    assert calculate_age(date_of_birth, today=today) == expected


def test_user_age_uses_birthday_without_storing_age(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 7)

    monkeypatch.setattr("app.models.dt.date", FixedDate)
    user = User(date_of_birth=date(2000, 11, 8))
    assert user.age == 25
    user.date_of_birth = date(2000, 11, 7)
    assert user.age == 26
    user.date_of_birth = None
    assert user.age is None
