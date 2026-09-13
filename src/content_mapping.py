"""
Stage 3: Content Mapping.

Maps extracted entities + reply points onto the reference document's ten
structural slots, applying the fixed phrases and rules from
`01_Affidavit_Format_Explained` (deponent rule, verb agreement, paragraph
sequencing, fixed phrase glossary).

This stage is deliberately rule-based, not LLM-generated: the format
document gives an exact phrase glossary, so filling it with an LLM would
only add hallucination risk for zero benefit. The one place an LLM COULD
help is smoothing the substantive-answer sentences (Stage 4 optionally
does this) — mapping itself stays deterministic.
"""
from dataclasses import dataclass, field
import re
from src.extraction import Entities

VERB_MAP = {
    "solemnly affirm": "Solemnly affirmed",
    "swear and affirm": "Sworn",
}


@dataclass
class MappedContent:
    forum_heading: str
    jurisdiction_line: str
    case_number_line: str
    petitioner_block: str
    respondent_blocks: list       # list[str], one per respondent
    affidavit_title: str
    deponent_clause: str
    paragraphs: list = field(default_factory=list)   # list[dict]: {number, move, text, source_point}
    prayer_lines: list = field(default_factory=list)  # list[str]
    jurat: str = ""
    verification: str = ""
    advocate_block: str = ""


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _format_date_for_jurat(date_str: str) -> str:
    """'5 September 2026' -> ('5th', 'September', '2026')"""
    parts = date_str.split()
    day = int(parts[0])
    month, year = parts[1], parts[2]
    return _ordinal(day), month, year


def _lower_first(s: str) -> str:
    """Lowercase the first letter, but never for defined/proper terms
    (Respondent, Petitioner) that must stay capitalized throughout a legal
    document regardless of sentence position."""
    if not s:
        return s
    protected_starts = ("Respondent", "Petitioner")
    if s.startswith(protected_starts):
        return s
    return s[0].lower() + s[1:]


def _first_person(text: str) -> str:
    """
    Normalize case-info facts (written in third person about the deponent,
    e.g. 'The deponent has perused...') into the first-person voice required
    throughout an affidavit ('I have perused...').

    Note: this deliberately does NOT touch third-person references to the
    respondent ORGANISATION itself (e.g. 'Respondent No. 2 denies...') —
    that usage is correct as-is, since the deponent (a person) speaks in
    first person about themself but refers to the organisation they
    represent in the third person. Only 'the deponent ...' phrasing (which
    refers to the speaker) is converted.
    """
    text = re.sub(r"\bThe deponent has\b", "I have", text)
    text = re.sub(r"\bThe deponent is\b", "I am", text)
    text = re.sub(r"\bThe deponent was\b", "I was", text)
    text = re.sub(r"\bthe deponent has\b", "I have", text)
    text = re.sub(r"\bthe deponent is\b", "I am", text)
    text = re.sub(r"\bThe deponent\b", "I", text)
    text = re.sub(r"\bthe deponent\b", "I", text)
    return text


def _title_case_proceeding(case_type: str) -> str:
    """'WRIT PETITION' -> 'Writ Petition' for use in body prose;
    headings/case-number lines keep the ALL CAPS form separately."""
    return case_type.title()


