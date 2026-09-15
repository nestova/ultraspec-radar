import re

from app.models import OwnershipClassification

CORPORATE_TOKENS = [
    "llc",
    "l l c",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "lp",
    "llp",
    "plc",
    "partners",
    "partnership",
    "holdings",
    "properties",
    "ventures",
    "capital",
    "group",
    "enterprises",
    "investments",
    "realty",
    "development",
    "developers",
]

TRUST_TOKENS = ["trust", "trs", "tr", "revocable", "living trust", "family trust", "trustee"]

GOVERNMENT_TOKENS = ["city of", "county of", "state of", "school board", "housing authority", "district"]

AMBIGUOUS_TOKENS = ["et al", "etal", "estate of", "c/o", "& sons", "and sons"]

_NON_WORD = re.compile(r"[^a-z0-9& ]+")


def _tokens(name: str) -> list[str]:
    return _NON_WORD.sub(" ", name.lower()).split()


def classify_owner(owner_name: str | None) -> OwnershipClassification:
    if not owner_name or not owner_name.strip():
        return OwnershipClassification(
            owner_name=owner_name or "",
            ownership_type="unknown",
            confidence=0.0,
            matched_rule="empty_owner_name",
            needs_review=True,
        )

    normalized = " ".join(_tokens(owner_name))
    tokens = normalized.split()

    for phrase in GOVERNMENT_TOKENS:
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            return OwnershipClassification(
                owner_name=owner_name,
                ownership_type="government",
                confidence=0.95,
                matched_rule=f"government_token:{phrase}",
                needs_review=False,
            )

    corporate_hit = next((t for t in CORPORATE_TOKENS if t in tokens or f" {t} " in f" {normalized} "), None)
    trust_hit = next((t for t in TRUST_TOKENS if t in tokens), None)

    # Trusts count as individual ownership; a trust that is also an LLC is corporate.
    if corporate_hit and trust_hit:
        return OwnershipClassification(
            owner_name=owner_name,
            ownership_type="corporate",
            confidence=0.6,
            matched_rule=f"corporate_token:{corporate_hit}+trust_token:{trust_hit}",
            needs_review=True,
        )
    if corporate_hit:
        return OwnershipClassification(
            owner_name=owner_name,
            ownership_type="corporate",
            confidence=0.93,
            matched_rule=f"corporate_token:{corporate_hit}",
            needs_review=False,
        )
    if trust_hit:
        return OwnershipClassification(
            owner_name=owner_name,
            ownership_type="trust",
            confidence=0.9,
            matched_rule=f"trust_token:{trust_hit}",
            needs_review=False,
        )

    ambiguous_hit = next((p for p in AMBIGUOUS_TOKENS if p in normalized), None)
    if ambiguous_hit:
        return OwnershipClassification(
            owner_name=owner_name,
            ownership_type="individual",
            confidence=0.55,
            matched_rule=f"ambiguous_token:{ambiguous_hit}",
            needs_review=True,
        )

    co_owners = [part for part in re.split(r" & | and ", normalized) if part]
    if len(co_owners) > 1 and all(len(part.split()) <= 4 for part in co_owners):
        return OwnershipClassification(
            owner_name=owner_name,
            ownership_type="individual",
            confidence=0.8,
            matched_rule="co_owners_no_entity_token",
            needs_review=False,
        )

    if len(tokens) > 4:
        return OwnershipClassification(
            owner_name=owner_name,
            ownership_type="unknown",
            confidence=0.4,
            matched_rule="long_name_no_entity_token",
            needs_review=True,
        )

    return OwnershipClassification(
        owner_name=owner_name,
        ownership_type="individual",
        confidence=0.85,
        matched_rule="no_entity_token",
        needs_review=False,
    )


def is_eligible(
    classification: OwnershipClassification, include_trusts: bool, exclude_corporate: bool
) -> bool:
    if classification.ownership_type == "government":
        return False
    if classification.ownership_type == "corporate":
        return not exclude_corporate
    if classification.ownership_type == "trust":
        return include_trusts
    return classification.ownership_type != "unknown"
