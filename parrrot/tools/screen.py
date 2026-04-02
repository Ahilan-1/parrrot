"""
Parrrot — Screenshot, OCR, screen vision, and smart element-finding tools.
Uses mss (capture) + pytesseract (OCR) + vision LLM (understanding).
No Playwright. No external browser driver. Pure screen watching.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from parrrot.tools.registry import registry

_MSS_MSG = "Screen capture requires mss + Pillow. Install: pip install mss Pillow"
_OCR_MSG = (
    "Tesseract OCR not found.\n"
    "Install:\n"
    "  pip install pytesseract Pillow\n"
    "  Windows: https://github.com/UB-Mannheim/tesseract/wiki  (run installer, default path is fine)\n"
    "  Linux:   sudo apt install tesseract-ocr\n"
    "  macOS:   brew install tesseract"
)


def _configure_tesseract() -> bool:
    """
    Auto-detect and configure the Tesseract executable path.
    Returns True if Tesseract is available.
    """
    try:
        import pytesseract
    except ImportError:
        return False

    import platform, os, shutil

    # Already configured or on PATH
    if shutil.which("tesseract"):
        return True

    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("APPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Tesseract-OCR", "tesseract.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return True
        return False

    return True  # On Linux/macOS Tesseract should be on PATH


# Run once at import time
_TESSERACT_OK = _configure_tesseract()


# ---------------------------------------------------------------------------
# Core capture
# ---------------------------------------------------------------------------

def capture_screen(region: Optional[dict] = None, save_path: Optional[str] = None) -> str:
    """
    Capture the full screen (or a region) and save as PNG.
    region = {"top": y, "left": x, "width": w, "height": h}
    Returns the path to the saved PNG, or an error string.
    """
    try:
        import mss
        import mss.tools
    except ImportError:
        return _MSS_MSG

    if save_path is None:
        save_path = tempfile.mktemp(suffix=".png")

    with mss.mss() as sct:
        monitor = region if region else sct.monitors[1]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=save_path)

    return save_path


def capture_screen_image():
    """Return raw PIL Image of screen (for vision calls). Returns None on failure."""
    try:
        import mss
        from PIL import Image as PILImage
        import io
    except ImportError:
        return None

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = sct.grab(monitor)
        # Convert mss screenshot to PIL Image
        return PILImage.frombytes("RGB", img.size, img.rgb)


def screen_dimensions() -> tuple[int, int]:
    """Return (width, height) of the primary monitor."""
    try:
        import mss
        with mss.mss() as sct:
            m = sct.monitors[1]
            return m["width"], m["height"]
    except Exception:
        try:
            import pyautogui
            return pyautogui.size()
        except Exception:
            return (1920, 1080)


# ---------------------------------------------------------------------------
# Public tool: take_screenshot
# ---------------------------------------------------------------------------

def _take_screenshot(region: Optional[dict] = None, save_path: Optional[str] = None) -> str:
    path = capture_screen(region, save_path)
    if path.startswith("Screen capture"):
        return path  # error message
    return f"Screenshot saved: {path}"


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _read_screen_text(region: Optional[dict] = None) -> str:
    """Read all text on the screen using Tesseract OCR (primary method)."""
    if not _TESSERACT_OK:
        return _OCR_MSG
    text = _ocr_screen(region)
    return text if text else "(no text detected — screen may be blank or Tesseract config issue)"


# ---------------------------------------------------------------------------
# OCR fallback helper
# ---------------------------------------------------------------------------

def _ocr_screen(region: Optional[dict] = None) -> str:
    """
    PRIMARY screen reader — Tesseract OCR on the full screen or a region.
    Returns extracted text, or empty string on failure.
    """
    if not _TESSERACT_OK:
        return ""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    path = capture_screen(region)
    if path.startswith("Screen capture"):
        return ""
    try:
        img = Image.open(path)
        config = "--psm 6 --oem 3"
        return pytesseract.image_to_string(img, config=config).strip()
    except Exception:
        return ""


def _ocr_region(left: int, top: int, width: int, height: int) -> str:
    """OCR a specific pixel region of the screen."""
    return _ocr_screen({"left": left, "top": top, "width": width, "height": height})


def _is_vision_error(exc: Exception) -> bool:
    """Return True if the exception is a known 'model doesn't support images' error."""
    msg = str(exc).lower()
    return (
        "does not support vision" in msg
        or "400" in msg
        or "bad request" in msg
        or "images" in msg
    )


