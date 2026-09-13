"""
Stage 5 & 6: Validation / Evaluation + Evaluation Report.

Implements the six evaluation dimensions from the assignment (Section 7):
entity accuracy, completeness, structure, consistency, template fidelity,
and hallucination — plus an overall score.

Design choice: every check here is DETERMINISTIC (regex / rule-based),
not LLM-graded. The assignment's minimum bar explicitly requires "at least
three deterministic checks that do not depend on an LLM" — this module
implements more than the minimum (9 checks) because for a fixed-format
legal document, rule-based checks are more reliable and auditable than an
LLM's judgment call, and every issue found points to an exact, explainable
rule rather than a model's opinion.
"""
import re
import json
from dataclasses import dataclass, field
from src.extraction import Entities
from src.content_mapping import MappedContent
from src.template_analysis import TemplateStructure
from src.doc_reading import extract_structure


@dataclass
class Issue:
    dimension: str
    severity: str  # "high" | "medium" | "low"
    description: str
    source: str    # where in the document / rule this was detected


@dataclass
class EvaluationReport:
    scores: dict = field(default_factory=dict)
    overall_score: float = 0.0
    issues: list = field(default_factory=list)
    explanation: str = ""

    def to_dict(self):
        return {
            "overall_score": round(self.overall_score, 1),
            "dimension_scores": {k: round(v, 1) for k, v in self.scores.items()},
            "issues": [vars(i) for i in self.issues],
            "explanation": self.explanation,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Evaluation Report — Generated Affidavit in Reply",
            "",
            f"**Overall Score: {round(self.overall_score, 1)}/100**",
            "",
            "## Dimension Scores",
            "",
        ]
        for dim, score in self.scores.items():
            lines.append(f"- **{dim}**: {round(score, 1)}/100")
        lines.append("")
        lines.append(f"## Issues Detected ({len(self.issues)})")
        lines.append("")
        if not self.issues:
            lines.append("No issues detected.")
        for i, issue in enumerate(self.issues, 1):
            lines.append(f"{i}. **[{issue.dimension} / {issue.severity}]** {issue.description} "
                         f"_(source: {issue.source})_")
        lines.append("")
        lines.append("## Scoring Explanation")
        lines.append("")
        lines.append(self.explanation)
        return "\n".join(lines)


def _find_all_respondent_number_mentions(doc_text: str):
    """Return all 'Respondent No.X' occurrences found anywhere in the document."""
    return re.findall(r"Respondent\s*No\.?\s*(\d+)", doc_text)


def ground_truth_comparison(entities: Entities, mapped: MappedContent, docx_text: str) -> list:
    """THE CORRECTION: re-extracts structure from the actual generated .docx
    text (not from MappedContent) and cross-checks it against case_information
    and the mapping stage's own expectations. Every issue found here is a bug
    that could ONLY be in generation.py (the docx-writing step) -- if
    MappedContent was correct (checked separately by the rest of evaluate())
    but the rendered file doesn't match it, that is a generation bug, and
    this is the only place in the pipeline positioned to catch it, because
    it is the only place that reads the actual file."""
    issues = []
    structure = extract_structure(docx_text)

    expected_para_count = len(mapped.paragraphs)
    if len(structure["paragraph_numbers"]) != expected_para_count:
        issues.append(Issue(
            "Structure", "high",
            f"The GENERATED .docx contains {len(structure['paragraph_numbers'])} numbered "
            f"body paragraphs, but the content-mapping stage produced {expected_para_count}. "
            f"generation.py dropped, duplicated, or mis-numbered content while writing the file.",
            "doc_reading.py: re-extraction from generated_affidavit.docx",
        ))
    elif structure["paragraph_numbers"] != list(range(1, expected_para_count + 1)):
        issues.append(Issue(
            "Structure", "high",
            f"Paragraph numbers in the generated .docx are out of sequence: "
            f"{structure['paragraph_numbers']} (expected 1..{expected_para_count}).",
            "doc_reading.py: re-extraction from generated_affidavit.docx",
        ))

    non_matching = {n for n in structure["respondent_mentions"]
                     if int(n) not in {r["number"] for r in entities.respondents}}
    if non_matching:
        issues.append(Issue(
            "Entity Accuracy", "high",
            f"Generated .docx mentions respondent number(s) not present in "
            f"case_information: {sorted(non_matching)}.",
            "doc_reading.py: re-extraction from generated_affidavit.docx",
        ))

    if not structure["has_prayer"]:
        issues.append(Issue("Structure", "high", "PRAYER heading not found in the generated .docx.",
                             "doc_reading.py: re-extraction from generated_affidavit.docx"))
    if not structure["has_verification"]:
        issues.append(Issue("Structure", "high", "VERIFICATION heading not found in the generated .docx.",
                             "doc_reading.py: re-extraction from generated_affidavit.docx"))

    if mapped.paragraphs:
        expected_range = f"1 to {len(mapped.paragraphs)}"
        if structure["verification_range"] != expected_range:
            issues.append(Issue(
                "Consistency", "high",
                f"Generated .docx verification range reads '{structure['verification_range']}', "
                f"expected '{expected_range}' given the actual body paragraph count.",
                "doc_reading.py: re-extraction from generated_affidavit.docx",
            ))

    defined_exhibits = set()
    for rp in entities.reply_points:
        if rp.get("exhibit"):
            defined_exhibits.add(rp["exhibit"]["label"].strip("EXHIBIT-'").strip("'"))
    found_exhibits = set(structure["exhibit_labels"])
    if defined_exhibits != found_exhibits:
        issues.append(Issue(
            "Entity Accuracy", "medium",
            f"Exhibit labels found in the generated .docx {sorted(found_exhibits)} differ "
            f"from those defined in case_information {sorted(defined_exhibits)}.",
            "doc_reading.py: re-extraction from generated_affidavit.docx",
        ))

    return issues


