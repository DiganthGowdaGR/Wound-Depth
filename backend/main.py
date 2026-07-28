from __future__ import annotations

import os
import shutil
import tempfile
import uuid
import logging
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import joblib
import matplotlib
import numpy as np
from scipy import ndimage
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from backend.database import DATABASE_PATH
from backend.environment import load_local_env
from backend.persistence import WoundLensStore
from backend.schemas import ClinicalContextInput, ClinicalPlanInput, PatientCreate, VisitCreate
from backend.services.groq_service import AIUnavailable, GroqService
from backend.services.report_service import create_report
from backend.services.storage_service import StorageService

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_local_env(PROJECT_ROOT / ".env")
MODEL_DIR = PROJECT_ROOT / "woundlens_trained_model"
DATASET_DIR = Path(os.environ.get("WOUNDLENS_DATASET_DIR", PROJECT_ROOT / "dataset")).resolve()
SESSION_DIR = Path(tempfile.gettempdir()) / "woundlens-upload-sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
LOGGER = logging.getLogger("woundlens.assets")
LOGGER.setLevel(logging.INFO)
SESSION_ASSET_NAMES = {
    "baseline_rgb", "baseline_thermal", "baseline_depth",
    "current_rgb", "current_thermal", "current_depth",
    "baseline_rgb_roi", "current_rgb_roi",
    "baseline_relative_depth", "current_relative_depth",
    "baseline_3d", "current_3d",
    "current_structural_overview",
    "current_detection_debug",
}
MODALITY_FILE_NAMES = {
    "rgb": ("photo.png", "photo.jpg", "photo.jpeg", "rgb.png", "rgb.jpg", "image.png"),
    "thermal": ("thermal.png", "thermal.jpg", "thermal.jpeg"),
    "depth": ("depth.png", "depth.jpg", "depth.jpeg"),
    "surface": ("surface_3d.png", "3d_wound_surface.png", "wound_3d_analysis.png", "3d.png"),
    "relative_depth": ("relative_depth.png", "relative_depth_map.png", "depth_map.png"),
}


class VisitSummary(BaseModel):
    day: int
    scene: str
    assets: dict[str, str]


class CaseSummary(BaseModel):
    case_id: str
    visit_count: int
    multimodal_visit_count: int


class FollowupRequest(BaseModel):
    previous_case_id: str = Field(..., examples=["case_12"])
    previous_day: int = Field(..., examples=[124])
    previous_scene: str = Field("scene_1", examples=["scene_1"])
    current_case_id: str = Field(..., examples=["case_12"])
    current_day: int = Field(..., examples=[313])
    current_scene: str = Field("scene_1", examples=["scene_1"])


class DepthStatistics(BaseModel):
    relative_depth_range: float
    mean_absolute_variation: float
    depth_variation_std: float
    wound_roi_pixel_count: int
    region_label: str


class StructuralAssessment(BaseModel):
    depth_statistics: DepthStatistics
    roi_available: bool


class TechnicalPipeline(BaseModel):
    baseline_features: dict[str, float]
    current_features: dict[str, float]
    change_features: dict[str, float]
    raw_model_score: float
    low_threshold: float
    high_threshold: float


class AnalyzeFollowupResponse(BaseModel):
    change_level: str
    change_score: float
    rgb_change_index: float
    thermal_change_index: float
    depth_change_index: float
    review_required: bool
    model_loaded: bool
    assets: dict[str, str] = Field(default_factory=dict)
    surface_region_label: str | None = None
    assessments: dict[str, StructuralAssessment] = Field(default_factory=dict)
    technical_pipeline: TechnicalPipeline | None = None


class CurrentStructuralMeasurements(BaseModel):
    wound_roi_pixels: int
    relative_depth_range: float
    mean_absolute_depth_variation: float
    depth_variation_std: float


class AnalyzeCurrentResponse(BaseModel):
    analysis_id: str
    patient_id: str
    visit_id: str
    assets: dict[str, str]
    structural_measurements: CurrentStructuralMeasurements
    surface_region_label: str
    roi_mapping_method: str
    segmentation_status: str
    segmentation_score: float
    thermal_assistance_used: bool
    rgb_url: str
    thermal_url: str
    wound_overlay_url: str
    relative_depth_map_url: str
    surface_3d_url: str


class AiExplanationRequest(BaseModel):
    analysis_id: str
    patient_id: str
    visit_id: str
    wound_roi_pixels: int
    relative_depth_range: float
    mean_depth_variation: float
    depth_variation_std: float
    thermal_summary: str = ""
    clinical_notes: str = ""


class ClinicalPlan(BaseModel):
    clinical_assessment: str = ""
    medication_prescription_entered_by_clinician: str = ""
    dressing_wound_care_plan: str = ""
    follow_up_interval: str = ""
    additional_tests_requested: str = ""
    escalation_required: bool = False


class ReportResponse(BaseModel):
    report_id: str
    report_url: str


@dataclass(frozen=True)
class DepthGeometry:
    """Single source of truth for Colab-equivalent relative-depth analysis."""

    wound_mask: np.ndarray
    depth_gray: np.ndarray
    reference_depth: float
    relative_z: np.ndarray
    percentile_low: float
    percentile_high: float
    x_plot: np.ndarray
    y_plot: np.ndarray
    z_plot: np.ndarray
    depth_only: np.ndarray
    relative_range: float
    mean_absolute_variation: float
    depth_variation_std: float


@dataclass(frozen=True)
class AutomaticSegmentation:
    mask: np.ndarray
    wound_likelihood: np.ndarray
    score: float
    thermal_assistance_used: bool


def _load_artifact(name: str) -> Any:
    path = MODEL_DIR / name
    if not path.exists():
        raise RuntimeError(f"Missing model artifact: {path}")
    return joblib.load(path)


