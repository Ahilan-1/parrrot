"""
Parrrot — Self-learning engine.
When Parrrot doesn't know something it:
  1. Opens a new tab in Firefox (never Chromium)
  2. Searches Google / DuckDuckGo
  3. Extracts result URLs via httpx (clean, reliable — OCR URLs are unreliable)
  4. Opens each result in Firefox new tabs, OCRs the page text
  5. Synthesises facts + steps with the LLM
  6. Saves facts to memory
  7. Generates a Python skill file if the knowledge is a procedure
The user watches Firefox browsing in real time.
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from html.parser import HTMLParser
from typing import Optional

SKILLS_DIR = Path.home() / ".parrrot" / "skills"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name.lower())
    name = re.sub(r"[\s-]+", "_", name).strip("_")
    return name[:60] or "learned_skill"


async def _llm_ask(prompt: str, router=None, max_tokens: int = 2500) -> str:
    if router is None:
        from parrrot.core.router import Router
        router = Router()
    from parrrot.models.base import CompletionRequest, Message
    req = CompletionRequest(
        messages=[Message(role="user", content=prompt)],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    resp = await router.complete(req)
    return resp.content.strip()


# ---------------------------------------------------------------------------
# URL extraction via httpx (reliable — no OCR guesswork)
# ---------------------------------------------------------------------------

class _LinkParser(HTMLParser):
    """Pull href links out of an HTML page."""
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list):
        if tag == "a":
            for name, val in attrs:
                if name == "href" and val:
                    self.links.append(val)


def _extract_search_result_urls(query: str, engine: str = "google", max_results: int = 5) -> list[str]:
    """
    Fetch a Google/DDG search results page with httpx and extract real URLs.
    Falls back to DuckDuckGo HTML (more scraper-friendly).
    Returns a list of clean result URLs.
    """
    try:
        import httpx
    except ImportError:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
            "Gecko/20100101 Firefox/124.0"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    urls_found: list[str] = []

    # Try DuckDuckGo HTML first — no JS required, clean result links
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        resp = httpx.get(ddg_url, headers=headers, timeout=10, follow_redirects=True)
        parser = _LinkParser()
        parser.feed(resp.text)
        for link in parser.links:
            if link.startswith("//duckduckgo.com/l/?uddg="):
                # DDG redirect URL — extract the real URL
                import urllib.parse
                parsed = urllib.parse.urlparse("https:" + link)
                params = urllib.parse.parse_qs(parsed.query)
                real = params.get("uddg", [""])[0]
                if real and real.startswith("http"):
                    urls_found.append(urllib.parse.unquote(real))
            elif link.startswith("http") and "duckduckgo.com" not in link:
                urls_found.append(link)
    except Exception:
        pass

    if not urls_found:
        # Fallback: try Google
        try:
            g_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=en"
            resp = httpx.get(g_url, headers=headers, timeout=10, follow_redirects=True)
            # Google wraps result URLs — extract from /url?q= patterns
            raw_urls = re.findall(r'/url\?q=(https?://[^&"]+)', resp.text)
            for u in raw_urls:
                import urllib.parse
                urls_found.append(urllib.parse.unquote(u))
        except Exception:
            pass

    # Clean and filter
    skip = {
        "google.com", "duckduckgo.com", "bing.com", "youtube.com",
        "facebook.com", "twitter.com", "instagram.com", "pinterest.com",
        "amazon.com", "ebay.com",
    }
    clean: list[str] = []
    seen: set[str] = set()
    for url in urls_found:
        url = url.rstrip("&").split("&")[0]  # strip tracking params
        if not url.startswith("http"):
            continue
        # Check not a blocked domain
        try:
            import urllib.parse
            domain = urllib.parse.urlparse(url).netloc.lower()
            if any(s in domain for s in skip):
                continue
        except Exception:
            pass
        if url not in seen:
            seen.add(url)
            clean.append(url)
        if len(clean) >= max_results:
            break

    return clean


def _fetch_page_text(url: str, max_chars: int = 5000) -> str:
    """
    Fetch a URL with httpx and return clean readable text (strips HTML tags).
    Used as a supplement to OCR — gets the article text even if OCR is patchy.
    """
    try:
        import httpx
    except ImportError:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
            "Gecko/20100101 Firefox/124.0"
        )
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=12, follow_redirects=True)
        html = resp.text

        # Strip scripts and styles
        html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Strip all remaining tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Main research function
# ---------------------------------------------------------------------------

async def _research_with_firefox(topic: str, n_pages: int = 4) -> str:
    """
    1. Open Firefox to Google/DDG search for topic
    2. Extract real result URLs via httpx (reliable)
    3. Open each result in a Firefox new tab (user can see it happening)
    4. OCR the page AND fetch page text via httpx for max coverage
    5. Return all collected text
    """
    from parrrot.tools.browser_control import _open_new_tab, _navigate_to, _focus_firefox
    from parrrot.tools.screen import _ocr_screen, _configure_tesseract

    _configure_tesseract()

    query = topic if topic.lower().startswith("how") else f"how to {topic}"
    all_text: list[str] = []

    # Step 1: Open search in Firefox new tab
    search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
    await _open_new_tab(search_url, wait=3.0)

    # OCR the search results page while user can see it
    ocr_text = _ocr_screen()
    if ocr_text:
        all_text.append(f"=== DuckDuckGo search results ===\n{ocr_text[:2000]}")

    # Step 2: Extract clean URLs via httpx (much more reliable than OCR URL parsing)
    result_urls = _extract_search_result_urls(query, max_results=n_pages)

    if not result_urls:
        # Couldn't get URLs via httpx — use what we have from OCR
        return "\n\n".join(all_text) if all_text else f"No results found for '{topic}'"

    # Step 3: For each URL — open in Firefox new tab AND fetch text via httpx
    pages_done = 0
    for url in result_urls[:n_pages]:
        # Show Firefox browsing the page (user sees it)
        await _open_new_tab(url, wait=2.5)

        # OCR the rendered page
        ocr_page = _ocr_screen()

        # Also fetch clean text via httpx (covers what OCR misses)
        http_text = _fetch_page_text(url, max_chars=4000)

        # Combine — prefer httpx text as it's cleaner, supplement with OCR
        if http_text and len(http_text) > 200:
            combined = http_text
            if ocr_page and len(ocr_page) > 100:
                combined += f"\n[OCR supplement]\n{ocr_page[:1000]}"
        elif ocr_page:
            combined = ocr_page[:4000]
        else:
            continue

        all_text.append(f"=== Source: {url[:80]} ===\n{combined[:4000]}")
        pages_done += 1

        # Small delay between pages so Firefox stays responsive
        time.sleep(0.8)

    if not all_text:
        return f"Searched for '{topic}' but could not read any page content."

    return "\n\n".join(all_text)


# ---------------------------------------------------------------------------
# Knowledge extraction
# ---------------------------------------------------------------------------

async def _extract_knowledge(topic: str, raw_text: str, router=None) -> dict:
    prompt = f"""You are a knowledge extraction AI. I researched "{topic}" and collected the following text from multiple web pages:

