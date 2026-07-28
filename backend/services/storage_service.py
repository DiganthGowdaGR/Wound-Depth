from __future__ import annotations

import shutil
from pathlib import Path


class StorageService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save_visit_assets(self, patient_id: str, visit_id: str, sources: dict[str, Path]) -> dict[str, Path]:
        destination = self.root / "patients" / patient_id / "visits" / visit_id
        destination.mkdir(parents=True, exist_ok=True)
        saved: dict[str, Path] = {}
        for name, source in sources.items():
            target = destination / f"{name}.png"
            shutil.copyfile(source, target)
            saved[name] = target
        return saved
