"""SQLite persistence for WoundLens patients, visits, and analysis records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WoundLensStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.root = database_path.parent
        self.storage_root = self.root / "storage"
        self.report_root = self.storage_root / "reports"
        self.root.mkdir(parents=True, exist_ok=True)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.report_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY, patient_code TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, age INTEGER, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
                    visit_date TEXT NOT NULL, clinical_notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scan_assets (
                    id TEXT PRIMARY KEY, visit_id TEXT NOT NULL UNIQUE REFERENCES visits(id),
                    rgb_path TEXT NOT NULL, thermal_path TEXT NOT NULL, depth_path TEXT NOT NULL,
                    wound_overlay_path TEXT NOT NULL, relative_depth_map_path TEXT NOT NULL,
                    surface_3d_path TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, visit_id TEXT NOT NULL UNIQUE REFERENCES visits(id),
                    wound_roi_pixels INTEGER NOT NULL, relative_depth_range REAL NOT NULL,
                    mean_depth_variation REAL NOT NULL, depth_variation_std REAL NOT NULL,
                    thermal_summary TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_summaries (
                    id TEXT PRIMARY KEY, visit_id TEXT NOT NULL UNIQUE REFERENCES visits(id),
                    assessment_summary TEXT NOT NULL, structural_findings_json TEXT NOT NULL,
                    thermal_findings_json TEXT NOT NULL, attention_points_json TEXT NOT NULL,
                    clinician_summary TEXT NOT NULL, patient_friendly_summary TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS clinical_plans (
                    id TEXT PRIMARY KEY, visit_id TEXT NOT NULL UNIQUE REFERENCES visits(id),
                    clinician_assessment TEXT NOT NULL, medication TEXT NOT NULL, wound_care_plan TEXT NOT NULL,
                    follow_up_interval TEXT NOT NULL, additional_tests TEXT NOT NULL,
                    escalation_required INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, visit_id TEXT NOT NULL REFERENCES visits(id),
                    pdf_path TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )
            self._add_column_if_missing(connection, "ai_summaries", "model_name", "TEXT NOT NULL DEFAULT ''")
            self._add_column_if_missing(connection, "ai_summaries", "headline", "TEXT NOT NULL DEFAULT ''")
            self._add_column_if_missing(connection, "ai_summaries", "measured_findings_json", "TEXT NOT NULL DEFAULT '[]'")
            self._add_column_if_missing(connection, "ai_summaries", "data_quality_json", "TEXT NOT NULL DEFAULT '[]'")
            self._add_column_if_missing(connection, "ai_summaries", "generation_source", "TEXT NOT NULL DEFAULT 'ai_provider'")
            self._add_column_if_missing(connection, "ai_summaries", "reviewed_by_clinician", "INTEGER NOT NULL DEFAULT 0")
            self._add_column_if_missing(connection, "ai_summaries", "reviewed_at", "TEXT")

    @staticmethod
    def _add_column_if_missing(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def healthy(self) -> bool:
        with self._connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return True

    def create_patient(self, patient_code: str, display_name: str, age: int | None = None) -> dict[str, Any]:
        patient_id = uuid.uuid4().hex
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO patients(id, patient_code, display_name, age, created_at) VALUES (?, ?, ?, ?, ?)",
                    (patient_id, patient_code.strip(), display_name.strip(), age, self._now()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("A patient with this patient code already exists.") from error
        return self.patient(patient_id) or {}

    def patients(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT p.*, COUNT(v.id) AS visit_count FROM patients p LEFT JOIN visits v ON v.patient_id = p.id "
                "GROUP BY p.id ORDER BY p.created_at DESC"
            ).fetchall()
        return [self._patient_row(row) for row in rows]

    def patient(self, patient_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT p.*, COUNT(v.id) AS visit_count FROM patients p LEFT JOIN visits v ON v.patient_id = p.id "
                "WHERE p.id = ? GROUP BY p.id", (patient_id,)
            ).fetchone()
        return self._patient_row(row) if row else None

    @staticmethod
    def _patient_row(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "patient_code": row["patient_code"], "display_name": row["display_name"], "age": row["age"], "created_at": row["created_at"], "visit_count": row["visit_count"]}

    def create_visit(self, patient_id: str, clinical_notes: str = "", visit_date: str | None = None) -> dict[str, Any]:
        if self.patient(patient_id) is None:
            raise KeyError("Patient was not found.")
        visit_id = uuid.uuid4().hex
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO visits(id, patient_id, visit_date, clinical_notes, created_at) VALUES (?, ?, ?, ?, ?)",
                (visit_id, patient_id, visit_date or now, clinical_notes, now),
            )
        return self.visit(visit_id) or {}

    def visits_for_patient(self, patient_id: str) -> list[dict[str, Any]]:
        if self.patient(patient_id) is None:
            raise KeyError("Patient was not found.")
        with self._connection() as connection:
            rows = connection.execute("SELECT id FROM visits WHERE patient_id = ? ORDER BY visit_date DESC", (patient_id,)).fetchall()
        return [self.visit(row["id"]) for row in rows if self.visit(row["id"])]

    def save_assets(self, visit_id: str, paths: dict[str, Path]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO scan_assets(id, visit_id, rgb_path, thermal_path, depth_path, wound_overlay_path, relative_depth_map_path, surface_3d_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(visit_id) DO UPDATE SET rgb_path=excluded.rgb_path, thermal_path=excluded.thermal_path, depth_path=excluded.depth_path, wound_overlay_path=excluded.wound_overlay_path, relative_depth_map_path=excluded.relative_depth_map_path, surface_3d_path=excluded.surface_3d_path",
                (uuid.uuid4().hex, visit_id, *(str(paths[key]) for key in ("rgb", "thermal", "depth", "rgb_roi", "relative_depth", "surface"))),
            )

    def save_analysis(self, visit_id: str, metrics: dict[str, Any], thermal_summary: str) -> str:
        analysis_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO analyses(id, visit_id, wound_roi_pixels, relative_depth_range, mean_depth_variation, depth_variation_std, thermal_summary, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(visit_id) DO UPDATE SET wound_roi_pixels=excluded.wound_roi_pixels, relative_depth_range=excluded.relative_depth_range, mean_depth_variation=excluded.mean_depth_variation, depth_variation_std=excluded.depth_variation_std, thermal_summary=excluded.thermal_summary, created_at=excluded.created_at",
                (analysis_id, visit_id, metrics["wound_roi_pixels"], metrics["relative_depth_range"], metrics["mean_absolute_depth_variation"], metrics["depth_variation_std"], thermal_summary, self._now()),
            )
        return analysis_id

    def save_summary(self, visit_id: str, summary: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO ai_summaries(id, visit_id, assessment_summary, structural_findings_json, thermal_findings_json, attention_points_json, clinician_summary, patient_friendly_summary, created_at, model_name, headline, measured_findings_json, data_quality_json, generation_source, reviewed_by_clinician, reviewed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL) ON CONFLICT(visit_id) DO UPDATE SET assessment_summary=excluded.assessment_summary, structural_findings_json=excluded.structural_findings_json, thermal_findings_json=excluded.thermal_findings_json, attention_points_json=excluded.attention_points_json, clinician_summary=excluded.clinician_summary, patient_friendly_summary=excluded.patient_friendly_summary, created_at=excluded.created_at, model_name=excluded.model_name, headline=excluded.headline, measured_findings_json=excluded.measured_findings_json, data_quality_json=excluded.data_quality_json, generation_source=excluded.generation_source, reviewed_by_clinician=0, reviewed_at=NULL",
                (uuid.uuid4().hex, visit_id, summary["assessment_summary"], json.dumps(summary["structural_findings"]), json.dumps(summary["thermal_findings"]), json.dumps(summary["attention_points"]), summary["clinician_summary"], summary["patient_friendly_summary"], self._now(), summary.get("model_name", ""), summary.get("headline", ""), json.dumps(summary.get("measured_findings", [])), json.dumps(summary.get("data_quality", [])), summary.get("generation_source", "ai_provider")),
            )

    def update_clinical_notes(self, visit_id: str, clinical_notes: str) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE visits SET clinical_notes = ? WHERE id = ?", (clinical_notes, visit_id))

    def mark_summary_reviewed(self, visit_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            connection.execute("UPDATE ai_summaries SET reviewed_by_clinician = 1, reviewed_at = ? WHERE visit_id = ?", (self._now(), visit_id))
        return self.visit(visit_id)

    def save_plan(self, visit_id: str, plan: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO clinical_plans(id, visit_id, clinician_assessment, medication, wound_care_plan, follow_up_interval, additional_tests, escalation_required, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(visit_id) DO UPDATE SET clinician_assessment=excluded.clinician_assessment, medication=excluded.medication, wound_care_plan=excluded.wound_care_plan, follow_up_interval=excluded.follow_up_interval, additional_tests=excluded.additional_tests, escalation_required=excluded.escalation_required, created_at=excluded.created_at",
                (uuid.uuid4().hex, visit_id, plan["clinician_assessment"], plan["medication"], plan["wound_care_plan"], plan["follow_up_interval"], plan["additional_tests"], int(plan["escalation_required"]), self._now()),
            )

    def save_report(self, visit_id: str, file_path: Path) -> str:
        report_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute("INSERT INTO reports(id, visit_id, pdf_path, created_at) VALUES (?, ?, ?, ?)", (report_id, visit_id, str(file_path), self._now()))
        return report_id

    def reports(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT r.id, r.visit_id, r.pdf_path, r.created_at, p.patient_code, p.display_name, v.visit_date FROM reports r JOIN visits v ON v.id=r.visit_id JOIN patients p ON p.id=v.patient_id ORDER BY r.created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def report_path(self, report_id: str) -> Path | None:
        with self._connection() as connection:
            row = connection.execute("SELECT pdf_path FROM reports WHERE id = ?", (report_id,)).fetchone()
        return Path(row["pdf_path"]) if row else None

    def visit(self, visit_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT v.*, p.patient_code, p.display_name, p.age FROM visits v JOIN patients p ON p.id=v.patient_id WHERE v.id=?", (visit_id,)).fetchone()
            if row is None:
                return None
            assets = connection.execute("SELECT * FROM scan_assets WHERE visit_id=?", (visit_id,)).fetchone()
            analysis = connection.execute("SELECT * FROM analyses WHERE visit_id=?", (visit_id,)).fetchone()
            summary = connection.execute("SELECT * FROM ai_summaries WHERE visit_id=?", (visit_id,)).fetchone()
            plan = connection.execute("SELECT * FROM clinical_plans WHERE visit_id=?", (visit_id,)).fetchone()
        result: dict[str, Any] = {"id": row["id"], "patient_id": row["patient_id"], "patient_code": row["patient_code"], "display_name": row["display_name"], "age": row["age"], "visit_date": row["visit_date"], "clinical_notes": row["clinical_notes"], "created_at": row["created_at"]}
        if assets:
            result["assets"] = {"rgb": assets["rgb_path"], "thermal": assets["thermal_path"], "depth": assets["depth_path"], "rgb_roi": assets["wound_overlay_path"], "relative_depth": assets["relative_depth_map_path"], "surface": assets["surface_3d_path"]}
        if analysis:
            result["analysis"] = {"id": analysis["id"], "wound_roi_pixels": analysis["wound_roi_pixels"], "relative_depth_range": analysis["relative_depth_range"], "mean_depth_variation": analysis["mean_depth_variation"], "depth_variation_std": analysis["depth_variation_std"], "thermal_summary": analysis["thermal_summary"], "created_at": analysis["created_at"]}
        if summary:
            result["ai_summary"] = {"headline": summary["headline"], "assessment_summary": summary["assessment_summary"], "measured_findings": json.loads(summary["measured_findings_json"]), "structural_findings": json.loads(summary["structural_findings_json"]), "thermal_findings": json.loads(summary["thermal_findings_json"]), "attention_points": json.loads(summary["attention_points_json"]), "data_quality": json.loads(summary["data_quality_json"]), "clinician_summary": summary["clinician_summary"], "patient_friendly_summary": summary["patient_friendly_summary"], "model_name": summary["model_name"], "generation_source": summary["generation_source"], "reviewed_by_clinician": bool(summary["reviewed_by_clinician"]), "reviewed_at": summary["reviewed_at"], "created_at": summary["created_at"]}
        if plan:
            result["clinical_plan"] = {"clinician_assessment": plan["clinician_assessment"], "medication": plan["medication"], "wound_care_plan": plan["wound_care_plan"], "follow_up_interval": plan["follow_up_interval"], "additional_tests": plan["additional_tests"], "escalation_required": bool(plan["escalation_required"]), "created_at": plan["created_at"]}
        return result
