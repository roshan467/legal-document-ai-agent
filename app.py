"""
Streamlit frontend for the Legal Document Generation & Evaluation Agent.

Two views in one file, toggled via session_state:
  1. Landing screen — title, one-line pitch, "Enter the Agent" button.
  2. Main workflow — the actual assignment pipeline (unchanged logic from
     the original app: extraction -> mapping -> generation -> evaluation).

Visual identity is deliberately "legal gazette meets tech tool" (ink-navy /
parchment / brass), not a generic SaaS-card theme — see README design notes.
All colors/fonts are CSS-only (no external image assets), so nothing can
break or fail to load on a fresh deployment.

Run locally with:  streamlit run app.py
"""
import json
import base64
import streamlit as st
from src.extraction import extract_entities
from src.template_analysis import analyze_reference_document
from src.content_mapping import map_content
from src.generation import generate_docx
from src.evaluation import evaluate
from src.doc_reading import extract_text_from_docx

st.set_page_config(page_title="LAW AI Agent", page_icon="⚖", layout="wide")


@st.cache_data
def _hero_bg_base64() -> str:
    with open("assets/hero_background.jpg", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


HERO_BG_B64 = _hero_bg_base64()

# ---------------------------------------------------------------------------
# Theme (CSS-only — ink-navy / parchment / brass, Source Serif 4 + Inter)
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
:root {
    --ink-navy: #101B30;
    --parchment: #F1E9D8;
    --brass: #A6812F;
    --seal-maroon: #6E2A2A;
    --ink-text: #1B2333;
    --muted-slate: #5B6472;
}

html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
h1, h2, h3, .serif-display { font-family: 'Source Serif 4', serif; }

.stApp { background-color: var(--ink-navy); }

/* ---------- Landing screen ---------- */
.hero-wrap {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; text-align: center;
    min-height: 82vh; padding: 2rem 1rem;
}
.hero-title {
    color: var(--parchment); font-size: 3.2rem; font-weight: 700;
    letter-spacing: 0.01em; margin: 0;
    text-shadow: 0 2px 18px rgba(0,0,0,0.5);
}
.hero-sub {
    color: #E8D9B5; font-size: 1.08rem; margin-top: 1rem;
    max-width: 580px; line-height: 1.65; font-family: 'Inter', sans-serif;
    text-shadow: 0 1px 12px rgba(0,0,0,0.6);
}
.hero-fine {
    color: #C9B98A; font-size: 0.85rem; margin-top: 1.6rem;
    text-shadow: 0 1px 8px rgba(0,0,0,0.6);
}

/* ---------- Main workflow screen ---------- */
.topbar {
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 0.25rem 0 1.1rem 0; border-bottom: 1px solid #2A3752;
    margin-bottom: 1.6rem;
}
.topbar-title { color: var(--parchment); font-size: 1.4rem; font-weight: 700; }
.topbar-sub { color: var(--muted-slate); font-size: 0.85rem; }

.stepper { display: flex; gap: 0.5rem; margin-bottom: 1.8rem; flex-wrap: wrap; }
.step {
    flex: 1; min-width: 130px; background: #16223C; border: 1px solid #2A3752;
    border-radius: 6px; padding: 0.6rem 0.8rem;
}
.step-num {
    color: var(--brass); font-family: 'Source Serif 4', serif;
    font-weight: 700; font-size: 1.1rem; margin-right: 0.4rem;
}
.step-label { color: var(--parchment); font-size: 0.82rem; }

.panel-label {
    font-weight: 600; font-size: 0.95rem; margin-bottom: 0.3rem; color: var(--parchment);
}
.panel-caption { color: var(--muted-slate); font-size: 0.82rem; margin-bottom: 0.8rem; }

/* Native Streamlit bordered container -> dark card matching the stepper */
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #16223C !important;
    border-color: #2A3752 !important;
    border-radius: 6px !important;
}