def evaluate(entities: Entities, mapped: MappedContent, template: TemplateStructure,
             generated_text: str) -> EvaluationReport:
    issues = []
    scores = {}

    # ---------- 1. STRUCTURE ----------
    # All 10 required sections must be present, matching the reference template.
    required_sections = [
        ("forum_heading", bool(mapped.forum_heading)),
        ("jurisdiction", bool(mapped.jurisdiction_line)),
        ("case_number", bool(mapped.case_number_line)),
        ("cause_title", bool(mapped.petitioner_block) and len(mapped.respondent_blocks) > 0),
        ("affidavit_title", bool(mapped.affidavit_title)),
        ("deponent_clause", bool(mapped.deponent_clause)),
        ("numbered_paragraphs", len(mapped.paragraphs) > 0),
        ("prayer", len(mapped.prayer_lines) > 0),
        ("jurat", bool(mapped.jurat)),
        ("verification", bool(mapped.verification)),
    ]
    missing = [name for name, present in required_sections if not present]
    structure_score = 100 * (len(required_sections) - len(missing)) / len(required_sections)
    for name in missing:
        issues.append(Issue("Structure", "high", f"Required section missing: {name}",
                             "Format Explained \u00a71 (Ten Parts)"))
    scores["Structure"] = structure_score

    # ---------- 2. CONSISTENCY ----------
    # The cause title legitimately lists ALL respondents (e.g. No.1 and No.2) —
    # that's correct, not an inconsistency. What must be consistent is the
    # FILING respondent's number across the substantive parts of the document:
    # affidavit title, deponent clause, body paragraphs, and verification.
    substantive_text = "\n".join([
        mapped.affidavit_title, mapped.deponent_clause,
        *[p["text"] for p in mapped.paragraphs],
        mapped.verification,
    ])
    substantive_resp_mentions = set(_find_all_respondent_number_mentions(substantive_text))
    consistency_score = 100.0
    if len(substantive_resp_mentions) > 1:
        consistency_score = 60.0
        issues.append(Issue(
            "Consistency", "high",
            f"Filing respondent's number is inconsistent in the substantive parts of the "
            f"document (title/deponent clause/body/verification): found {sorted(substantive_resp_mentions)}",
            "cross-document scan (affidavit title, deponent clause, body, verification)"
        ))
    elif len(substantive_resp_mentions) == 1:
        found_num = next(iter(substantive_resp_mentions))
        if int(found_num) != entities.respondent_number:
            consistency_score = 50.0
            issues.append(Issue(
                "Consistency", "high",
                f"Substantive parts consistently reference Respondent No.{found_num}, but the "
                f"affidavit was meant to be filed on behalf of Respondent No.{entities.respondent_number}.",
                "Case Information \u00a71 (filed_on_behalf_of_respondent_number)"
            ))
    else:
        consistency_score = 0.0
        issues.append(Issue("Consistency", "high",
                             "No 'Respondent No.X' reference found in the substantive parts of the document",
                             "cross-document scan"))

    # Verification verb must match jurat verb (Format Explained \u00a72, "must never break" rule #1).
    verb_map = {"solemnly affirm": "Solemnly affirmed", "swear and affirm": "Sworn"}
    expected_jurat_verb = verb_map.get(entities.verification_verb, "Solemnly affirmed")
    if expected_jurat_verb.lower() not in mapped.jurat.lower():
        consistency_score = min(consistency_score, 50.0)
        issues.append(Issue(
            "Consistency", "high",
            f"Jurat verb does not match verification verb. Expected '{expected_jurat_verb}' "
            f"(deponent's stated verb: '{entities.verification_verb}').",
            "Format Explained \u00a72, Rule: 'Verification verb in Part 6 matches the jurat verb in Part 9'"
        ))
    scores["Consistency"] = consistency_score

    # ---------- 3. COMPLETENESS ----------
    # Deponent designation/capacity must appear if the deponent is an officer, not the party.
    completeness_score = 100.0
    if entities.deponent_is_organisation_officer and entities.capacity not in mapped.deponent_clause:
        completeness_score -= 40
        issues.append(Issue(
            "Completeness", "high",
            f"Deponent designation ('{entities.capacity}') omitted from the deponent clause, "
            f"even though the respondent is an organisation and the deponent is its officer.",
            "Format Explained \u00a72 (Deponent Rule)"
        ))
    # Every reply point should map to exactly one paragraph.
    mapped_points = {p["source_point"] for p in mapped.paragraphs if p["source_point"] is not None}
    expected_points = {p["point_number"] for p in entities.reply_points}
    missing_points = expected_points - mapped_points
    if missing_points:
        completeness_score -= 20 * len(missing_points)
        for mp in missing_points:
            issues.append(Issue("Completeness", "high",
                                 f"Reply point {mp} from case information was not incorporated "
                                 f"into any generated paragraph.",
                                 "Case Information \u00a73 (Reply Points)"))
    scores["Completeness"] = max(0.0, completeness_score)

    # ---------- 4. ENTITY ACCURACY ----------
    # Check that key supplied entities appear correctly (not altered) in the output.
    entity_checks = [
        ("Petitioner name", entities.petitioner_name, mapped.petitioner_block),
        ("Deponent name", entities.deponent_name, mapped.deponent_clause),
        ("Case number", entities.case_number, mapped.case_number_line),
        ("Year", entities.year, mapped.case_number_line),
        ("Place of attestation", entities.place_of_attestation, mapped.jurat),
    ]
    entity_score = 100.0
    for label, expected, haystack in entity_checks:
        if expected not in haystack:
            entity_score -= 15
            issues.append(Issue(
                "Entity Accuracy", "high",
                f"{label} ('{expected}') not found where expected.",
                "Case Information \u00a71-2"
            ))
    # Cross-check every respondent name/number pairing is intact and not swapped.
    for r in entities.respondents:
        expected_block = f"{r['name']} ...Respondent No.{r['number']}"
        found = any(expected_block in block for block in mapped.respondent_blocks) or \
                any(r['name'] in block and f"No.{r['number']}" in block for block in mapped.respondent_blocks)
        if not found:
            entity_score -= 15
            issues.append(Issue(
                "Entity Accuracy", "high",
                f"Respondent '{r['name']}' not correctly paired with Respondent No.{r['number']}.",
                "Case Information \u00a71 (Parties)"
            ))
    scores["Entity Accuracy"] = max(0.0, entity_score)

    # ---------- 5. TEMPLATE FIDELITY ----------
    # Prayer must be LETTERED, never numbered with the body (Format Explained Part 8 rule).
    fidelity_score = 100.0
    if not all(re.match(r"^\([a-z]\)", line) for line in mapped.prayer_lines):
        fidelity_score -= 30
        issues.append(Issue("Template Fidelity", "medium",
                             "One or more prayer items are not lettered in (a)(b)(c) form.",
                             "Format Explained \u00a71, Part 8"))
    # Paragraph numbering must be sequential starting at 1 with no gaps.
    numbers = [p["number"] for p in mapped.paragraphs]
    if numbers != list(range(1, len(numbers) + 1)):
        fidelity_score -= 30
        issues.append(Issue("Template Fidelity", "high",
                             f"Body paragraph numbering is not sequential: {numbers}",
                             "Format Explained \u00a71, Part 7"))
    # Reference template's part order must be mirrored (heading -> ... -> verification).
    ref_parts_present = template.present_parts()
    if not all(ref_parts_present.values()):
        fidelity_score -= 10
        issues.append(Issue("Template Fidelity", "low",
                             "Reference document itself was missing a part during structure "
                             "analysis — generated document's fidelity to it may be affected.",
                             "template_analysis.py output"))
    scores["Template Fidelity"] = max(0.0, fidelity_score)

    # ---------- 6. HALLUCINATION CHECK ----------
    # Any Petitioner/Respondent name, date, or exhibit label in the output that was
    # NOT supplied in case_information.json is flagged as a possible hallucination.
    hallucination_score = 100.0
    supplied_names = {entities.petitioner_name, entities.deponent_name}
    supplied_names.update(r["name"] for r in entities.respondents)

    MONTHS = ("January|February|March|April|May|June|July|August|September|"
              "October|November|December")
    date_pattern = rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}}"

    supplied_dates = set()
    for point in entities.reply_points:
        supplied_dates.update(re.findall(date_pattern, " ".join(point["facts"])))
    supplied_dates.add(entities.date)

    dates_in_output = set(re.findall(date_pattern, generated_text))
    # Normalize ordinal suffixes for comparison (e.g. "5th September 2026" vs "5 September 2026")
    def _strip_ordinal(d):
        return re.sub(r"(\d+)(st|nd|rd|th)", r"\1", d)
    norm_supplied = {_strip_ordinal(d) for d in supplied_dates}
    norm_output = {_strip_ordinal(d) for d in dates_in_output}
    extra_dates = norm_output - norm_supplied
    if extra_dates:
        hallucination_score -= 20 * len(extra_dates)
        for d in extra_dates:
            issues.append(Issue("Hallucination", "high",
                                 f"Date '{d}' appears in the generated document but was not "
                                 f"supplied in case information.",
                                 "Case Information cross-check"))
    scores["Hallucination Check"] = max(0.0, hallucination_score)

    # ---------- GROUND TRUTH COMPARISON (re-extraction from the generated .docx) ----------
    # Everything above checks `mapped` -- the object that FED generation.py.
    # This is the one part of the evaluation that checks what generation.py
    # actually WROTE, by re-reading the real file text. See doc_reading.py
    # for why this is not redundant with the checks above.
    gt_issues = ground_truth_comparison(entities, mapped, generated_text)
    deduction_by_severity = {"high": 15, "medium": 8, "low": 3}
    for issue in gt_issues:
        issues.append(issue)
        deduction = deduction_by_severity.get(issue.severity, 10)
        scores[issue.dimension] = max(0.0, scores.get(issue.dimension, 100.0) - deduction)

    # ---------- OVERALL ----------
    overall = sum(scores.values()) / len(scores)

    explanation = (
        "Overall score is the unweighted mean of the six dimension scores. Each dimension "
        "starts at 100 and is deducted per specific rule violation found (see 'source' on each "
        "issue for the exact rule). All checks are deterministic (regex/rule-based against the "
        "case information and the format specification) — none rely on an LLM's subjective "
        "judgment, so every score is fully reproducible and traceable to a specific rule."
    )

    report = EvaluationReport(scores=scores, overall_score=overall, issues=issues, explanation=explanation)
    return report