# ---------------------------------------------------------------------------
# Vision model: ask the LLM about the screen
# ---------------------------------------------------------------------------

async def _ask_screen(question: str) -> str:
    """
    Take a screenshot and ask the vision LLM a question about it.
    Falls back to OCR + text-only LLM if the model doesn't support images.
    """
    path = capture_screen()
    if path.startswith("Screen capture"):
        return path

    # Try vision model first
    try:
        from parrrot.core.router import Router
        from parrrot.models.base import CompletionRequest, Message

        img_bytes = Path(path).read_bytes()
        router = Router()
        request = CompletionRequest(
            messages=[Message(role="user", content=question)],
            images=[img_bytes],
            max_tokens=1500,
        )
        response = await router.complete(request)
        return response.content
    except Exception as e:
        if not _is_vision_error(e):
            return f"Screen query failed: {e}"
        # Vision not supported — fall back to OCR
        pass

    # OCR fallback: extract text and ask the text-only model about it
    ocr_text = _ocr_screen()
    if not ocr_text:
        return (
            "Could not read screen content.\n"
            "For full screen vision, install a vision model:\n"
            "  ollama pull llava\n"
            "Then set it in ~/.parrrot/config.toml: local_model = 'llava'\n\n"
            "Alternatively, install pytesseract for OCR:\n"
            "  pip install pytesseract Pillow\n"
            "  Download Tesseract: https://github.com/UB-Mannheim/tesseract/wiki"
        )

    try:
        from parrrot.core.router import Router
        from parrrot.models.base import CompletionRequest, Message

        router = Router()
        prompt = (
            f"The following is text extracted from a computer screen via OCR:\n\n"
            f"---\n{ocr_text[:3000]}\n---\n\n"
            f"Based on this screen text, answer: {question}"
        )
        request = CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            max_tokens=1500,
        )
        response = await router.complete(request)
        return f"[OCR fallback — install llava for full vision]\n\n{response.content}"
    except Exception as e:
        return f"OCR fallback also failed: {e}"


async def _describe_screen() -> str:
    """Take a screenshot and describe everything visible on screen."""
    return await _ask_screen(
        "Describe in detail everything you can see on this computer screen. "
        "Include: what application is open, what content is visible, "
        "any buttons or UI elements, and the general layout."
    )


# ---------------------------------------------------------------------------
# Smart element finding — OCR-first, vision optional
# ---------------------------------------------------------------------------

