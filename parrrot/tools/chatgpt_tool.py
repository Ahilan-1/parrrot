"""
Parrrot — ChatGPT integration via Firefox.
Opens chatgpt.com in Firefox, asks questions, reads full responses (with
auto-scroll), learns from the answers, and saves knowledge to memory.
No API key needed — uses the web UI exactly as a human would.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import re
import time
from typing import Optional

from parrrot.tools.registry import registry


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _navigate_to_chatgpt(wait: float = 3.5) -> str:
    """Open chatgpt.com in Firefox (new tab if already open)."""
    from parrrot.tools.browser_control import _open_new_tab, _is_firefox_running, _navigate_to

    if _is_firefox_running():
        return _open_new_tab("https://chatgpt.com", wait=wait)
    return _navigate_to("https://chatgpt.com", wait=wait)


def _is_chatgpt_generating() -> bool:
    """
    Check if ChatGPT is still generating a response.
    Looks for "Stop generating" / "Stop" text in OCR output.
    """
    from parrrot.tools.screen import _ocr_screen
    text = _ocr_screen().lower()
    return "stop generating" in text or ("stop" in text and "generating" in text)


def _ocr_full_page_text(scroll_attempts: int = 6) -> str:
    """
    OCR the current page, scroll down, OCR again, combine.
    Returns deduplicated full page text.
    """
    from parrrot.tools.screen import _ocr_screen

    all_text_parts: list[str] = []
    seen_lines: set[str] = set()

    for i in range(scroll_attempts):
        chunk = _ocr_screen()
        if chunk:
            # Add only new lines (dedup)
            for line in chunk.splitlines():
                stripped = line.strip()
                if stripped and stripped not in seen_lines:
                    seen_lines.add(stripped)
                    all_text_parts.append(stripped)

        if i < scroll_attempts - 1:
            # Scroll down to reveal more content
            try:
                import pyautogui
                pyautogui.scroll(-5)
                time.sleep(0.6)
            except ImportError:
                break

    return "\n".join(all_text_parts)


def _wait_for_response_complete(
    timeout: int = 90,
    poll_interval: float = 2.5,
    stable_checks: int = 3,
) -> str:
    """
    Poll the screen until ChatGPT finishes generating.
    Detection: OCR text stops growing AND "Stop generating" disappears.

    Returns the final OCR text of the completed response page.
    """
    from parrrot.tools.screen import _ocr_screen

    prev_length = 0
    stable_count = 0
    start = time.time()

    while time.time() - start < timeout:
        current_text = _ocr_screen()
        current_len = len(current_text)

        still_generating = _is_chatgpt_generating()

        if not still_generating and current_len == prev_length and current_len > 100:
            stable_count += 1
            if stable_count >= stable_checks:
                # Response has stabilized and "Stop" button is gone — done
                return current_text
        else:
            stable_count = 0

        prev_length = current_len
        time.sleep(poll_interval)

    # Timed out — return whatever we have
    return _ocr_screen()


def _type_into_chatgpt(text: str) -> bool:
    """
    Click the ChatGPT message input and type (paste) text.
    Returns True on success.
    """
    from parrrot.tools.pc_control import _ocr_click, _type_paste

    # Best-effort: ensure Firefox is focused before clicking/typing.
    try:
        from parrrot.tools.browser_control import _focus_firefox

        _focus_firefox(wait=0.2)
    except Exception:
        pass

    # Verification: use a stable snippet of the question.
    snippet = " ".join(text.strip().split())[:35].lower()

    def _normalize_ocr(s: str) -> str:
        return " ".join((s or "").lower().split())

    try:
        import pyautogui
        from parrrot.tools.screen import _ocr_screen

        # Try a few plausible click positions (ChatGPT layout varies by screen/zoom).
        # We will retry paste until OCR sees the snippet.
        attempts = [
            (0.50, 0.85),
            (0.50, 0.82),
            (0.50, 0.88),
            (0.40, 0.86),
            (0.60, 0.86),
        ]

        # First: try OCR labels to focus input.
        try_labels = ["Message ChatGPT", "Send a message", "Ask anything", "message"]
        for label in try_labels:
            try:
                result = _ocr_click(label)
                if "OCR-clicked" in result or "clicked" in result.lower():
                    break
            except Exception:
                continue

        w, h = pyautogui.size()
        for x_frac, y_frac in attempts:
            # Click near the input area.
            pyautogui.click(int(w * x_frac), int(h * y_frac))
            time.sleep(0.15)

            # Clear existing content.
            try:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
                pyautogui.press("backspace")
                time.sleep(0.08)
            except Exception:
                pass

            _type_paste(text)
            time.sleep(0.25)

            # Verify using OCR; if OCR doesn't match, we assume focus failed and retry.
            ocr_text = _normalize_ocr(_ocr_screen())
            if snippet and snippet in ocr_text:
                return True

        return False
    except ImportError:
        return False


def _submit_chatgpt_message() -> None:
    """Submit the typed message (Enter key)."""
    try:
        import pyautogui
        pyautogui.press("enter")
        time.sleep(0.5)
    except ImportError:
        pass


def _extract_chatgpt_response(page_text: str) -> str:
    """
    Extract just the ChatGPT response from a full page OCR dump.
    Strips header/footer/UI noise. Returns the response text.
    """
    lines = page_text.splitlines()
    # Remove known UI chrome lines
    noise_patterns = [
        r"^chatgpt$", r"^new chat$", r"^sign (in|up)$", r"^log (in|out)$",
        r"^send$", r"^stop$", r"^regenerate$", r"^copy$", r"^share$",
        r"^(message|send a message|ask anything)\s*$",
        r"^\d+\s*/\s*\d+$",  # page numbers
    ]
    noise_re = re.compile("|".join(noise_patterns), re.IGNORECASE)

    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if noise_re.match(stripped):
            continue
        cleaned.append(stripped)

    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def _chatgpt_open() -> str:
    """Open ChatGPT in Firefox and wait for it to load."""
    result = _navigate_to_chatgpt(wait=4.0)
    return f"{result}\nChatGPT is ready. Use ask_chatgpt to ask a question."


async def _ask_chatgpt(
    question: str,
    learn: bool = True,
    scroll_pages: int = 5,
) -> str:
    """
    Ask ChatGPT a question via Firefox:
    1. Opens/navigates to chatgpt.com
    2. Types the question and submits
    3. Waits for the full response (auto-detects completion)
    4. Scrolls down to capture any overflow
    5. Optionally saves the knowledge to memory and creates a skill if procedural

    learn=True: saves the response to memory (default)
    scroll_pages: how many scroll steps to collect the full answer (default 5)
    """
    from parrrot.tools.screen import _ocr_screen
    from parrrot.core import memory as mem

    steps: list[str] = []

    # Step 1: Open ChatGPT
    steps.append("Opening ChatGPT in Firefox...")
    nav = _navigate_to_chatgpt(wait=3.5)
    steps.append(nav)
    time.sleep(1.0)

    # Step 2: Type question
    steps.append(f"Typing question: {question[:80]}...")
    success = _type_into_chatgpt(question)
    if not success:
        return "Could not find ChatGPT input field. Is chatgpt.com loaded in Firefox?"

    time.sleep(0.4)

    # Step 3: Submit
    _submit_chatgpt_message()
    steps.append("Submitted — waiting for ChatGPT to respond...")
    time.sleep(2.0)  # brief pause before polling

    # Step 4: Wait for full response
    raw_page = _wait_for_response_complete(timeout=120, poll_interval=2.5, stable_checks=3)
    steps.append("Response received. Scrolling to capture full answer...")

    # Step 5: Scroll down and collect more text
    full_text = _ocr_full_page_text(scroll_attempts=scroll_pages)
    if not full_text:
        full_text = raw_page

    response_text = _extract_chatgpt_response(full_text)

    if not response_text or len(response_text) < 30:
        steps.append("Warning: could not extract response text (page may not have loaded).")
        response_text = full_text[:3000] if full_text else "No response captured."

    steps.append(f"\n--- ChatGPT Response ---\n{response_text[:3000]}\n--- End ---")

    # Step 6: Save to memory and learn
    if learn and response_text:
        try:
            # Save raw response to memory
            key = re.sub(r"[^\w]", "_", question.lower()[:40]).strip("_")
            mem.remember(f"chatgpt_{key}", response_text[:500])

            # Use the learner to extract structured knowledge from the response
            from parrrot.core.learner import _extract_knowledge, save_skill_file
            knowledge = await _extract_knowledge(question, response_text)

            if knowledge["summary"]:
                mem.remember(f"learned_{key}", knowledge["summary"])
            for i, fact in enumerate(knowledge["facts"][:10]):
                mem.remember(f"fact_{key}_{i}", fact)

            steps.append(f"\nLearned: {knowledge['summary']}")
            steps.append(f"Confidence: {knowledge['confidence']}")

            if knowledge["facts"]:
                steps.append("Key facts:")
                for f in knowledge["facts"][:6]:
                    steps.append(f"  • {f}")

            if knowledge["is_procedural"] and len(knowledge["steps"]) >= 2:
                from parrrot.core.learner import _generate_skill_code
                code = await _generate_skill_code(knowledge)
                path = save_skill_file(question, code)
                steps.append(f"  Skill saved: {path}")

        except Exception as e:
            steps.append(f"(Knowledge extraction failed: {e} — response saved to memory anyway)")

    return "\n".join(steps)


async def _chatgpt_followup(message: str) -> str:
    """
    Send a follow-up message in the current ChatGPT conversation
    (does NOT open a new chat — continues the existing one).
    Waits for the response and returns it.
    """
    from parrrot.tools.browser_control import _focus_firefox

    steps: list[str] = []

    # Focus Firefox — ChatGPT should already be open
    focused = _focus_firefox(wait=0.5)
    if not focused:
        return "Firefox is not open. Use ask_chatgpt first to start a conversation."

    steps.append(f"Sending follow-up: {message[:80]}...")

    success = _type_into_chatgpt(message)
    if not success:
        return "Could not find ChatGPT input. Is the ChatGPT tab still open in Firefox?"

    time.sleep(0.4)
    _submit_chatgpt_message()
    steps.append("Waiting for response...")
    time.sleep(2.0)

    raw = _wait_for_response_complete(timeout=120, poll_interval=2.5, stable_checks=3)
    full = _ocr_full_page_text(scroll_attempts=4)
    response = _extract_chatgpt_response(full or raw)

    if not response:
        response = raw[:3000]

    steps.append(f"\n--- ChatGPT Response ---\n{response[:3000]}\n--- End ---")
    return "\n".join(steps)


async def _chatgpt_scroll_and_read() -> str:
    """
    Scroll the current ChatGPT page and read the full visible conversation.
    Useful when a long response got cut off.
    """
    from parrrot.tools.browser_control import _focus_firefox
    from parrrot.tools.screen import _ocr_screen

    _focus_firefox(wait=0.4)
    time.sleep(0.3)

    full_text = _ocr_full_page_text(scroll_attempts=8)
    if not full_text:
        return "Could not read ChatGPT page. Make sure Firefox has ChatGPT open."

    response = _extract_chatgpt_response(full_text)
    return f"Full ChatGPT conversation text:\n\n{response[:5000]}"


def _chatgpt_new_chat() -> str:
    """Start a new ChatGPT conversation (opens a fresh chatgpt.com tab)."""
    from parrrot.tools.browser_control import _open_new_tab
    result = _open_new_tab("https://chatgpt.com", wait=3.5)
    return f"{result}\nNew ChatGPT conversation started."


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

registry.register(
    "chatgpt_open",
    "Open ChatGPT (chatgpt.com) in Firefox",
    {},
)(_chatgpt_open)

registry.register(
    "ask_chatgpt",
    "Ask ChatGPT a question via Firefox: opens chatgpt.com, types the question, "
    "waits for the full response, scrolls to capture it all, and saves the knowledge to memory. "
    "Use this when you want to learn something from ChatGPT or verify information.",
    {
        "question": "the question to ask ChatGPT",
        "learn": "save the response to memory and generate a skill if procedural (default true)",
        "scroll_pages": "how many scroll steps to collect the full answer (default 5)",
    },
)(_ask_chatgpt)

registry.register(
    "chatgpt_followup",
    "Send a follow-up message in the current ChatGPT conversation without opening a new chat. "
    "Use this to ask doubts, get clarifications, or continue a ChatGPT conversation.",
    {
        "message": "the follow-up message or question to send",
    },
)(_chatgpt_followup)

registry.register(
    "chatgpt_scroll_read",
    "Scroll the current ChatGPT page and read the full conversation text (for long responses)",
    {},
)(_chatgpt_scroll_and_read)

registry.register(
    "chatgpt_new_chat",
    "Start a new ChatGPT conversation (opens a fresh tab)",
    {},
)(_chatgpt_new_chat)
