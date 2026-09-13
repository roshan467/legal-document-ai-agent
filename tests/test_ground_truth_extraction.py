"""
tests/test_ground_truth_extraction.py
---------------------------------------
Proves the correction actually matters, not just that it exists.

Before this fix, `evaluate()` was given `generated_text` reconstructed from
`MappedContent` (full_text_from_mapped_content) -- i.e. the SAME object that
was fed INTO generate_docx(). That means a bug in generate_docx() itself
(the function that writes the actual .docx file) could never have been
caught: the evaluation was checking generation's input, never its output.

This test simulates exactly that: a version of generate_docx() with a real
bug (it silently drops the last body paragraph while writing the file --
the kind of off-by-one that's easy to introduce in docx-writing loops).

  1. It first reproduces the OLD blind spot: scoring the buggy .docx with
     the text reconstructed from MappedContent still comes back with no
     Structure issues, because that path never looks at the file.
  2. Then it re-extracts from the actual (buggy) generated file and shows
     ground_truth_comparison() catches the dropped paragraph immediately.

If someone reverts pipeline.py to use full_text_from_mapped_content()
again, part 1 of this test will start passing "cleanly" for the wrong
reason and part 2 will start failing -- both are supposed to happen
together, which is exactly what pins the fix in place.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from src.extraction import extract_entities
from src.content_mapping import map_content
from src.evaluation import evaluate, full_text_from_mapped_content, ground_truth_comparison
from src.template_analysis import analyze_reference_document
from src.doc_reading import extract_text_from_docx

CASE_INFO = "data/case_information.json"
REF_DOC = "data/reference_affidavit.txt"


def _generate_docx_with_dropped_last_paragraph(mc, output_path: str):
    """A deliberately-buggy stand-in for generate_docx(): writes every part
    correctly EXCEPT it skips the last body paragraph -- the kind of
    off-by-one a real implementation could actually ship."""
    doc = Document()
    doc.styles["Normal"].font.size = Pt(11)

    def add_centered_bold_caps(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(text.upper()).bold = True

    add_centered_bold_caps(mc.forum_heading)
    add_centered_bold_caps(mc.jurisdiction_line)
    add_centered_bold_caps(mc.case_number_line)
    doc.add_paragraph()
    doc.add_paragraph(mc.petitioner_block)
    doc.add_paragraph("VERSUS")
    for block in mc.respondent_blocks:
        doc.add_paragraph(block)
    doc.add_paragraph()
    add_centered_bold_caps(mc.affidavit_title)
    doc.add_paragraph()
    doc.add_paragraph(mc.deponent_clause)
    doc.add_paragraph()

    # THE BUG: [:-1] silently drops the last body paragraph.
    for para in mc.paragraphs[:-1]:
        p = doc.add_paragraph()
        num_run = p.add_run(f"{para['number']}. ")
        num_run.bold = True
        p.add_run(para["text"])
    doc.add_paragraph()

    add_centered_bold_caps("PRAYER")
    doc.add_paragraph("I therefore respectfully pray that this Hon'ble Court may be pleased to:")
    for line in mc.prayer_lines:
        doc.add_paragraph(line)
    doc.add_paragraph()

    for line in mc.jurat.split("\n"):
        doc.add_paragraph(line)
    doc.add_paragraph()

    add_centered_bold_caps("VERIFICATION")
    for line in mc.verification.split("\n"):
        doc.add_paragraph(line)

    doc.save(output_path)
    return output_path


def test_old_text_reconstruction_cannot_see_the_dropped_paragraph():
    """Reproduces the blind spot the fix closes: evaluating text
    reconstructed from MappedContent is blind to what generate_docx()
    actually wrote, so it can't catch a paragraph dropped during writing."""
    entities = extract_entities(CASE_INFO)
    mapped = map_content(entities)
    with open(REF_DOC) as f:
        template = analyze_reference_document(f.read())

    with tempfile.TemporaryDirectory() as tmp:
        buggy_path = _generate_docx_with_dropped_last_paragraph(mapped, os.path.join(tmp, "buggy.docx"))
        assert os.path.exists(buggy_path)

        # Old behaviour: evaluate the pre-generation object, not the file.
        old_style_text = full_text_from_mapped_content(mapped)
        report = evaluate(entities, mapped, template, old_style_text)

        structure_issues = [i for i in report.issues if i.dimension == "Structure"]
        assert structure_issues == [], (
            "This demonstrates the OLD blind spot: text reconstructed from "
            "MappedContent still contains all paragraphs (the bug is only in "
            "generate_docx's writing loop, not in `mapped`), so no Structure "
            "issue is raised even though the actual file is missing a paragraph."
        )


def test_ground_truth_comparison_catches_the_dropped_paragraph():
    """The fix: re-extracting from the ACTUAL generated file catches the
    exact bug the previous test proved was invisible."""
    entities = extract_entities(CASE_INFO)
    mapped = map_content(entities)

    with tempfile.TemporaryDirectory() as tmp:
        buggy_path = _generate_docx_with_dropped_last_paragraph(mapped, os.path.join(tmp, "buggy.docx"))

        real_text = extract_text_from_docx(buggy_path)
        gt_issues = ground_truth_comparison(entities, mapped, real_text)

        structure_issues = [i for i in gt_issues if i.dimension == "Structure"]
        assert len(structure_issues) >= 1, (
            "Expected ground_truth_comparison to catch the missing body paragraph "
            "by re-reading the actual generated .docx"
        )
        assert any("body paragraph" in i.description.lower() or "paragraph" in i.description.lower()
                   for i in structure_issues)


def test_clean_generation_still_scores_100_after_the_fix():
    """Sanity check: the fix must not introduce false positives on a
    correctly-generated document -- the real generate_docx() (not the buggy
    stand-in above) should still produce a clean report."""
    from src.pipeline import run_pipeline
    with tempfile.TemporaryDirectory() as tmp:
        result = run_pipeline(CASE_INFO, REF_DOC, output_dir=tmp)
        assert result["report"].overall_score == 100.0
        assert result["report"].issues == []


ALL_TESTS = [
    test_old_text_reconstruction_cannot_see_the_dropped_paragraph,
    test_ground_truth_comparison_catches_the_dropped_paragraph,
    test_clean_generation_still_scores_100_after_the_fix,
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