def _ocr_find_text_coords(description: str, img_path: str) -> tuple[int, int] | None:
    """
    Use Tesseract image_to_data() to find the pixel coordinates of text
    matching a natural-language description. Works with ANY LLM — no vision needed.

    Strategy:
      1. Strip UI noise words from description → extract keywords
      2. Try multi-word phrase match across consecutive OCR words
      3. Try single-word best-match (exact contains → fuzzy ratio)
    Returns center (x, y) of best match, or None.
    """
    if not _TESSERACT_OK:
        return None
    try:
        import pytesseract
        from pytesseract import Output
        from PIL import Image
        import difflib
    except ImportError:
        return None

    try:
        img = Image.open(img_path)
        data = pytesseract.image_to_data(img, output_type=Output.DICT, config="--psm 6 --oem 3")
    except Exception:
        return None

    # Normalise description: lowercase, remove UI noise words
    desc_clean = description.lower()
    noise_words = [
        "button", "field", "the ", "click ", " on ", " in ", "link", "icon",
        "tab", "checkbox", "dropdown", "menu item", "bar", "box", "area",
        "label", "text", "input", "option", "item",
    ]
    for nw in noise_words:
        desc_clean = desc_clean.replace(nw, " ")
    desc_words = [w.strip(",:;()") for w in desc_clean.split() if len(w.strip(",:;()")) > 1]
    if not desc_words:
        # Fallback: use original words
        desc_words = [w for w in description.lower().split() if len(w) > 1]

    if not desc_words:
        return None

    # Build structured word list from OCR data
    n = len(data["text"])
    words: list[dict] = []
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            conf = 0
        if txt and conf > 15:
            left = data["left"][i]
            top = data["top"][i]
            w_px = data["width"][i]
            h_px = data["height"][i]
            words.append({
                "text": txt,
                "lower": txt.lower(),
                "cx": left + w_px // 2,
                "cy": top + h_px // 2,
                "left": left,
                "top": top,
                "right": left + w_px,
                "bottom": top + h_px,
            })

    if not words:
        return None

    lower_texts = [w["lower"] for w in words]

    # Strategy 1: multi-word phrase match in consecutive OCR words
    if len(desc_words) >= 2:
        phrase = " ".join(desc_words)
        for span in range(len(desc_words), 1, -1):
            for i in range(len(words) - span + 1):
                window_words = words[i : i + span]
                window_text = " ".join(w["lower"] for w in window_words)
                ratio = __import__("difflib").SequenceMatcher(None, phrase, window_text).ratio()
                if ratio >= 0.75 or phrase in window_text:
                    # Return center of the entire matched region
                    lft = min(w["left"] for w in window_words)
                    top = min(w["top"] for w in window_words)
                    rgt = max(w["right"] for w in window_words)
                    btm = max(w["bottom"] for w in window_words)
                    return (lft + rgt) // 2, (top + btm) // 2

    # Strategy 2: best single-word match for any keyword in description
    import difflib as _dl
    best_score = 0.0
    best_word: dict | None = None

    for dw in desc_words:
        for i, lt in enumerate(lower_texts):
            # Exact substring
            if dw in lt:
                score = len(dw) / max(len(lt), 1) + 0.3  # bonus for exact
                if score > best_score:
                    best_score = score
                    best_word = words[i]
            elif lt in dw and len(lt) >= 3:
                score = len(lt) / max(len(dw), 1)
                if score > best_score:
                    best_score = score
                    best_word = words[i]
            # Fuzzy ratio
            ratio = _dl.SequenceMatcher(None, dw, lt).ratio()
            if ratio > best_score and ratio >= 0.72:
                best_score = ratio
                best_word = words[i]

    if best_word and best_score >= 0.6:
        return best_word["cx"], best_word["cy"]

    return None


async def find_element_coords(description: str) -> tuple[int, int] | None:
    """
    Find a UI element on screen by description and return (x, y) pixel coordinates.

    Works in two modes:
      1. OCR-first (Tesseract): reads all text + positions → fuzzy-matches description.
         Works with ANY LLM including text-only models like llama3.2, mistral, etc.
      2. Vision model fallback: if OCR finds nothing, tries the vision LLM.

    Returns None if the element cannot be found.
    Never raises — all errors are handled internally.
    """
    path = capture_screen()
    if path.startswith("Screen capture"):
        return None

    # --- Primary: OCR-based element finding (no vision model required) ---
    ocr_coords = _ocr_find_text_coords(description, path)
    if ocr_coords:
        return ocr_coords

    # --- Secondary: vision LLM (only if available) ---
    w, h = screen_dimensions()
    prompt = (
        f"This is a screenshot of a computer screen ({w}x{h} pixels).\n"
        f"I need to click on: {description}\n\n"
        f"If you can see it, reply with ONLY the pixel coordinates in this exact format:\n"
        f"COORDS: x,y\n\n"
        f"If you cannot find it, reply with:\n"
        f"NOT_FOUND\n\n"
        f"Do not include any other text."
    )

    try:
        from parrrot.core.router import Router
        from parrrot.models.base import CompletionRequest, Message

        img_bytes = Path(path).read_bytes()
        router = Router()
        request = CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            images=[img_bytes],
            max_tokens=50,
            temperature=0.1,
        )
        response = await router.complete(request)
        text = response.content.strip()

        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"COORDS:\s*(\d+)\s*,\s*(\d+)", text, re.IGNORECASE)
        if not match:
            match = re.search(r"(\d{2,4})\s*,\s*(\d{2,4})", text)
        if match:
            return int(match.group(1)), int(match.group(2))

        return None
    except Exception:
        # Vision not available or failed — OCR already tried, nothing found
        return None


