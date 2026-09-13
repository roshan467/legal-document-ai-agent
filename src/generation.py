"""
Stage 4: Document Generation.

Renders a MappedContent object into a .docx file, applying the formatting
rules from `01_Affidavit_Format_Explained` Section 5:
  - Forum heading, jurisdiction, case number, affidavit title: bold, ALL CAPS, centred
  - PRAYER / VERIFICATION headings: bold, ALL CAPS, centred
  - Cause title party names: normal, left; status tags: right-aligned
  - VERSUS: centred, own line
  - Paragraph numbers, prayer letters: bold
  - DEPONENT: ALL CAPS, right-aligned
"""
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from src.content_mapping import MappedContent


def _add_centered_bold_caps(doc, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text.upper())
    run.bold = True
    return p


def _add_two_column_line(doc, left_text: str, right_text: str):
    """Party name (left) ... status tag (right), approximated with a tab stop."""
    p = doc.add_paragraph()
    p.add_run(left_text)
    p.add_run("\t" + right_text)
    # Simple right-tab approximation; a production version would set an
    # explicit right-aligned tab stop at the page-width margin.
    return p


def generate_docx(mc: MappedContent, output_path: str):
    doc = Document()
    style = doc.styles["Normal"]
    style.font.size = Pt(11)

    # Part 1: Forum heading
    _add_centered_bold_caps(doc, mc.forum_heading)
    # Part 2: Jurisdiction
    _add_centered_bold_caps(doc, mc.jurisdiction_line)
    # Part 3: Case number
    _add_centered_bold_caps(doc, mc.case_number_line)
    doc.add_paragraph()

    # Part 4: Cause title
    _add_two_column_line(doc, mc.petitioner_block.replace(" ...Petitioner", ""), "...Petitioner")
    versus_p = doc.add_paragraph()
    versus_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    versus_p.add_run("VERSUS")
    for block in mc.respondent_blocks:
        # split "N. Name ...Respondent No.N" into left/right for formatting
        left, _, right = block.partition("...")
        _add_two_column_line(doc, left.strip(), "..." + right.strip())
    doc.add_paragraph()

    # Part 5: Affidavit title
    _add_centered_bold_caps(doc, mc.affidavit_title)
    doc.add_paragraph()

    # Part 6: Deponent clause
    doc.add_paragraph(mc.deponent_clause)
    doc.add_paragraph()

    # Part 7: Numbered paragraphs
    for para in mc.paragraphs:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        num_run = p.add_run(f"{para['number']}. ")
        num_run.bold = True
        p.add_run(para["text"])
    doc.add_paragraph()

    # Part 8: Prayer
    _add_centered_bold_caps(doc, "PRAYER")
    doc.add_paragraph("I therefore respectfully pray that this Hon'ble Court may be pleased to:")
    for line in mc.prayer_lines:
        letter, _, rest = line.partition(" ")
        p = doc.add_paragraph()
        run = p.add_run(letter + " ")
        run.bold = True
        p.add_run(rest)
    doc.add_paragraph()

    # Part 9: Jurat
    for line in mc.jurat.split("\n"):
        if not line.strip():
            doc.add_paragraph()
            continue
        if "DEPONENT" in line:
            p = doc.add_paragraph()
            left, _, right = line.partition("DEPONENT")
            p.add_run(left.strip())
            p.add_run("\tDEPONENT").bold = False
            run = p.runs[-1]
            run.text = "\tDEPONENT"
        else:
            doc.add_paragraph(line)
    doc.add_paragraph()

    # Part 10: Verification
    _add_centered_bold_caps(doc, "VERIFICATION")
    for line in mc.verification.split("\n"):
        if line.strip() == "DEPONENT":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p.add_run("DEPONENT")
        elif line.strip():
            doc.add_paragraph(line)
        else:
            doc.add_paragraph()

    # Advocate block
    doc.add_paragraph()
    for line in mc.advocate_block.split("\n"):
        doc.add_paragraph(line)

    doc.save(output_path)
    return output_path


if __name__ == "__main__":
    from src.extraction import extract_entities
    from src.content_mapping import map_content

    e = extract_entities("data/case_information.json")
    mc = map_content(e)
    path = generate_docx(mc, "outputs/generated_affidavit.docx")
    print(f"Generated: {path}")
