"""The offline questionnaire's questions, taken from the real interviews.

Shared by make_questionnaire.py (builds the HTML file to email) and
import_answers.py (turns a returned answers file into a VAI profile). Answers
are matched by key only; question text always comes from here, never from the
returned file.
"""
from deep_interview import (CDM_CLOSING, CDM_FALLBACK_PROBES, CDM_OPENING, KNOWLEDGE_AUDIT,
                            WALKTHROUGH_QUESTIONS)
from interviewer import INTERVIEW_QUESTIONS

FORMAT = "vai-questionnaire"
VERSION = 1

PROFILE_KEYS = [f"profile_{n}" for n in range(1, len(INTERVIEW_QUESTIONS) + 1)]
AUDIT_KEYS = {f"audit_{item}": (item, template) for item, template in KNOWLEDGE_AUDIT}
CASE_QUESTIONS = (
    [(item, template) for item, template in CDM_OPENING]
    + [(f"probe_{n}", text) for n, text in enumerate(CDM_FALLBACK_PROBES, start=1)]
    + [CDM_CLOSING]
)
CASE_KEYS = {f"case_{item}": (item, template) for item, template in CASE_QUESTIONS}
WALK_TASK_KEY = "walk_task"
WALK_TASK_QUESTION = ("Describe a typical small task a client might give you in {domain}: "
                      "2-3 sentences with concrete details. The next questions are about how you'd handle it.")
WALK_KEYS = {f"walk_{item}": (item, text) for item, text in WALKTHROUGH_QUESTIONS}
AREA_KEY = "area"

ALL_KEYS = set(PROFILE_KEYS) | set(AUDIT_KEYS) | set(CASE_KEYS) | {WALK_TASK_KEY, AREA_KEY} | set(WALK_KEYS)


def _js_template(template: str) -> str:
    """{domain} -> {area} placeholder that the page fills in with the chosen area."""
    return template.replace("{domain}", "{area}")


def build_spec() -> list[dict]:
    """Sections and questions shown on the page, in order."""
    return [
        {
            "id": "profile",
            "title": "About you and your work",
            "intro": "These build your VAI's profile. They matter most, so please answer as many as you can.",
            "optional": False,
            "questions": [{"key": k, "text": q} for k, q in zip(PROFILE_KEYS, INTERVIEW_QUESTIONS)],
        },
        {
            "id": "area",
            "title": "Pick one area to go deeper",
            "intro": "The rest is optional. It teaches your VAI how you think in one area, "
                     "not just what you do. Choose the area you know best.",
            "optional": True,
            "questions": [{"key": AREA_KEY, "text": "Which one area of expertise should the next questions focus on?",
                           "short": True}],
        },
        {
            "id": "audit",
            "title": "How you think about {area}",
            "intro": "What you notice, your rules of thumb and the mistakes you avoid. Short answers with "
                     "one concrete example work best.",
            "optional": True,
            "questions": [{"key": k, "text": _js_template(t)} for k, (_, t) in AUDIT_KEYS.items()],
        },
        {
            "id": "case",
            "title": "A tough case in {area}",
            "intro": "One real, difficult situation from your experience, and the decisions you made. "
                     "Leave out names and anything confidential.",
            "optional": True,
            "questions": [{"key": k, "text": _js_template(t)} for k, (_, t) in CASE_KEYS.items()],
        },
        {
            "id": "walk",
            "title": "Walk through a typical task",
            "intro": "Describe a typical task, then talk through how you'd handle it.",
            "optional": True,
            "questions": [{"key": WALK_TASK_KEY, "text": _js_template(WALK_TASK_QUESTION)}]
                         + [{"key": k, "text": t} for k, (_, t) in WALK_KEYS.items()],
        },
    ]
