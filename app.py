"""
Streamlit frontend for the Legal Document Generation & Evaluation Agent.

Run locally with:  streamlit run app.py
"""
import json
import streamlit as st
from src.extraction import extract_entities
from src.template_analysis import analyze_reference_document
from src.content_mapping import map_content
from src.generation import generate_docx
from src.evaluation import evaluate, full_text_from_mapped_content

st.set_page_config(page_title="Legal Document Generation & Evaluation Agent", layout="wide")

st.title("Legal Document Generation & Evaluation Agent")
st.caption(
    "Extracts structured entities \u2192 analyzes a reference document's structure \u2192 "
    "generates a new Affidavit in Reply \u2192 evaluates it against the ground truth. "
    "Supports **Affidavit in Reply** only (scoped per the assignment)."
)

with st.expander("How this works (architecture)", expanded=False):
    st.markdown("""
```
Reference Document  ->  Template / Structure Analysis  \\
                                                          -> Content Mapping -> Document Generation
Case Information     -> Entity Extraction               /                            |
                                                                                       v
                                                                     Evaluation (vs. ground truth)
                                                                                       |
                                                                                       v
                                                                       Evaluation Score + Report
```
    All extraction, mapping, and evaluation logic is **deterministic (rule-based)** —
    not LLM-graded — so every score is reproducible and traceable to a specific rule
    in the format specification. See the README for full design rationale.
    """)

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Reference Document")
    st.caption("The sample Affidavit in Reply used as the format reference.")
    use_sample_ref = st.checkbox("Use bundled sample reference document", value=True)
    if use_sample_ref:
        with open("data/reference_affidavit.txt") as f:
            ref_text = f.read()
        st.text_area("Reference document (read-only preview)", ref_text, height=200, disabled=True)
    else:
        uploaded_ref = st.file_uploader("Upload a reference Affidavit in Reply (.txt)", type=["txt"])
        ref_text = uploaded_ref.read().decode("utf-8") if uploaded_ref else None

with col2:
    st.subheader("2. Case Information")
    st.caption("The facts, parties, and reply points for the affidavit to generate.")
    use_sample_case = st.checkbox("Use bundled sample case information", value=True)
    if use_sample_case:
        with open("data/case_information.json") as f:
            case_json_text = f.read()
        st.text_area("Case information (read-only preview)", case_json_text, height=200, disabled=True)
    else:
        uploaded_case = st.file_uploader("Upload case information (.json)", type=["json"])
        case_json_text = uploaded_case.read().decode("utf-8") if uploaded_case else None

st.divider()

if st.button("Generate Affidavit & Evaluate", type="primary", use_container_width=True):
    if not ref_text or not case_json_text:
        st.error("Please provide both a reference document and case information.")
        st.stop()

    with st.spinner("Running pipeline: extraction \u2192 mapping \u2192 generation \u2192 evaluation..."):
        # Stage 1: Template analysis
        template = analyze_reference_document(ref_text)

        # Stage 2: Entity extraction (write uploaded case info to a temp path if needed)
        case_data = json.loads(case_json_text)
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(case_data, tmp)
            tmp_path = tmp.name
        entities = extract_entities(tmp_path)
        os.unlink(tmp_path)

        # Stage 3: Content mapping
        mapped = map_content(entities)

        # Stage 4: Document generation
        docx_path = "outputs/generated_affidavit_streamlit.docx"
        generate_docx(mapped, docx_path)

        # Stage 5 & 6: Evaluation + report
        gen_text = full_text_from_mapped_content(mapped)
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
        st.subheader(f"Overall Score: {report.overall_score:.1f} / 100")
        score_cols = st.columns(len(report.scores))
        for col, (dim, score) in zip(score_cols, report.scores.items()):
            col.metric(dim, f"{score:.0f}/100")

        st.markdown("### Issues Detected")
        if not report.issues:
            st.info("No issues detected.")
        else:
            for issue in report.issues:
                severity_color = {"high": "\U0001F534", "medium": "\U0001F7E1", "low": "\U0001F7E2"}
                st.markdown(
                    f"{severity_color.get(issue.severity, '')} **[{issue.dimension}]** "
                    f"{issue.description}  \n_Source: {issue.source}_"
                )

        st.markdown("### Scoring Explanation")
        st.write(report.explanation)

        st.download_button(
            "Download evaluation report (JSON)",
            json.dumps(report.to_dict(), indent=2),
            file_name="evaluation_report.json", mime="application/json"
        )
        st.download_button(
            "Download evaluation report (Markdown)",
            report.to_markdown(),
            file_name="evaluation_report.md", mime="text/markdown"
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

st.divider()
st.caption("Built for the Brainwonders AI Internship assignment \u2014 Legal Document Generation & Evaluation Agent.")
