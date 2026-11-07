"""AI Lesson Studio - instructor app.

Run from the backend folder:
    streamlit run streamlit_app.py
"""

import json

import streamlit as st

from app.core.config import get_settings
from app.llm.base import LLMConfigError
from app.llm.factory import create_llm_client
from app.modules.qc.enums import ReleaseDecision, severity_rank
from app.modules.qc.reporting import render_audit_report
from app.generation.render import render_lesson_markdown
from app.workflow import InputError, Project, StepFailed, validate_inputs

st.set_page_config(page_title="AI Lesson Studio", layout="wide")

STEP_LABEL = {"research": "1. Research", "generation": "2. Lesson generation", "qc": "3. Quality control"}
STATUS_ICON = {"done": "✅", "failed": "❌", "running": "⏳", "pending": "⬜"}
DECISION_STYLE = {
    ReleaseDecision.ELIGIBLE: ("success", "Eligible for instructor review: no blocking problems"),
    ReleaseDecision.REVISION_REQUIRED: ("warning", "Revision required: fix the high-severity issues"),
    ReleaseDecision.MANUAL_REVIEW: ("info", "Manual review: QC could not decide some points"),
    ReleaseDecision.BLOCKED: ("error", "Blocked: a hard rule failed"),
}


@st.cache_resource
def llm():
    settings = get_settings()
    return settings, create_llm_client(settings)


def open_project(project_id: str | None) -> None:
    st.session_state["project_id"] = project_id
    st.rerun()


def current_project() -> Project | None:
    pid = st.session_state.get("project_id")
    return next((p for p in Project.list_all() if p.meta["project_id"] == pid), None) if pid else None


def run_with_status(project: Project) -> None:
    settings, client = llm()
    with st.status("Working...", expanded=True) as box:
        try:
            project.run_remaining(client, settings, progress=lambda s: box.write(f"Running {STEP_LABEL[s]}..."))
            box.update(label="Done", state="complete")
        except StepFailed as exc:
            box.update(label="A step failed - your previous work is saved", state="error")
            st.error(str(exc))


# ----------------------------------------------------------------- sidebar

with st.sidebar:
    st.title("AI Lesson Studio")
    if st.button("➕ New lesson", use_container_width=True):
        open_project(None)
    st.subheader("Lessons")
    for p in Project.list_all():
        label = f"{p.inputs.title} (v{p.current_version or '-'})"
        if st.button(label, key=f"open-{p.meta['project_id']}", use_container_width=True):
            open_project(p.meta["project_id"])

try:
    llm()
except LLMConfigError as exc:
    st.error(f"LLM not configured: {exc}. Set LLM_API_KEY and LLM_MODEL in backend/.env.")
    st.stop()

project = current_project()

# --------------------------------------------------------------- new lesson

if project is None:
    st.header("Create a lesson")
    st.caption("Researches Wikipedia (websites), Open Library (books) and YouTube, writes a "
               "45-minute lesson, then checks it with two independent QC layers.")
    with st.form("new"):
        title = st.text_input("Lesson title", placeholder="HTTP Requests and Responses")
        objective = st.text_area("Learning objective", placeholder="Explain GET and POST methods and "
                                 "distinguish between 2xx, 4xx, and 5xx response status categories.")
        level = st.selectbox("Learner level", ["beginner", "intermediate", "advanced"])
        submitted = st.form_submit_button("Research and generate", type="primary")
    if submitted:
        try:
            new = Project.create(validate_inputs(title, objective, level))
        except InputError as exc:
            st.error(str(exc))
            st.stop()
        st.session_state["project_id"] = new.meta["project_id"]
        run_with_status(new)
        st.rerun()
    st.stop()

# ------------------------------------------------------------ project view

inputs = project.inputs
st.header(inputs.title)
st.caption(f"Objective: {inputs.objective} - level: {inputs.learner_level}")

cols = st.columns(4)
for col, name in zip(cols, STEP_LABEL):
    step = project.step(name)
    col.markdown(f"{STATUS_ICON[step['status']]} **{STEP_LABEL[name]}**")
    if step["status"] == "failed":
        col.caption(step["error"][:300])
if project.next_step():
    label = "🔁 Retry failed step" if project.step(project.next_step())["status"] == "failed" else "▶ Continue"
    if cols[3].button(label, type="primary"):
        run_with_status(project)
        st.rerun()

