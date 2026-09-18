"""Scrapling spider: log into FollowUpBoss and loop through API clients.

Flow:
1. Fetch the client list from the FollowUpBoss REST API (smart list).
2. Open the login page and authenticate (page_action).
3. For each client, navigate directly to their profile page
   (/2/people/view/{id}).
4. On the profile page, click the Home Activity "See all" button
   (page_action) which opens a modal with date-grouped property cards.
5. Extract the properties viewed today/yesterday into the client's
   `viewed_homes` field.

The `AsyncDynamicSession` uses a persistent browser profile, so after the
login request completes, all subsequent requests share the authenticated
cookies.
"""

import re
from datetime import date, datetime, timedelta
from typing import Any, AsyncGenerator, Dict, Optional

from playwright.async_api import Page
from scrapling.fetchers import AsyncDynamicSession
from scrapling.spiders import Request, Response, SessionManager, Spider

from resources.fb_browser import login_page_action
from resources.fb_api import get_people_to_check
from resources.variables import (
    DATE_WINDOW_DAYS,
    HOME_ACTIVITY_MODAL_SELECTOR,
    HOME_ACTIVITY_SECTION_SELECTOR,
    HOME_ACTIVITY_SEE_ALL_XPATH,
    LOGIN_URL,
    PEOPLE_URL,
    PERSON_LINK_SELECTOR,
    PERSON_NAME_SELECTOR,
    PROFILE_URL_TEMPLATE,
)

# Date group headers in the Home Activity modal: "Today", "Yesterday" or
# full dates like "September 12, 2026".
_HEADER_DATE_RE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$")
_HEADER_DATE_FORMAT = "%B %d, %Y"

# Property card text parsing.
_ADDRESS_RE = re.compile(
    r"^(?P<address>.+), (?P<city>[^,]+), (?P<state>[A-Z]{2}) (?P<zip>\d{5})$"
)
_PRICE_RE = re.compile(r"^\$[\d,]+$")
_SPECS_RE = re.compile(r"\b(bd|ba|sqft)\b")
_VIEWS_RE = re.compile(r"^\d+ views?$")


# Poll condition: the modal has rendered at least one date-group header
# ("Today", "Yesterday" or e.g. "September 12, 2026").
_MODAL_LOADED_JS = """() => {
    const dlg = document.querySelector('dialog');
    if (!dlg) return false;
    const re = /^(Today|Yesterday|[A-Z][a-z]+ \\d{1,2}, \\d{4})$/;
    for (const s of dlg.querySelectorAll('span')) {
        if (re.test(s.textContent.trim())) return true;
    }
    return false;
}"""


async def open_home_activity(page: Page) -> None:
    """Page action: click the Home Activity "See all" button.

    Opens the "...'s home activity" modal and waits until its date-grouped
    property cards have rendered before Scrapling snapshots the DOM.
    People without website activity have no button — skip silently.
    """
    try:
        section = page.locator(HOME_ACTIVITY_SECTION_SELECTOR)
        button = section.locator(HOME_ACTIVITY_SEE_ALL_XPATH).first
        if not await button.count():
            return
        await button.scroll_into_view_if_needed()
        await button.click()
        await page.wait_for_selector(HOME_ACTIVITY_MODAL_SELECTOR, timeout=10_000)
        await page.wait_for_function(_MODAL_LOADED_JS, timeout=15_000)
    except Exception:
        # No Home Activity section/button, or the modal never loaded —
        # parse_person will just find no cards.
        pass


def _header_within_window(header: str, days: int = DATE_WINDOW_DAYS) -> bool:
    """True if a modal date-group header is today or within `days` back."""
    header = header.strip()
    if header == "Today":
        return True
    if header == "Yesterday":
        return days >= 1
    if not _HEADER_DATE_RE.match(header):
        return False
    try:
        group_date = datetime.strptime(header, _HEADER_DATE_FORMAT).date()
    except ValueError:
        return False
    return 0 <= (date.today() - group_date).days <= days


def _is_date_header(text: str) -> bool:
    text = text.strip()
    return text in ("Today", "Yesterday") or bool(_HEADER_DATE_RE.match(text))


def _header_to_iso_date(header: str) -> str:
    """Resolve a modal date-group header to an ISO date (YYYY-MM-DD).

    "Today"/"Yesterday" are relative labels, so they are resolved against
    the current date; full dates like "September 17, 2026" are parsed.
    Returns the raw header when nothing matches.
    """
    header = header.strip()
    if header == "Today":
        return date.today().isoformat()
    if header == "Yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    if _HEADER_DATE_RE.match(header):
        try:
            return datetime.strptime(header, _HEADER_DATE_FORMAT).date().isoformat()
        except ValueError:
            pass
    return header


