import { Platform } from 'react-native';

export type ChangeLevel = 'LOW CHANGE' | 'MODERATE CHANGE' | 'HIGH CHANGE';
export type Modality = 'rgb' | 'rgb_roi' | 'thermal' | 'depth' | 'relative_depth' | 'surface' | 'structural_overview' | 'detection_debug';

export interface DepthStatistics {
  relativeDepthRange: number;
  meanAbsoluteVariation: number;
  depthVariationStd: number;
  woundRoiPixelCount: number;
  regionLabel: string;
}

export interface StructuralAssessment {
  depthStatistics: DepthStatistics;
  roiAvailable: boolean;
}

export interface TechnicalPipeline {
  baselineFeatures: Record<string, number>;
  currentFeatures: Record<string, number>;
  changeFeatures: Record<string, number>;
  rawModelScore: number;
  lowThreshold: number;
  highThreshold: number;
}

export interface WoundAnalysisResult {
  multimodalChange: ChangeLevel;
  modelChangeScore: number;
  rgbChangeIndex: number;
  thermalChangeIndex: number;
  depthChangeIndex: number;
  clinicalReviewRequired: boolean;
  explanatoryNote: string;
  assets: Partial<Record<
    'baseline_rgb' | 'baseline_rgb_roi' | 'baseline_thermal' | 'baseline_depth' | 'baseline_relative_depth' | 'baseline_3d' |
    'current_rgb' | 'current_rgb_roi' | 'current_thermal' | 'current_depth' | 'current_relative_depth' | 'current_3d',
    string
  >>;
  surfaceRegionLabel?: string;
  assessments: Partial<Record<'baseline' | 'current', StructuralAssessment>>;
  technicalPipeline?: TechnicalPipeline;
}

export interface WoundVisit {
  id: string;
  caseId: string;
  day: number;
  scene: string;
  visitDate: string;
  assets: Partial<Record<Modality, string>>;
}

export interface PatientWoundHistory {
  caseId: string;
  visits: WoundVisit[];
  previousVisit: WoundVisit;
  currentVisit: WoundVisit;
  analysis?: WoundAnalysisResult;
}

export interface CaseSummary {
  caseId: string;
  visitCount: number;
  multimodalVisitCount: number;
}

export interface UploadedScanInput {
  uri: string;
  fileName: string;
  mimeType: string;
}

export interface CurrentWoundAssessment {
  analysisId: string;
  patientId: string;
  visitId: string;
  assets: Partial<Record<Modality, string>>;
  woundRoiPixels: number;
  relativeDepthRange: number;
  meanAbsoluteDepthVariation: number;
  depthVariationStd: number;
  surfaceRegionLabel: string;
  roiMappingMethod: string;
  segmentationStatus: 'success';
  segmentationScore: number;
  thermalAssistanceUsed: boolean;
}

export interface AiAssessmentSummary {
  assessmentSummary: string;
  structuralFindings: string[];
  thermalFindings: string[];
  attentionPoints: string[];
  clinicianSummary: string;
  patientFriendlySummary: string;
}

export interface ClinicalPlan {
  clinicalAssessment: string;
  medicationPrescriptionEnteredByClinician: string;
  dressingWoundCarePlan: string;
  followUpInterval: string;
  additionalTestsRequested: string;
  escalationRequired: boolean;
}

interface ApiVisit {
  day: number;
  scene: string;
  assets: Partial<Record<Modality, string>>;
}

interface ApiCaseSummary {
  case_id: string;
  visit_count: number;
  multimodal_visit_count: number;
}

interface AnalyzeResponse {
  change_level: ChangeLevel;
  change_score: number;
  rgb_change_index: number;
  thermal_change_index: number;
  depth_change_index: number;
  review_required: boolean;
  assets?: WoundAnalysisResult['assets'];
  surface_region_label?: string;
  assessments?: Record<string, { depth_statistics: { relative_depth_range: number; mean_absolute_variation: number; depth_variation_std: number; wound_roi_pixel_count: number; region_label: string }; roi_available: boolean }>;
  technical_pipeline?: { baseline_features: Record<string, number>; current_features: Record<string, number>; change_features: Record<string, number>; raw_model_score: number; low_threshold: number; high_threshold: number };
}

interface AnalyzeCurrentResponse {
  analysis_id: string;
  patient_id: string;
  visit_id: string;
  assets: Partial<Record<Modality, string>>;
  structural_measurements: {
    wound_roi_pixels: number;
    relative_depth_range: number;
    mean_absolute_depth_variation: number;
    depth_variation_std: number;
  };
  surface_region_label: string;
  roi_mapping_method: string;
  segmentation_status: 'success';
  segmentation_score: number;
  thermal_assistance_used: boolean;
}

const apiBaseUrl = 'http://127.0.0.1:8011';
const note = 'High change indicates an unusual multimodal change compared with learned longitudinal wound patterns. It is not a diagnosis or a probability of deterioration.';