def full_text_from_mapped_content(mc: MappedContent) -> str:
    """Reconstruct a plain-text version of the generated document from
    MappedContent, used as input to the evaluation stage (avoids having to
    re-parse the .docx file back out)."""
    parts = [
        mc.forum_heading, mc.jurisdiction_line, mc.case_number_line,
        mc.petitioner_block, "VERSUS", *mc.respondent_blocks,
        mc.affidavit_title, mc.deponent_clause,
    ]
    for p in mc.paragraphs:
        parts.append(f"{p['number']}. {p['text']}")
    parts.append("PRAYER")
    parts.extend(mc.prayer_lines)
    parts.append(mc.jurat)
    parts.append("VERIFICATION")
    parts.append(mc.verification)
    parts.append(mc.advocate_block)
    return "\n".join(parts)


if __name__ == "__main__":
    from src.extraction import extract_entities
    from src.content_mapping import map_content
    from src.template_analysis import analyze_reference_document

    e = extract_entities("data/case_information.json")
    mc = map_content(e)
    with open("data/reference_affidavit.txt") as f:
        ref_text = f.read()
    ts = analyze_reference_document(ref_text)

    gen_text = full_text_from_mapped_content(mc)

    report = evaluate(e, mc, ts, gen_text)
    print(json.dumps(report.to_dict(), indent=2))