def _parse_property_card(details: str) -> Dict[str, str]:
    """Split a property card's text into structured fields.

    Card text is newline-separated, e.g.:
        Viewed | Active | $575,000 | ··· | 4 bd | 2.0 ba | 1,404 sqft |
        127 Hillcrest Ave, Edison, NJ 08817 | MLS #2700662R | 23 views
    Missing pieces (status, mls_id, ...) are returned as empty strings.
    """
    lines = [line.strip() for line in details.split("\n") if line.strip()]

    result = {
        "status": "",
        "price": "",
        "address": "",
        "city": "",
        "state": "",
        "zip": "",
        "mls_id": "",
    }
    if not lines:
        return result

    # lines[0] is the badge ("Viewed" / "Saved") — skipped.
    idx = 1

    # Optional status line ("Active", "Active - Atty Revu", ...): present
    # only when the next line is not the price or the "···" separator.
    if (
        idx < len(lines)
        and lines[idx] != "···"
        and not _PRICE_RE.match(lines[idx])
        and lines[idx] != "Price Unavailable"
    ):
        result["status"] = lines[idx]
        idx += 1

    # Skip the "···" separator(s) before the price line.
    while idx < len(lines) and lines[idx] == "···":
        idx += 1

    if idx < len(lines):
        result["price"] = lines[idx]
        idx += 1

    for line in lines[idx:]:
        if line == "···" or _SPECS_RE.search(line) or _VIEWS_RE.match(line):
            continue
        address_match = _ADDRESS_RE.match(line)
        if address_match:
            result["address"] = address_match.group("address")
            result["city"] = address_match.group("city")
            result["state"] = address_match.group("state")
            result["zip"] = address_match.group("zip")
        elif line.startswith("MLS #"):
            result["mls_id"] = line.removeprefix("MLS #").strip()
        # "MLS ID Unavailable" -> mls_id stays ""

    return result


class FollowUpBossSpider(Spider):
    name = "followupboss"
    allowed_domains = {
        "app.followupboss.com",
        "followupboss.com",
        "regimperial.followupboss.com",
    }

    # Be gentle with the live site.
    concurrent_requests = 2
    download_delay = 1.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Loaded lazily in start_requests so importing this module does not
        # perform a network call.
        self._clients: list[Dict[str, Any]] = []

    def configure_sessions(self, manager: SessionManager) -> None:
        # Persistent browser profile -> login cookies stay valid for all
        # requests made by this spider.
        manager.add("default",
                    AsyncDynamicSession(headless=False,
                                        user_data_dir='browser_temp',
                                        # additional_args={
                                        #     "viewport": {"width": 1920, "height": 1080},
                                        #     "screen": {"width": 1920, "height": 1080},
                                        # },
                                        # extra_flags=["--window-size=1920,1080"],
                                        ),
                    )


    async def start_requests(self) -> AsyncGenerator[Request, None]:
        # Load the client list from the API (once), then log in first;
        # `after_login` runs only once authentication finished.
        self._clients = get_people_to_check()
        self.logger.info(f"Loaded {len(self._clients)} clients from the API")
        yield Request(LOGIN_URL, page_action=login_page_action, callback=self.after_login)

    async def after_login(self, response: Response) -> AsyncGenerator[Request, None]:
        yield Request(
            PEOPLE_URL,
            callback=self.parse,
            network_idle=True,
            wait_selector=PERSON_LINK_SELECTOR,
        )
        
    async def parse(
        self, response: Response
    ) -> AsyncGenerator[Optional[Dict[str, Any] | Request], None]:
        """Loop through the API client list and visit each client's profile."""
        for client in self._clients:
            yield Request(
                PROFILE_URL_TEMPLATE.format(id=client["id"]),
                callback=self.parse_person,
                network_idle=True,
                page_action=open_home_activity,
                meta={"client": client},
            )

    async def parse_person(
        self, response: Response
    ) -> AsyncGenerator[Optional[Dict[str, Any] | Request], None]:
        """Person profile page: fill the client dict with today's/yesterday's
        viewed properties."""
        client = response.meta.get("client", {})

        name_elements = response.css(PERSON_NAME_SELECTOR)
        scraped_name = (
            (name_elements[0].get_all_text() or "").strip() if name_elements else ""
        )

        yield {
            "id": client.get("id"),
            "name": client.get("name") or scraped_name,
            "email": client.get("email", ""),
            "viewed_homes": self._extract_home_activity(response),
        }

    def _extract_home_activity(self, response: Response) -> list[Dict[str, Any]]:
        """Parse the Home Activity modal: date-grouped property cards.

        The modal (<dialog>) holds one container whose direct children are
        <span> date headers and <div> property cards; each card belongs to
        the header above it. Only cards within the date window are kept.
        """
        dialogs = response.css(HOME_ACTIVITY_MODAL_SELECTOR)
        if not dialogs:
            return []
        dialog = dialogs[0]

        # Find the container holding the date headers / cards: climb up from
        # any date-header span until the ancestor whose direct children mix
        # <span> headers and <div> cards.
        container = None
        for span in dialog.css("span"):
            if not _is_date_header(span.get_all_text()):
                continue
            node = span
            while node.parent is not None:
                node = node.parent
                children = node.css(":scope > *")
                tags = {child.tag for child in children}
                if len(children) > 1 and "span" in tags and "div" in tags:
                    container = node
                    break
            if container is not None:
                break
        if container is None:
            return []

        activities = []
        current_header = ""
        keep = False
        for child in container.css(":scope > *"):
            if child.tag == "span":
                current_header = child.get_all_text().strip()
                keep = _header_within_window(current_header)
            elif child.tag == "div" and keep:
                links = child.css("a")
                activities.append(
                    {
                        "date": _header_to_iso_date(current_header),
                        **_parse_property_card(child.get_all_text()),
                        "url": links[0].attrib.get("href") if links else None,
                    }
                )
        return activities