export async function getCases(): Promise<CaseSummary[]> {
  const response = await fetch(`${apiBaseUrl}/cases`);
  await assertOk(response);
  return (await response.json() as ApiCaseSummary[]).map((item) => ({
    caseId: item.case_id,
    visitCount: item.visit_count,
    multimodalVisitCount: item.multimodal_visit_count,
  }));
}

export async function getCaseHistory(caseId = 'case_12'): Promise<PatientWoundHistory> {
  const response = await fetch(`${apiBaseUrl}/cases/${encodeURIComponent(caseId)}/visits`);
  await assertOk(response);
  const visits = (await response.json() as ApiVisit[]).map((visit) => toVisit(caseId, visit));
  if (visits.length < 2) {
    throw new Error('This dataset case needs at least two visits for longitudinal comparison.');
  }
  const previousVisit = visits.find((visit) => visit.day === 124) ?? visits[0];
  const currentVisit = visits.find((visit) => visit.day === 313) ?? visits[visits.length - 1];
  return { caseId, visits, previousVisit, currentVisit };
}

export async function analyzeFollowup(previousVisit: WoundVisit, currentVisit: WoundVisit): Promise<WoundAnalysisResult> {
  const response = await fetch(`${apiBaseUrl}/analyze-followup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      previous_case_id: previousVisit.caseId,
      previous_day: previousVisit.day,
      previous_scene: previousVisit.scene,
      current_case_id: currentVisit.caseId,
      current_day: currentVisit.day,
      current_scene: currentVisit.scene,
    }),
  });
  await assertOk(response);
  return mapAnalysisResponse(await response.json() as AnalyzeResponse);
}

export async function analyzeUpload(baseline: WoundVisit, uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>): Promise<WoundAnalysisResult> {
  const body = new FormData();
  body.append('baseline_case', baseline.caseId);
  body.append('baseline_day', String(baseline.day));
  body.append('baseline_scene', baseline.scene);
  await Promise.all((Object.entries(uploads) as [keyof typeof uploads, UploadedScanInput][]).map(async ([key, upload]) => {
    const value = Platform.OS === 'web'
      ? await (await fetch(upload.uri)).blob()
      : ({ uri: upload.uri, name: upload.fileName, type: upload.mimeType } as unknown as Blob);
    body.append(`${key}_file`, value, upload.fileName);
  }));
  const response = await fetch(`${apiBaseUrl}/analyze-upload`, { method: 'POST', body });
  await assertOk(response);
  return mapAnalysisResponse(await response.json() as AnalyzeResponse);
}

export async function analyzeCurrent(uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>): Promise<CurrentWoundAssessment> {
  const body = await uploadFormData(uploads);
  const response = await fetch(`${apiBaseUrl}/analyze-current`, { method: 'POST', body });
  await assertOk(response);
  const result = await response.json() as AnalyzeCurrentResponse;
  return {
    analysisId: result.analysis_id,
    patientId: result.patient_id,
    visitId: result.visit_id,
    assets: Object.entries(result.assets).reduce<Partial<Record<Modality, string>>>((assets, [key, value]) => {
      assets[key as Modality] = value.startsWith('/') ? `${apiBaseUrl}${value}` : value;
      return assets;
    }, {}),
    woundRoiPixels: result.structural_measurements.wound_roi_pixels,
    relativeDepthRange: result.structural_measurements.relative_depth_range,
    meanAbsoluteDepthVariation: result.structural_measurements.mean_absolute_depth_variation,
    depthVariationStd: result.structural_measurements.depth_variation_std,
    surfaceRegionLabel: result.surface_region_label,
    roiMappingMethod: result.roi_mapping_method,
    segmentationStatus: result.segmentation_status,
    segmentationScore: result.segmentation_score,
    thermalAssistanceUsed: result.thermal_assistance_used,
  };
}

export async function explainAssessment(assessment: CurrentWoundAssessment, clinicalNotes: string): Promise<AiAssessmentSummary> {
  const response = await fetch(`${apiBaseUrl}/ai/explain-assessment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysis_id: assessment.analysisId,
      patient_id: assessment.patientId,
      visit_id: assessment.visitId,
      wound_roi_pixels: assessment.woundRoiPixels,
      relative_depth_range: assessment.relativeDepthRange,
      mean_depth_variation: assessment.meanAbsoluteDepthVariation,
      depth_variation_std: assessment.depthVariationStd,
      thermal_summary: assessment.thermalAssistanceUsed ? 'Relative thermal contrast was included in automatic localization.' : 'Thermal image was preserved without registered contrast assistance.',
      clinical_notes: clinicalNotes,
    }),
  });
  await assertOk(response);
  const result = await response.json() as { assessment_summary: string; structural_findings: string[]; thermal_findings: string[]; attention_points: string[]; clinician_summary: string; patient_friendly_summary: string };
  return { assessmentSummary: result.assessment_summary, structuralFindings: result.structural_findings, thermalFindings: result.thermal_findings, attentionPoints: result.attention_points, clinicianSummary: result.clinician_summary, patientFriendlySummary: result.patient_friendly_summary };
}

