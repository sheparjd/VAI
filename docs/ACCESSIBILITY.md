# Voiceprint AI (VAI) — Accessibility & Inclusive Design Guidelines

## 1. Core Accessibility Philosophy

In **Voiceprint AI (VAI)**, accessibility is not a post-launch feature—it is the core architectural reason the project exists. Disabled workers often possess deep expertise and sharp judgment while facing physical fatigue, speech differences, sensory sensitivities, or barriers to real-time typing.

Every contribution to `local_node/` and `web_platform/` must reduce physical and cognitive friction rather than demanding speed or continuous presence.

---

## 2. Five Non-Negotiable Engineering Principles

### 1. Asynchronous Pacing Over Real-Time Pressure
* **No Countdown Timers:** Never add expiring session timers or rapid-response deadlines to training interviews or task approval screens.
* **Save-As-You-Go:** Scripts like `local_node/interviewer.py` must save each answer immediately so a user can pause, quit, or resume across days without losing progress.
* **Configurable Workload Caps:** Respect `max_active_tasks` and `review_window_hours` in `voiceprint.json` so the local node never floods the worker's review queue.

### 2. Multi-Modal Input Compatibility
* **Voice, Switch, and Keyboard First:** All local CLI tools and web interfaces must be 100% operable via keyboard navigation (`Tab`, `Enter`, `Space`), switch-access devices, and OS-level dictation (such as Windows Voice Access, macOS Voice Control, or Whisper).
* **No Complex Gestures:** Never require drag-and-drop, hover-only menus, or precision mouse movements to complete core workflows.

### 3. Screen-Reader-First Web UI (`web_platform/`)
* **Semantic HTML:** Always use native `<header>`, `<nav>`, `<main>`, `<form>`, `<label for="...">`, and `<button>` elements rather than clickable `<div>` tags.
* **Clear Status Announcements:** Use explicit text badges (`OPEN`, `DRAFT_READY`, `APPROVED`, `DECLINED`) rather than relying solely on color to communicate task state.
* **High Contrast & Clean Typography:** Maintain high contrast ratios (at least 4.5:1 for body text), generous line spacing, and clean sans-serif fonts without distracting animations or auto-playing media.

### 4. Low-Cognitive-Load Interactions
* **One Question at a Time:** Training interviews must present a single, focused question per step rather than overwhelming multi-part forms.
* **Plain, Direct Language:** Keep UI labels, error messages, and documentation concise and free of unnecessary jargon.
* **One-Click Approval Gates:** Reviewing an AI draft should require minimal effort—ideally reviewing a clear summary and triggering a single **Approve & Deliver** action.

### 5. Privacy-Preserving Profiles
* **Never Require Medical Disclosure:** Public VAI profiles (`WorkerProfile`) and local configurations (`voiceprint.json`) must focus strictly on **skills, communication style, and operational boundaries**—never requiring users to disclose diagnoses, medical history, or disability classifications to participate.

---

## 3. Contributor Checklist Before Submitting a Pull Request

Before opening a PR that touches UI templates, CLI prompts, or agent workflows, verify the following:

- [ ] Can the entire workflow be completed using **only a keyboard** (no mouse required)?
- [ ] Does every form `<input>` and `<textarea>` have a matching `<label>`?
- [ ] Can the user **pause or exit** a multi-step process at any point without losing saved data?
- [ ] Are status changes communicated with **clear text** in addition to color badges?
- [ ] Does the feature avoid forcing real-time responses or strict time limits?

---

## 4. Planned Accessibility Enhancements (Open for Contributors)

* **Local Speech-to-Text & Text-to-Speech (`local_node/`):** Integrate offline **Whisper** (input) and **Piper** (audio readout) into `interviewer.py` and `worker_agent.py` for hands-free training and draft review.
* **ARIA Live Regions (`web_platform/`):** Add `aria-live="polite"` notifications when background tasks transition from `OPEN` to `DRAFT_READY`.
* **High-Contrast & Dyslexia-Friendly Theme Toggle:** Add user-selectable display presets in the Worker Control Dashboard.
