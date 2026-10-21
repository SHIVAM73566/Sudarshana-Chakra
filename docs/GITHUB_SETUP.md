# GitHub Optimization Guide

Follow these steps once to maximize Sudarshana Chakra's ranking in **GitHub
search**, **Google**, and social previews. These are the levers that actually
move discovery.

---

## 1. About Section (repo home, top-right **⚙ About**)

### Description (paste exactly — ~150 chars)
```
The free, open, JARVIS-style AI assistant for Windows — voice, vision, and autonomous desktop control. Self-evolving, local-first personal AI agent.
```

### Website
```
https://github.com/SHIVAM73566/Sudarshana-Chakra#-quick-install-one-command
```

### Topics (⚙ About → Topics) — paste one per line
These are the **#1 in-GitHub discovery lever**. GitHub shows topic pages and
search surfaces repos by topics.
```
ai-assistant
jarvis
windows-desktop
ai-agent
desktop-automation
voice-assistant
computer-vision
pyqt6
python
autonomous-agents
gemini
llm
model-context-protocol
mcp
self-evolving
self-healing
ai-tools
productivity
local-first
open-source
artificial-intelligence
automation
```

> GitHub allows up to 20 topics — trim to your best 20 if needed. Prioritize:
> `ai-assistant`, `jarvis`, `desktop-automation`, `ai-agent`, `computer-vision`,
> `pyqt6`, `autonomous-agents`, `model-context-protocol`, `self-evolving`,
> `local-first`.

### Other About toggles
- ✅ **Releases** — off until you publish a release (then on).
- ✅ **Packages** — off unless you publish packages.
- ✅ **Environments** — off.
- ☐ **Include in the home page** — on.

---

## 2. Social Preview Image (Settings → General → Social preview)

Upload `assets/og_preview_sudarshana_chakra.png` (1200×630). This is what shows
when the repo is linked on **X, LinkedIn, Slack, Discord, WhatsApp** — huge for
click-through.

1. Repo → **Settings** → scroll to **Social preview**
2. **Upload an image** → select `assets/og_preview_sudarshana_chakra.png`
3. Done.

---

## 3. Repository Features (Settings → General → Features)

Enable for a richer, more shareable repo:
- ✅ **Wikis** (optional — your `docs/` already covers most)
- ✅ **Issues**
- ✅ **Discussions** ← **important**: enables the community link in your issue
  config and gives a place for Q&A (good for engagement signals)
- ✅ **Projects** (optional)
- ✅ **Sponsorships** (if you enable GitHub Sponsors)

---

## 4. Repository Name & Identifier

- Keep `Sudarshana-Chakra` — clear and searchable.
- Add a **short name** if you publish packages (e.g. `sudarshana-chakra`).

---

## 5. Commit & Content Cadence (algorithm-friendly)

GitHub surfaces actively maintained repos. To build momentum:
- Commit **regularly** (a few times a week) — real changes, not noise.
- Publish a **Release** with notes (your `CHANGELOG.md` is ready to convert).
- The CI badge (`actions/workflows/ci.yml`) should stay **green** — it signals health.
- Keep **Issues/Discussions** responsive — activity feeds discovery.

---

## 6. README ranking factors (already implemented)

GitHub search indexes README text. To rank:
- ✅ Keyword-rich intro + tagline (done)
- ✅ Table of Contents + navigation bar (done)
- ✅ Screenshots/GIF gallery (add your GIFs via [`DEMO.md`](../DEMO.md))
- ✅ Badges (CI, stars, activity) — done
- ✅ Backlinks from Reddit/HN/blogs point Google's crawler at the repo

---

## 7. Enable Discussions (extra detail)

Settings → General → Features → **Discussions** ✅ → then create categories:
*Announcements, Q&A, Show and tell, Ideas*.

---

## 8. Pin the repo

On your GitHub profile → **Customize pins** → pin **Sudarshana-Chakra** so every
profile visitor sees it first.

---

## 9. Release creation (do this for ranking + credibility)

```powershell
git tag -a v1.0.0 -m "Sudarshana Chakra v1.0.0"
git push origin v1.0.0
```
Then on GitHub → **Releases → Draft a new release** → choose tag `v1.0.0`, paste
the v1.0.0 section from `CHANGELOG.md`, and attach
`Sudarshana_Chakra_AI_v1.0_COMMERCIAL.zip`.

---

## 10. Checklist

- [ ] About description set
- [ ] 20 Topics added
- [ ] Social preview image uploaded
- [ ] Discussions enabled
- [ ] Repo pinned on profile
- [ ] v1.0.0 Release published (with ZIP)
- [ ] Demo GIFs added to README (see `DEMO.md`)
- [ ] Launch posts shared (see `launch/`)

---

> **Reality check:** GitHub optimization makes you *discoverable* and *converts*
> visitors — but trends are earned by **real** stars from **real** traffic. Drive
> traffic with the `launch/` copy and demo GIFs; the optimization above ensures
> that traffic turns into stars and search rank.
