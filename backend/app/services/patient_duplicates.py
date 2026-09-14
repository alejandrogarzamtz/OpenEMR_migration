import re
import unicodedata
from collections.abc import Iterable

from ..models import Patient


def normalized_text(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_value.casefold())


def normalized_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def duplicate_score(candidate: Patient, probe: object) -> tuple[int, list[str]]:
    score = 0
    matches: list[str] = []
    comparisons = (
        ("date_of_birth", 40, candidate.date_of_birth == getattr(probe, "date_of_birth", None)),
        ("last_name", 25, normalized_text(candidate.last_name) == normalized_text(getattr(probe, "last_name", None))),
        ("first_name", 20, normalized_text(candidate.first_name) == normalized_text(getattr(probe, "first_name", None))),
        ("email", 10, bool(candidate.email and getattr(probe, "email", None)) and normalized_text(candidate.email) == normalized_text(str(getattr(probe, "email", "")))),
        ("phone", 5, bool(normalized_phone(candidate.phone) and normalized_phone(getattr(probe, "phone", None))) and normalized_phone(candidate.phone) == normalized_phone(getattr(probe, "phone", None))),
    )
    for field, weight, matched in comparisons:
        if matched:
            score += weight
            matches.append(field)
    return score, matches


def duplicate_candidates(patients: Iterable[Patient], probe: object, *, exclude_id: int | None = None, minimum_score: int = 65) -> list[tuple[Patient, int, list[str]]]:
    matches = []
    for patient in patients:
        if patient.id == exclude_id:
            continue
        score, fields = duplicate_score(patient, probe)
        if score >= minimum_score:
            matches.append((patient, score, fields))
    return sorted(matches, key=lambda item: (-item[1], item[0].last_name.casefold(), item[0].first_name.casefold(), item[0].id))
