"""Server-only Groq documentation assistant. It never participates in wound analysis."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError


SYSTEM_INSTRUCTION = """You are the WoundLens clinical documentation assistant.
Summarize measured wound-analysis data for clinician review. Do not diagnose infection,
prescribe medication, recommend dosage, determine surgery, invent measurements, claim
healing probability, state physical wound depth, or claim muscle involvement. Clearly
distinguish measured findings, observed imaging findings, and clinician-provided notes.
"""


class AssessmentSummary(BaseModel):
    assessment_summary: str
    structural_findings: list[str] = Field(default_factory=list)
    thermal_findings: list[str] = Field(default_factory=list)
    attention_points: list[str] = Field(default_factory=list)
    clinician_summary: str
    patient_friendly_summary: str


class AIUnavailable(RuntimeError):
    pass


class GroqService:
    def __init__(self) -> None:
        configured_keys = os.environ.get("GROQ_API_KEYS", "")
        self._api_keys = [key.strip() for key in configured_keys.replace(";", ",").split(",") if key.strip()]
        primary_key = os.environ.get("GROQ_API_KEY", "").strip()
        if primary_key and primary_key not in self._api_keys:
            self._api_keys.insert(0, primary_key)
        self._model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._next_key_index = 0

    @property
    def configured(self) -> bool:
        return bool(self._api_keys)

    def explain_assessment(self, payload: dict[str, Any]) -> AssessmentSummary:
        if not self._api_keys:
            raise AIUnavailable("AI summary unavailable.")
        prompt = "Return only a JSON object matching the requested fields. Summarize only this structured WoundLens assessment data:\n" + json.dumps(payload, ensure_ascii=True)
        failures: list[Exception] = []
        start_index = self._next_key_index % len(self._api_keys)
        ordered_keys = self._api_keys[start_index:] + self._api_keys[:start_index]
        self._next_key_index = (start_index + 1) % len(self._api_keys)
        for api_key in ordered_keys:
            request_body = json.dumps({
                "model": self._model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": prompt}],
            }).encode("utf-8")
            request = Request("https://api.groq.com/openai/v1/chat/completions", data=request_body, method="POST", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=25) as response:
                    content = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"]
                return AssessmentSummary.model_validate(json.loads(content))
            except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as error:
                failures.append(error)
        raise AIUnavailable("AI summary unavailable.") from failures[-1]