---
{raw_text[:7000]}
---

Extract structured knowledge. Reply in EXACTLY this format, no extra text:

SUMMARY: <1-2 sentence explanation of the topic>
IS_PROCEDURAL: <yes or no — is this a step-by-step task that can be automated?>
CONFIDENCE: <high / medium / low — how confident are you in the information?>
FACTS:
- <key fact>
- <key fact>
- <key fact>
STEPS:
1. <first step>
2. <second step>
(leave STEPS empty if IS_PROCEDURAL is no)
TOOLS_NEEDED: <comma-separated list of tools needed, e.g. browser, keyboard, mouse, file system>
"""
    response = await _llm_ask(prompt, router)
    return _parse_knowledge(response, topic)


def _parse_knowledge(text: str, topic: str) -> dict:
    result: dict = {
        "topic": topic,
        "summary": "",
        "facts": [],
        "steps": [],
        "is_procedural": False,
        "confidence": "medium",
        "tools_needed": [],
        "raw": text,
    }
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("SUMMARY:"):
            result["summary"] = line[8:].strip()
        elif line.startswith("IS_PROCEDURAL:"):
            result["is_procedural"] = "yes" in line.lower()
        elif line.startswith("CONFIDENCE:"):
            result["confidence"] = line[11:].strip().lower()
        elif line.startswith("TOOLS_NEEDED:"):
            result["tools_needed"] = [t.strip() for t in line[13:].split(",") if t.strip()]
        elif line.startswith("- ") and not result["steps"]:
            result["facts"].append(line[2:].strip())
        elif re.match(r"^\d+\.\s", line):
            result["steps"].append(re.sub(r"^\d+\.\s+", "", line))
    return result


# ---------------------------------------------------------------------------
# Skill code generation
# ---------------------------------------------------------------------------

async def _generate_skill_code(knowledge: dict, router=None) -> str:
    topic = knowledge["topic"]
    steps_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(knowledge["steps"]))
    tools_str = ", ".join(knowledge["tools_needed"]) or "browser, mouse, keyboard"

    prompt = f"""Write a Parrrot skill Python file. A skill is a Python module that the agent can execute.

Topic: {topic}
Summary: {knowledge["summary"]}
Tools needed: {tools_str}
Steps to automate:
{steps_str}

