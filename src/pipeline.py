"""
End-to-end orchestrator: Reference Document -> Template Analysis
                          Case Information  -> Entity Extraction
                          -> Content Mapping -> Document Generation
                          -> Evaluation -> Report

Mirrors the workflow diagram in the assignment brief (Section 9).
"""
import json
import os
from src.extraction import extract_entities
from src.template_analysis import analyze_reference_document
from src.content_mapping import map_content
from src.generation import generate_docx
from src.evaluation import evaluate
from src.doc_reading import extract_text_from_docx


def run_pipeline(case_info_path: str, reference_doc_path: str, output_dir: str = "outputs"):
    os.makedirs(output_dir, exist_ok=True)

    # Stage 1: Template / document understanding
    with open(reference_doc_path) as f:
        ref_text = f.read()
    template = analyze_reference_document(ref_text)

    # Stage 2: Entity extraction
    entities = extract_entities(case_info_path)

    # Stage 3: Content mapping
    mapped = map_content(entities)

    # Stage 4: Document generation
    docx_path = os.path.join(output_dir, "generated_affidavit.docx")
    generate_docx(mapped, docx_path)

    # Stage 5a: Entity / Structure Extraction FROM THE GENERATED FILE.
    # This is the correction: previously `generated_text` was a text
    # reconstruction of `mapped` (the object that fed generation.py), which
    # meant the evaluation below could never detect a bug in generation.py
    # itself. Reading the actual .docx closes that gap -- see doc_reading.py.
    generated_text = extract_text_from_docx(docx_path)

    # Stage 5b & 6: Validation / evaluation + report
    report = evaluate(entities, mapped, template, generated_text)

    report_json_path = os.path.join(output_dir, "evaluation_report.json")
    with open(report_json_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    report_md_path = os.path.join(output_dir, "evaluation_report.md")
    with open(report_md_path, "w") as f:
        f.write(report.to_markdown())

    return {
        "docx_path": docx_path,
        "report_json_path": report_json_path,
        "report_md_path": report_md_path,
        "template": template,
        "entities": entities,
        "mapped": mapped,
        "report": report,
        "generated_text": generated_text,
    }


if __name__ == "__main__":
    result = run_pipeline("data/case_information.json", "data/reference_affidavit.txt")
    print(f"Generated document: {result['docx_path']}")
    print(f"Evaluation report (JSON): {result['report_json_path']}")
    print(f"Evaluation report (Markdown): {result['report_md_path']}")
    print(f"\nOverall score: {result['report'].overall_score:.1f}/100")
