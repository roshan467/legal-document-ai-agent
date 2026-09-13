"""
Stage 2: Entity Extraction.

Loads the case information (supplied as structured JSON per the assignment's
"input data" file) and normalizes it into the entity schema defined in
`01_Affidavit_Format_Explained` Section 6 (FORUM, JURISDICTION_TYPE,
CASE_TYPE, CASE_NUMBER, YEAR, PETITIONER, RESPONDENT, RESPONDENT_NUMBER,
DEPONENT, CAPACITY, ORGANISATION, VERIFICATION_VERB, PLACE_OF_ATTESTATION,
DATE, PARAGRAPH_COUNT).

In a fuller system this stage would also parse *unstructured* case files
(plain text / PDF) using an LLM or NER model. Here the case information is
already supplied in structured form, so extraction is a deterministic
mapping — this keeps the highest-stakes stage (getting entities right)
free of LLM hallucination risk.
"""
import json
from dataclasses import dataclass, field


@dataclass
class Entities:
    forum: str
    jurisdiction_type: str
    case_type: str
    case_number: str
    year: str
    petitioner_name: str
    respondents: list          # list of dicts: {number, name}
    respondent_number: int     # which respondent this affidavit is filed for
    respondent_name: str       # convenience: name of the filing respondent
    deponent_name: str
    capacity: str              # designation, if deponent is not the party itself
    organisation: str          # set if respondent is a company/authority
    verification_verb: str
    place_of_attestation: str
    date: str
    advocate_firm: str
    reply_points: list = field(default_factory=list)
    prayer_facts: list = field(default_factory=list)

    @property
    def deponent_is_organisation_officer(self) -> bool:
        """True if the deponent is an officer speaking for an organisation
        (per the Deponent Rule in Format Explained Section 2), rather than
        the named individual respondent speaking for themself."""
        return bool(self.organisation) and self.deponent_name != self.respondent_name


def extract_entities(case_info_path: str) -> Entities:
    with open(case_info_path) as f:
        data = json.load(f)

    court = data["court"]
    resp_num = data["filed_on_behalf_of_respondent_number"]
    respondents = data["parties"]["respondents"]
    filing_respondent = next(r for r in respondents if r["number"] == resp_num)

    dep = data["deponent"]
    organisation = dep.get("organisation", "")
    # The deponent speaks "for" the organisation only if the filing respondent
    # itself IS that organisation (not a person) — this mirrors the Deponent
    # Rule: a person deposes for themself; an officer deposes for a company.
    respondent_is_org = filing_respondent["name"] == organisation

    return Entities(
        forum=court["forum"],
        jurisdiction_type=court["jurisdiction_type"],
        case_type=court["proceeding_type"],
        case_number=court["case_number"],
        year=court["year"],
        petitioner_name=data["parties"]["petitioner"]["name"],
        respondents=respondents,
        respondent_number=resp_num,
        respondent_name=filing_respondent["name"],
        deponent_name=dep["name"],
        capacity=dep.get("designation", "") if respondent_is_org else "",
        organisation=organisation if respondent_is_org else "",
        verification_verb=dep["verification_verb"],
        place_of_attestation=data["attestation"]["place"],
        date=data["attestation"]["date"],
        advocate_firm=data["advocate"]["firm"],
        reply_points=data["reply_points"],
        prayer_facts=data["prayer_facts"],
    )


if __name__ == "__main__":
    e = extract_entities("data/case_information.json")
    print("Respondent is organisation officer case:", e.deponent_is_organisation_officer)
    print("Capacity:", e.capacity)
    print("Organisation:", e.organisation)
    print("Number of reply points:", len(e.reply_points))
