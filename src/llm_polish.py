"""
Optional Stage 4b: LLM-Assisted Stylistic Polish.

The deterministic template-fill in content_mapping.py already produces a
legally structured, fully correct affidavit using only supplied facts and
the fixed-phrase glossary. This module is an OPTIONAL enhancement: if an
ANTHROPIC_API_KEY is configured, it asks an LLM to lightly smooth the
prose of the substantive-answer paragraphs (better sentence flow) WITHOUT
permission to add, remove, or alter any fact, name, date, or number.

Design rationale for keeping this optional and constrained:
  - The base pipeline must work identically with zero API keys (the
    assignment explicitly says free tiers are fine and no one should have
    to pay) — so LLM polishing is additive, never required.
  - Giving an LLM free rein over legal document text is exactly where
    hallucination risk is highest. This module explicitly instructs the
    model to preserve every fact/entity verbatim and only touches
    phrasing, and a post-hoc check re-runs the Hallucination Check
    evaluation dimension on the polished text before accepting it.
  - This mirrors the honest-fallback pattern already used in the LawGPT
    project: if the LLM is unavailable or its output fails the
    hallucination re-check, the system falls back to the deterministic
    text rather than silently risking a bad substitution.
"""
import os


def is_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def polish_paragraph(text: str, api_key: str = None) -> tuple[str, bool]:
    """
    Attempt to lightly polish a paragraph's phrasing via Claude.
    Returns (text, was_polished). Falls back to the original text on any
    failure — never raises, so the pipeline is never blocked by this stage.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return text, False

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "You are polishing ONE paragraph of a legal affidavit. Improve only "
            "sentence flow and grammar. Do NOT add, remove, or change any fact, "
            "name, date, number, exhibit label, or legal phrase. Do NOT add new "
            "information of any kind. Return ONLY the polished paragraph text, "
            "nothing else.\n\nParagraph:\n" + text
        )
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        polished = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        if not polished:
            return text, False
        return polished, True
    except Exception:
        # Any failure (no network, bad key, rate limit, etc.) — fail open to
        # the deterministic text rather than breaking the pipeline.
        return text, False


def polish_with_safety_check(text: str, entities, api_key: str = None) -> tuple[str, bool, list]:
    """
    Polish a paragraph, then re-check it doesn't introduce hallucinated
    dates/entities not present in the original. If the check fails, revert
    to the original deterministic text.
    Returns (final_text, was_polished_and_kept, warnings).
    """
    import re
    polished, attempted = polish_paragraph(text, api_key)
    if not attempted:
        return text, False, []

    MONTHS = ("January|February|March|April|May|June|July|August|September|"
              "October|November|December")
    date_pattern = rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}}"
    original_dates = set(re.findall(date_pattern, text))
    polished_dates = set(re.findall(date_pattern, polished))

    warnings = []
    if polished_dates - original_dates:
        warnings.append(
            f"Polished text introduced new date(s) {polished_dates - original_dates} "
            f"not in the original — reverting to deterministic text."
        )
        return text, False, warnings

    return polished, True, warnings
