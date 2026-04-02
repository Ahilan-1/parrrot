"""
Parrrot — Gmail control via screen vision + mouse/keyboard.
No Playwright. No IMAP. No external dependencies beyond mss + pyautogui.
Opens gmail.com in the default system browser, then watches the screen
and controls mouse/keyboard to read and send emails — exactly like a human.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import time
from typing import Optional

from parrrot.tools.registry import registry


# ---------------------------------------------------------------------------
# Gmail navigation
# ---------------------------------------------------------------------------

def _open_gmail() -> str:
    """
    Open Gmail in the default browser. Waits for it to load before returning.
    Uses navigate_to (Ctrl+L method) if a browser is already open,
    otherwise opens a new browser window.
    """
    from parrrot.tools.browser_control import _navigate_to
    result = _navigate_to("https://mail.google.com", wait=4.0)
    return (
        f"{result}\n\n"
        "Gmail should now be open. Use read_gmail_inbox to see your emails."
    )


# ---------------------------------------------------------------------------
# Reading emails
# ---------------------------------------------------------------------------

async def _read_gmail_inbox(count: int = 10) -> str:
    """
    Read the visible Gmail inbox by OCR first (works with any model),
    then use vision LLM to interpret it if available.
    """
    from parrrot.tools.screen import _ask_screen, _ocr_screen

    # Try OCR first — fast and works without a vision model
    ocr_text = _ocr_screen()
    if ocr_text and len(ocr_text) > 50:
        # Ask the text model to parse the raw OCR into a readable email list
        try:
            from parrrot.core.router import Router
            from parrrot.models.base import CompletionRequest, Message

            router = Router()
            prompt = (
                f"This is text extracted from a Gmail inbox screen via OCR:\n\n"
                f"---\n{ocr_text[:4000]}\n---\n\n"
                f"Please list up to {count} emails you can identify. "
                f"For each one show: sender, subject, and date/preview if present. "
                f"If this looks like a login page, say so clearly."
            )
            resp = await router.complete(
                CompletionRequest(messages=[Message(role="user", content=prompt)], max_tokens=1000)
            )
            return resp.content
        except Exception:
            # OCR worked but text-LLM failed — just return raw OCR
            return f"Raw screen text (OCR):\n\n{ocr_text[:3000]}"

    # OCR got nothing — fall back to vision ask_screen (works with llava/gpt-4o)
    return await _ask_screen(
        f"I'm looking at Gmail. Please list up to {count} visible emails: "
        f"sender, subject, preview. If it's a login page say so."
    )


async def _open_email(description: str) -> str:
    """
    Find and click an email in the inbox by its description (sender, subject, etc.).
    Then read the full email content from the screen.
    """
    from parrrot.tools.screen import _ask_screen
    from parrrot.tools.pc_control import _ocr_click, _smart_click

    # Try OCR click first (finds the text directly), then smart_click fallback
    click_result = _ocr_click(description)
    if "Could not find" in click_result:
        click_result = await _smart_click(description)

    time.sleep(2)  # Wait for email to open

    # Read the email content
    content = await _ask_screen(
        "An email is now open. Please read and return: "
        "the sender, subject, date, and the full body text of the email."
    )

    return f"{click_result}\n\nEmail content:\n{content}"


async def _read_current_email() -> str:
    """Read the email that is currently open on screen."""
    from parrrot.tools.screen import _ask_screen

    return await _ask_screen(
        "An email is open on screen. Please read and return everything: "
        "sender, recipient, subject, date, and the complete email body text."
    )


# ---------------------------------------------------------------------------
# Composing and sending
# ---------------------------------------------------------------------------

async def _compose_gmail(to: str, subject: str, body: str) -> str:
    """
    Compose a new Gmail message using OCR + keyboard.
    Clicks Compose, fills To/Subject/Body fields, but does NOT send yet.
    Call send_current_email() to send after reviewing.
    """
    from parrrot.tools.screen import _ask_screen, _wait_for_element
    from parrrot.tools.pc_control import _ocr_click, _smart_click, _type_paste

    steps: list[str] = []

    # Step 1: Click Compose button (OCR finds the text "Compose" directly)
    r = _ocr_click("Compose")
    if "Could not find" in r:
        r = await _smart_click("Compose button")
    steps.append(r)
    time.sleep(1.5)

    # Step 2: Click To field and type recipient
    r = _ocr_click("To")
    if "Could not find" in r:
        r = await _smart_click("To: field in compose")
    steps.append(r)
    time.sleep(0.3)
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
    except ImportError:
        pass
    r = _type_paste(to)
    steps.append(f"Typed To: {r}")
    time.sleep(0.3)

    # Tab to Subject
    try:
        import pyautogui
        pyautogui.press("tab")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
    except ImportError:
        pass

    # Step 3: Type subject
    r = _type_paste(subject)
    steps.append(f"Typed Subject: {r}")
    time.sleep(0.3)

    # Tab to body
    try:
        import pyautogui
        pyautogui.press("tab")
        time.sleep(0.2)
    except ImportError:
        pass

    # Step 4: Type body
    r = _type_paste(body)
    steps.append(f"Typed body: {r}")
    time.sleep(0.3)

    # Confirm compose state
    confirm = await _ask_screen(
        "Is there a Gmail compose window open with a filled To field, Subject, and message body? "
        "What does it show?"
    )
    steps.append(f"Compose state: {confirm}")

    return "\n".join(steps)


async def _send_current_email() -> str:
    """
    Click the Send button in the currently open Gmail compose window.
    Only call this after compose_gmail and confirming the content looks right.
    """
    from parrrot.tools.screen import _ask_screen
    from parrrot.tools.pc_control import _ocr_click, _smart_click

    # Click Send via OCR (finds the text "Send" on screen)
    result = _ocr_click("Send")
    if "Could not find" in result:
        result = await _smart_click("Send button in Gmail compose window")
    time.sleep(1.5)

    # Confirm it sent
    confirm = await _ask_screen(
        "Did the email send successfully? "
        "Is the compose window gone? What does Gmail show now?"
    )

    return f"{result}\n\nAfter sending: {confirm}"


# ---------------------------------------------------------------------------
# Gmail search
# ---------------------------------------------------------------------------

async def _search_gmail(query: str) -> str:
    """
    Type a search query into the Gmail search bar and read the results.
    """
    from parrrot.tools.screen import _ask_screen, _wait_for_element
    from parrrot.tools.pc_control import _ocr_click, _type_paste

    steps: list[str] = []

    # Click the search bar and type query
    r = _ocr_click("Search mail")
    if "Could not find" in r:
        r = _ocr_click("Search")
    steps.append(r)
    time.sleep(0.3)
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
    except ImportError:
        pass
    _type_paste(query)
    time.sleep(0.3)

    try:
        import pyautogui
        pyautogui.press("enter")
    except ImportError:
        pass

    time.sleep(2)

    results = await _ask_screen(
        f"I searched Gmail for '{query}'. What email results are visible? "
        f"List each result: sender, subject, date, preview."
    )
    steps.append(f"Search results for '{query}':\n{results}")

    return "\n".join(steps)


# ---------------------------------------------------------------------------
# Reply to current email
# ---------------------------------------------------------------------------

async def _reply_to_email(body: str) -> str:
    """
    Reply to the currently open email. Clicks Reply, types body, does NOT send.
    Call send_current_email() to send.
    """
    from parrrot.tools.screen import _ask_screen
    from parrrot.tools.pc_control import _ocr_click, _smart_click, _type_paste

    steps: list[str] = []

    r = _ocr_click("Reply")
    if "Could not find" in r:
        r = await _smart_click("Reply button in the open email")
    steps.append(r)
    time.sleep(1.5)

    # Click reply body area (look for "Reply" area or just click below the quote)
    r = _ocr_click("Reply")
    if "Could not find" in r:
        r = await _smart_click("reply message body area")
    steps.append(r)
    time.sleep(0.3)

    r = _type_paste(body)
    steps.append(f"Typed reply: {r}")

    confirm = await _ask_screen("Is a reply compose window open with the typed message?")
    steps.append(confirm)

    return "\n".join(steps)


# ---------------------------------------------------------------------------
# Navigate Gmail folders
# ---------------------------------------------------------------------------

async def _open_gmail_folder(folder: str) -> str:
    """
    Click a Gmail folder/label (Inbox, Sent, Drafts, Spam, Starred, or any label name).
    """
    from parrrot.tools.pc_control import _ocr_click, _smart_click
    from parrrot.tools.screen import _ask_screen

    r = _ocr_click(folder)
    if "Could not find" in r:
        r = await _smart_click(f"{folder} link or label in the Gmail sidebar")
    time.sleep(1.5)

    content = await _ask_screen(f"What emails are now visible in {folder}?")
    return f"{r}\n\n{content}"


# ---------------------------------------------------------------------------
# Register all tools
# ---------------------------------------------------------------------------

registry.register(
    "open_gmail",
    "Open Gmail in the default system browser (no Playwright). Then use read_gmail_inbox or ask_screen to see what loaded.",
    {},
)(_open_gmail)

registry.register(
    "read_gmail_inbox",
    "Read the Gmail inbox currently visible on screen using the vision model",
    {"count": "max number of emails to list (default 10)"},
)(_read_gmail_inbox)

registry.register(
    "open_email",
    "Find and click an email in the Gmail inbox by sender or subject, then read it",
    {"description": "describe the email to open, e.g. 'email from John about the meeting'"},
)(_open_email)

registry.register(
    "read_current_email",
    "Read the full content of the email currently open on screen",
    {},
)(_read_current_email)

registry.register(
    "compose_gmail",
    "Compose a new Gmail message (fills To, Subject, Body). Does NOT send — call send_current_email() to send.",
    {
        "to": "recipient email address",
        "subject": "email subject line",
        "body": "email body text",
    },
    requires_confirm=False,
)(_compose_gmail)

registry.register(
    "send_current_email",
    "Click Send on the currently open Gmail compose window",
    {},
    requires_confirm=True,
)(_send_current_email)

registry.register(
    "search_gmail",
    "Search Gmail for emails matching a query",
    {"query": "search query, e.g. 'from:boss subject:urgent'"},
)(_search_gmail)

registry.register(
    "reply_to_email",
    "Reply to the currently open email (fills body, does NOT send)",
    {"body": "reply text"},
)(_reply_to_email)

registry.register(
    "open_gmail_folder",
    "Navigate to a Gmail folder or label (Inbox, Sent, Drafts, Spam, Starred, or any label)",
    {"folder": "folder name, e.g. 'Sent', 'Drafts', 'Starred'"},
)(_open_gmail_folder)
