"""AI Lesson Studio - the app.

Run from the backend folder:
    streamlit run streamlit_app.py
"""

import random
import time

import streamlit as st

from app.core.config import get_settings
from app.generation.render import render_lesson_markdown, render_references
from app.llm.base import LLMConfigError
from app.llm.factory import create_llm_client
from app.modules.qc.enums import ReleaseDecision, severity_rank
from app.modules.qc.reporting import render_audit_report
from app.schemas.enums import AssessmentKind, ContentBlockType, QuestionType, SectionType, SourceType
from app.workflow import InputError, Project, StepFailed, validate_inputs

st.set_page_config(page_title="AI Lesson Studio", page_icon="🎓", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1100px;}
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
</style>
""", unsafe_allow_html=True)

STAGES = [
    ("research", "🔎", "Researching your topic",
     "Searching Wikipedia, books and YouTube, and keeping the exact passages we can trust."),
    ("generation", "✍️", "Writing your lesson",
     "Turning the evidence into explanations, examples, an activity and quizzes - under 45 minutes."),
    ("qc1", "✅", "Fact-checking every claim",
     "QC Layer 1 compares each statement with the research evidence."),
    ("qc2", "🎓", "Checking it teaches well",
     "QC Layer 2 checks the lesson really covers your objective, clearly and in a good order."),
]
TIPS = [
    "Tip: try explaining what you learn to a friend - teaching is one of the best ways to remember.",
    "Tip: short breaks every 20-25 minutes help you stay focused.",
    "Tip: answer the knowledge checks before peeking at the answers - retrieval builds memory.",
    "Tip: write down one question you still have after each section.",
    "Did you know? Every fact in your lesson is linked to the source it came from.",
    "Did you know? Two separate quality checks review your lesson before you see it.",
]
EXAMPLES = [
    ("HTTP Requests and Responses",
     "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories."),
    ("Photosynthesis",
     "Describe the inputs and outputs of photosynthesis and explain the role of chlorophyll and sunlight."),
    ("The Water Cycle",
     "Explain the stages of the water cycle and describe how evaporation and condensation drive it."),
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


def _stage_html(icon: str, title: str, state: str, detail: str) -> str:
    mark = {"done": "✔", "active": "⏳", "failed": "✖", "waiting": "•"}[state]
    return (f'<div class="stage {state}"><div class="title">{mark} {icon} {title}</div>'
            f'<div class="detail">{detail}</div></div>')


def _research_summary(project: Project) -> str:
    package, _, _ = project.research()
    articles = [s for s in package.sources if s.evidence_passages]
    books = [s for s in package.sources if s.source_type is SourceType.BOOK]
    videos = [s for s in package.sources if s.source_type is SourceType.VIDEO]
    passages = sum(len(s.evidence_passages) for s in articles)
    names = ", ".join(s.title.replace(" (Wikipedia)", "") for s in articles)
    return (f"Found <b>{len(articles)} articles</b> ({names}) with <b>{passages} evidence passages</b>, "
            f"<b>{len(books)} books</b> and <b>{len(videos)} videos</b>.")


def _lesson_summary(project: Project) -> str:
    lesson = project.lesson()
    minutes = sum(s.duration_minutes for s in lesson.sections)
    return (f"<b>{len(lesson.sections)} sections</b>, <b>{len(lesson.activities)} activity</b>, "
            f"<b>{len(lesson.assessments)} quiz questions</b>, <b>{len(lesson.claims)} sourced facts</b> - "
            f"about <b>{minutes} minutes</b>.")


def _qc_summary(project: Project, index: int) -> str:
    audits = project.audits()
    if not audits:
        return ""
    audit = audits[index]
    issues = len(audit.issues)
    found = "no issues" if not issues else f"{issues} suggestion{'s' if issues > 1 else ''} for improvement"
    return f"Score <b>{audit.score:g} / 100</b> - {found}."


def generate_with_progress(project: Project) -> bool:
    """Run every unfinished step with a live, friendly progress view. Returns True on success."""
    settings, client = llm()
    st.markdown(f"### Building your lesson: *{project.inputs.title}*")
    bar = st.progress(0, text="Getting started...")
    boxes = {key: st.empty() for key, *_ in STAGES}
    tip_box, clock = st.empty(), st.empty()
    details: dict[str, str] = {}
    started = time.monotonic()

    def draw(active: str | None, failed: str | None = None) -> None:
        order = [key for key, *_ in STAGES]
        done_count = 0
        for key, icon, title, blurb in STAGES:
            if key == failed:
                state = "failed"
            elif key == active:
                state = "active"
            elif key in details:
                state, done_count = "done", done_count + 1
            else:
                state = "waiting"
            boxes[key].markdown(_stage_html(icon, title, state, details.get(key, blurb)),
                                unsafe_allow_html=True)
        label = (f"Step {min(done_count + 1, 4)} of 4 - {dict((k, t) for k, _, t, _ in STAGES)[active]}..."
                 if active else "All done!")
        bar.progress(done_count / len(order), text=label)
        tip_box.markdown(f'<div class="tip">{random.choice(TIPS)}</div>', unsafe_allow_html=True)
        clock.caption(f"⏱ {time.monotonic() - started:.0f} s elapsed - this usually takes 30-60 seconds.")

    # Steps already finished in an earlier attempt are shown as done.
    if project.step("research")["status"] == "done":
        details["research"] = _research_summary(project)
    if project.step("generation")["status"] == "done" and project.lesson():
        details["generation"] = _lesson_summary(project)

    try:
        if project.step("research")["status"] != "done":
            draw("research")
            project.run_research(client, settings)
            details["research"] = _research_summary(project)
        if project.step("generation")["status"] != "done":
            draw("generation")
            project.run_generation(client)
            details["generation"] = _lesson_summary(project)
        if project.step("qc")["status"] != "done":
            draw("qc1")
            boxes["qc2"].markdown(_stage_html("🎓", "Checking it teaches well", "active",
                                              "Runs together with the fact check."), unsafe_allow_html=True)
            project.run_qc(client, settings)
        details["qc1"], details["qc2"] = _qc_summary(project, 0), _qc_summary(project, 1)
        draw(None)
        tip_box.empty()
        st.balloons()
        return True
    except StepFailed as exc:
        failed = project.next_step()
        failed_key = "qc1" if failed == "qc" else failed
        draw(None, failed=failed_key)
        tip_box.empty()
        st.error(f"Something went wrong while **{failed}** was running. Everything finished before it "
                 f"is saved - press **Try again** to continue from this step.\n\n`{exc}`")
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
            st.markdown(f'<div class="objective">☐ {o.description}</div>', unsafe_allow_html=True)

    number = 0
    for s in sections:
        with st.container(border=True):
            st.markdown(f'<div class="section-head"><h4 style="margin:0">{s.title}</h4>'
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

with st.sidebar:
    st.markdown("## 🎓 AI Lesson Studio")
    if st.button("✨ New lesson", use_container_width=True, type="primary"):
        go(None)
    st.markdown("#### My lessons")
    for p in Project.list_all():
        ready = p.next_step() is None
        icon = "📗" if ready else ("⚠️" if any(s["status"] == "failed" for s in p.meta["steps"].values()) else "⏳")
        if st.button(f"{icon} {p.inputs.title}", key=f"open-{p.meta['project_id']}", use_container_width=True):
            go(p.meta["project_id"])

try:
    llm()
except LLMConfigError as exc:
    st.error(f"The AI is not configured: {exc}. Set LLM_API_KEY and LLM_MODEL in backend/.env.")
    st.stop()

project = current_project()

# ---------------------------------------------------------------- landing

if project is None:
    st.markdown('<div class="hero"><h1>What do you want to learn today?</h1>'
                '<p>Give a topic and a goal. We research trusted sources, write a lesson you can finish '
                'in 45 minutes, and double-check it for accuracy and teaching quality.</p></div>',
                unsafe_allow_html=True)
    st.markdown("**Try an example:**")
    cols = st.columns(len(EXAMPLES))
    for col, (t, o) in zip(cols, EXAMPLES):
        if col.button(f"💡 {t}", use_container_width=True):
            st.session_state["in_title"], st.session_state["in_objective"] = t, o
            st.rerun()

    with st.form("new"):
        title = st.text_input("📌 Lesson topic", key="in_title", placeholder="e.g. HTTP Requests and Responses")
        objective = st.text_area("🎯 What should you be able to do after the lesson?", key="in_objective",
                                 placeholder="e.g. Explain GET and POST methods and distinguish between "
                                             "2xx, 4xx, and 5xx response status categories.")
        level = st.select_slider("🎚 Your level", ["beginner", "intermediate", "advanced"], value="beginner")
        submitted = st.form_submit_button("🚀 Create my lesson", type="primary", use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.markdown("**🔎 Researched**  \nFrom Wikipedia, books and YouTube - with every fact traced to its source.")
    c2.markdown("**⏱ 45 minutes**  \nExplanations, examples, a hands-on activity and quizzes.")
    c3.markdown("**✅ Double-checked**  \nOne check for facts, one for teaching quality.")

    if submitted:
        try:
            new = Project.create(validate_inputs(title, objective, level))
        except InputError as exc:
            st.warning(f"Please check your input: {exc}")
            st.stop()
        st.session_state["project_id"] = new.meta["project_id"]
        if generate_with_progress(new):
            time.sleep(1.2)
            st.rerun()
    st.stop()

# ------------------------------------------------------------ lesson page

inputs = project.inputs
st.markdown(f'<div class="hero"><h1>{inputs.title}</h1><p>🎯 {inputs.objective}</p></div>',
            unsafe_allow_html=True)

if project.next_step():
    failed = any(s["status"] == "failed" for s in project.meta["steps"].values())
    if project.lesson() is None or project.next_step() != "qc" or failed:
        st.info("This lesson isn't finished yet. Your progress so far is saved.")
        if st.button("🔁 Try again" if failed else "▶ Continue", type="primary"):
            if generate_with_progress(project):
                time.sleep(1.2)
                st.rerun()
        if project.lesson() is None:
            st.stop()

lesson = project.lesson()
audits = project.audits()
research = project.research()
if project.step("qc")["status"] != "done":
    st.warning(f"Version {lesson.version} hasn't been quality-checked yet.")
    if st.button("✅ Run quality checks", type="primary"):
        if generate_with_progress(project):
            st.rerun()

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
