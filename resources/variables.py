"""Shared constants for the FollowUpBoss spider."""

import os
from pathlib import Path


def _load_env() -> None:
    """Minimal .env loader so credentials work without extra dependencies."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

# FollowUpBoss REST API (credentials come from .env / environment).
FB_API_KEY = os.environ.get("FB_API_KEY", "")
FB_ENDPOINT = "https://api.followupboss.com/v1/people?sort=lastActivity&limit=100&offset=0&fields=id%2Cname%2Cemails&smartListId=128&includeTrash=false&includeUnclaimed=True"

BASE_URL = os.environ.get("FUB_BASE_URL", "https://app.followupboss.com")
LOGIN_URL = f"{BASE_URL}/login"
PEOPLE_URL = f"{BASE_URL}/2/people"
PROFILE_URL_TEMPLATE = f"{BASE_URL}/2/people/view/{{id}}"

# People list
PERSON_LINK_SELECTOR = "a[href*='/people/view/']"
NEXT_PAGE_SELECTORS = ("a[rel='next']", "a.next", "li.next a")

# Person profile
PERSON_NAME_SELECTOR = "[data-fub-id='PersonDetailsEditLink-names']"

# Home Activity "See all" — stable data-fub-id + label-text based
# (verified live; avoids brittle styled-components hash classes).
# NOTE: the label is "<strong>HOME ACTIVITY</strong>" and the button text is
# "SEE ALL" (uppercase in the DOM), hence the case-insensitive translate().
HOME_ACTIVITY_SECTION_SELECTOR = "[data-fub-id='person-section-websiteActivity']"
HOME_ACTIVITY_SEE_ALL_XPATH = (
    "xpath=.//strong[contains(., 'HOME ACTIVITY')]/following::span["
    "translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    "='see all'][1]"
)

# Clicking "See all" opens a <dialog> modal ("...'s home activity") with
# date-grouped property cards: direct children of one container, where
# <span> children are date headers ("Today", "September 12, 2026") and
# <div> children are the property cards belonging to the header above them.
HOME_ACTIVITY_MODAL_SELECTOR = "dialog"

# How many days back to keep activities: 0 = today only, 1 = today + yesterday.
DATE_WINDOW_DAYS = 1