Write the skill as a complete Python file. Requirements:
1. SKILL_NAME = short descriptive name
2. SKILL_DESCRIPTION = what it does
3. SCHEDULE = None  (unless it should run on a schedule — then a cron string like "0 9 * * 1")
4. async def run(agent, memory, tools): — the main function

In the run() function, use agent.run_task() with a detailed natural-language description of the steps,
so the agent can execute them using its tools (visual_click, visual_type, navigate_to, etc.)

Example format:
```python
SKILL_NAME = "Example Skill"
SKILL_DESCRIPTION = "Does something useful"
SCHEDULE = None

async def run(agent, memory, tools):
    result = await agent.run_task(
        "Step 1: navigate to X. "
        "Step 2: click the Y button. "
        "Step 3: type Z into the field. "
    )
    if memory:
        memory.remember("last_example_result", result[:200])
    return result
```

Reply with ONLY the Python code (no markdown, no explanation).
"""
    response = await _llm_ask(prompt, router, max_tokens=1200)

    # Strip markdown code fences if present
    code = re.sub(r"^```python\s*", "", response, flags=re.MULTILINE)
    code = re.sub(r"^```\s*$", "", code, flags=re.MULTILINE)
    code = code.strip()

    # Validate it has the required parts
    if "SKILL_NAME" not in code or "async def run" not in code:
        safe = _sanitize_filename(topic)
        steps_nl = " ".join(knowledge["steps"])
        code = f'''SKILL_NAME = "{topic.title()}"
SKILL_DESCRIPTION = "{knowledge["summary"]}"
SCHEDULE = None

async def run(agent, memory, tools):
    """Auto-generated skill from web research."""
    result = await agent.run_task(
        "Follow these steps for {topic}: {steps_nl}"
    )
    if memory:
        memory.remember("last_{safe}", result[:200])
    return result
'''
    return code


# ---------------------------------------------------------------------------
# Save skill
# ---------------------------------------------------------------------------

def save_skill_file(skill_name: str, code: str) -> str:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(skill_name) + ".py"
    path = SKILLS_DIR / filename
    header = (
        f'"""\nParrrot Auto-Learned Skill: {skill_name}\n'
        f'Generated by Parrrot self-learning engine.\n"""\n\n'
    )
    path.write_text(header + code, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def learn_about(topic: str, save_skill: bool = True) -> str:
    """
    Full self-learning pipeline. Opens Firefox, researches topic,
    extracts knowledge, saves to memory, optionally generates skill file.
    """
    from parrrot.core import memory as mem

    output: list[str] = [f"🔍 Researching: '{topic}'"]

    # Research
    try:
        raw_text = await _research_with_firefox(topic, n_pages=4)
        output.append(f"  Read {raw_text.count('=== Source:')} page(s) of content")
    except Exception as e:
        raw_text = ""
        output.append(f"  Web research failed: {e} — working from model knowledge only")

    # Extract knowledge
    try:
        knowledge = await _extract_knowledge(topic, raw_text or f"Topic: {topic}")
    except Exception as e:
        return "\n".join(output) + f"\n\nKnowledge extraction failed: {e}"

    # Save to memory
    key = _sanitize_filename(topic)
    if knowledge["summary"]:
        mem.remember(f"learned_{key}", knowledge["summary"])
    for i, fact in enumerate(knowledge["facts"][:15]):
        mem.remember(f"fact_{key}_{i}", fact)

    # Format output
    output.append(f"\n📚 Summary: {knowledge['summary']}")
    output.append(f"   Confidence: {knowledge['confidence']}")

    if knowledge["facts"]:
        output.append("\nKey facts:")
        for f in knowledge["facts"][:8]:
            output.append(f"  • {f}")

    if knowledge["steps"]:
        output.append(f"\nProcedure ({len(knowledge['steps'])} steps):")
        for i, s in enumerate(knowledge["steps"][:10], 1):
            output.append(f"  {i}. {s}")

    # Generate skill
    if save_skill and knowledge["is_procedural"] and len(knowledge["steps"]) >= 2:
        output.append(f"\n⚙  Creating skill file...")
        try:
            code = await _generate_skill_code(knowledge)
            path = save_skill_file(topic, code)
            output.append(f"  ✓ Skill saved: {path}")
            output.append("    It will be available after: parrrot daemon (restart) or reload_skills")
        except Exception as e:
            output.append(f"  Skill generation failed: {e}")
    elif not knowledge["is_procedural"]:
        output.append(f"\n  (Knowledge saved to memory — not procedural, no skill generated)")

    output.append(f"\n✓ Done. I now know about '{topic}' and saved it to memory.")
    return "\n".join(output)
