"""Build the offline VAI questionnaire: one HTML file you can email to colleagues.

The page works by double-clicking it, with nothing to install. A strict Content
Security Policy stops it from making any network request, so answers can't be
sent anywhere. Answers are autosaved in the colleague's own browser, and
"Save my answers" downloads a .json file that they email back to you. Then:

    python local_node/import_answers.py vai-answers-alice.json --profile alice

Usage:  python local_node/make_questionnaire.py [--out PATH] [--sender "Your name"]
"""
import argparse
import json
from html import escape
from pathlib import Path

from questionnaire_spec import FORMAT, VERSION, build_spec

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "questionnaire" / "vai_questionnaire.html"

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VAI Questionnaire</title>
<style>
:root {
  --bg: #f7f7f5; --surface: #ffffff; --text: #1c1c1a; --muted: #5f5f5a; --line: #dcdcd6;
  --accent: #1f6f5c; --accent-text: #ffffff; --focus: #b45309; --ok: #1f6f5c; --chip: #ecece7;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161615; --surface: #1f1f1d; --text: #ecece8; --muted: #a3a39c; --line: #3a3a36;
    --accent: #5fbfa3; --accent-text: #0f1f1a; --focus: #f59e0b; --ok: #5fbfa3; --chip: #2a2a27;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 17px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 32px 16px 120px; }
h1 { font-size: 1.7rem; line-height: 1.25; margin: 0 0 12px; }
h2 { font-size: 1.25rem; margin: 0 0 4px; }
p { margin: 0 0 12px; }
.lede { color: var(--muted); }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 20px; margin: 20px 0; }
.privacy { border-left: 4px solid var(--accent); }
.privacy ul { margin: 8px 0 0; padding-left: 20px; }
fieldset { border: 0; margin: 0; padding: 0; }
legend { padding: 0; }
.tag { display: inline-block; font-size: .8rem; font-weight: 600; background: var(--chip); color: var(--muted);
  border-radius: 999px; padding: 1px 10px; margin-left: 8px; vertical-align: middle; }
