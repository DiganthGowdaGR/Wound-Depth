"""Server-only Groq documentation assistant. It never participates in wound analysis."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError


SYSTEM_INSTRUCTION = """You are WoundLens AI, a clinical documentation and wound-analysis assistant.
You explain measurements produced by WoundLens; you are not the measurement engine.
Never invent or estimate numerical measurements not supplied. Clearly distinguish measured
findings, imaging observations, clinician-provided information, and historical context.
Do not diagnose infection, prescribe medication or dosage, determine surgery, claim healing
probability, claim internal infection depth, claim physical millimetre depth, or claim muscle
involvement. When data is insufficient, explicitly state that the available scan does not
establish that conclusion. Use concise clinician-facing language and return JSON only.
"""


class MeasuredFinding(BaseModel):
    label: str
    value: str
    interpretation: str


class AssessmentSummary(BaseModel):
    headline: str
    assessment_summary: str
    measured_findings: list[MeasuredFinding] = Field(default_factory=list)
    structural_findings: list[str] = Field(default_factory=list)
    thermal_findings: list[str] = Field(default_factory=list)
    attention_points: list[str] = Field(default_factory=list)
    data_quality: list[str] = Field(default_factory=list)
    clinician_summary: str
    patient_friendly_summary: str


class HistorySummary(BaseModel):
    timeline_summary: str
    measurement_changes: list[str] = Field(default_factory=list)
    thermal_changes: list[str] = Field(default_factory=list)
    clinical_context_changes: list[str] = Field(default_factory=list)
    follow_up_points: list[str] = Field(default_factory=list)


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

    @property
    def model_name(self) -> str:
        return self._model

    def _generate(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        if not self._api_keys:
            raise AIUnavailable("AI summary unavailable.")
        prompt = "Return only a JSON object matching the requested fields.\n" + prompt
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
                return schema.model_validate(json.loads(content))
            except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as error:
                failures.append(error)
        raise AIUnavailable("AI summary unavailable.") from failures[-1]

    def explain_assessment(self, payload: dict[str, Any]) -> AssessmentSummary:
        return self._generate(
            "Summarize only this structured WoundLens assessment data:\n" + json.dumps(payload, ensure_ascii=True),
            AssessmentSummary,
        )  # type: ignore[return-value]

    def summarize_history(self, payload: dict[str, Any]) -> HistorySummary:
        return self._generate(
            "Summarize only this chronological same-patient WoundLens history. Do not infer values that are absent:\n" + json.dumps(payload, ensure_ascii=True),
            HistorySummary,
        )  # type: ignore[return-value]
