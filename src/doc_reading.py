"""
Stage 5a: Entity / Structure Extraction from the GENERATED document.

Per the assignment's Section 9 workflow diagram:

    Generated Affidavit in Reply
      |
    Entity / Structure Extraction
      |
    Ground Truth Comparison
      |
    Evaluation Score + Error Report

Before this module existed, evaluation.py's six dimensions all read fields
off `MappedContent` -- the exact object that was fed INTO generation.py to
produce the .docx -- and `full_text_from_mapped_content()` reconstructed a
plain-text version of that same object rather than reading the file that
was actually written to disk. That means every check was really asking
"did the content-mapping stage produce the right data?", never "did the
generation stage correctly write that data into the file a reviewer will
actually open?" A bug in generation.py itself -- a dropped paragraph, a
mis-rendered heading, a garbled respondent number introduced while writing
docx runs -- could not have been caught by that evaluation, because it
never looked at the generated file. See
tests/test_ground_truth_extraction.py for a reproduction: it deliberately
breaks generate_docx() to drop the last body paragraph and shows the old
(mapped-content-only) evaluation still scores 100/100, while re-extraction
from the real file catches it immediately.

This module closes that gap: it independently re-derives the same facts by
reading the actual .docx bytes, so `ground_truth_comparison()` in
evaluation.py can check the delivered artefact, not just its own blueprint.
"""

import re
from docx import Document


def extract_text_from_docx(path: str) -> str:
    """The ONLY reliable way to know what a .docx actually contains is to
    open it and read it -- reconstructing text from the pre-generation
    object (as the old full_text_from_mapped_content() did) tells you what
    SHOULD be in the file, not what IS in it."""
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_structure(text: str) -> dict:
    """Re-derive the same structural facts evaluation.py needs, but from
    real document text instead of from MappedContent fields."""
    paragraph_numbers = [
        int(n) for n in re.findall(
            r"^(\d+)\.\s+(?:I say|At the outset|With reference|In the premises)",
            text, re.MULTILINE,
        )
    ]
    respondent_mentions = re.findall(r"Respondent\s*No\.?\s*(\d+)", text)
    verification_match = re.search(r"paragraphs (\d+ to \d+)", text)
    exhibit_labels = re.findall(r"EXHIBIT-'([A-Z])'", text)
    return {
        "paragraph_numbers": paragraph_numbers,
        "respondent_mentions": respondent_mentions,
        "verification_range": verification_match.group(1) if verification_match else None,
        "exhibit_labels": exhibit_labels,
        "has_prayer": bool(re.search(r"^PRAYER$", text, re.MULTILINE)),
        "has_verification": bool(re.search(r"^VERIFICATION$", text, re.MULTILINE)),
    }