def map_content(entities: Entities) -> MappedContent:
    e = entities
    proceeding_title = _title_case_proceeding(e.case_type)

    # --- Forum / jurisdiction / case number ---
    forum_heading = e.forum
    jurisdiction_line = e.jurisdiction_type
    case_number_line = f"{e.case_type} NO. {e.case_number} OF {e.year}"

    # --- Cause title ---
    petitioner_block = f"{e.petitioner_name} ...Petitioner"
    respondent_blocks = []
    for r in e.respondents:
        respondent_blocks.append(f"{r['number']}. {r['name']} ...Respondent No.{r['number']}")

    # --- Affidavit title ---
    affidavit_title = f"AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO. {e.respondent_number}"

    # --- Deponent clause (applies the Deponent Rule) ---
    if e.deponent_is_organisation_officer:
        who_clause = f"the {e.capacity} of the Respondent No.{e.respondent_number} above named"
    else:
        who_clause = f"the Respondent No.{e.respondent_number} above named"
    deponent_clause = (
        f"I, {e.deponent_name}, {who_clause}, "
        f"do hereby solemnly affirm and state as under:"
    )

    # --- Numbered paragraphs, built from reply_points via fixed-phrase templates ---
    paragraphs = []
    para_num = 1

    for point in e.reply_points:
        move = point["move"]
        facts = _first_person(" ".join(point["facts"]))

        if move == "IDENTITY_AND_PERUSAL":
            subject = (f"the {e.capacity} of the Respondent No.{e.respondent_number}"
                       if e.deponent_is_organisation_officer
                       else f"the Respondent No.{e.respondent_number}")
            text = (
                f"I say that I am {subject} in the above {proceeding_title} and am well "
                f"acquainted with the facts and circumstances of the case. {facts} "
                f"I am competent to affirm this Affidavit in Reply."
            )
        elif move == "BLANKET_DENIAL":
            text = (
                f"At the outset, I deny each and every allegation, contention and "
                f"submission made in the {proceeding_title}, save and except those "
                f"specifically admitted herein. I say that the {proceeding_title} is "
                f"misconceived, devoid of merits and is liable to be dismissed in "
                f"limine. {facts}"
            )
        elif move == "PRELIMINARY_POSITION":
            text = (
                f"I say that {_lower_first(facts)} The action complained of has been taken "
                f"strictly in accordance with law and after following due "
                f"procedure. No legal, constitutional or fundamental right of the "
                f"Petitioner has been infringed."
            )
        elif move == "SUBSTANTIVE_ANSWER":
            # Note: earlier draft always prepended "I say that the same are false,
            # incorrect and denied" before EVERY substantive point. That's wrong for
            # a point like "Authority for the Communication", which is an affirmative
            # explanation, not a denial — asserting "false, incorrect and denied"
            # immediately before an affirmative statement is a logical inconsistency,
            # not just a style issue. Instead we use a neutral lead-in and let each
            # point's own fact text (which already states denial/affirmation as
            # appropriate) carry the substance.
            exhibit = point.get("exhibit")
            lead = "With reference to the averments made in the Petition, I say that"
            if exhibit:
                # The fixed exhibit sentence below already states the annexure —
                # drop any raw fact sentence that redundantly says the same thing
                # (e.g. "A copy of that communication is to be annexed and marked
                # as EXHIBIT-'A'.") to avoid stating it twice.
                fact_sentences = [
                    s.strip() for s in re.split(r"(?<=[.])\s+", facts)
                    if s.strip() and "annexed" not in s.lower() and "marked as" not in s.lower()
                ]
                core_facts = " ".join(fact_sentences)
                text = (
                    f"{lead} {_lower_first(core_facts)} "
                    f"Hereto annexed and marked as {exhibit['label']} is a copy of "
                    f"the {exhibit['description']}."
                )
            else:
                text = f"{lead} {_lower_first(facts)}"
        else:
            text = facts

        paragraphs.append({
            "number": para_num,
            "move": move,
            "text": text,
            "source_point": point["point_number"],
        })
        para_num += 1

    # Closing paragraph (always last, fixed phrase, not tied to a reply point)
    paragraphs.append({
        "number": para_num,
        "move": "CLOSING",
        "text": f"In the premises aforesaid, I say that the {proceeding_title} deserves to be dismissed with costs.",
        "source_point": None,
    })
    total_paragraphs = para_num

    # --- Prayer ---
    letters = "abcdefghijklmnopqrstuvwxyz"
    prayer_lines = []
    base_prayers = [
        f"dismiss the present {proceeding_title} with costs;",
        "refuse any interim or ad-interim relief sought by the Petitioner; and",
        "grant such other and further reliefs as this Hon'ble Court may deem fit "
        "and proper in the facts and circumstances of the case.",
    ]
    for i, p in enumerate(base_prayers):
        prayer_lines.append(f"({letters[i]}) {p}")

    # --- Jurat ---
    day_ord, month, year = _format_date_for_jurat(e.date)
    verb_past = VERB_MAP.get(e.verification_verb, "Solemnly affirmed")
    jurat = (
        f"{verb_past} at {e.place_of_attestation}\n"
        f"On this {day_ord} day of {month} {year}\n\n"
        f"Before Me DEPONENT"
    )

    # --- Verification ---
    verification = (
        f"I, {e.deponent_name}, the Deponent above named, do hereby verify that "
        f"the contents of paragraphs 1 to {total_paragraphs} and the Prayer above "
        f"are true and correct to my knowledge and belief and that nothing "
        f"material has been concealed therefrom.\n\n"
        f"Verified at {e.place_of_attestation} on this {day_ord} day of {month} {year}.\n\n"
        f"DEPONENT"
    )

    advocate_block = f"{e.advocate_firm}\nAdvocates for the Respondent No.{e.respondent_number}."

    return MappedContent(
        forum_heading=forum_heading,
        jurisdiction_line=jurisdiction_line,
        case_number_line=case_number_line,
        petitioner_block=petitioner_block,
        respondent_blocks=respondent_blocks,
        affidavit_title=affidavit_title,
        deponent_clause=deponent_clause,
        paragraphs=paragraphs,
        prayer_lines=prayer_lines,
        jurat=jurat,
        verification=verification,
        advocate_block=advocate_block,
    )


if __name__ == "__main__":
    from src.extraction import extract_entities
    e = extract_entities("data/case_information.json")
    mc = map_content(e)
    print("Deponent clause:", mc.deponent_clause)
    print("Number of body paragraphs:", len(mc.paragraphs))
    for p in mc.paragraphs:
        print(f"  [{p['number']}] ({p['move']}) {p['text'][:80]}...")
