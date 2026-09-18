"""Login helpers for FollowUpBoss used as Scrapling `page_action` functions.

Credentials are read from environment variables `FUB_EMAIL` and
`FUB_PASSWORD`. They can also be provided through a `.env` file in the
project root (KEY=VALUE per line).
"""

import os
from pathlib import Path

from playwright.sync_api import Page


def _load_env() -> None:
    """Minimal .env loader so we don't need an extra dependency."""
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


async def login_page_action(page: Page) -> None:
    """Scrapling page_action: fill and submit the FollowUpBoss login form.

    Runs after navigation to the login URL. Waits until the browser is
    redirected away from /login so the authenticated cookies are stored in
    the session's persistent browser profile for all later requests.
    Works with the async page object used by AsyncDynamicSession.
    """
    email = os.environ.get("FUB_EMAIL", "")
    password = os.environ.get("FUB_PASSWORD", "")
    if not email or not password:
        raise RuntimeError(
            "FUB_EMAIL / FUB_PASSWORD are not set. "
            "Create a .env file in the project root or export them first."
        )
        
    #First check if session didn't expired and you don't need to log
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=5_000)
        return
    except Exception:
        pass
    

    check_for_sms_code = await page.locator("#code").is_visible()
    if check_for_sms_code:
        print("You need to provide code to access")
        
    else:
        try:
            await page.wait_for_selector("#username", timeout=15_000)
            await page.locator("#username").fill(email)
            await page.locator("body > div > div > main > section > div > div > div > div.cf2abdb86.cd43cf1d7 > div > form > div.ce03cec30 > button").click()
            #Still missing captacha function it need to happen for me to try capture it for error recording
            
            await page.locator("#password").fill(password)
            # await page.locator(".u-bigBlueButton").click()
            await page.locator("body > div > div > main > section > div > div > div > form > div.ce03cec30 > button").click()
        
        except Exception:
            print("There was issue with logging into the page.")
    
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=15_000)
    except Exception:
        pass
