# Developer Notes

## Browser Compatibility

**Chrome does not work reliably with Parrrot.** The CDP (Chrome DevTools Protocol) automation is built and tested against **Chromium**, not Google Chrome.

If you do not have Chromium installed, please download it:
- **Windows / Mac / Linux:** https://www.chromium.org/getting-the-chromium-source-code/ — or search "download Chromium browser" and grab a build from https://chromium.woolyss.com/

> Chrome and Chromium look identical but Chrome includes proprietary layers that break CDP automation. Chromium is the open-source version and is what Parrrot expects.

The agent will still try to complete your task without a working browser — it will take a longer path and use fallback tools. That is normal. But for best results, use Chromium.

**Recommended browsers (in order):**
1. **Chromium** — best compatibility, what Parrrot is built for
2. **Microsoft Edge** — works well, built into Windows
3. **Firefox** — works for most tasks

---

If the agent stumbles, do not interrupt it. Let it try alternative methods and it will get there.

> tl;dr — Chrome doesn't work, Chromium does. Download Chromium if you don't have it. Edge and Firefox also work.