.q { margin-top: 20px; }
.q label { display: block; font-weight: 600; margin-bottom: 6px; }
.q .num { color: var(--muted); font-weight: 400; margin-right: 4px; }
textarea, input[type=text] { width: 100%; font: inherit; color: var(--text); background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
textarea { min-height: 96px; resize: vertical; }
textarea:focus, input:focus, button:focus, summary:focus { outline: 3px solid var(--focus); outline-offset: 2px; }
details > summary { cursor: pointer; font-weight: 600; color: var(--accent); margin-top: 8px; }
.bar { position: fixed; left: 0; right: 0; bottom: 0; background: var(--surface); border-top: 1px solid var(--line); }
.bar-inner { max-width: 760px; margin: 0 auto; padding: 12px 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.progress { flex: 1 1 160px; color: var(--muted); font-size: .95rem; }
button { font: inherit; font-weight: 600; border-radius: 8px; padding: 10px 16px; cursor: pointer;
  border: 1px solid var(--line); background: var(--surface); color: var(--text); }
button.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
#status { min-height: 1.6em; color: var(--ok); font-weight: 600; }
.after { display: none; }
.after.show { display: block; }
.small { font-size: .9rem; color: var(--muted); }
</style>
</head>
<body>
<main>
  <h1>Help build a test VAI</h1>
  <p class="lede">VAI (Voiceprint AI) lets people train a personal AI representative from their own expertise.
  __SENDER_CAP__ is testing it with a few colleagues, and your answers would become one of the test VAIs.</p>

  <section class="panel privacy" aria-labelledby="privacy-h">
    <h2 id="privacy-h">Your answers stay with you until you send them</h2>
    <ul>
      <li>This page works offline and is blocked from sending anything over the internet.</li>
      <li>Your answers are saved as you type, in this browser only, so you can close it and come back.</li>
      <li>When you're done, <strong>Save my answers</strong> downloads a file. You choose whether to email it back.</li>
      <li>The test VAI is built on __SENDER_POSSESSIVE__ own computer. Only its public card appears on the test
        marketplace: name, headline, short summary, areas of expertise and the kinds of work it turns down.
        Your answers themselves stay on that computer.</li>
    </ul>
    <p class="small" style="margin-top:10px;">Skip any question. Leave out names, client details and anything confidential.
    The first part takes about 10 minutes; the optional deeper parts take 30–45 more.</p>
  </section>

  <form id="form" autocomplete="off" onsubmit="return false"></form>

  <section class="panel after" id="after" aria-live="polite">
    <h2>Saved</h2>
    <p>Email the downloaded file (<strong id="fname"></strong>) back to __SENDER__.</p>
    <p class="small">If the download didn't work, use <em>Copy answers</em> and paste them into the email instead.
    After sending, you can clear your answers from this browser.</p>
    <button type="button" id="clear">Clear my answers from this browser</button>
  </section>
</main>

<div class="bar" role="region" aria-label="Save">
  <div class="bar-inner">
    <div class="progress" id="progress" aria-live="polite"></div>
    <button type="button" id="copy">Copy answers</button>
    <button type="button" class="primary" id="save">Save my answers</button>
  </div>
  <div class="bar-inner" style="padding-top:0;"><div id="status" role="status"></div></div>
</div>

<script>
"use strict";
const SPEC = __SPEC__;
const FORMAT = __FORMAT__, VERSION = __VERSION__;
const STORE_KEY = "vai-questionnaire-v" + VERSION;
const form = document.getElementById("form");
let answers = {};
try { answers = JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch (e) { answers = {}; }

function area() { return (answers.area || "").trim() || "your area"; }
function fill(t) { return t.split("{area}").join(area()); }

function build() {
  let n = 0;
  for (const sec of SPEC) {
    const panel = document.createElement("section");
    panel.className = "panel";
    const fs = document.createElement("fieldset");
    const lg = document.createElement("legend");
    const h = document.createElement("h2");
    h.dataset.template = sec.title;
    h.textContent = fill(sec.title);
    if (sec.optional) { const t = document.createElement("span"); t.className = "tag"; t.textContent = "Optional"; h.appendChild(t); }
    lg.appendChild(h);
    fs.appendChild(lg);
    const intro = document.createElement("p");
    intro.className = "small"; intro.textContent = sec.intro;
    fs.appendChild(intro);
    let host = fs;
    if (sec.optional && sec.id !== "area") {
      const d = document.createElement("details");
      d.open = sec.questions.some(q => (answers[q.key] || "").trim());
      const s = document.createElement("summary");
      s.textContent = "Show these questions";
      d.appendChild(s); fs.appendChild(d); host = d;
    }
    for (const q of sec.questions) {
      n += 1;
      const wrap = document.createElement("div"); wrap.className = "q";
      const id = "q_" + q.key;
      const label = document.createElement("label"); label.htmlFor = id;
      const num = document.createElement("span"); num.className = "num"; num.textContent = n + ".";
      const txt = document.createElement("span"); txt.dataset.template = q.text; txt.textContent = fill(q.text);
      label.append(num, txt);
      const field = q.short ? document.createElement("input") : document.createElement("textarea");
      if (q.short) field.type = "text";
      field.id = id; field.name = q.key; field.value = answers[q.key] || "";
      field.maxLength = 8000;
      field.addEventListener("input", () => {
        answers[q.key] = field.value;
        persist();
        if (q.key === "area") refreshText();
        progress();
      });
      wrap.append(label, field); host.appendChild(wrap);
    }
    panel.appendChild(fs); form.appendChild(panel);
  }
}

function refreshText() {
  document.querySelectorAll("[data-template]").forEach(el => {
    const tag = el.querySelector(".tag");
    el.textContent = fill(el.dataset.template);
    if (tag) el.appendChild(tag);
  });
}

function persist() { try { localStorage.setItem(STORE_KEY, JSON.stringify(answers)); } catch (e) {} }

function counts() {
  const all = SPEC.flatMap(s => s.questions.map(q => q.key));
  const done = all.filter(k => (answers[k] || "").trim()).length;
  return [done, all.length];
}
function progress() {
  const [done, total] = counts();
  document.getElementById("progress").textContent = done + " of " + total + " answered";
}

function payload() {
  const clean = {};
  for (const [k, v] of Object.entries(answers)) if ((v || "").trim()) clean[k] = v.trim();
  return { format: FORMAT, version: VERSION, exported_at: new Date().toISOString(), answers: clean };
}
function fileName() {
  const name = (answers.profile_1 || "colleague").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 30) || "colleague";
  return "vai-answers-" + name + ".json";
}
function status(msg) { document.getElementById("status").textContent = msg; }

document.getElementById("save").addEventListener("click", () => {
  const [done] = counts();
  if (!done) { status("Answer at least one question first."); return; }
  const blob = new Blob([JSON.stringify(payload(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = fileName();
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  document.getElementById("fname").textContent = fileName();
  document.getElementById("after").classList.add("show");
  status("Downloaded " + fileName() + ". Email it back when you're ready.");
});

document.getElementById("copy").addEventListener("click", async () => {
  const text = JSON.stringify(payload(), null, 2);
  try { await navigator.clipboard.writeText(text); status("Copied. Paste it into your email reply."); }
  catch (e) {
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select();
    const ok = document.execCommand && document.execCommand("copy"); t.remove();
    status(ok ? "Copied. Paste it into your email reply." : "Couldn't copy here; please use Save my answers.");
  }
});

document.getElementById("clear").addEventListener("click", () => {
  if (!confirm("Clear all your answers from this browser? Do this only after you've sent them.")) return;
  answers = {};
  try { localStorage.removeItem(STORE_KEY); } catch (e) {}
  form.innerHTML = ""; build(); progress();
  document.getElementById("after").classList.remove("show");
  status("Cleared from this browser.");
});

build(); progress();
</script>
</body>
</html>
"""


def build_page(sender: str | None) -> str:
    spec_json = json.dumps(build_spec(), ensure_ascii=False).replace("</", "<\\/")
    who = sender.strip() if sender and sender.strip() else None
    replacements = {
        "__SPEC__": spec_json,
        "__FORMAT__": json.dumps(FORMAT),
        "__VERSION__": json.dumps(VERSION),
        "__SENDER_POSSESSIVE__": f"{who}'s" if who else "the sender's",
        "__SENDER_CAP__": who or "The person who sent you this",
        "__SENDER__": who or "the person who sent you this",
    }
    page = PAGE
    for key, value in replacements.items():
        if key.startswith("__SENDER"):
            value = escape(value)
        page = page.replace(key, value)
    return page


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the offline VAI questionnaire HTML file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"Output file (default: {DEFAULT_OUT})")
    parser.add_argument("--sender", help="Your name, shown to colleagues (default: 'the person who sent you this').")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_page(args.sender), encoding="utf-8")
    print(f"Questionnaire written to {args.out}")
    print("Email it as an attachment (zip it if your mail system blocks .html files).")


if __name__ == "__main__":
    main()
