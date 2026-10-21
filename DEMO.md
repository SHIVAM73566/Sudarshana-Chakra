# Demo GIF & Recording Guide

High-impact demos are the single biggest driver of stars. A 20–30 second GIF at
the top of the README converts visitors into stargazers. This guide shows exactly
how to record, compress, and embed them.

---

## 1. What to record (pick 3–4)

| # | Demo | Why it converts | Target length |
| :--- | :--- | :--- | :--- |
| 1 | **Voice → action** — say *"create a project roadmap spreadsheet"*, watch Excel open and fill | Shows real autonomy, not chat | 20–25s |
| 2 | **Self-evolution** — ask for a task with no tool, watch it forge + load a new skill | The "wow" differentiator | 25–30s |
| 3 | **Browser automation** — *"find flights Mumbai→London"*, real logged-in browser drives itself | Visceral, easy to grasp | 20s |
| 4 | **Self-healing** — trigger an error, watch the HUD repair card fix it live | Builds trust | 15–20s |
| 5 | **Business vertical** — build + export an inventory sheet | Enterprise appeal | 20s |

---

## 2. Recording tools

### Option A — ScreenToGif (best for GIFs, Windows, free)
1. Download: https://www.screentogif.com/
2. Open → **Recorder** → set capture region to the app window (drag the frame).
3. Frame rate: **12–15 fps** is plenty (keeps file size low).
4. Click **Record**, perform the workflow, press **F7** to stop.
5. **Editor** → delete dead frames, trim start/end → **Save as** → **GIF**.
6. In the save dialog: reduce colors to **128–256**, enable **encoder optimizations**.

### Option B — OBS Studio (best for MP4/YouTube, then convert to GIF)
1. https://obsproject.com/ → add a **Window Capture** source.
2. Output: 1080p (or 1280×720), 30 fps, MP4.
3. Record the workflow → **File → Stop Recording**.
4. Convert to GIF (pick one):
   - `ffmpeg -i demo.mp4 -vf "fps=14,scale=960:-1:flags=lanczos" demo.gif`
   - Upload to https://ezgif.com/video-to-gif (set 12–15 fps, width 960).

### Option C — Windows built-in (quickest)
`Win + G` → Xbox Game Bar → **Capture** → record a clip → convert with ezgif.

---

## 3. Recording tips (make it look pro)

- **Clean your desktop first** — no personal files, close unrelated windows.
- Use a **dark wallpaper** so the app's glow pops.
- **Move deliberately** — pause on the moment of magic (the file opening, the tool firing).
- **Zoom into the action** if the region is small; 960–1280 px wide is ideal.
- Keep each GIF **under 5 MB** for fast README load (GitHub renders larger, but slow).
- Add a **caption overlay** (ScreenToGif editor → add text) like *"voice → executed"*.
- Loop cleanly: end on the result, not mid-animation.

---

## 4. Where to save

Put files in `assets/`:

```
assets/demo_voice.gif
assets/demo_self_evolution.gif
assets/demo_browser.gif
assets/demo_self_healing.gif
```

---

## 5. Embed in README

In `README.md`, find the **📸 Demo & Screenshots** section and replace the
commented block with:

```markdown
### 🎙️ Voice → Action
![Voice command demo](assets/demo_voice.gif)

### 🧬 Self-Evolution — forges a new tool on the fly
![Self-evolution demo](assets/demo_self_evolution.gif)

### 🌐 Browser automation with your real session
![Browser demo](assets/demo_browser.gif)
```

Or a side-by-side table:

```markdown
| Voice → Action | Self-Evolution |
| :---: | :---: |
| ![voice](assets/demo_voice.gif) | ![evolve](assets/demo_self_evolution.gif) |
```

> Tip: put the **strongest GIF in the first screen** of the README (right under
> the hero image) — most visitors decide in 5 seconds.

---

## 6. Also reuse the GIFs for launch posts

The same GIFs power your Reddit / X / Product Hunt posts — they outperform
link-only posts by a wide margin. See [`launch/`](launch/) for ready copy.
