import pytest

from app.ownership import classify_owner, is_eligible


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Bay Road Holdings LLC", "corporate"),
        ("Sunset Isles Properties Inc", "corporate"),
        ("Grove Capital Partners LP", "corporate"),
        ("Smith Family Trust", "trust"),
        ("Maria Delgado Revocable Trust", "trust"),
        ("Robert Alvarez", "individual"),
        ("Robert Ferguson & Elena Kaplan", "individual"),
        ("City of Miami Beach", "government"),
    ],
)
def test_classification(name: str, expected: str) -> None:
    assert classify_owner(name).ownership_type == expected


def test_trusts_are_eligible_and_corporates_are_not() -> None:
    trust = classify_owner("Smith Family Trust")
    corporate = classify_owner("Bay Road Holdings LLC")
    assert is_eligible(trust, include_trusts=True, exclude_corporate=True)
    assert not is_eligible(corporate, include_trusts=True, exclude_corporate=True)


def test_ambiguous_names_hit_review_queue() -> None:
    assert classify_owner("Estate of Henry Kaplan").needs_review
    assert classify_owner("").needs_review
    assert classify_owner("Kaplan Family Holdings Trust").needs_review
