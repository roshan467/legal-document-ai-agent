"""
Stage 1: Template / Document Understanding.

Parses a reference Affidavit in Reply into its ten fixed structural parts,
per the rules in `01_Affidavit_Format_Explained`. This does NOT use an LLM —
the affidavit format is fixed and well-defined, so a rule-based parser is
more reliable and fully deterministic (no hallucination risk at this stage).
"""
import re
from dataclasses import dataclass, field


PART_NAMES = [
    "forum_heading",
    "jurisdiction",
    "case_number",
    "cause_title",
    "affidavit_title",
    "deponent_clause",
    "numbered_paragraphs",
    "prayer",
    "jurat",
    "verification",
]


@dataclass
class TemplateStructure:
    """Structured representation of the reference document's ten parts."""
    forum_heading: str = ""
    jurisdiction: str = ""
    case_number: str = ""
    cause_title_raw: str = ""
    affidavit_title: str = ""
    deponent_clause: str = ""
    paragraphs: list = field(default_factory=list)   # list[str], numbered body paragraphs
    prayer_lines: list = field(default_factory=list)  # list[str], lettered (a)(b)(c)...
    jurat: str = ""
    verification: str = ""
    advocate_block: str = ""

    def present_parts(self):
        """Which of the 10 required parts were actually found (non-empty)."""
        checks = {
            "forum_heading": bool(self.forum_heading),
            "jurisdiction": bool(self.jurisdiction),
            "case_number": bool(self.case_number),
            "cause_title": bool(self.cause_title_raw),
            "affidavit_title": bool(self.affidavit_title),
            "deponent_clause": bool(self.deponent_clause),
            "numbered_paragraphs": len(self.paragraphs) > 0,
            "prayer": len(self.prayer_lines) > 0,
            "jurat": bool(self.jurat),
            "verification": bool(self.verification),
        }
        return checks


def analyze_reference_document(text: str) -> TemplateStructure:
    """Parse a reference affidavit's raw text into its 10 structural parts."""
    ts = TemplateStructure()
    lines = [l.rstrip() for l in text.splitlines()]
    joined = "\n".join(lines)

    # 1. Forum heading: line starting with "IN THE ... COURT ..."
    m = re.search(r"^(IN THE .*(COURT|TRIBUNAL).*)$", joined, re.MULTILINE)
    if m:
        ts.forum_heading = m.group(1).strip()

    # 2. Jurisdiction: line ending in "JURISDICTION"
    m = re.search(r"^([A-Z ]*JURISDICTION)\s*$", joined, re.MULTILINE)
    if m:
        ts.jurisdiction = m.group(1).strip()

    # 3. Case number: "<PROCEEDING> NO. <NUMBER> OF <YEAR>"
    m = re.search(r"^([A-Z ]+ NO\.\s*\d+\s*OF\s*\d{4})\s*$", joined, re.MULTILINE)
    if m:
        ts.case_number = m.group(1).strip()

    # 4. Cause title: everything between the case number line and "AFFIDAVIT IN REPLY"
    m = re.search(r"OF\s*\d{4}\s*\n(.*?)\nAFFIDAVIT IN REPLY", joined, re.DOTALL)
    if m:
        ts.cause_title_raw = m.group(1).strip()

    # 5. Affidavit title
    m = re.search(r"^(AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO\.?\s*\d+)\s*$", joined, re.MULTILINE)
    if m:
        ts.affidavit_title = m.group(1).strip()

    # 6. Deponent clause: from "I, ..." up to "...state as under:"
    m = re.search(r"(I,.*?do hereby (?:solemnly affirm|swear)[^:]*state as under:)", joined, re.DOTALL)
    if m:
        ts.deponent_clause = re.sub(r"\s+", " ", m.group(1)).strip()

    # 7. Numbered paragraphs: lines starting with "<digit>." up to (but not including) PRAYER
    body_match = re.search(r"state as under:\s*(.*?)\nPRAYER", joined, re.DOTALL)
    if body_match:
        body_text = body_match.group(1)
        # split on "N. " at start of a paragraph (paragraph numbers are standalone)
        raw_paras = re.split(r"\n(?=\d+\.\s)", body_text.strip())
        ts.paragraphs = [re.sub(r"\s+", " ", p).strip() for p in raw_paras if p.strip()]

    # 8. Prayer: lines "(a) ...", "(b) ...", etc. up to "Solemnly affirmed"
    prayer_match = re.search(r"PRAYER\s*(.*?)\n\s*Solemnly affirmed", joined, re.DOTALL)
    if prayer_match:
        prayer_text = prayer_match.group(1)
        ts.prayer_lines = re.findall(r"\([a-z]\)\s*.*?(?=\([a-z]\)|\Z)", prayer_text, re.DOTALL)
        ts.prayer_lines = [re.sub(r"\s+", " ", p).strip() for p in ts.prayer_lines]

    # 9. Jurat: "Solemnly affirmed at ... Before Me DEPONENT"
    m = re.search(r"(Solemnly affirmed at.*?Before Me\s*DEPONENT)", joined, re.DOTALL)
    if m:
        ts.jurat = re.sub(r"\s+", " ", m.group(1)).strip()

    # 10. Verification block
    m = re.search(r"(VERIFICATION\s*\n.*?DEPONENT)", joined, re.DOTALL)
    if m:
        ts.verification = re.sub(r"\s+", " ", m.group(1)).strip()

    # Advocate block: last non-empty lines after verification's final "DEPONENT"
    m = re.search(r"VERIFICATION.*?DEPONENT\s*\n\s*(.*)\Z", joined, re.DOTALL)
    if m:
        ts.advocate_block = m.group(1).strip()

    return ts


if __name__ == "__main__":
    with open("data/reference_affidavit.txt") as f:
        text = f.read()
    structure = analyze_reference_document(text)
    print("Present parts:", structure.present_parts())
    print("Body paragraph count:", len(structure.paragraphs))
    print("Prayer items:", len(structure.prayer_lines))
