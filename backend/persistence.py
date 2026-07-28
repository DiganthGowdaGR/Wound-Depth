"""Small SQLite store for WoundLens analysis records, clinician plans, and reports."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WoundLensStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.asset_root = root / "assets"
        self.report_root = root / "reports"
        self.root.mkdir(parents=True, exist_ok=True)
        self.asset_root.mkdir(parents=True, exist_ok=True)
        self.report_root.mkdir(parents=True, exist_ok=True)
        self.database_path = root / "woundlens.sqlite3"
        self._initialize()

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS patients (patient_id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS visits (visit_id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, created_at TEXT NOT NULL, clinical_notes TEXT);
                CREATE TABLE IF NOT EXISTS analyses (analysis_id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, visit_id TEXT NOT NULL, created_at TEXT NOT NULL, metrics_json TEXT NOT NULL, thermal_summary TEXT, gemini_summary_json TEXT);
                CREATE TABLE IF NOT EXISTS assets (asset_id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, asset_name TEXT NOT NULL, file_path TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS clinical_plans (analysis_id TEXT PRIMARY KEY, plan_json TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (report_id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_analysis(self, patient_id: str, visit_id: str, metrics: dict[str, Any], thermal_summary: str, source_assets: dict[str, Path]) -> str:
        analysis_id = uuid.uuid4().hex
        destination = self.asset_root / analysis_id
        destination.mkdir(parents=True, exist_ok=False)
        copied_assets: list[tuple[str, Path]] = []
        for name, source in source_assets.items():
            if source.is_file():
                target = destination / source.name
                shutil.copyfile(source, target)
                copied_assets.append((name, target))
        with self._connection() as connection:
            connection.execute("INSERT OR IGNORE INTO patients(patient_id, created_at) VALUES (?, ?)", (patient_id, self._now()))
            connection.execute("INSERT OR REPLACE INTO visits(visit_id, patient_id, created_at, clinical_notes) VALUES (?, ?, ?, COALESCE((SELECT clinical_notes FROM visits WHERE visit_id = ?), ''))", (visit_id, patient_id, self._now(), visit_id))
            connection.execute("INSERT INTO analyses(analysis_id, patient_id, visit_id, created_at, metrics_json, thermal_summary) VALUES (?, ?, ?, ?, ?, ?)", (analysis_id, patient_id, visit_id, self._now(), json.dumps(metrics), thermal_summary))
            connection.executemany("INSERT INTO assets(asset_id, analysis_id, asset_name, file_path) VALUES (?, ?, ?, ?)", [(uuid.uuid4().hex, analysis_id, name, str(path)) for name, path in copied_assets])
        return analysis_id

    def analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
            if row is None:
                return None
            assets = connection.execute("SELECT asset_name, file_path FROM assets WHERE analysis_id = ?", (analysis_id,)).fetchall()
            plan = connection.execute("SELECT plan_json FROM clinical_plans WHERE analysis_id = ?", (analysis_id,)).fetchone()
        return {"analysis_id": row["analysis_id"], "patient_id": row["patient_id"], "visit_id": row["visit_id"], "metrics": json.loads(row["metrics_json"]), "thermal_summary": row["thermal_summary"] or "", "gemini_summary": json.loads(row["gemini_summary_json"]) if row["gemini_summary_json"] else None, "assets": {item["asset_name"]: Path(item["file_path"]) for item in assets}, "clinical_plan": json.loads(plan["plan_json"]) if plan else None}

    def update_summary(self, analysis_id: str, summary: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE analyses SET gemini_summary_json = ? WHERE analysis_id = ?", (json.dumps(summary), analysis_id))

    def save_plan(self, analysis_id: str, plan: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute("INSERT INTO clinical_plans(analysis_id, plan_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(analysis_id) DO UPDATE SET plan_json = excluded.plan_json, updated_at = excluded.updated_at", (analysis_id, json.dumps(plan), self._now()))

    def history(self, patient_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT analysis_id, visit_id, created_at, metrics_json, thermal_summary FROM analyses WHERE patient_id = ? ORDER BY created_at", (patient_id,)).fetchall()
        return [{"analysis_id": row["analysis_id"], "visit_id": row["visit_id"], "created_at": row["created_at"], "metrics": json.loads(row["metrics_json"]), "thermal_summary": row["thermal_summary"] or ""} for row in rows]

    def save_report(self, analysis_id: str, file_path: Path) -> str:
        report_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute("INSERT INTO reports(report_id, analysis_id, file_path, created_at) VALUES (?, ?, ?, ?)", (report_id, analysis_id, str(file_path), self._now()))
        return report_id

    def report_path(self, report_id: str) -> Path | None:
        with self._connection() as connection:
            row = connection.execute("SELECT file_path FROM reports WHERE report_id = ?", (report_id,)).fetchone()
        return Path(row["file_path"]) if row else None
