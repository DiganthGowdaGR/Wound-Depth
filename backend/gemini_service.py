"""Optional Gemini documentation assistant. It never participates in wound analysis."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from pydantic import BaseModel, Field, ValidationError


SYSTEM_INSTRUCTION = """You are the WoundLens clinical documentation assistant.
Your role is to summarize measured wound-analysis data for clinician review.
You must not diagnose infection, prescribe medication, recommend dosage, determine surgery,
claim healing probability, or invent measurements. Always distinguish measured findings,
observed imaging findings, and clinician-provided notes. If evidence is insufficient,
explicitly say so. Do not state or imply physical wound depth or involvement of muscle.
"""


class AssessmentSummary(BaseModel):
    assessment_summary: str
    structural_findings: list[str] = Field(default_factory=list)
    thermal_findings: list[str] = Field(default_factory=list)
    attention_points: list[str] = Field(default_factory=list)
    clinician_summary: str
    patient_friendly_summary: str


class HistorySummary(BaseModel):
    chronological_summary: str
    structural_changes: list[str] = Field(default_factory=list)
    thermal_observations: list[str] = Field(default_factory=list)
    clinical_plan_summary: str
    follow_up_summary: str


class GeminiUnavailable(RuntimeError):
    pass


class GeminiService:
    def __init__(self) -> None:
        configured_keys = os.environ.get("GEMINI_API_KEYS", "")
        self._api_keys = [key.strip() for key in configured_keys.replace(";", ",").split(",") if key.strip()]
        primary_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if primary_key and primary_key not in self._api_keys:
            self._api_keys.insert(0, primary_key)
        self._clients: list[Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_keys)

    def _clients_or_raise(self) -> list[Any]:
        if not self._api_keys:
            raise GeminiUnavailable("AI summary unavailable - GEMINI_API_KEY not configured.")
        if self._clients is None:
            try:
                from google import genai
                self._clients = [genai.Client(api_key=key) for key in self._api_keys]
            except Exception as error:
                raise GeminiUnavailable("AI summary unavailable - Gemini client could not be initialized.") from error
        return self._clients

    def _generate_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        clients = self._clients_or_raise()
        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=schema,
                temperature=0.1,
            )
            failures: list[Exception] = []
            for client in clients:
                executor = ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(
                        client.models.generate_content,
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=config,
                    )
                    response = future.result(timeout=25)
                    if response.text:
                        return json.loads(response.text)
                    failures.append(RuntimeError("Gemini returned an empty response."))
                except Exception as error:
                    failures.append(error)
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
            raise GeminiUnavailable("AI summary unavailable - all configured Gemini keys failed.") from failures[-1]
        except TimeoutError as error:
            raise GeminiUnavailable("AI summary unavailable - Gemini request timed out.") from error
        except GeminiUnavailable:
            raise
        except Exception as error:
            raise GeminiUnavailable("AI summary unavailable - Gemini request failed.") from error

    def explain_assessment(self, payload: dict[str, Any]) -> AssessmentSummary:
        schema = AssessmentSummary.model_json_schema()
        prompt = "Summarize only this structured WoundLens assessment data:\n" + json.dumps(payload, ensure_ascii=True)
        for attempt in range(2):
            try:
                return AssessmentSummary.model_validate(self._generate_json(prompt, schema))
            except (ValidationError, json.JSONDecodeError) as error:
                if attempt:
                    raise GeminiUnavailable("AI summary unavailable - Gemini returned malformed structured data.") from error
        raise GeminiUnavailable("AI summary unavailable.")

    def summarize_history(self, patient_id: str, entries: list[dict[str, Any]]) -> HistorySummary:
        schema = HistorySummary.model_json_schema()
        prompt = "Summarize only this chronological structured WoundLens history for patient " + patient_id + ":\n" + json.dumps(entries, ensure_ascii=True)
        for attempt in range(2):
            try:
                return HistorySummary.model_validate(self._generate_json(prompt, schema))
            except (ValidationError, json.JSONDecodeError) as error:
                if attempt:
                    raise GeminiUnavailable("AI summary unavailable - Gemini returned malformed structured data.") from error
        raise GeminiUnavailable("AI summary unavailable.")
