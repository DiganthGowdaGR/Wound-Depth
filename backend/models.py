"""Persistence model names are represented by SQLite rows in ``persistence``."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PatientModel:
    id: str
    patient_code: str
    display_name: str
