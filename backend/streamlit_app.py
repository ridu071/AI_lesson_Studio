"""AI Lesson Studio - the app.

Run from the backend folder:
    streamlit run streamlit_app.py
"""

import random
import time
from datetime import UTC, datetime, timedelta
from html import escape

import streamlit as st

from app.core.config import get_settings
from app.generation.goal import suggest_goal
from app.generation.render import render_lesson_markdown, render_references
from app.llm.base import LLMConfigError
from app.llm.factory import create_llm_client
from app.modules.qc.enums import ReleaseDecision, severity_rank
from app.modules.qc.reporting import render_audit_report
from app.schemas.enums import AssessmentKind, ContentBlockType, QuestionType, SectionType, SourceType
from app.workflow import InputError, Project, StepFailed, validate_inputs

st.set_page_config(page_title="AI Lesson Studio", page_icon="🎓", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container {padding-top: 3.8rem; max-width: 1200px;}
.hero {background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); color: white;
       padding: 2rem 2.2rem; border-radius: 18px; margin-bottom: 1.5rem;}
.hero h1 {color: white; margin: 0 0 .4rem 0; font-size: 2.1rem;}
.hero p {color: #E0E7FF; margin: 0; font-size: 1.05rem;}
.badge {display: inline-block; padding: .18rem .65rem; border-radius: 999px; font-size: .82rem;
        font-weight: 600; margin-right: .35rem; background: #EEF2FF; color: #4338CA;}
.badge.green {background: #DCFCE7; color: #166534;}
.badge.amber {background: #FEF3C7; color: #92400E;}
.badge.red {background: #FEE2E2; color: #991B1B;}
.stage {border: 1px solid #E5E7EB; border-radius: 14px; padding: .9rem 1.1rem; margin-bottom: .6rem;}
.stage.done {border-color: #86EFAC; background: #F0FDF4;}
.stage.active {border-color: #A5B4FC; background: #EEF2FF;}
.stage.failed {border-color: #FCA5A5; background: #FEF2F2;}
.stage .title {font-weight: 700; font-size: 1.02rem;}
.stage .detail {color: #4B5563; font-size: .92rem; margin-top: .25rem;}
.tip {background: #FFFBEB; border-left: 4px solid #F59E0B; padding: .7rem 1rem; border-radius: 8px;
      color: #78350F; font-size: .95rem;}
.objective {padding: .35rem 0; font-size: 1.02rem;}
.section-head {display: flex; justify-content: space-between; align-items: center;}
.minutes {color: #6B7280; font-size: .9rem;}

/* ---- landing ---- */
.landing-title {text-align: center; font-size: 2.2rem; font-weight: 800; margin: 0 0 .2rem 0;
  white-space: nowrap;
  background: linear-gradient(135deg, #4F46E5, #7C3AED); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;}
.landing-sub {text-align: center; color: #374151; font-size: 1rem; margin-bottom: 1rem;}
.features {display: flex; justify-content: center; gap: 1.6rem; color: #374151; font-size: .9rem;
  margin-top: .6rem; flex-wrap: wrap;}

/* ---- duck pond loading screen ---- */
.pond {position: relative; border-radius: 22px; padding: 2.2rem 1rem 1.2rem 1rem; overflow: hidden;
  background: linear-gradient(180deg, #E0F2FE 0%, #BAE6FD 55%, #7DD3FC 100%);}
.pond::after {content: ""; position: absolute; left: -50%; bottom: 58px; width: 200%; height: 18px;
  background: radial-gradient(circle at 10px -4px, transparent 12px, rgba(255,255,255,.55) 13px) repeat-x;
  background-size: 34px 18px; animation: waves 3s linear infinite; opacity: .9;}
@keyframes waves {from {transform: translateX(0);} to {transform: translateX(34px);}}
.duck-row {display: flex; justify-content: space-around; align-items: flex-end; position: relative; z-index: 1;}
.duck {display: flex; flex-direction: column; align-items: center; width: 19%; text-align: center;}
.duck .body {font-size: 3.1rem; line-height: 1; transform: scaleX(-1); position: relative;}
.duck .bob {display: inline-block;}
.duck.waiting .body {filter: grayscale(1); opacity: .35;}
.duck.active .bob {animation: bob 1.1s ease-in-out infinite, paddle 2.2s ease-in-out infinite;}
.duck.active .body::after {content: ""; position: absolute; left: 50%; bottom: -6px; width: 70px; height: 12px;
  margin-left: -35px; border-radius: 50%; border: 2px solid rgba(255,255,255,.8);
  animation: ripple 1.4s ease-out infinite;}
.duck.failed .body {filter: grayscale(1) sepia(1) hue-rotate(-50deg) saturate(4); opacity: .8;}
@keyframes bob {0%,100% {transform: translateY(0) rotate(-4deg);} 50% {transform: translateY(-9px) rotate(4deg);}}
@keyframes paddle {0%,100% {margin-left: -8px;} 50% {margin-left: 8px;}}
@keyframes ripple {from {transform: scale(.4); opacity: 1;} to {transform: scale(1.4); opacity: 0;}}
.duck .badge-done {font-size: .95rem; height: 1.3rem;}
.duck .label {font-weight: 700; font-size: .9rem; color: #0C4A6E; margin-top: .55rem;}
.duck .what {font-size: .78rem; color: #075985; min-height: 2.4rem; margin-top: .15rem; padding: 0 .2rem;}
.duck.active .label {color: #4338CA;}
.duck.failed .label {color: #B91C1C;}
/* ---- build screen: the student's title as the headline, everything on one screen ---- */
.build-wrap {text-align: center; margin: 0 0 1.2rem 0; animation: rise .7s ease-out both;}
.build-wrap .eyebrow {text-transform: uppercase; letter-spacing: .12em; font-size: .8rem; font-weight: 700;
  color: #7C3AED;}
.build-wrap .build-title {font-size: 2.7rem; font-weight: 800; line-height: 1.15; margin: .35rem 0 .45rem 0;
  background: linear-gradient(135deg, #4F46E5, #7C3AED); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;}
.build-wrap .build-goal {color: #6B7280; font-size: 1rem; max-width: 760px; margin: 0 auto;}
.pond {animation: rise .7s .15s ease-out both;}
@keyframes rise {from {opacity: 0; transform: translateY(46px);} to {opacity: 1; transform: none;}}
.pond-status {text-align: center; margin: 1.1rem 0 .3rem 0; font-size: 1.15rem; font-weight: 700; color: #1F2937;}
.pond-detail {text-align: center; color: #4B5563; font-size: .95rem;}
.features span {cursor: help;}
.you-get {font-size: .9rem; color: #374151; background: #F5F3FF; border-radius: 10px; padding: .55rem .8rem;
  margin: .2rem 0 .5rem 0;}
.group-label {font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: #4B5563; margin: .8rem 0 .3rem 0;}
[data-testid="stVerticalBlockBorderWrapper"] {box-shadow: 0 6px 24px rgba(79, 70, 229, .08);}
[data-testid="stDecoration"] {display: none;}
button:focus-visible, input:focus-visible, textarea:focus-visible, [role="radio"]:focus-visible,
[role="tab"]:focus-visible {outline: 3px solid #A78BFA !important; outline-offset: 2px;}
@media (max-width: 760px) {
  .landing-title {white-space: normal; font-size: 1.7rem;}
  .build-wrap .build-title {font-size: 1.9rem;}
  .duck .body {font-size: 2.2rem;}
}
/* ================= sidebar lesson list ================= */
.side-brand {font-weight: 800; font-size: 1.05rem; color: #1F2937; margin: 0 0 .6rem .1rem;}

/* 14. "New lesson": the only solid indigo button */
.st-key-newlesson button {background: #4F46E5; border: 1px solid #4F46E5; color: #fff; border-radius: 10px;}
.st-key-newlesson button:hover {background: #4338CA; border-color: #4338CA; color: #fff;}

/* 15. Search box styled like the cards, indigo ring when focused */
.st-key-lsearch [data-baseweb="input"] {background: #fff; border: 1px solid #E5E7EB; border-radius: 10px;}
.st-key-lsearch [data-baseweb="input"] > div, .st-key-lsearch input {background: #fff;}
.st-key-lsearch [data-baseweb="input"]:focus-within {border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, .18);}

/* 6. Small, even gaps between cards */
.st-key-llist [data-testid="stVerticalBlock"] {gap: .4rem;}

/* 7 + 16. Group label: small, bold, uppercase, grey; more space above than below */
.st-key-llist .group-label {font-size: .7rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  color: #6B7280; margin: .9rem 0 .15rem .15rem;}
.st-key-llist [data-testid="stElementContainer"]:first-child .group-label {margin-top: .1rem;}

/* 8. Card */
[class*="st-key-lcard"] {background: #fff; border: 1px solid #E5E7EB; border-radius: 12px;
  padding: .45rem .3rem .5rem .75rem; box-shadow: 0 1px 2px rgba(17, 24, 39, .04);
  transition: background .15s, border-color .15s; gap: 0 !important;}
[class*="st-key-lcard"] [data-testid="stVerticalBlock"] {gap: 0 !important;}
/* 9. Hover */
[class*="st-key-lcard-"]:hover {background: #F5F3FF; border-color: #C7D2FE;}
/* 10. Selected lesson */
[class*="st-key-lcardsel-"] {background: #EEF2FF; border-color: #C7D2FE; border-left: 4px solid #4F46E5;
  padding-left: calc(.75rem - 3px);}

/* 4 + 5. Title: bold, left-aligned, cut off with "…" */
[class*="st-key-lcard"] [data-testid="stColumn"] {min-width: 0;}
[class*="st-key-lcard"] [class*="st-key-open-"] button {justify-content: flex-start; text-align: left;
  padding: 0; min-height: 0; width: 100%; color: #111827;}
[class*="st-key-lcard"] [class*="st-key-open-"] button > div,
[class*="st-key-lcard"] [class*="st-key-open-"] button [data-testid="stMarkdownContainer"] {min-width: 0; max-width: 100%;}
[class*="st-key-lcard"] [class*="st-key-open-"] button p {font-weight: 650; font-size: .95rem; margin: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left;}
[class*="st-key-lcard"] [class*="st-key-open-"] button:hover {color: #4338CA;}
/* 11. Meta line (and goal snippet for repeated titles) */
.lmeta, .lgoal {font-size: .76rem; color: #6B7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  line-height: 1.35;}
.lgoal {color: #4B5563; font-style: italic;}

/* 2 + 3 + 12. ⋮ menu: small, borderless, grey; indigo tint on hover; no dropdown arrow */
[class*="st-key-lmenu-"] button {border: none !important; background: transparent !important; color: #6B7280;
  padding: .15rem .25rem; min-height: 0; border-radius: 8px;}
[class*="st-key-lmenu-"] button:hover {background: #EEF2FF !important; color: #4F46E5;}
/* Streamlit renders the dropdown arrow as a trailing aria-hidden span after the label: hide only that. */
[class*="st-key-lmenu-"] button div > [aria-hidden="true"]:last-child:not(:first-child) {display: none;}

/* 13. Delete in red */
[class*="st-key-ldel-"] button {color: #B91C1C; border-color: #FECACA;}
[class*="st-key-ldel-"] button:hover:not(:disabled) {background: #FEF2F2; border-color: #F87171; color: #991B1B;}
</style>
""", unsafe_allow_html=True)

DUCKS = [
    ("plan", "Planning", "Working out the key ideas and what to search for"),
    ("sources", "Finding sources", "Reading Wikipedia, finding books and YouTube videos"),
    ("generation", "Writing", "Writing explanations, examples, an activity and quizzes"),
    ("qc1", "Fact check", "QC Layer 1: checking every fact against the sources"),
    ("qc2", "Teaching check", "QC Layer 2: checking it teaches the goal clearly"),
]
TIPS = [
    "Tip: try explaining what you learn to a friend - teaching is one of the best ways to remember.",
    "Tip: short breaks every 20-25 minutes help you stay focused.",
    "Tip: answer the quiz questions before peeking - recalling builds memory.",
    "Tip: write down one question you still have after each section.",
    "Did you know? Every fact in your lesson is linked to the source it came from.",
    "Did you know? Two separate quality checks review your lesson before you see it.",
]
EXAMPLES = [
    ("HTTP Requests and Responses",
     "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories."),
    ("Photosynthesis",
     "Describe the inputs and outputs of photosynthesis and explain the role of chlorophyll and sunlight."),
    ("Newton's Laws of Motion",
     "Explain Newton's three laws of motion and apply them to everyday examples."),
    ("The French Revolution",
     "Describe the main causes of the French Revolution and explain how it changed French government."),
]
DECISION_BADGE = {
    ReleaseDecision.ELIGIBLE: ("green", "✔ Checked: accurate and well structured"),
    ReleaseDecision.REVISION_REQUIRED: ("amber", "⚠ Needs improvement (see the QC tabs)"),
    ReleaseDecision.MANUAL_REVIEW: ("amber", "⚠ Needs a teacher's review"),
    ReleaseDecision.BLOCKED: ("red", "⛔ Blocked by quality control"),
}


@st.cache_resource
def llm():
    settings = get_settings()
    return settings, create_llm_client(settings)


def go(project_id: str | None) -> None:
    st.session_state["project_id"] = project_id
    st.rerun()


def current_project() -> Project | None:
    pid = st.session_state.get("project_id")
    return next((p for p in Project.list_all() if p.meta["project_id"] == pid), None) if pid else None


# ----------------------------------------------------------- loading screen


def _pond_html(states: dict[str, str], notes: dict[str, str]) -> str:
    ducks = []
    for key, label, blurb in DUCKS:
        state = states.get(key, "waiting")
        badge = {"done": "✔", "failed": "✖", "active": "", "waiting": ""}[state]
        ducks.append(
            f'<div class="duck {state}"><div class="badge-done">{badge}</div>'
            f'<div class="body"><span class="bob">🦆</span></div>'
            f'<div class="label">{label}</div><div class="what">{escape(notes.get(key, blurb))}</div></div>'
        )
    return f'<div class="pond"><div class="duck-row">{"".join(ducks)}</div></div>'


def _research_note(project: Project) -> str:
    package, _, _ = project.research()
    passages = sum(len(s.evidence_passages) for s in package.sources)
    books = sum(s.source_type is SourceType.BOOK for s in package.sources)
    videos = sum(s.source_type is SourceType.VIDEO for s in package.sources)
    articles = sum(bool(s.evidence_passages) for s in package.sources)
    return f"{articles} articles, {passages} passages, {books} books, {videos} videos"


def _lesson_note(project: Project) -> str:
    lesson = project.lesson()
    minutes = sum(s.duration_minutes for s in lesson.sections)
    return f"{len(lesson.sections)} sections, {len(lesson.assessments)} quiz questions, {minutes} min"


def _audit_note(audit) -> str:
    if audit.score is None:
        return "could not finish"
    n = len(audit.issues)
    return f"score {audit.score:g}/100, " + ("no issues" if not n else f"{n} suggestion{'s' * (n > 1)}")


def generate_with_progress(project: Project) -> bool:
    """Run every unfinished step on the duck-pond screen: one duck per process.
    Returns True on success."""
    settings, client = llm()
    order = [key for key, *_ in DUCKS]
    states: dict[str, str] = {}
    notes: dict[str, str] = {}
    started = time.monotonic()

    _, middle, _ = st.columns([1, 6, 1])
    with middle:
        # The student's own title becomes the headline (escaped: it is user input).
        st.markdown(f'<div class="build-wrap"><div class="eyebrow">Building your lesson</div>'
                    f'<div class="build-title">{escape(project.inputs.title)}</div>'
                    f'<div class="build-goal">🎯 {escape(project.inputs.objective)}</div></div>',
                    unsafe_allow_html=True)
        pond, status, bar, tip_box, clock = (st.empty() for _ in range(5))

    def show(active: str | None, failed: str | None = None) -> None:
        for key in order:
            if key == failed:
                states[key] = "failed"
            elif key == active:
                states[key] = "active"
            elif key not in notes:
                states[key] = "waiting"
            else:
                states[key] = "done"
        pond.markdown(_pond_html(states, notes), unsafe_allow_html=True)
        done = sum(s == "done" for s in states.values())
        if active:
            label, blurb = next((lab, b) for k, lab, b in DUCKS if k == active)
            status.markdown(f'<div class="pond-status">Duck {order.index(active) + 1} of 5 is swimming: '
                            f'{label}</div><div class="pond-detail">{blurb}...</div>', unsafe_allow_html=True)
        bar.progress(done / len(order))
        tip_box.markdown(f'<div class="tip">{random.choice(TIPS)}</div>', unsafe_allow_html=True)
        clock.caption(f"⏱ {time.monotonic() - started:.0f} s - usually 30-60 seconds")

    # Steps finished in an earlier attempt are shown as done.
    if project.step("research")["status"] == "done":
        notes["plan"] = ", ".join(project.research()[1].key_concepts[:3])
        notes["sources"] = _research_note(project)
    if project.step("generation")["status"] == "done" and project.lesson():
        notes["generation"] = _lesson_note(project)

    def research_progress(stage, plan) -> None:
        notes["plan"] = ", ".join(plan.key_concepts[:3])
        show("sources")

    def qc_progress(stage, qc1_audit) -> None:
        notes["qc1"] = _audit_note(qc1_audit)
        show("qc2")

    try:
        if project.step("research")["status"] != "done":
            show("plan")
            project.run_research(client, settings, progress=research_progress)
            notes["sources"] = _research_note(project)
        if project.step("generation")["status"] != "done":
            show("generation")
            project.run_generation(client)
            notes["generation"] = _lesson_note(project)
        if project.step("qc")["status"] != "done":
            show("qc1")
            project.run_qc(client, settings, progress=qc_progress)
        audits = project.audits()
        notes["qc1"], notes["qc2"] = _audit_note(audits[0]), _audit_note(audits[1])
        show(None)
        status.markdown('<div class="pond-status">All five ducks made it across! 🎉</div>'
                        '<div class="pond-detail">Opening your lesson...</div>', unsafe_allow_html=True)
        tip_box.empty()
        st.balloons()
        return True
    except StepFailed as exc:
        failed = next(k for k in order if k not in notes)
        show(None, failed=failed)
        label = next(lab for k, lab, _ in DUCKS if k == failed)
        status.markdown(f'<div class="pond-status">The "{label}" duck got stuck</div>'
                        f'<div class="pond-detail">Everything before it is saved. '
                        f'Press <b>Try again</b> to continue from here.</div>', unsafe_allow_html=True)
        tip_box.empty()
        with middle:
            st.error(f"`{exc}`")
        return False


# ------------------------------------------------------------- learn view


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def render_question(q, key: str, number: int) -> None:
    st.markdown(f"**Question {number}.** {q.prompt}")
    if q.question_type in (QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE) and q.options:
        choice = st.radio("Your answer", q.options, index=None, key=f"{key}-radio",
                          label_visibility="collapsed")
        if st.button("Check answer", key=f"{key}-check", disabled=choice is None):
            if _norm(choice) == _norm(q.answer_key):
                st.success(f"Correct! {q.explanation}")
            else:
                st.error(f"Not quite. The answer is **{q.answer_key}**. {q.explanation}")
    else:
        st.text_area("Write your answer", key=f"{key}-text", height=90)
        with st.expander("Show a model answer"):
            st.markdown(f"**{q.answer_key}**\n\n{q.explanation}")


def render_learn(project: Project, lesson, research) -> None:
    package = research[0]
    minutes = sum(s.duration_minutes for s in lesson.sections)
    audits = project.audits()
    badge = ""
    if audits and audits[2]:
        color, text = DECISION_BADGE[audits[2].decision]
        badge = f'<span class="badge {color}">{text}</span>'
    st.markdown(f'<span class="badge">⏱ {minutes} min</span><span class="badge">🎚 {lesson.learner_level}</span>'
                f'<span class="badge">📚 {len([s for s in package.sources if s.evidence_passages])} sources</span>'
                f'{badge}', unsafe_allow_html=True)

    sections = [s for s in lesson.sections if s.section_type is not SectionType.LEARNING_OBJECTIVES]
    done_key = f"done-{project.meta['project_id']}-v{lesson.version}"
    done: set = st.session_state.setdefault(done_key, set())
    st.progress(len(done) / len(sections), text=f"Your progress: {len(done)} of {len(sections)} sections")

    with st.container(border=True):
        st.markdown("#### 🎯 By the end of this lesson you will be able to")
        for o in lesson.learning_objectives:
            st.markdown(f'<div class="objective">☐ {escape(o.description)}</div>', unsafe_allow_html=True)

    number = 0
    for s in sections:
        with st.container(border=True):
            st.markdown(f'<div class="section-head"><h4 style="margin:0">{escape(s.title)}</h4>'
                        f'<span class="minutes">⏱ {s.duration_minutes} min</span></div>', unsafe_allow_html=True)
            for block in s.content_blocks:
                if block.type is ContentBlockType.DEFINITION:
                    st.info(f"**Definition** - {block.content}", icon="📘")
                elif block.type is ContentBlockType.EXAMPLE:
                    st.success(f"**Example** - {block.content}", icon="💡")
                elif block.type is ContentBlockType.CODE:
                    st.code(block.content)
                elif block.type is ContentBlockType.NOTE:
                    st.caption(block.content)
                else:
                    st.markdown(block.content)
            for a in [a for a in lesson.activities if a.section_id == s.section_id]:
                with st.expander(f"🛠 Activity: {a.title} ({a.duration_minutes} min)", expanded=True):
                    st.markdown(a.instructions)
                    st.text_area("Your work", key=f"act-{done_key}-{a.activity_id}", height=110)
            for q in [q for q in lesson.assessments if q.section_id == s.section_id]:
                number += 1
                render_question(q, f"q-{done_key}-{q.question_id}", number)
            checked = st.checkbox("I've finished this section", value=s.section_id in done,
                                  key=f"chk-{done_key}-{s.section_id}")
            if checked != (s.section_id in done):
                done.add(s.section_id) if checked else done.discard(s.section_id)
                st.rerun()

    if lesson.videos:
        st.markdown("### 🎬 Want to go further? Watch (optional)")
        cols = st.columns(2)
        for i, v in enumerate(lesson.videos):
            with cols[i % 2]:
                st.video(str(v.url))
                st.caption(f"{v.title}" + (f" - {v.duration_minutes} min" if v.duration_minutes else ""))

    with st.expander("📚 References and further reading"):
        st.markdown("\n".join(render_references(lesson, package)[1:]))

    if len(done) == len(sections):
        st.success("🎉 You've completed the whole lesson. Great work!")


# ----------------------------------------------------------------- sidebar


def _when(created_at: str) -> tuple[str, str]:
    """(group, relative label) for a creation timestamp."""
    created = datetime.fromisoformat(created_at)
    age = datetime.now(UTC) - created
    if age < timedelta(minutes=1):
        label = "just now"
    elif age < timedelta(hours=1):
        label = f"{int(age.total_seconds() // 60)} min ago"
    elif age < timedelta(days=1):
        label = f"{int(age.total_seconds() // 3600)} h ago"
    else:
        label = f"{age.days} day{'s' * (age.days > 1)} ago"
    if created.date() == datetime.now(UTC).date():
        return "Today", label
    return ("This week" if age < timedelta(days=7) else "Earlier"), label


def _lesson_card(p: Project, duplicated: bool) -> None:
    """One lesson = one card: bold title, meta line (and goal if the title repeats), ⋮ menu."""
    pid = p.meta["project_id"]
    current = st.session_state.get("project_id") == pid
    created = datetime.fromisoformat(p.meta["created_at"])
    failed = any(s["status"] == "failed" for s in p.meta["steps"].values())
    meta = [p.inputs.learner_level.capitalize(), _when(p.meta["created_at"])[1],
            created.astimezone().strftime("%H:%M")]
    if p.current_version and p.current_version > 1:
        meta.append(f"v{p.current_version}")
    if p.next_step() is not None:
        meta.append("needs retry" if failed else "unfinished")

    with st.container(key=f"{'lcardsel' if current else 'lcard'}-{pid}"):
        c1, c2 = st.columns([9, 1], vertical_alignment="center", gap="small")
        with c1:
            if st.button(p.display_name, key=f"open-{pid}", type="tertiary", use_container_width=True,
                         help=p.display_name):
                go(pid)
            goal = (f'<div class="lgoal">{escape(" ".join(p.inputs.objective.split()[:9]))}…</div>'
                    if duplicated else "")
            st.markdown(f'<div class="lmeta">{escape(" · ".join(meta))}</div>{goal}', unsafe_allow_html=True)
        with c2:
            with st.popover("", icon=":material/more_vert:", type="tertiary", key=f"lmenu-{pid}",
                            help="Rename or delete"):
                new_name = st.text_input("Rename", p.display_name, key=f"rn-{pid}")
                if st.button("Save name", key=f"rn-save-{pid}", icon=":material/edit:"):
                    try:
                        p.rename(new_name)
                        st.rerun()
                    except InputError as exc:
                        st.error(str(exc))
                st.divider()
                sure = st.checkbox("Yes, delete this lesson and all its versions", key=f"del-ok-{pid}")
                with st.container(key=f"ldel-{pid}"):
                    if st.button("Delete", key=f"del-{pid}", disabled=not sure, icon=":material/delete:"):
                        p.delete()
                        if current:
                            st.session_state["project_id"] = None
                        st.rerun()


with st.sidebar:
    st.markdown('<div class="side-brand">AI Lesson Studio</div>', unsafe_allow_html=True)
    with st.container(key="newlesson"):
        if st.button("New lesson", use_container_width=True, type="primary", icon=":material/add:"):
            go(None)
    lessons = Project.list_all()
    with st.container(key="lsearch"):
        query = st.text_input("Search lessons", placeholder="Search lessons", key="lesson_search",
                              label_visibility="collapsed", icon=":material/search:")
    if query.strip():
        q = query.casefold()
        lessons = [p for p in lessons if q in p.display_name.casefold() or q in p.inputs.objective.casefold()]
    names = [p.display_name.casefold() for p in lessons]
    with st.container(height=600, border=False, key="llist"):
        if not lessons:
            st.caption("No lessons found." if query.strip() else "No lessons yet. Create your first one!")
        for group in ("Today", "This week", "Earlier"):
            members = [p for p in lessons if _when(p.meta["created_at"])[0] == group]
            if members:
                st.markdown(f'<div class="group-label">{group}</div>', unsafe_allow_html=True)
                for p in members:
                    _lesson_card(p, names.count(p.display_name.casefold()) > 1)

try:
    llm()
except LLMConfigError as exc:
    st.error(f"The AI is not configured: {exc}. Set LLM_API_KEY and LLM_MODEL in backend/.env.")
    st.stop()

project = current_project()


def start_building(project_id: str) -> None:
    """Switch to the build screen on the next run (used as a button callback)."""
    st.session_state["project_id"] = project_id
    st.session_state["building"] = project_id


# ------------------------------------------------------------ build screen
# Shown on its own: the input box is gone and the student's title is the headline.

def go_home() -> None:
    """Back to the first screen, with the student's topic and goal still filled in.
    Work finished so far is saved in the lesson and can be continued later."""
    st.session_state.pop("building", None)
    st.session_state["project_id"] = None
    st.session_state["in_title"] = st.session_state.get("last_title", "")
    st.session_state["in_objective"] = st.session_state.get("last_objective", "")


if project is not None and st.session_state.get("building") == project.meta["project_id"]:
    st.session_state.pop("building")
    st.session_state.setdefault("last_title", project.inputs.title)
    st.session_state.setdefault("last_objective", project.inputs.objective)
    _, back_col, _ = st.columns([1, 6, 1])
    back_col.button("← Back", on_click=go_home, help="Stop and go back to the first screen. "
                    "Anything already finished is saved.")
    if generate_with_progress(project):
        time.sleep(1.5)
        st.rerun()
    _, middle, _ = st.columns([1, 6, 1])
    with middle:
        st.button("🔁 Try again", type="primary", use_container_width=True,
                  on_click=start_building, args=(project.meta["project_id"],))
    st.stop()

# ---------------------------------------------------------------- landing

LEVELS = {
    "Beginner": "New to the topic: plain words, every term explained.",
    "Intermediate": "Know the basics: more detail and connections between ideas.",
    "Advanced": "Comfortable with the field: precise terms and deeper reasoning.",
}


def _fill_example() -> None:
    picked = st.session_state.get("example_pick")
    goal = dict(EXAMPLES).get(picked)
    if goal:
        st.session_state["in_title"], st.session_state["in_objective"] = picked, goal


def _suggest_goal() -> None:
    topic = (st.session_state.get("in_title") or "").strip()
    if len(topic) < 3:
        st.session_state["goal_hint"] = "Type a topic first, then I can suggest a goal."
        return
    level = (st.session_state.get("in_level") or "Beginner").lower()
    try:
        st.session_state["in_objective"] = suggest_goal(topic, level, llm()[1])
        st.session_state["goal_hint"] = "Suggested goal added. Edit it if you like."
    except Exception as exc:  # noqa: BLE001 - any failure: just tell the user
        st.session_state["goal_hint"] = f"Couldn't suggest a goal right now ({type(exc).__name__}). Try again."


if project is None:
    _, middle, _ = st.columns([0.6, 4, 0.6])
    with middle:
        st.markdown('<div class="landing-title">What do you want to learn today?</div>'
                    '<div class="landing-sub">Give a topic and a goal. We research trusted sources and '
                    'build a 45-minute lesson, double-checked for accuracy.</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.pills("Try an example", [t for t, _ in EXAMPLES], key="example_pick", on_change=_fill_example)
            c_topic, c_level = st.columns([3, 2])
            title = c_topic.text_input("Topic", key="in_title",
                                       placeholder="e.g. Photosynthesis, Binary search, The French Revolution")
            level_name = c_level.segmented_control("Level", list(LEVELS), key="in_level",
                                                   default="Beginner") or "Beginner"
            c_level.caption(f"**{level_name}:** {LEVELS[level_name]}")
            g1, g2 = st.columns([3, 1], vertical_alignment="bottom")
            objective = g1.text_area("After this lesson, I want to be able to...", key="in_objective",
                                     placeholder="e.g. Describe the inputs and outputs of photosynthesis "
                                                 "and explain the role of chlorophyll.", height=76)
            g2.button("✨ Suggest a goal", on_click=_suggest_goal, use_container_width=True,
                      help="Drafts a clear goal from your topic and level")
            if st.session_state.get("goal_hint"):
                st.caption(st.session_state.pop("goal_hint"))
            st.markdown('<div class="you-get"><b>You\'ll get:</b> clear explanations · worked examples · '
                        'a hands-on activity · quiz questions with instant feedback · a summary · '
                        'videos and references</div>', unsafe_allow_html=True)
            submitted = st.button("Create my lesson", type="primary", use_container_width=True)
            if not (title or "").strip() or not (objective or "").strip():
                st.caption("Add a topic and a goal to start - or pick an example above.")
        st.markdown(
            '<div class="features">'
            '<span title="Facts come from Wikipedia articles, quoted word for word; books and YouTube '
            'videos are added as references and extra viewing.">🔎 Researched from trusted sources ⓘ</span>'
            '<span title="Sections, activities and quizzes are timed so the whole lesson takes at most '
            '45 minutes.">⏱ Finish in 45 minutes ⓘ</span>'
            '<span title="Check 1 compares every fact with its source. Check 2 makes sure the lesson '
            'really teaches your goal, clearly and in a good order.">✅ Double-checked ⓘ</span></div>',
            unsafe_allow_html=True)
        problem = st.empty()

        duplicate = st.session_state.get("duplicate")
        if duplicate:
            existing = next((p for p in Project.list_all() if p.meta["project_id"] == duplicate), None)
            if existing:
                with problem.container(border=True):
                    st.markdown(f"You already have a **{existing.inputs.learner_level}** lesson on "
                                f"**{escape(existing.display_name)}**.")
                    d1, d2 = st.columns(2)
                    if d1.button("Open existing lesson", type="primary", use_container_width=True):
                        st.session_state.pop("duplicate")
                        go(existing.meta["project_id"])
                    if d2.button("Create a new one anyway", use_container_width=True):
                        st.session_state.pop("duplicate")
                        st.session_state["force_new"] = True
                        submitted = True

        recent = [p for p in Project.list_all() if p.next_step() is None][:3]
        if recent and not duplicate:
            st.markdown('<div class="group-label" style="text-align:center;margin-top:1rem">'
                        'Continue where you left off</div>', unsafe_allow_html=True)
            cols = st.columns(len(recent))
            for col, p in zip(cols, recent):
                if col.button(p.display_name, key=f"recent-{p.meta['project_id']}", use_container_width=True,
                              help=f"{p.inputs.learner_level.capitalize()} · {_when(p.meta['created_at'])[1]}"):
                    go(p.meta["project_id"])

    if submitted:
        try:
            inputs = validate_inputs(title, objective, level_name.lower())
        except InputError as exc:
            problem.warning(f"Please check your input: {exc}")
            st.stop()
        existing = None if st.session_state.pop("force_new", False) else Project.find_existing(inputs)
        if existing:
            st.session_state["duplicate"] = existing.meta["project_id"]
            st.rerun()
        new = Project.create(inputs)
        st.session_state["last_title"], st.session_state["last_objective"] = title, objective
        start_building(new.meta["project_id"])
        st.rerun()
    st.stop()

# ------------------------------------------------------------ lesson page

inputs = project.inputs
st.markdown(f'<div class="hero"><h1>{escape(project.display_name)}</h1><p>🎯 {escape(inputs.objective)}</p></div>',
            unsafe_allow_html=True)

if project.next_step():
    failed = any(s["status"] == "failed" for s in project.meta["steps"].values())
    if project.lesson() is None or project.next_step() != "qc" or failed:
        st.info("This lesson isn't finished yet. Your progress so far is saved.")
        st.button("🔁 Try again" if failed else "▶ Continue", type="primary",
                  on_click=start_building, args=(project.meta["project_id"],))
        if project.lesson() is None:
            st.stop()

lesson = project.lesson()
audits = project.audits()
research = project.research()
if project.step("qc")["status"] != "done":
    st.warning(f"Version {lesson.version} hasn't been quality-checked yet.")
    st.button("✅ Run quality checks", type="primary",
              on_click=start_building, args=(project.meta["project_id"],))

tabs = st.tabs(["📖 Learn", "✅ Fact check (QC1)", "🎓 Teaching check (QC2)", "🛠 Improve",
                "✏️ Edit", "📚 Sources", "⬇ Export", "🕘 History"])

with tabs[0]:
    render_learn(project, lesson, research)

for tab, index in ((tabs[1], 0), (tabs[2], 1)):
    with tab:
        if audits:
            st.markdown(render_audit_report(project.qc_input(), audits[index]))
        else:
            st.info("Run the quality checks to see this report.")

with tabs[3]:
    st.caption("For teachers: pick QC suggestions (or write your own instruction) and let the AI "
               "create an improved version. The new version is checked again automatically.")
    if not audits:
        st.info("Run the quality checks first.")
    else:
        dismissed = project.dismissed()
        issues = sorted(audits[0].issues + audits[1].issues, key=lambda i: -severity_rank(i.severity))
        open_issues = [i for i in issues if i.issue_id not in dismissed]
        if not open_issues:
            st.success("No open suggestions for this version. 🎉")
        selected = []
        for issue in open_issues:
            with st.container(border=True):
                c1, c2 = st.columns([9, 1])
                fix = issue.recommendation.action if issue.recommendation else "-"
                if c1.checkbox(f"**{issue.issue_id} · {issue.severity} · {issue.issue_type}**  \n"
                               f"{issue.explanation}  \n💡 *{fix}*", key=f"sel-{lesson.version}-{issue.issue_id}"):
                    selected.append(issue.issue_id)
                if c2.button("Dismiss", key=f"dis-{lesson.version}-{issue.issue_id}"):
                    project.dismiss(issue.issue_id)
                    st.rerun()
        note = st.text_area("Your own instruction for the AI (optional)",
                            placeholder="e.g. Add a real-world example about online shopping.")
        if st.button("✨ Improve the lesson", type="primary"):
            settings, client = llm()
            with st.spinner("Improving the lesson and checking it again..."):
                try:
                    project.apply_recommendations(selected, note, client, settings)
                    st.toast("Improved version created and checked.", icon="✅")
                    st.rerun()
                except StepFailed as exc:
                    st.error(f"{exc} The current version is unchanged.")

with tabs[4]:
    st.caption("Edits are saved as a new version; the old version stays in History. "
               "Run the quality checks again after saving.")
    data = lesson.model_dump(mode="json")
    v = lesson.version
    for s in data["sections"]:
        with st.expander(f"{s['section_id']} - {s['title']} ({s['duration_minutes']} min)"):
            s["title"] = st.text_input("Title", s["title"], key=f"t-{v}-{s['section_id']}")
            s["duration_minutes"] = st.number_input("Minutes", 0, 60, s["duration_minutes"],
                                                    key=f"m-{v}-{s['section_id']}")
            for n, block in enumerate(s["content_blocks"]):
                block["content"] = st.text_area(block["type"], block["content"],
                                                key=f"b-{v}-{s['section_id']}-{n}")
    for a in data["activities"]:
        with st.expander(f"Activity {a['activity_id']} - {a['title']}"):
            a["instructions"] = st.text_area("Instructions", a["instructions"], key=f"a-{v}-{a['activity_id']}")
    for q in data["assessments"]:
        with st.expander(f"Question {q['question_id']} ({q['kind']})"):
            q["prompt"] = st.text_area("Question", q["prompt"], key=f"qp-{v}-{q['question_id']}")
            if q["options"]:
                q["options"] = [o for o in st.text_area("Options (one per line)", "\n".join(q["options"]),
                                key=f"qo-{v}-{q['question_id']}").splitlines() if o.strip()]
            q["answer_key"] = st.text_input("Answer key", q["answer_key"], key=f"qa-{v}-{q['question_id']}")
            q["explanation"] = st.text_area("Explanation", q["explanation"], key=f"qe-{v}-{q['question_id']}")
    data["stated_duration_minutes"] = sum(s["duration_minutes"] for s in data["sections"])
    note = st.text_input("What did you change? (saved in history)", key=f"note-{v}")
    if st.button("💾 Save as new version", type="primary"):
        try:
            saved = project.save_edit(data, note)
            st.toast(f"Saved version {saved.version}.", icon="💾")
            st.rerun()
        except InputError as exc:
            st.error(str(exc))

with tabs[5]:
    package, plan, _ = research
    st.markdown("**Key concepts researched:** " + " · ".join(plan.key_concepts))
    for s in package.sources:
        icon = {"website": "🌐", "book": "📕", "video": "🎬"}.get(s.source_type, "📄")
        with st.expander(f"{icon} {s.title}  ·  {len(s.evidence_passages)} passages"):
            st.markdown(f"[{s.url}]({s.url})" if s.url else "no link")
            for p in s.evidence_passages:
                st.markdown(f"**{p.passage_id}** {p.text}")
    for limitation in package.limitations:
        st.caption("ℹ " + limitation)

with tabs[6]:
    st.caption(f"Exports version {lesson.version}: lesson, references and both QC reports.")
    st.download_button("⬇ Download everything (zip)", project.export_zip(),
                       file_name=f"lesson-v{lesson.version}.zip", type="primary")
    cols = st.columns(2)
    for i, (name, content) in enumerate(project.export_files().items()):
        cols[i % 2].download_button(f"⬇ {name}", content, file_name=name, key=f"dl-{name}",
                                    use_container_width=True)

with tabs[7]:
    for entry in reversed(project.meta["versions"]):
        a = project.audits(entry["version"])
        decision = a[2].decision if a and a[2] else "not checked"
        st.markdown(f"**v{entry['version']}** · {entry['origin']} · {entry['created_at']} · "
                    f"QC: {decision}  \n{entry['note']}")
    old = st.selectbox("Preview an older version", [e["version"] for e in project.meta["versions"]][::-1])
    if old != lesson.version:
        st.markdown(render_lesson_markdown(project.lesson(old), research[0]))