class DatasetRepository:
    """Safely maps known case/visit modality files without exposing arbitrary paths."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def list_cases(self) -> list[CaseSummary]:
        if not self.root.exists():
            return []
        cases: list[CaseSummary] = []
        for case_dir in sorted(path for path in self.root.iterdir() if path.is_dir() and path.name.startswith("case_")):
            visits = self.list_visits(case_dir.name)
            cases.append(CaseSummary(
                case_id=case_dir.name,
                visit_count=len(visits),
                multimodal_visit_count=sum(self._has_core_modalities(visit) for visit in visits),
            ))
        return cases

    def list_visits(self, case_id: str) -> list[VisitSummary]:
        case_dir = self._case_dir(case_id)
        visits: list[VisitSummary] = []
        day_dirs = [path for path in case_dir.iterdir() if path.is_dir() and self._day_from_name(path.name) is not None]
        for day_dir in sorted(day_dirs, key=lambda path: self._day_from_name(path.name) or 0):
            day = self._day_from_name(day_dir.name)
            if day is None:
                continue
            scene_dirs = [path for path in day_dir.rglob("scene_*") if path.is_dir()]
            if not scene_dirs:
                scene_dirs = [day_dir]
            for scene_dir in scene_dirs:
                scene = scene_dir.name if scene_dir.name.startswith("scene_") else "scene_1"
                assets = self._assets_for_dir(scene_dir)
                if assets:
                    visits.append(VisitSummary(day=day, scene=scene, assets={modality: modality for modality in assets}))
        return visits

    def read_asset(self, case_id: str, day: int, scene: str, modality: str) -> Path:
        visit_dir = self._visit_dir(case_id, day, scene)
        asset = self._assets_for_dir(visit_dir).get(modality)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"No {modality} image exists for {case_id}/day_{day}/{scene}.")
        return asset

    def registration_file(self, case_id: str, day: int, scene: str) -> Path | None:
        registration = self._visit_dir(case_id, day, scene) / "registration.json"
        return registration if registration.is_file() else None

    def _case_dir(self, case_id: str) -> Path:
        if not case_id.startswith("case_") or any(part in case_id for part in ("/", "\\", "..")):
            raise HTTPException(status_code=400, detail="Invalid case id.")
        case_dir = self.root / case_id
        if not case_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"Dataset case {case_id} was not found. Configure WOUNDLENS_DATASET_DIR.")
        return case_dir

    def _visit_dir(self, case_id: str, day: int, scene: str) -> Path:
        if not scene.startswith("scene_") or any(part in scene for part in ("/", "\\", "..")):
            raise HTTPException(status_code=400, detail="Invalid scene.")
        case_dir = self._case_dir(case_id)
        day_dir = next((path for path in case_dir.iterdir() if path.is_dir() and self._day_from_name(path.name) == day), None)
        if day_dir is None:
            raise HTTPException(status_code=404, detail=f"Visit day {day} was not found for {case_id}.")
        scene_dir = next((path for path in day_dir.rglob(scene) if path.is_dir()), None)
        return scene_dir or day_dir

    @staticmethod
    def _day_from_name(name: str) -> int | None:
        normalized = name.lower().replace("-", "_")
        if not normalized.startswith("day_"):
            return None
        try:
            return int(normalized.split("_", maxsplit=1)[1])
        except ValueError:
            return None

    @staticmethod
    def _has_core_modalities(visit: VisitSummary) -> bool:
        return all(modality in visit.assets for modality in ("rgb", "thermal", "depth"))

    @staticmethod
    def _assets_for_dir(visit_dir: Path) -> dict[str, Path]:
        assets: dict[str, Path] = {}
        if not visit_dir.exists():
            return assets
        available = {path.name.lower(): path for path in visit_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS}
        for modality, names in MODALITY_FILE_NAMES.items():
            for name in names:
                if name in available:
                    assets[modality] = available[name]
                    break
        return assets


class WoundLensModel:
    def __init__(self) -> None:
        self.change_model = _load_artifact("woundlens_change_model.pkl")
        self.scaler = _load_artifact("woundlens_scaler.pkl")
        self.features = list(_load_artifact("woundlens_features.pkl"))
        self.thresholds = _load_artifact("woundlens_thresholds.pkl")

    def analyze(self, baseline: dict[str, np.ndarray], current: dict[str, np.ndarray]) -> AnalyzeFollowupResponse:
        baseline_features = self._extract_features(baseline)
        current_features = self._extract_features(current)
        feature_values = self._feature_changes(baseline_features, current_features)
        vector = np.asarray([[feature_values[name] for name in self.features]], dtype=float)
        transformed = self.scaler.transform(vector)
        raw_score = float(np.ravel(self.change_model.decision_function(transformed))[0])
        change_level = self._classify_change(raw_score)
        return AnalyzeFollowupResponse(
            change_level=change_level,
            change_score=round(abs(raw_score), 4),
            rgb_change_index=round(self._index(feature_values, "rgb_"), 2),
            thermal_change_index=round(self._index(feature_values, "thermal_"), 2),
            depth_change_index=round(self._index(feature_values, "depth_"), 2),
            review_required=change_level == "HIGH CHANGE",
            model_loaded=True,
            technical_pipeline=TechnicalPipeline(
                baseline_features=baseline_features,
                current_features=current_features,
                change_features=feature_values,
                raw_model_score=raw_score,
                low_threshold=float(self.thresholds["low_threshold"]),
                high_threshold=float(self.thresholds["high_threshold"]),
            ),
        )

    @staticmethod
    def _extract_features(images: dict[str, np.ndarray]) -> dict[str, float]:
        rgb = images["rgb"]
        values: dict[str, float] = {}
        for index, channel in enumerate(("r", "g", "b")):
            values[f"rgb_{channel}_mean"] = float(rgb[..., index].mean())
            values[f"rgb_{channel}_std"] = float(rgb[..., index].std())
        for modality in ("thermal", "depth"):
            modality_values = images[modality].reshape(-1)
            values[f"{modality}_mean"] = float(modality_values.mean())
            values[f"{modality}_std"] = float(modality_values.std())
            for percentile in (25, 50, 75):
                values[f"{modality}_p{percentile}"] = float(np.percentile(modality_values, percentile))
        return values

    def _feature_changes(self, baseline: dict[str, float], current: dict[str, float]) -> dict[str, float]:
        return {f"{name}_pct_change": self._percent_change(baseline[name], current[name]) for name in self.features_for_raw_values()}

    def features_for_raw_values(self) -> list[str]:
        return [str(name).removesuffix("_pct_change") for name in self.features]

    @staticmethod
    def _percent_change(previous: float, current: float) -> float:
        if not np.isfinite(previous) or not np.isfinite(current) or abs(previous) < 1e-6:
            raise ValueError("A required baseline feature is invalid or zero; percentage change cannot be calculated.")
        return ((current - previous) / abs(previous)) * 100

    @staticmethod
    def _index(feature_values: dict[str, float], prefix: str) -> float:
        values = [abs(value) for key, value in feature_values.items() if key.startswith(prefix)]
        return float(np.mean(values)) if values else 0.0

    def _classify_change(self, raw_score: float) -> str:
        high = float(self.thresholds["high_threshold"])
        low = float(self.thresholds["low_threshold"])
        if raw_score <= high:
            return "HIGH CHANGE"
        if raw_score <= low:
            return "MODERATE CHANGE"
        return "LOW CHANGE"


def _load_image(source: Path | UploadFile) -> np.ndarray:
    if isinstance(source, Path):
        with Image.open(source) as image:
            return np.asarray(image.convert("RGB"), dtype=np.float64)
    try:
        with Image.open(source.file) as image:
            return np.asarray(image.convert("RGB"), dtype=np.float64)
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Invalid image file: {source.filename or 'upload'}") from error


def _write_png(source: Path | UploadFile, destination: Path) -> None:
    try:
        if isinstance(source, Path):
            shutil.copyfile(source, destination)
            return
        source.file.seek(0)
        with destination.open("wb") as output:
            shutil.copyfileobj(source.file, output)
        source.file.seek(0)
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Unable to store image file: {getattr(source, 'filename', destination.name)}") from error


def _load_depth_gray(depth_image: Path) -> np.ndarray:
    """Load the original depth PNG exactly as the Colab structural pipeline did."""

    depth_bgr = cv2.imread(str(depth_image), cv2.IMREAD_COLOR)
    if depth_bgr is None:
        raise ValueError(f"Unable to read depth image: {depth_image.name}")
    return cv2.cvtColor(depth_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)


def _build_depth_geometry(depth_image: Path, roi_mask: np.ndarray | None) -> DepthGeometry:
    """Apply the one Colab depth calculation used by metrics, map, and 3D points."""

    depth_gray = _load_depth_gray(depth_image)
    wound_mask = np.ones(depth_gray.shape, dtype=bool) if roi_mask is None else roi_mask.astype(bool)
    if wound_mask.shape != depth_gray.shape:
        raise ValueError("Wound ROI and original depth image dimensions do not match.")
    if not np.any(wound_mask):
        raise ValueError("No wound pixels are available for structural analysis.")

    ys, xs = np.where(wound_mask)
    z = depth_gray[wound_mask]
    reference_depth = float(np.median(z))
    relative_z = z - reference_depth
    percentile_low, percentile_high = (float(value) for value in np.percentile(relative_z, (2, 98)))
    keep = (relative_z >= percentile_low) & (relative_z <= percentile_high)
    x_plot, y_plot, z_plot = xs[keep], ys[keep], relative_z[keep]
    if z_plot.size == 0:
        raise ValueError("No wound depth points remained after percentile clipping.")

    depth_only = np.full(depth_gray.shape, np.nan, dtype=np.float32)
    depth_only[wound_mask] = relative_z
    return DepthGeometry(
        wound_mask=wound_mask,
        depth_gray=depth_gray,
        reference_depth=reference_depth,
        relative_z=relative_z,
        percentile_low=percentile_low,
        percentile_high=percentile_high,
        x_plot=x_plot,
        y_plot=y_plot,
        z_plot=z_plot,
        depth_only=depth_only,
        relative_range=float(np.max(z_plot) - np.min(z_plot)),
        mean_absolute_variation=float(np.mean(np.abs(z_plot))),
        depth_variation_std=float(np.std(z_plot)),
    )


def _log_depth_geometry(label: str, geometry: DepthGeometry) -> None:
    LOGGER.info(
        "%s depth geometry: depth_shape=%s mask_shape=%s mask_pixels=%s depth_min=%.2f depth_max=%.2f "
        "wound_depth_pixels=%s reference_depth=%.2f p2=%.2f p98=%.2f relative_min=%.2f relative_max=%.2f "
        "range=%.2f mean_abs=%.2f std=%.2f plotted_points=%s x_range=(%s,%s) y_range=(%s,%s)",
        label,
        geometry.depth_gray.shape,
        geometry.wound_mask.shape,
        int(geometry.wound_mask.sum()),
        float(geometry.depth_gray.min()),
        float(geometry.depth_gray.max()),
        geometry.relative_z.size,
        geometry.reference_depth,
        geometry.percentile_low,
        geometry.percentile_high,
        float(geometry.z_plot.min()),
        float(geometry.z_plot.max()),
        geometry.relative_range,
        geometry.mean_absolute_variation,
        geometry.depth_variation_std,
        geometry.z_plot.size,
        int(geometry.x_plot.min()),
        int(geometry.x_plot.max()),
        int(geometry.y_plot.min()),
        int(geometry.y_plot.max()),
    )


def _render_relative_depth(geometry: DepthGeometry, destination: Path) -> None:
    figure = Figure(figsize=(8, 6), dpi=150)
    figure.patch.set_facecolor("white")
    axis = figure.add_subplot(111)
    depth_map = np.ma.masked_invalid(geometry.depth_only)
    image = axis.imshow(depth_map, cmap="viridis", vmin=geometry.percentile_low, vmax=geometry.percentile_high)
    axis.set_title("Wound Relative Depth Map")
    axis.set_axis_off()
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="Relative depth value")
    figure.tight_layout()
    FigureCanvasAgg(figure).print_png(destination)


def _render_depth_surface(geometry: DepthGeometry, destination: Path) -> None:
    figure = Figure(figsize=(8, 6), dpi=150)
    figure.patch.set_facecolor("white")
    axis = figure.add_subplot(111, projection="3d")
    points = axis.scatter(
        geometry.x_plot,
        geometry.y_plot,
        geometry.z_plot,
        c=geometry.z_plot,
        cmap="viridis",
        vmin=geometry.percentile_low,
        vmax=geometry.percentile_high,
        s=5,
        linewidths=0,
    )
    axis.set_title("3D Wound Surface")
    axis.set_xlabel("X")
    axis.set_ylabel("Y")
    axis.set_zlabel("Relative Depth")
    axis.invert_yaxis()
    axis.view_init(elev=35, azim=-60)
    figure.colorbar(points, ax=axis, fraction=0.046, pad=0.08, label="Relative depth value")
    figure.tight_layout()
    FigureCanvasAgg(figure).print_png(destination)


def _render_structural_overview(rgb_image: Path, thermal_image: Path, geometry: DepthGeometry, destination: Path) -> None:
    """Render the real four-modality structural assessment figure used in the demo."""

    with Image.open(rgb_image) as image:
        rgb = np.asarray(image.convert("RGB"))
    with Image.open(thermal_image) as image:
        thermal = np.asarray(image.convert("RGB"))

    figure = Figure(figsize=(20, 6.4), dpi=160)
    figure.patch.set_facecolor("white")
    figure.suptitle("WoundLens - Multimodal Structural Assessment", fontsize=18, fontweight="bold")

    rgb_axis = figure.add_subplot(141)
    rgb_axis.imshow(rgb)
    rgb_axis.contour(geometry.wound_mask.astype(np.uint8), levels=[0.5], colors="#17dbe6", linewidths=2)
    rgb_axis.set_title("RGB + Wound Region", fontweight="bold")
    rgb_axis.set_axis_off()

    thermal_axis = figure.add_subplot(142)
    thermal_axis.imshow(thermal)
    thermal_axis.set_title("Thermal View", fontweight="bold")
    thermal_axis.set_axis_off()

    depth_axis = figure.add_subplot(143)
    depth_map = np.ma.masked_invalid(geometry.depth_only)
    depth_image = depth_axis.imshow(depth_map, cmap="viridis", vmin=geometry.percentile_low, vmax=geometry.percentile_high)
    depth_axis.set_title("Wound Relative Depth Map", fontweight="bold")
    depth_axis.set_axis_off()
    figure.colorbar(depth_image, ax=depth_axis, fraction=0.046, pad=0.04, label="Relative depth value")

    surface_axis = figure.add_subplot(144, projection="3d")
    surface_axis.scatter(
        geometry.x_plot,
        geometry.y_plot,
        geometry.z_plot,
        c=geometry.z_plot,
        cmap="viridis",
        vmin=geometry.percentile_low,
        vmax=geometry.percentile_high,
        s=5,
        linewidths=0,
    )
    surface_axis.set_title("3D Wound Surface", fontweight="bold")
    surface_axis.set_xlabel("X")
    surface_axis.set_ylabel("Y")
    surface_axis.set_zlabel("Relative Depth")
    surface_axis.invert_yaxis()
    surface_axis.view_init(elev=35, azim=-60)
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    FigureCanvasAgg(figure).print_png(destination)


def _robust_normalize(values: np.ndarray, support: np.ndarray) -> np.ndarray:
    samples = values[support]
    if samples.size < 20:
        samples = values.ravel()
    low, high = (float(value) for value in np.percentile(samples, (5, 95)))
    return np.clip((values - low) / (high - low + 1e-6), 0.0, 1.0)


def _draw_wound_overlay(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    output = rgb.copy()
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(output, contours, -1, (23, 219, 230), 2)
    return output


def _render_automatic_detection_debug(rgb_image: Path, segmentation: AutomaticSegmentation, destination: Path) -> None:
    """Inspection image used to validate automatic localization before depth analysis."""

    with Image.open(rgb_image) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    figure = Figure(figsize=(16, 4.4), dpi=150)
    figure.patch.set_facecolor("white")
    panels = (
        ("Original RGB", rgb, None),
        ("Wound Likelihood", segmentation.wound_likelihood, "magma"),
        ("Binary Wound Mask", segmentation.mask, "gray"),
        ("RGB + Automatic Wound Boundary", _draw_wound_overlay(rgb, segmentation.mask), None),
    )
    for index, (title, data, cmap) in enumerate(panels, start=1):
        axis = figure.add_subplot(1, 4, index)
        axis.imshow(data, cmap=cmap, vmin=0, vmax=1 if cmap else None)
        axis.set_title(title, fontweight="bold")
        axis.set_axis_off()
    figure.tight_layout()
    FigureCanvasAgg(figure).print_png(destination)


def _automatic_wound_localization(rgb_image: Path, thermal_image: Path) -> AutomaticSegmentation:
    """Classical RGB/LAB/HSV localization with relative thermal assistance when registered."""

    with Image.open(rgb_image) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    luminance, lab_a, lab_b = (lab[..., channel] for channel in range(3))
    warm_hue = (hsv[..., 0] <= 28) | (hsv[..., 0] >= 165)
    limb_mask = warm_hue & (hsv[..., 1] >= 30) & (
        ((lab_a >= 138) & (luminance < 165))
        | ((luminance < 130) & (lab_a >= 132) & (lab_b >= 135))
    )
    limb_mask = cv2.morphologyEx(limb_mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    if int(limb_mask.sum()) < max(250, int(height * width * 0.03)):
        raise ValueError("Automatic wound localization is uncertain: no reliable limb/skin region was found.")

    local_luminance = cv2.GaussianBlur(luminance, (0, 0), 15)
    local_a = cv2.GaussianBlur(lab_a, (0, 0), 15)
    local_b = cv2.GaussianBlur(lab_b, (0, 0), 15)
    texture_mean = cv2.GaussianBlur(luminance, (0, 0), 4)
    texture_squared_mean = cv2.GaussianBlur(luminance * luminance, (0, 0), 4)
    texture = np.sqrt(np.maximum(texture_squared_mean - (texture_mean * texture_mean), 0.0))
    red_channel, green_channel, _ = (rgb[..., channel].astype(np.float32) for channel in range(3))
    absolute_redness = _robust_normalize(lab_a, limb_mask)
    channel_redness = _robust_normalize(red_channel - green_channel, limb_mask)
    local_redness = _robust_normalize(lab_a - local_a, limb_mask)
    dark_tissue = _robust_normalize(local_luminance - luminance, limb_mask)
    texture_score = _robust_normalize(texture, limb_mask)
    # Strong local redness is more specific to the visible ulcer than a dark ankle/foot edge.
    rgb_score = (0.36 * absolute_redness) + (0.25 * channel_redness) + (0.17 * local_redness) + (0.12 * dark_tissue) + (0.10 * texture_score)
    rgb_score *= limb_mask

    thermal_assistance_used = False
    thermal_score = np.zeros_like(rgb_score)
    with Image.open(thermal_image) as image:
        thermal = np.asarray(image.convert("L"), dtype=np.float32)
    if thermal.shape == rgb_score.shape:
        thermal_assistance_used = True
        thermal_background = cv2.GaussianBlur(thermal, (0, 0), 13)
        thermal_score = _robust_normalize(np.abs(thermal - thermal_background), limb_mask)
        likelihood = (0.85 * rgb_score) + (0.15 * thermal_score * limb_mask)
    else:
        likelihood = rgb_score

    # Keep connected red, yellow, and dark wound-bed tissue together. A stricter seed split
    # elongated ulcers into separate components and could select only the distal fragment.
    candidate = (likelihood >= np.percentile(likelihood[limb_mask], 85)) & (rgb_score >= np.percentile(rgb_score[limb_mask], 75)) & limb_mask
    candidate = cv2.morphologyEx(candidate.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    label_count, labels, stats, centers = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    components: list[dict[str, Any]] = []
    for label in range(1, label_count):
        x, y, component_width, component_height, area = (int(value) for value in stats[label])
        edge_margin = min(x, y, width - (x + component_width), height - (y + component_height))
        if area < max(75, int(height * width * 0.001)) or edge_margin < min(width, height) * 0.10:
            continue
        components.append({"label": label, "area": area, "center": centers[label]})
    if not components:
        raise ValueError("Automatic wound localization is uncertain: no wound-like tissue candidates were found.")

    # Nearby abnormal-tissue components form a wound candidate; distant background/limb-edge findings do not.
    groups: list[list[dict[str, Any]]] = []
    linkage_distance = min(width, height) * 0.30
    for component in components:
        matches = [index for index, group in enumerate(groups) if any(np.linalg.norm(component["center"] - item["center"]) <= linkage_distance for item in group)]
        if not matches:
            groups.append([component])
            continue
        target = matches[0]
        groups[target].append(component)
        for index in reversed(matches[1:]):
            groups[target].extend(groups.pop(index))

    best_mask: np.ndarray | None = None
    best_score = -1.0
    image_area = float(height * width)
    for group in groups:
        source_mask = np.isin(labels, [item["label"] for item in group])
        points = np.column_stack(np.nonzero(source_mask)[::-1]).astype(np.int32)
        if points.shape[0] < 3:
            continue
        hull = cv2.convexHull(points)
        proposed = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(proposed, hull, 1)
        proposed = cv2.morphologyEx(proposed, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
        core_mask = proposed
        # The seed is the high-evidence tissue core. Expand only into nearby limb pixels so
        # the ROI includes its visible border without drifting into the bed/background.
        border_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
        limb_allowance = cv2.dilate(limb_mask.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 0
        proposed = (cv2.dilate(proposed.astype(np.uint8), border_kernel) > 0) & limb_allowance
        area = int(proposed.sum())
        if area < max(250, int(image_area * 0.003)) or area > int(image_area * 0.18):
            continue
        y_values, x_values = np.nonzero(proposed)
        margin = min(int(x_values.min()), int(y_values.min()), width - 1 - int(x_values.max()), height - 1 - int(y_values.max()))
        if margin < min(width, height) * 0.10:
            continue
        margin_score = float(np.clip(margin / max(1.0, min(width, height) * 0.5), 0.0, 1.0))
        core_area = int(core_mask.sum())
        # In this workflow the visible wound bed is often elongated. Prefer a coherent
        # wound-bed extent over a tiny, very-red patch on nearby intact skin.
        area_score = float(np.exp(-abs(np.log(max(core_area / image_area, 1e-6) / 0.12))))
        mean_rgb = float(rgb_score[core_mask].mean())
        mean_thermal = float(thermal_score[core_mask].mean()) if thermal_assistance_used else 0.0
        component_density = float(source_mask.sum() / max(1, int(core_mask.sum())))
        group_evidence = min(1.0, len(group) / 3.0)
        score = (0.32 * mean_rgb) + (0.07 * mean_thermal) + (0.10 * margin_score) + (0.34 * area_score) + (0.10 * component_density) + (0.07 * group_evidence)
        if score > best_score:
            best_mask = proposed
            best_score = score

    if best_mask is None or best_score < 0.50:
        raise ValueError("Automatic wound localization is uncertain: candidate quality checks did not pass.")
    return AutomaticSegmentation(best_mask, likelihood, best_score, thermal_assistance_used)


def _generate_rgb_roi(rgb_image: Path, destination: Path) -> np.ndarray | None:
    with Image.open(rgb_image) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
    channels = rgb / 255.0
    maximum = channels.max(axis=-1)
    saturation = np.divide(maximum - channels.min(axis=-1), maximum, out=np.zeros_like(maximum), where=maximum > 0)
    redness = channels[..., 0] - ((channels[..., 1] + channels[..., 2]) / 2)
    score = redness + (0.35 * saturation)
    candidate = score >= np.percentile(score, 92)
    candidate = ndimage.binary_opening(candidate, iterations=1)
    candidate = ndimage.binary_closing(candidate, iterations=2)
    labels, count = ndimage.label(candidate)
    if count == 0:
        return None
    component_sizes = np.bincount(labels.ravel())
    component_sizes[0] = 0
    roi = labels == component_sizes.argmax()
    if roi.sum() < 40:
        return None
    output = rgb.astype(np.uint8).copy()
    output[roi] = ((0.72 * output[roi]) + (0.28 * np.array((30, 200, 207))).astype(np.uint8))
    outline = roi & ~ndimage.binary_erosion(roi, iterations=1)
    output[outline] = np.array((19, 219, 230), dtype=np.uint8)
    Image.fromarray(output, mode="RGB").save(destination, format="PNG")
    return roi


def _registered_depth_roi(rgb_roi: np.ndarray | None, registration_file: Path | None, depth_shape: tuple[int, int]) -> np.ndarray | None:
    if rgb_roi is None or registration_file is None or not registration_file.is_file():
        return None
    try:
        transforms = {item["type"]: np.asarray(item["transformation_matrix"], dtype=float) for item in json.loads(registration_file.read_text())}
        thermal_to_photo = transforms["ThermalToPhoto"]
        thermal_to_depth = transforms["ThermalToTof"]
        photo_to_thermal = np.linalg.inv(thermal_to_photo)
        y, x = np.nonzero(rgb_roi)
        points = np.column_stack((x, y, np.ones_like(x, dtype=float)))
        thermal = points @ photo_to_thermal.T
        depth = thermal @ thermal_to_depth.T
        depth_x = np.rint(depth[:, 0] / depth[:, 2]).astype(int)
        depth_y = np.rint(depth[:, 1] / depth[:, 2]).astype(int)
        in_bounds = (depth_x >= 0) & (depth_x < depth_shape[1]) & (depth_y >= 0) & (depth_y < depth_shape[0])
        mask = np.zeros(depth_shape, dtype=bool)
        mask[depth_y[in_bounds], depth_x[in_bounds]] = True
        mask = ndimage.binary_dilation(mask, iterations=2)
        mask = ndimage.binary_closing(mask, iterations=2)
        return mask if mask.sum() >= 40 else None
    except Exception:
        LOGGER.exception("Unable to register RGB ROI to depth image using %s", registration_file)
        return None


def _map_rgb_roi_to_depth(rgb_roi: np.ndarray, registration_file: Path | None, depth_shape: tuple[int, int]) -> tuple[np.ndarray, str]:
    registered = _registered_depth_roi(rgb_roi, registration_file, depth_shape)
    if registered is not None:
        return registered, "Registered RGB-to-depth ROI mapping"
    resized = Image.fromarray((rgb_roi.astype(np.uint8) * 255), mode="L").resize((depth_shape[1], depth_shape[0]), Image.Resampling.NEAREST)
    mapped = np.asarray(resized, dtype=np.uint8) > 0
    if not np.any(mapped):
        raise ValueError("The RGB wound ROI could not be mapped to the depth image.")
    return mapped, "Normalized image-coordinate ROI mapping (registration unavailable)"


def _depth_statistics(depth_image: Path, roi_mask: np.ndarray | None) -> DepthStatistics:
    geometry = _build_depth_geometry(depth_image, roi_mask)
    return DepthStatistics(
        relative_depth_range=geometry.relative_range,
        mean_absolute_variation=geometry.mean_absolute_variation,
        depth_variation_std=geometry.depth_variation_std,
        wound_roi_pixel_count=int(geometry.wound_mask.sum()),
        region_label="Wound ROI" if roi_mask is not None else "Full scan region",
    )


def _asset_url(session_id: str, asset_name: str) -> str:
    return f"/analysis-assets/{session_id}/{asset_name}"


def _cleanup_expired_sessions() -> None:
    expiry = time.time() - (24 * 60 * 60)
    for session in SESSION_DIR.iterdir():
        if session.is_dir() and session.stat().st_mtime < expiry:
            shutil.rmtree(session, ignore_errors=True)


def _process_scan_pair(
    baseline_sources: dict[str, Path | UploadFile],
    current_sources: dict[str, Path | UploadFile],
    baseline_registration: Path | None = None,
    current_registration: Path | None = None,
) -> tuple[dict[str, Path], dict[str, Path], dict[str, str], dict[str, StructuralAssessment]]:
    _cleanup_expired_sessions()
    session_id = uuid.uuid4().hex
    session_path = SESSION_DIR / session_id
    session_path.mkdir(parents=True, exist_ok=False)
    baseline_paths: dict[str, Path] = {}
    current_paths: dict[str, Path] = {}
    assets: dict[str, str] = {}
    for modality in ("rgb", "thermal", "depth"):
        baseline_path = session_path / f"baseline_{modality}.png"
        current_path = session_path / f"current_{modality}.png"
        _write_png(baseline_sources[modality], baseline_path)
        _write_png(current_sources[modality], current_path)
        baseline_paths[modality] = baseline_path
        current_paths[modality] = current_path
        assets[f"baseline_{modality}"] = _asset_url(session_id, f"baseline_{modality}")
        assets[f"current_{modality}"] = _asset_url(session_id, f"current_{modality}")
    assessments: dict[str, StructuralAssessment] = {}
    for prefix, paths, registration_file in (
        ("baseline", baseline_paths, baseline_registration),
        ("current", current_paths, current_registration),
    ):
        try:
            rgb_roi = _generate_rgb_roi(paths["rgb"], session_path / f"{prefix}_rgb_roi.png")
            if rgb_roi is not None:
                assets[f"{prefix}_rgb_roi"] = _asset_url(session_id, f"{prefix}_rgb_roi")
            depth_shape = _load_depth_gray(paths["depth"]).shape
            depth_roi = _registered_depth_roi(rgb_roi, registration_file, depth_shape)
            relative_name = f"{prefix}_relative_depth"
            surface_name = f"{prefix}_3d"
            geometry = _build_depth_geometry(paths["depth"], depth_roi)
            _render_relative_depth(geometry, session_path / f"{relative_name}.png")
            _render_depth_surface(geometry, session_path / f"{surface_name}.png")
            assets[relative_name] = _asset_url(session_id, relative_name)
            assets[surface_name] = _asset_url(session_id, surface_name)
            assessments[prefix] = StructuralAssessment(
                depth_statistics=DepthStatistics(
                    relative_depth_range=geometry.relative_range,
                    mean_absolute_variation=geometry.mean_absolute_variation,
                    depth_variation_std=geometry.depth_variation_std,
                    wound_roi_pixel_count=int(geometry.wound_mask.sum()),
                    region_label="Wound ROI" if depth_roi is not None else "Full scan region",
                ),
                roi_available=depth_roi is not None,
            )
        except Exception:
            LOGGER.exception("Unable to generate %s depth visualizations for session %s", prefix, session_id)
    return baseline_paths, current_paths, assets, assessments


def _analyze_pair(
    baseline_sources: dict[str, Path | UploadFile],
    current_sources: dict[str, Path | UploadFile],
    baseline_registration: Path | None = None,
    current_registration: Path | None = None,
) -> AnalyzeFollowupResponse:
    try:
        baseline_paths, current_paths, assets, assessments = _process_scan_pair(
            baseline_sources, current_sources, baseline_registration, current_registration
        )
        result = model.analyze(
            {modality: _load_image(path) for modality, path in baseline_paths.items()},
            {modality: _load_image(path) for modality, path in current_paths.items()},
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Analysis failed: {error}") from error
    surface_label = "Depth Surface - wound ROI" if assessments and all(item.roi_available for item in assessments.values()) else "Depth Surface - full scan region"
    return result.model_copy(update={"assets": assets, "assessments": assessments, "surface_region_label": surface_label})


def _analyze_current_scan(sources: dict[str, UploadFile], patient_id: str, clinical_notes: str) -> AnalyzeCurrentResponse:
    if store.patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient was not found.")
    _cleanup_expired_sessions()
    session_id = uuid.uuid4().hex
    session_path = SESSION_DIR / session_id
    session_path.mkdir(parents=True, exist_ok=False)
    paths: dict[str, Path] = {}
    for modality, source in sources.items():
        path = session_path / f"current_{modality}.png"
        _write_png(source, path)
        paths[modality] = path
    try:
        segmentation = _automatic_wound_localization(paths["rgb"], paths["thermal"])
        rgb_roi = segmentation.mask
        _render_automatic_detection_debug(paths["rgb"], segmentation, session_path / "current_detection_debug.png")
        with Image.open(paths["rgb"]) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        Image.fromarray(_draw_wound_overlay(rgb, rgb_roi), mode="RGB").save(session_path / "current_rgb_roi.png", format="PNG")
        depth_shape = _load_depth_gray(paths["depth"]).shape
        if rgb_roi.shape != depth_shape:
            raise ValueError("RGB-to-depth mapping mismatch: automatic ROI requires matching RGB and depth image dimensions.")
        depth_roi = rgb_roi
        mapping_method = "Automatic RGB/thermal wound mask in original image coordinates"
        geometry = _build_depth_geometry(paths["depth"], depth_roi)
        _log_depth_geometry("current-upload", geometry)
        _render_relative_depth(geometry, session_path / "current_relative_depth.png")
        _render_depth_surface(geometry, session_path / "current_3d.png")
        _render_structural_overview(paths["rgb"], paths["thermal"], geometry, session_path / "current_structural_overview.png")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Analysis failed: {error}") from error
    measurements = CurrentStructuralMeasurements(
        wound_roi_pixels=int(geometry.wound_mask.sum()),
        relative_depth_range=geometry.relative_range,
        mean_absolute_depth_variation=geometry.mean_absolute_variation,
        depth_variation_std=geometry.depth_variation_std,
    )
    persisted_assets = {
        "rgb": paths["rgb"],
        "rgb_roi": session_path / "current_rgb_roi.png",
        "thermal": paths["thermal"],
        "depth": paths["depth"],
        "relative_depth": session_path / "current_relative_depth.png",
        "surface": session_path / "current_3d.png",
        "structural_overview": session_path / "current_structural_overview.png",
    }
    try:
        visit = store.create_visit(patient_id, clinical_notes)
        visit_id = visit["id"]
        saved_assets = storage.save_visit_assets(patient_id, visit_id, persisted_assets)
        store.save_assets(visit_id, saved_assets)
        analysis_id = store.save_analysis(visit_id, measurements.model_dump(), "Thermal image is preserved for relative contrast review; WoundLens does not interpret image pixels as Celsius.")
    except Exception as error:
        LOGGER.exception("Unable to persist analysis session %s", session_id)
        raise HTTPException(status_code=500, detail="Analysis completed but could not be saved.") from error
    return AnalyzeCurrentResponse(
        analysis_id=analysis_id,
        patient_id=patient_id,
        visit_id=visit_id,
        assets={name: _stored_asset_url(patient_id, visit_id, path.name) for name, path in saved_assets.items()},
        structural_measurements=measurements,
        surface_region_label="3D Wound Surface - Automatic ROI",
        roi_mapping_method=mapping_method,
        segmentation_status="success",
        segmentation_score=segmentation.score,
        thermal_assistance_used=segmentation.thermal_assistance_used,
        rgb_url=_stored_asset_url(patient_id, visit_id, saved_assets["rgb"].name),
        thermal_url=_stored_asset_url(patient_id, visit_id, saved_assets["thermal"].name),
        wound_overlay_url=_stored_asset_url(patient_id, visit_id, saved_assets["rgb_roi"].name),
        relative_depth_map_url=_stored_asset_url(patient_id, visit_id, saved_assets["relative_depth"].name),
        surface_3d_url=_stored_asset_url(patient_id, visit_id, saved_assets["surface"].name),
    )


repository = DatasetRepository(DATASET_DIR)
model = WoundLensModel()
store = WoundLensStore(DATABASE_PATH)
storage = StorageService(store.storage_root)
ai_service = GroqService()
app = FastAPI(title="WoundLens ML API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "database": store.healthy(),
        "groq_configured": ai_service.configured,
    }


def _stored_asset_url(patient_id: str, visit_id: str, filename: str) -> str:
    return f"/storage/patients/{patient_id}/visits/{visit_id}/{filename}"


def _visit_response(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    if record.get("assets"):
        result["assets"] = {name: _stored_asset_url(record["patient_id"], record["id"], Path(path).name) for name, path in record["assets"].items()}
    return result


def _measured_findings(analysis: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": "Relative depth range", "value": f"{analysis['relative_depth_range']:.2f} relative units", "interpretation": "Variation across the reconstructed visible wound surface."},
        {"label": "Mean surface variation", "value": f"{analysis['mean_depth_variation']:.2f}", "interpretation": "Average magnitude of relative surface variation in the analyzed wound region."},
        {"label": "Depth variation", "value": f"{analysis['depth_variation_std']:.2f}", "interpretation": "Heterogeneity of the reconstructed relative surface geometry."},
        {"label": "Detected wound ROI", "value": f"{analysis['wound_roi_pixels']} pixels", "interpretation": "Image pixels classified as belonging to the analyzed wound region."},
    ]


def _data_quality(record: dict[str, Any]) -> list[str]:
    assets = record.get("assets", {})
    analysis = record.get("analysis")
    return [
        f"RGB: {'Available' if assets.get('rgb') else 'Unavailable'}",
        f"Thermal: {'Available' if assets.get('thermal') else 'Unavailable'}",
        f"Depth: {'Available' if assets.get('depth') else 'Unavailable'}",
        f"Wound localization: {'Available' if assets.get('rgb_roi') else 'Unavailable'}",
        f"3D reconstruction: {'Available' if assets.get('surface') else 'Unavailable'}",
        f"Structural metrics: {'Available' if analysis else 'Unavailable'}",
        "Relative depth values are not calibrated physical depth in millimetres.",
    ]


def _previous_visits(patient_id: str, current_visit_id: str) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for visit_record in store.visits_for_patient(patient_id):
        if visit_record["id"] == current_visit_id:
            continue
        item: dict[str, Any] = {"visit_date": visit_record["visit_date"]}
        if visit_record.get("analysis"):
            item["structural_analysis"] = visit_record["analysis"]
        if visit_record.get("clinical_notes"):
            item["clinician_notes"] = visit_record["clinical_notes"]
        if visit_record.get("ai_summary"):
            item["previous_ai_summary"] = visit_record["ai_summary"]["assessment_summary"]
        if visit_record.get("clinical_plan"):
            item["clinical_plan"] = visit_record["clinical_plan"]
        history.append(item)
    return history[:5]


def _ai_assessment_payload(record: dict[str, Any]) -> dict[str, Any]:
    analysis = record.get("analysis")
    if analysis is None:
        raise HTTPException(status_code=404, detail="Saved analysis was not found.")
    assets = record.get("assets", {})
    return {
        "patient": {"patient_code": record["patient_code"]},
        "visit": {"visit_id": record["id"], "visit_date": record["visit_date"]},
        "structural_analysis": {
            "wound_roi_pixels": analysis["wound_roi_pixels"],
            "relative_depth_range": analysis["relative_depth_range"],
            "mean_absolute_variation": analysis["mean_depth_variation"],
            "depth_variation_std": analysis["depth_variation_std"],
        },
        "thermal_analysis": {"available": bool(assets.get("thermal")), "relative_thermal_summary": analysis["thermal_summary"] if assets.get("thermal") else None},
        "analysis_quality": {
            "segmentation_status": "success" if assets.get("rgb_roi") else "unavailable",
            "depth_available": bool(assets.get("depth")),
            "thermal_available": bool(assets.get("thermal")),
            "rgb_available": bool(assets.get("rgb")),
            "surface_3d_available": bool(assets.get("surface")),
        },
        "clinician_notes": record["clinical_notes"] or None,
        "previous_visits": _previous_visits(record["patient_id"], record["id"]),
    }


@app.post("/patients")
def create_patient(patient: PatientCreate) -> dict[str, Any]:
    try:
        return store.create_patient(patient.patient_code, patient.display_name, patient.age)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/patients")
def patients() -> list[dict[str, Any]]:
    return store.patients()


@app.get("/patients/{patient_id}")
def patient(patient_id: str) -> dict[str, Any]:
    record = store.patient(patient_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Patient was not found.")
    return record


@app.post("/patients/{patient_id}/visits")
def create_patient_visit(patient_id: str, visit: VisitCreate) -> dict[str, Any]:
    try:
        return _visit_response(store.create_visit(patient_id, visit.clinical_notes, visit.visit_date))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/patients/{patient_id}/visits")
def patient_visits(patient_id: str) -> list[dict[str, Any]]:
    try:
        return [_visit_response(item) for item in store.visits_for_patient(patient_id)]
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/visits/{visit_id}")
def visit(visit_id: str) -> dict[str, Any]:
    record = store.visit(visit_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Visit was not found.")
    return _visit_response(record)


@app.get("/storage/patients/{patient_id}/visits/{visit_id}/{filename}")
def stored_asset(patient_id: str, visit_id: str, filename: str) -> FileResponse:
    if filename not in {"rgb.png", "thermal.png", "depth.png", "rgb_roi.png", "relative_depth.png", "surface.png", "structural_overview.png"}:
        raise HTTPException(status_code=404, detail="Unknown saved asset.")
    path = storage.root / "patients" / patient_id / "visits" / visit_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Saved asset was not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/cases", response_model=list[CaseSummary])
def cases() -> list[CaseSummary]:
    return repository.list_cases()


@app.get("/cases/{case_id}/visits", response_model=list[VisitSummary])
def visits(case_id: str) -> list[VisitSummary]:
    return repository.list_visits(case_id)


@app.get("/media/{case_id}/{day}/{scene}/{modality}")
def media(case_id: str, day: int, scene: str, modality: str) -> FileResponse:
    if modality not in MODALITY_FILE_NAMES:
        raise HTTPException(status_code=404, detail="Unknown modality.")
    return FileResponse(repository.read_asset(case_id, day, scene, modality))


@app.get("/analysis-assets/{session_id}/{asset_name}")
def analysis_asset(session_id: str, asset_name: str) -> FileResponse:
    if len(session_id) != 32 or any(character not in "0123456789abcdef" for character in session_id):
        raise HTTPException(status_code=404, detail="Analysis session was not found.")
    if asset_name not in SESSION_ASSET_NAMES:
        raise HTTPException(status_code=404, detail="Unknown analysis asset.")
    asset_path = SESSION_DIR / session_id / f"{asset_name}.png"
    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Analysis visualization is unavailable.")
    return FileResponse(asset_path, media_type="image/png")


@app.post("/analyze-followup", response_model=AnalyzeFollowupResponse)
def analyze_followup(request: FollowupRequest) -> AnalyzeFollowupResponse:
    if request.previous_case_id != request.current_case_id:
        raise HTTPException(status_code=422, detail="Baseline and current visits must belong to the same dataset case.")
    baseline = {modality: repository.read_asset(request.previous_case_id, request.previous_day, request.previous_scene, modality) for modality in ("rgb", "thermal", "depth")}
    current = {modality: repository.read_asset(request.current_case_id, request.current_day, request.current_scene, modality) for modality in ("rgb", "thermal", "depth")}
    return _analyze_pair(
        baseline,
        current,
        repository.registration_file(request.previous_case_id, request.previous_day, request.previous_scene),
        repository.registration_file(request.current_case_id, request.current_day, request.current_scene),
    )


@app.post("/analyze-upload", response_model=AnalyzeFollowupResponse)
def analyze_upload(
    baseline_case: str = Form(...),
    baseline_day: int = Form(...),
    baseline_scene: str = Form("scene_1"),
    rgb_file: UploadFile = File(...),
    thermal_file: UploadFile = File(...),
    depth_file: UploadFile = File(...),
) -> AnalyzeFollowupResponse:
    uploads = {"rgb": rgb_file, "thermal": thermal_file, "depth": depth_file}
    for modality, upload in uploads.items():
        if Path(upload.filename or "").suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=422, detail=f"{modality} must be a PNG or JPEG image.")
    baseline = {modality: repository.read_asset(baseline_case, baseline_day, baseline_scene, modality) for modality in uploads}
    return _analyze_pair(baseline, uploads, repository.registration_file(baseline_case, baseline_day, baseline_scene))


@app.post("/analyze-current", response_model=AnalyzeCurrentResponse)
def analyze_current(
    patient_id: str = Form(...),
    clinical_notes: str = Form(""),
    rgb_file: UploadFile = File(...),
    thermal_file: UploadFile = File(...),
    depth_file: UploadFile = File(...),
) -> AnalyzeCurrentResponse:
    uploads = {"rgb": rgb_file, "thermal": thermal_file, "depth": depth_file}
    for modality, upload in uploads.items():
        if Path(upload.filename or "").suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=422, detail=f"{modality} must be a PNG or JPEG image.")
    return _analyze_current_scan(uploads, patient_id, clinical_notes)


@app.post("/ai/explain-assessment/{visit_id}")
def explain_assessment(visit_id: str) -> dict[str, Any]:
    record = store.visit(visit_id)
    if record is None or not record.get("analysis"):
        raise HTTPException(status_code=404, detail="Saved analysis was not found.")
    payload = _ai_assessment_payload(record)
    try:
        summary = ai_service.explain_assessment(payload).model_dump()
    except AIUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    summary["measured_findings"] = _measured_findings(record["analysis"])
    summary["data_quality"] = _data_quality(record)
    summary["model_name"] = ai_service.model_name
    store.save_summary(visit_id, summary)
    return {**summary, "reviewed_by_clinician": False, "reviewed_at": None}


@app.post("/visits/{visit_id}/clinical-context")
def save_clinical_context(visit_id: str, context: ClinicalContextInput) -> dict[str, str]:
    if store.visit(visit_id) is None:
        raise HTTPException(status_code=404, detail="Visit was not found.")
    store.update_clinical_notes(visit_id, context.clinical_notes)
    return {"clinical_notes": context.clinical_notes}


@app.post("/visits/{visit_id}/ai-summary/review")
def mark_ai_summary_reviewed(visit_id: str) -> dict[str, Any]:
    record = store.mark_summary_reviewed(visit_id)
    if record is None or not record.get("ai_summary"):
        raise HTTPException(status_code=404, detail="AI summary was not found.")
    return record["ai_summary"]


@app.post("/ai/summarize-history/{patient_id}")
def summarize_history(patient_id: str) -> dict[str, Any]:
    if store.patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient was not found.")
    visits = _previous_visits(patient_id, "")
    if not visits:
        raise HTTPException(status_code=404, detail="No saved visits were found for this patient.")
    try:
        return ai_service.summarize_history({"patient_code": store.patient(patient_id)["patient_code"], "previous_visits": visits}).model_dump()
    except AIUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/visits/{visit_id}/clinical-plan")
def save_clinical_plan(visit_id: str, plan: ClinicalPlanInput) -> dict[str, Any]:
    if store.visit(visit_id) is None:
        raise HTTPException(status_code=404, detail="Visit was not found.")
    store.save_plan(visit_id, plan.model_dump())
    return plan.model_dump()


@app.get("/visits/{visit_id}/clinical-plan")
def clinical_plan(visit_id: str) -> dict[str, Any]:
    record = store.visit(visit_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Visit was not found.")
    return record.get("clinical_plan") or ClinicalPlanInput().model_dump()


@app.post("/reports/{visit_id}")
def generate_report(visit_id: str) -> dict[str, str]:
    record = store.visit(visit_id)
    if record is None or not record.get("analysis") or not record.get("assets"):
        raise HTTPException(status_code=404, detail="Saved visit analysis was not found.")
    destination = store.report_root / f"woundlens-report-{visit_id}.pdf"
    try:
        create_report(destination, record)
        report_id = store.save_report(visit_id, destination)
    except Exception as error:
        LOGGER.exception("Unable to generate report for visit %s", visit_id)
        raise HTTPException(status_code=500, detail="Report generation failed.") from error
    return {"report_id": report_id, "pdf_url": f"/reports/{report_id}"}


@app.get("/reports")
def reports() -> list[dict[str, Any]]:
    return [{**report, "pdf_url": f"/reports/{report['id']}"} for report in store.reports()]


@app.get("/reports/{report_id}")
def report_file(report_id: str) -> FileResponse:
    path = store.report_path(report_id)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Report was not found.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