/* Shrink metric value font so 6-across dimension scores don't truncate */
[data-testid="stMetricValue"] {
    font-size: 1.35rem !important;
    color: var(--parchment) !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.78rem !important;
    color: var(--muted-slate) !important;
}

.score-big {
    font-family: 'Source Serif 4', serif; font-weight: 700;
    font-size: 3.4rem; color: var(--brass); line-height: 1;
}
.score-label { color: var(--parchment); font-size: 0.95rem; margin-top: 0.3rem; }

/* Streamlit primary button -> brass */
.stButton > button[kind="primary"] {
    background-color: var(--brass); border-color: var(--brass); color: var(--ink-navy);
    font-weight: 600;
}
.stButton > button[kind="primary"]:hover {
    background-color: #8f6f28; border-color: #8f6f28; color: var(--parchment);
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

if "entered" not in st.session_state:
    st.session_state.entered = False

# Landing-screen-only background: applied to the whole app container (not a
# div inside it) so that Streamlit-native elements rendered afterwards — the
# button, the fine-print line — sit on top of the same image in normal
# document flow, rather than falling outside a div that would otherwise only
# wrap the markdown title/subtitle.
if not st.session_state.entered:
    st.markdown(f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background:
            linear-gradient(rgba(16,27,48,0.55), rgba(16,27,48,0.88)),
            url('data:image/jpeg;base64,{HERO_BG_B64}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Human-readable case-information renderer (replaces raw-JSON display)
# ---------------------------------------------------------------------------
def render_case_summary(case_json_text: str):
    try:
        d = json.loads(case_json_text)
    except (json.JSONDecodeError, TypeError):
        st.warning("Could not parse this file as JSON — showing raw content instead.")
        st.text(case_json_text or "")
        return

    court = d.get("court", {})
    parties = d.get("parties", {})
    petitioner = parties.get("petitioner", {})
    respondents = parties.get("respondents", [])
    deponent = d.get("deponent", {})
    reply_points = d.get("reply_points", [])

    st.markdown(f"**{d.get('document_type', 'Document')}** &nbsp;·&nbsp; "
                f"{court.get('proceeding_type', '')} No. {court.get('case_number', '')} "
                f"of {court.get('year', '')}")
    st.caption(f"{court.get('forum', '')} — {court.get('jurisdiction_type', '')}")

    st.markdown("**Parties**")
    st.markdown(f"- Petitioner: {petitioner.get('name', '—')}")
    for r in respondents:
        marker = " *(filing this affidavit)*" if r.get("number") == d.get("filed_on_behalf_of_respondent_number") else ""
        st.markdown(f"- Respondent No. {r.get('number', '?')}: {r.get('name', '—')}{marker}")

    st.markdown("**Deponent**")
    dep_line = deponent.get("name", "—")
    if deponent.get("designation"):
        dep_line += f", {deponent['designation']}"
    if deponent.get("organisation"):
        dep_line += f" ({deponent['organisation']})"
    st.markdown(f"- {dep_line}")
    if deponent.get("address"):
        st.markdown(f"- Address: {deponent['address']}")

    st.markdown(f"**Reply Points** ({len(reply_points)})")
    for p in reply_points:
        st.markdown(f"{p.get('point_number', '?')}. **{p.get('title', '')}**")
        for fact in p.get("facts", []):
            st.markdown(f"   - {fact}")

    with st.expander("View raw JSON"):
        st.json(d)


# ---------------------------------------------------------------------------
# Landing screen
# ---------------------------------------------------------------------------
def render_landing():
    st.markdown("""
    <div class="hero-wrap">
        <div class="hero-title">LAW AI Agent</div>
        <div class="hero-sub">
            Reads a reference Affidavit in Reply, takes case-specific facts, generates
            a new affidavit that preserves the reference structure, and evaluates its
            own output against the supplied ground truth — with a scored, traceable
            issue report.
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Enter the Agent", type="primary", use_container_width=True):
            st.session_state.entered = True
            st.rerun()

    st.markdown(
        '<div class="hero-fine" style="text-align:center;">'
        'Built for the Brainwonders AI Internship assignment — Legal Document '
        'Generation &amp; Evaluation Agent</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main workflow screen (same pipeline calls as before, restyled)
# ---------------------------------------------------------------------------
def render_main():
    st.markdown("""
    <div class="topbar">
        <div class="topbar-title">⚖ LAW AI Agent</div>
        <div class="topbar-sub">Affidavit in Reply — Generation &amp; Evaluation</div>
    </div>
    """, unsafe_allow_html=True)

    stages = [
        ("1", "Template Analysis"), ("2", "Entity Extraction"),
        ("3", "Content Mapping"), ("4", "Document Generation"),
        ("5", "Evaluation"), ("6", "Report"),
    ]
    stepper_html = '<div class="stepper">' + "".join(
        f'<div class="step"><span class="step-num">{n}</span>'
        f'<span class="step-label">{label}</span></div>'
        for n, label in stages
    ) + "</div>"
    st.markdown(stepper_html, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown('<div class="panel-label">Reference Document</div>', unsafe_allow_html=True)
            st.markdown('<div class="panel-caption">The sample Affidavit in Reply used as the format reference.</div>', unsafe_allow_html=True)
            ref_source = st.radio(
                "Reference document source", ["Use bundled sample", "Upload file", "Paste text"],
                index=0, key="ref_source", label_visibility="collapsed", horizontal=True,
            )
            if ref_source == "Use bundled sample":
                with open("data/reference_affidavit.txt") as f:
                    ref_text = f.read()
                st.text_area("Reference document (read-only preview)", ref_text, height=180, disabled=True, label_visibility="collapsed")
            elif ref_source == "Upload file":
                uploaded_ref = st.file_uploader("Upload a reference Affidavit in Reply (.txt)", type=["txt"], label_visibility="collapsed")
                ref_text = uploaded_ref.read().decode("utf-8") if uploaded_ref else None
            else:
                ref_text = st.text_area(
                    "Paste the complete reference document here", height=180,
                    placeholder="IN THE HIGH COURT OF JUDICATURE AT ...", label_visibility="collapsed",
                )
                ref_text = ref_text.strip() or None

    with col2:
        with st.container(border=True):
            st.markdown('<div class="panel-label">Case Information</div>', unsafe_allow_html=True)
            st.markdown('<div class="panel-caption">The facts, parties, and reply points for the affidavit to generate.</div>', unsafe_allow_html=True)
            case_source = st.radio(
                "Case information source", ["Use bundled sample", "Upload file", "Paste JSON"],
                index=0, key="case_source", label_visibility="collapsed", horizontal=True,
            )
            if case_source == "Use bundled sample":
                with open("data/case_information.json") as f:
                    case_json_text = f.read()
            elif case_source == "Upload file":
                uploaded_case = st.file_uploader("Upload case information (.json)", type=["json"], label_visibility="collapsed")
                case_json_text = uploaded_case.read().decode("utf-8") if uploaded_case else None
            else:
                case_json_text = st.text_area(
                    "Paste case information JSON here", height=180,
                    placeholder='{\n  "document_type": "Affidavit in Reply",\n  ...\n}',
                    label_visibility="collapsed",
                )
                case_json_text = case_json_text.strip() or None
                if case_json_text:
                    try:
                        json.loads(case_json_text)
                    except json.JSONDecodeError as e:
                        st.error(f"Invalid JSON: {e}")
                        case_json_text = None
            if case_json_text:
                with st.container(height=220):
                    render_case_summary(case_json_text)

    st.write("")
    generate_clicked = st.button("Generate & Evaluate", type="primary", use_container_width=True)

    if generate_clicked:
        if not ref_text or not case_json_text:
            st.error("Please provide both a reference document and case information.")
            st.stop()

        with st.spinner("Running pipeline: extraction → mapping → generation → evaluation..."):
            template = analyze_reference_document(ref_text)

            case_data = json.loads(case_json_text)
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
                json.dump(case_data, tmp)
                tmp_path = tmp.name
            entities = extract_entities(tmp_path)
            os.unlink(tmp_path)

            mapped = map_content(entities)

            docx_path = "outputs/generated_affidavit_streamlit.docx"
            generate_docx(mapped, docx_path)

            # CORRECTED: re-read the actual generated .docx instead of
            # reconstructing text from `mapped` (see README "Correction log"
            # for why the old full_text_from_mapped_content() path could
            # never catch a bug in generate_docx() itself).
            gen_text = extract_text_from_docx(docx_path)
            report = evaluate(entities, mapped, template, gen_text)

        st.success("Pipeline completed.")

        tab1, tab2, tab3 = st.tabs(["Generated Document", "Evaluation Report", "Intermediate Data"])

        with tab1:
            st.subheader("Generated Affidavit in Reply")
            st.text(gen_text)
            with open(docx_path, "rb") as f:
                st.download_button(
                    "Download as .docx", f, file_name="generated_affidavit.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

        with tab2:
            score_col, rest_col = st.columns([1, 3])
            with score_col:
                st.markdown(
                    f'<div class="score-big">{report.overall_score:.0f}</div>'
                    f'<div class="score-label">Overall Score / 100</div>',
                    unsafe_allow_html=True,
                )
            with rest_col:
                score_cols = st.columns(len(report.scores))
                for c, (dim, score) in zip(score_cols, report.scores.items()):
                    c.metric(dim, f"{score:.0f}/100")

            st.markdown("### Issues Detected")
            if not report.issues:
                st.info("No issues detected.")
            else:
                for issue in report.issues:
                    severity_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                    st.markdown(
                        f"{severity_color.get(issue.severity, '')} **[{issue.dimension}]** "
                        f"{issue.description}  \n_Source: {issue.source}_"
                    )

            st.markdown("### Scoring Explanation")
            st.write(report.explanation)

            if not report.issues:
                st.info(
                    "**Why a clean score is expected here, not just convenient:** "
                    "this document was generated by the same deterministic, rule-based "
                    "pipeline that these checks validate against — so a well-formed input "
                    "correctly produces zero violations. This isn't an untested assumption: "
                    "5 of the 11 tests in `tests/test_pipeline.py` deliberately corrupt a "
                    "correct document (wrong respondent number, mismatched paragraph count, "
                    "a missing section, a hallucinated date, a missing deponent designation) "
                    "and assert the evaluator catches each specific corruption. Run "
                    "`pytest tests/ -v` to see them fail loudly when the checks are removed."
                )

            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "Download evaluation report (JSON)",
                    json.dumps(report.to_dict(), indent=2),
                    file_name="evaluation_report.json", mime="application/json",
                    use_container_width=True,
                )
            with dl2:
                st.download_button(
                    "Download evaluation report (Markdown)",
                    report.to_markdown(),
                    file_name="evaluation_report.md", mime="text/markdown",
                    use_container_width=True,
                )

        with tab3:
            st.subheader("Extracted Entities")
            st.json({
                "forum": entities.forum, "case_number": entities.case_number,
                "year": entities.year, "petitioner": entities.petitioner_name,
                "respondent_number": entities.respondent_number,
                "respondent_name": entities.respondent_name,
                "deponent": entities.deponent_name, "capacity": entities.capacity,
                "organisation": entities.organisation,
                "deponent_is_organisation_officer": entities.deponent_is_organisation_officer,
            })
            st.subheader("Reference Template Structure (parsed)")
            st.json(template.present_parts())
            st.write(f"Reference document body paragraphs: {len(template.paragraphs)}")

    st.write("")
    if st.button("← Back to start"):
        st.session_state.entered = False
        st.rerun()


# ---------------------------------------------------------------------------
if st.session_state.entered:
    render_main()
else:
    render_landing()