export async function saveClinicalPlan(analysisId: string, plan: ClinicalPlan): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/analyses/${encodeURIComponent(analysisId)}/clinical-plan`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      clinical_assessment: plan.clinicalAssessment,
      medication_prescription_entered_by_clinician: plan.medicationPrescriptionEnteredByClinician,
      dressing_wound_care_plan: plan.dressingWoundCarePlan,
      follow_up_interval: plan.followUpInterval,
      additional_tests_requested: plan.additionalTestsRequested,
      escalation_required: plan.escalationRequired,
    }),
  });
  await assertOk(response);
}

export async function generateReport(analysisId: string): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/reports/${encodeURIComponent(analysisId)}`, { method: 'POST' });
  await assertOk(response);
  const result = await response.json() as { report_url: string };
  return result.report_url.startsWith('/') ? `${apiBaseUrl}${result.report_url}` : result.report_url;
}

export function mediaUrl(visit: WoundVisit, modality: Modality): string | undefined {
  return visit.assets[modality];
}

export function analysisVisitAssets(analysis: WoundAnalysisResult, prefix: 'baseline' | 'current'): Partial<Record<Modality, string>> {
  return {
    rgb: analysis.assets[`${prefix}_rgb`],
    rgb_roi: analysis.assets[`${prefix}_rgb_roi`],
    thermal: analysis.assets[`${prefix}_thermal`],
    depth: analysis.assets[`${prefix}_depth`],
    relative_depth: analysis.assets[`${prefix}_relative_depth`],
    surface: analysis.assets[`${prefix}_3d`],
  };
}

function toVisit(caseId: string, visit: ApiVisit): WoundVisit {
  const assets = Object.keys(visit.assets).reduce<Partial<Record<Modality, string>>>((result, modality) => {
    const key = modality as Modality;
    result[key] = `${apiBaseUrl}/media/${encodeURIComponent(caseId)}/${visit.day}/${encodeURIComponent(visit.scene)}/${key}`;
    return result;
  }, {});
  return { id: `${caseId}_day_${visit.day}_${visit.scene}`, caseId, day: visit.day, scene: visit.scene, visitDate: `Day ${visit.day}`, assets };
}

function mapAnalysisResponse(response: AnalyzeResponse): WoundAnalysisResult {
  return {
    multimodalChange: response.change_level,
    modelChangeScore: response.change_score,
    rgbChangeIndex: response.rgb_change_index,
    thermalChangeIndex: response.thermal_change_index,
    depthChangeIndex: response.depth_change_index,
    clinicalReviewRequired: response.review_required,
    explanatoryNote: note,
    assets: Object.entries(response.assets ?? {}).reduce<WoundAnalysisResult['assets']>((result, [key, value]) => {
      result[key as keyof WoundAnalysisResult['assets']] = value.startsWith('/') ? `${apiBaseUrl}${value}` : value;
      return result;
    }, {}),
    surfaceRegionLabel: response.surface_region_label,
    assessments: Object.entries(response.assessments ?? {}).reduce<WoundAnalysisResult['assessments']>((result, [key, value]) => {
      if (key === 'baseline' || key === 'current') {
        result[key] = {
          roiAvailable: value.roi_available,
          depthStatistics: {
            relativeDepthRange: value.depth_statistics.relative_depth_range,
            meanAbsoluteVariation: value.depth_statistics.mean_absolute_variation,
            depthVariationStd: value.depth_statistics.depth_variation_std,
            woundRoiPixelCount: value.depth_statistics.wound_roi_pixel_count,
            regionLabel: value.depth_statistics.region_label,
          },
        };
      }
      return result;
    }, {}),
    technicalPipeline: response.technical_pipeline ? {
      baselineFeatures: response.technical_pipeline.baseline_features,
      currentFeatures: response.technical_pipeline.current_features,
      changeFeatures: response.technical_pipeline.change_features,
      rawModelScore: response.technical_pipeline.raw_model_score,
      lowThreshold: response.technical_pipeline.low_threshold,
      highThreshold: response.technical_pipeline.high_threshold,
    } : undefined,
  };
}

async function assertOk(response: Response): Promise<void> {
  if (response.ok) return;
  let message = `WoundLens API returned ${response.status}.`;
  try {
    const data = await response.json() as { detail?: string };
    message = data.detail ?? message;
  } catch {
    // Keep the meaningful status message when the server returned no JSON body.
  }
  throw new Error(message);
}

async function uploadFormData(uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>): Promise<FormData> {
  const body = new FormData();
  await Promise.all((Object.entries(uploads) as [keyof typeof uploads, UploadedScanInput][]).map(async ([key, upload]) => {
    const value = Platform.OS === 'web'
      ? await (await fetch(upload.uri)).blob()
      : ({ uri: upload.uri, name: upload.fileName, type: upload.mimeType } as unknown as Blob);
    body.append(`${key}_file`, value, upload.fileName);
  }));
  return body;
}
