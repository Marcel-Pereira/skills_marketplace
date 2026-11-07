"""Choices and validation for the personal-details form."""
from datetime import date
from zoneinfo import available_timezones

import pycountry


COUNTRY_OPTIONS = sorted(
    ((country.alpha_2, getattr(country, "common_name", country.name))
     for country in pycountry.countries),
    key=lambda option: option[1].casefold(),
)
COUNTRY_CODES = {code for code, name in COUNTRY_OPTIONS}
TIMEZONE_OPTIONS = sorted(available_timezones() - {"localtime"})
TIMEZONE_NAMES = set(TIMEZONE_OPTIONS)


def profile_values(user):
    return {
        "bio": user.bio or "",
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else "",
        "country_code": user.country_code or "",
        "timezone": user.timezone or "",
    }


def validate_profile_details(form, user):
    """Return displayed values, proposed changes and errors without changing the user."""
    values = profile_values(user)
    changes = {}
    errors = {}
    for field in values:
        if field in form:
            values[field] = form[field].strip()
            changes[field] = values[field] or None

    if "country_code" in changes:
        values["country_code"] = values["country_code"].upper()
        changes["country_code"] = values["country_code"] or None
        if (changes["country_code"] and changes["country_code"] not in COUNTRY_CODES
                and changes["country_code"] != user.country_code):
            errors["country_code"] = "Choose a valid country."

    if (changes.get("timezone") and changes["timezone"] not in TIMEZONE_NAMES
            and changes["timezone"] != user.timezone):
        errors["timezone"] = "Choose a valid timezone."

    if "date_of_birth" in changes and changes["date_of_birth"]:
        try:
            birthday = date.fromisoformat(values["date_of_birth"])
            if birthday.isoformat() != values["date_of_birth"]:
                raise ValueError
        except ValueError:
            changes["date_of_birth"] = None
            errors["date_of_birth"] = "Enter a valid date of birth."
        else:
            changes["date_of_birth"] = birthday
            if birthday > date.today():
                errors["date_of_birth"] = "Date of birth cannot be in the future."

    return values, changes, errors