async def _find_on_screen(description: str) -> str:
    """
    Find a UI element on screen by description.
    Returns the coordinates or a 'not found' message.
    """
    coords = await find_element_coords(description)
    if coords:
        return f"Found '{description}' at coordinates: x={coords[0]}, y={coords[1]}"
    return f"Could not find '{description}' on screen. Try taking a screenshot first to confirm it's visible."


# ---------------------------------------------------------------------------
# Read text from a specific region using vision
# ---------------------------------------------------------------------------

async def _read_screen_region_vision(region_description: str) -> str:
    """
    Ask the vision LLM to read and return all text in a specific area of the screen.
    region_description: plain English, e.g. "the email list on the left side"
    """
    return await _ask_screen(
        f"Please read and return ALL the text you can see in: {region_description}. "
        f"Return the text exactly as it appears, preserving structure."
    )


# ---------------------------------------------------------------------------
# Watch screen
# ---------------------------------------------------------------------------

def _watch_screen(duration: int = 10, interval: int = 2) -> str:
    """Take periodic screenshots over a duration. Returns list of saved paths."""
    paths: list[str] = []
    end = time.time() + duration
    while time.time() < end:
        path = capture_screen()
        if not path.startswith("Screen capture"):
            paths.append(path)
        time.sleep(interval)
    return f"Captured {len(paths)} screenshots:\n" + "\n".join(paths)


async def _wait_for_element(description: str, timeout: int = 15, interval: float = 1.5) -> str:
    """
    Poll the screen until a described element appears, or until timeout.
    Useful for waiting for page loads, popups, etc.
    """
    end = time.time() + timeout
    attempts = 0
    while time.time() < end:
        coords = await find_element_coords(description)
        attempts += 1
        if coords:
            return f"Found '{description}' after {attempts} check(s) at x={coords[0]}, y={coords[1]}"
        time.sleep(interval)
    return f"'{description}' did not appear within {timeout} seconds."


# ---------------------------------------------------------------------------
# Register all tools
# ---------------------------------------------------------------------------

registry.register(
    "take_screenshot",
    "Take a screenshot of the screen or a region. Returns the file path.",
    {
        "region": "optional {'top': y, 'left': x, 'width': w, 'height': h}",
        "save_path": "optional path to save the PNG",
    },
)(_take_screenshot)

registry.register(
    "read_screen_text",
    "Use OCR (pytesseract) to extract text from the screen or a region",
    {"region": "optional screen region dict"},
)(_read_screen_text)

registry.register(
    "describe_screen",
    "Take a screenshot and describe everything visible using the vision AI model",
    {},
)(_describe_screen)

registry.register(
    "ask_screen",
    "Take a screenshot and ask the vision AI a specific question about what it sees",
    {"question": "what to ask about the screen, e.g. 'Is Gmail open? What emails are visible?'"},
)(_ask_screen)

registry.register(
    "find_on_screen",
    "Find a UI element on screen by description and return its pixel coordinates",
    {"description": "describe what to find, e.g. 'Compose button', 'search bar', 'Send button'"},
)(_find_on_screen)

registry.register(
    "read_screen_region_vision",
    "Ask the vision AI to read all text in a specific area of the screen",
    {"region_description": "plain English description of the area, e.g. 'the email subject lines'"},
)(_read_screen_region_vision)

registry.register(
    "watch_screen",
    "Take periodic screenshots over a duration to monitor screen changes",
    {
        "duration": "total seconds to watch (default 10)",
        "interval": "seconds between screenshots (default 2)",
    },
)(_watch_screen)

registry.register(
    "wait_for_element",
    "Wait until a UI element appears on screen (polls until found or timeout)",
    {
        "description": "element to wait for, e.g. 'inbox loaded', 'Compose button'",
        "timeout": "max seconds to wait (default 15)",
        "interval": "seconds between checks (default 1.5)",
    },
)(_wait_for_element)
