"""
tests/test_extended_checks.py
-------------------------------
Proves two more corrections requested in review:

1. Hallucination detection previously only scanned for extraneous dates.
   `check_hallucinated_entities()` extends this to names, organisations,
   designations, case number, and year -- reproduces the reviewer's exact
   example (petitioner silently renamed from "Sunrise Housing Private
   Limited" to "Sunrise Housing Developers Private Limited") and confirms
   it's caught.

2. Template Fidelity previously only checked presence flags against
   `mapped` (the pre-generation object). `ground_truth_comparison()` now
   also parses the GENERATED text with the exact same parser used on the
   reference document (`analyze_reference_document`) and compares
   structures directly -- this test corrupts a structural marker in the
   real generated text (renames the PRAYER heading) and confirms it's
   caught by comparing reference-vs-output, not by re-checking `mapped`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from src.extraction import extract_entities
from src.content_mapping import map_content
from src.evaluation import check_hallucinated_entities, ground_truth_comparison
from src.doc_reading import extract_text_from_docx
from src.pipeline import run_pipeline

CASE_INFO = "data/case_information.json"
REF_DOC = "data/reference_affidavit.txt"


def _real_generated_text():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = run_pipeline(CASE_INFO, REF_DOC, output_dir=tmp)
        return extract_text_from_docx(result["docx_path"])


def test_extended_hallucination_check_is_clean_on_real_output():
    entities = extract_entities(CASE_INFO)
    text = _real_generated_text()
    assert check_hallucinated_entities(entities, text) == []


def test_extended_hallucination_check_catches_renamed_petitioner():
    """Reproduces the reviewer's exact example: 'Sunrise Housing Private
    Limited' silently becomes 'Sunrise Housing Developers Private Limited'
    in the generated text. The old date-only hallucination check could not
    have seen this (it isn't a date); the extended check must."""
    entities = extract_entities(CASE_INFO)
    text = _real_generated_text()
    corrupted = text.replace("Sunrise Housing Private Limited", "Sunrise Housing Developers Private Limited")

    issues = check_hallucinated_entities(entities, corrupted)
    assert len(issues) >= 1
    assert any("Sunrise Housing Private Limited" in i.description for i in issues)
    assert all(i.dimension == "Hallucination" for i in issues)


def test_extended_hallucination_check_catches_altered_case_number():
    entities = extract_entities(CASE_INFO)
    text = _real_generated_text()
    corrupted = text.replace(entities.case_number, "9999")
    issues = check_hallucinated_entities(entities, corrupted)
    assert any("case number" in i.description.lower() for i in issues)


def test_template_fidelity_reference_vs_generated_comparison_is_clean_on_real_output():
    entities = extract_entities(CASE_INFO)
    mapped = map_content(entities)
    text = _real_generated_text()
    issues = ground_truth_comparison(entities, mapped, text)
    fidelity_issues = [i for i in issues if i.dimension == "Template Fidelity"]
    assert fidelity_issues == []


def test_template_fidelity_catches_renamed_prayer_heading_in_generated_text():
    """Corrupts a structural marker directly in the GENERATED text (not in
    `mapped`) -- this can only be caught by re-parsing the actual output,
    which is exactly what this correction added."""
    entities = extract_entities(CASE_INFO)
    mapped = map_content(entities)
    text = _real_generated_text()
    corrupted = text.replace("PRAYER", "REQUEST FOR RELIEF")

    issues = ground_truth_comparison(entities, mapped, corrupted)
    fidelity_issues = [i for i in issues if i.dimension == "Template Fidelity"]
    assert len(fidelity_issues) >= 1, (
        "Expected the reference-vs-generated structural comparison to catch "
        "the renamed PRAYER heading in the actual generated text"
    )


ALL_TESTS = [
    test_extended_hallucination_check_is_clean_on_real_output,
    test_extended_hallucination_check_catches_renamed_petitioner,
    test_extended_hallucination_check_catches_altered_case_number,
    test_template_fidelity_reference_vs_generated_comparison_is_clean_on_real_output,
    test_template_fidelity_catches_renamed_prayer_heading_in_generated_text,
]

if __name__ == "__main__":
    passed, failed = 0, 0
    for test in ALL_TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