lesson = project.lesson()
if lesson is None:
    st.info("No lesson yet. Use the button above to run the remaining steps.")
    st.stop()

audits = project.audits()
if audits and audits[2]:
    kind, text = DECISION_STYLE[audits[2].decision]
    getattr(st, kind)(f"**Version {lesson.version}:** {text}. QC1 {audits[0].score} / 100, "
                      f"QC2 {audits[1].score} / 100")
elif project.step("qc")["status"] != "done":
    st.warning(f"Version {lesson.version} has not been checked by QC yet. Press Continue to run QC.")

research = project.research()
tabs = st.tabs(["👁 Preview", "🔎 QC1 factual", "🎓 QC2 instructional", "🛠 Apply recommendations",
                "✏️ Edit", "📚 Research", "⬇ Export", "🕘 History"])

with tabs[0]:
    st.markdown(render_lesson_markdown(lesson, research[0]))

for tab, index in ((tabs[1], 0), (tabs[2], 1)):
    with tab:
        if audits:
            st.markdown(render_audit_report(project.qc_input(), audits[index]))
        else:
            st.info("Run QC to see this report.")

with tabs[3]:
    if not audits:
        st.info("Run QC first.")
    else:
        dismissed = project.dismissed()
        issues = sorted(audits[0].issues + audits[1].issues, key=lambda i: -severity_rank(i.severity))
        open_issues = [i for i in issues if i.issue_id not in dismissed]
        if not open_issues:
            st.success("No open QC issues for this version.")
        selected = []
        for issue in open_issues:
            c1, c2 = st.columns([10, 1])
            fix = issue.recommendation.action if issue.recommendation else "-"
            if c1.checkbox(f"**{issue.issue_id} [{issue.severity}] {issue.issue_type}** - "
                           f"{issue.explanation}  \n*Suggested fix:* {fix}", key=f"sel-{lesson.version}-{issue.issue_id}"):
                selected.append(issue.issue_id)
            if c2.button("Dismiss", key=f"dis-{lesson.version}-{issue.issue_id}"):
                project.dismiss(issue.issue_id)
                st.rerun()
        note = st.text_area("Extra instruction for the AI (optional)",
                            placeholder="e.g. Add a real-world example about online shopping.")
        if st.button("Apply with AI → new version → re-run QC", type="primary"):
            settings, client = llm()
            with st.spinner("Revising and re-checking..."):
                try:
                    project.apply_recommendations(selected, note, client, settings)
                    st.rerun()
                except StepFailed as exc:
                    st.error(f"{exc} Your current version is unchanged.")

with tabs[4]:
    st.caption("Edits are saved as a new version; the old version stays in History. "
               "Run QC again after saving.")
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
            st.success(f"Saved version {saved.version}. Press Continue to run QC on it.")
            st.rerun()
        except InputError as exc:
            st.error(str(exc))

with tabs[5]:
    package, plan, _ = research
    st.markdown("**Research plan:** " + ", ".join(plan.key_concepts))
    for s in package.sources:
        with st.expander(f"{s.source_id} [{s.source_type}, {s.content_access}] {s.title}"):
            st.markdown(f"[{s.url}]({s.url})" if s.url else "no link")
            for p in s.evidence_passages:
                st.markdown(f"**{p.passage_id}** {p.text}")
    for limitation in package.limitations:
        st.caption("⚠ " + limitation)

with tabs[6]:
    st.caption(f"Exports version {lesson.version}.")
    st.download_button("⬇ Everything (zip)", project.export_zip(),
                       file_name=f"lesson-v{lesson.version}.zip", type="primary")
    for name, content in project.export_files().items():
        st.download_button(f"⬇ {name}", content, file_name=name, key=f"dl-{name}")

with tabs[7]:
    for entry in reversed(project.meta["versions"]):
        a = project.audits(entry["version"])
        decision = a[2].decision if a and a[2] else "not checked"
        st.markdown(f"**v{entry['version']}** - {entry['origin']} - {entry['created_at']} - "
                    f"QC: {decision}  \n{entry['note']}")
    old = st.selectbox("Preview an older version", [e["version"] for e in project.meta["versions"]][::-1])
    if old != lesson.version:
        st.markdown(render_lesson_markdown(project.lesson(old), research[0]))
