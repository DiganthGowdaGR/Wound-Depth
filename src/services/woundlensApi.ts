import { Platform } from 'react-native';

export type Modality = 'rgb' | 'rgb_roi' | 'thermal' | 'depth' | 'relative_depth' | 'surface' | 'structural_overview';

export interface UploadedScanInput { uri: string; fileName: string; mimeType: string; }
export interface Patient { id: string; patientCode: string; displayName: string; age?: number | null; createdAt: string; visitCount: number; }
export interface SavedVisit {
  id: string; patientId: string; patientCode: string; displayName: string; age?: number | null; visitDate: string; clinicalNotes: string; createdAt: string;
  assets?: Partial<Record<Modality, string>>;
  analysis?: { id: string; woundRoiPixels: number; relativeDepthRange: number; meanAbsoluteDepthVariation: number; depthVariationStd: number; thermalSummary: string; createdAt: string; };
  aiSummary?: AiAssessmentSummary;
  clinicalPlan?: ClinicalPlan;
}
export interface CurrentWoundAssessment {
  analysisId: string; patientId: string; visitId: string; assets: Partial<Record<Modality, string>>;
  woundRoiPixels: number; relativeDepthRange: number; meanAbsoluteDepthVariation: number; depthVariationStd: number;
  surfaceRegionLabel: string; roiMappingMethod: string; segmentationStatus: 'success' | 'review_required'; segmentationScore: number; thermalAssistanceUsed: boolean;
}
export interface AiMeasuredFinding { label: string; value: string; interpretation: string; }
export interface AiAssessmentSummary { headline: string; assessmentSummary: string; measuredFindings: AiMeasuredFinding[]; structuralFindings: string[]; thermalFindings: string[]; attentionPoints: string[]; dataQuality: string[]; clinicianSummary: string; patientFriendlySummary: string; modelName?: string; reviewedByClinician: boolean; reviewedAt?: string | null; }
export interface ClinicalPlan { clinicalAssessment: string; medicationPrescriptionEnteredByClinician: string; dressingWoundCarePlan: string; followUpInterval: string; additionalTestsRequested: string; escalationRequired: boolean; }
export interface SavedReport { id: string; visitId: string; patientCode: string; displayName: string; visitDate: string; createdAt: string; pdfUrl: string; }
// Retained only for the optional historical comparison view.
export interface WoundVisit { id: string; caseId: string; day: number; scene: string; visitDate: string; assets: Partial<Record<Modality, string>>; }
export interface PatientWoundHistory { caseId: string; visits: WoundVisit[]; previousVisit: WoundVisit; currentVisit: WoundVisit; analysis?: WoundAnalysisResult; }
export interface WoundAnalysisResult { multimodalChange: string; modelChangeScore: number; rgbChangeIndex: number; thermalChangeIndex: number; depthChangeIndex: number; clinicalReviewRequired: boolean; explanatoryNote: string; assets: Record<string, string | undefined>; surfaceRegionLabel?: string; assessments: Partial<Record<'baseline' | 'current', StructuralAssessment>>; technicalPipeline?: { baselineFeatures: Record<string, number>; currentFeatures: Record<string, number>; changeFeatures: Record<string, number>; rawModelScore: number; lowThreshold: number; highThreshold: number; }; }
export interface StructuralAssessment { depthStatistics: { relativeDepthRange: number; meanAbsoluteVariation: number; depthVariationStd: number; woundRoiPixelCount: number; regionLabel: string; }; roiAvailable: boolean; }

const apiBaseUrl = process.env.EXPO_PUBLIC_WOUNDLENS_API_URL || 'http://127.0.0.1:8011';

export async function getPatients(): Promise<Patient[]> {
  const response = await fetch(`${apiBaseUrl}/patients`); await assertOk(response);
  return (await response.json() as ApiPatient[]).map(mapPatient);
}

export async function createPatient(input: { patientCode: string; displayName: string; age?: number }): Promise<Patient> {
  const response = await fetch(`${apiBaseUrl}/patients`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ patient_code: input.patientCode, display_name: input.displayName, age: input.age }) });
  await assertOk(response); return mapPatient(await response.json() as ApiPatient);
}

export async function getPatient(patientId: string): Promise<Patient> {
  const response = await fetch(`${apiBaseUrl}/patients/${encodeURIComponent(patientId)}`); await assertOk(response); return mapPatient(await response.json() as ApiPatient);
}

export async function getPatientVisits(patientId: string): Promise<SavedVisit[]> {
  const response = await fetch(`${apiBaseUrl}/patients/${encodeURIComponent(patientId)}/visits`); await assertOk(response);
  return (await response.json() as ApiVisit[]).map(mapVisit);
}

export async function getVisit(visitId: string): Promise<SavedVisit> {
  const response = await fetch(`${apiBaseUrl}/visits/${encodeURIComponent(visitId)}`); await assertOk(response); return mapVisit(await response.json() as ApiVisit);
}

export async function analyzeCurrent(patientId: string, uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>, clinicalNotes = ''): Promise<CurrentWoundAssessment> {
  const body = await uploadFormData(uploads); body.append('patient_id', patientId); body.append('clinical_notes', clinicalNotes);
  const response = await fetch(`${apiBaseUrl}/analyze-current`, { method: 'POST', body }); await assertOk(response);
  const result = await response.json() as ApiCurrentAssessment;
  return {
    analysisId: result.analysis_id, patientId: result.patient_id, visitId: result.visit_id, assets: mapAssets(result.assets),
    woundRoiPixels: result.structural_measurements.wound_roi_pixels, relativeDepthRange: result.structural_measurements.relative_depth_range,
    meanAbsoluteDepthVariation: result.structural_measurements.mean_absolute_depth_variation, depthVariationStd: result.structural_measurements.depth_variation_std,
    surfaceRegionLabel: result.surface_region_label, roiMappingMethod: result.roi_mapping_method, segmentationStatus: result.segmentation_status,
    segmentationScore: result.segmentation_score, thermalAssistanceUsed: result.thermal_assistance_used,
  };
}

export async function explainAssessment(visitId: string): Promise<AiAssessmentSummary> {
  const response = await fetch(`${apiBaseUrl}/ai/explain-assessment/${encodeURIComponent(visitId)}`, { method: 'POST' }); await assertOk(response);
  return mapAiSummary(await response.json() as ApiAiSummary);
}

export async function saveClinicalContext(visitId: string, clinicalNotes: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/visits/${encodeURIComponent(visitId)}/clinical-context`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clinical_notes: clinicalNotes }) });
  await assertOk(response);
}

export async function markAiSummaryReviewed(visitId: string): Promise<AiAssessmentSummary> {
  const response = await fetch(`${apiBaseUrl}/visits/${encodeURIComponent(visitId)}/ai-summary/review`, { method: 'POST' });
  await assertOk(response); return mapAiSummary(await response.json() as ApiAiSummary);
}

export async function saveClinicalPlan(visitId: string, plan: ClinicalPlan): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/visits/${encodeURIComponent(visitId)}/clinical-plan`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clinician_assessment: plan.clinicalAssessment, medication: plan.medicationPrescriptionEnteredByClinician, wound_care_plan: plan.dressingWoundCarePlan, follow_up_interval: plan.followUpInterval, additional_tests: plan.additionalTestsRequested, escalation_required: plan.escalationRequired }) });
  await assertOk(response);
}

export async function generateReport(visitId: string): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/reports/${encodeURIComponent(visitId)}`, { method: 'POST' }); await assertOk(response);
  const result = await response.json() as { pdf_url: string }; return absoluteUrl(result.pdf_url);
}

export async function getReports(): Promise<SavedReport[]> {
  const response = await fetch(`${apiBaseUrl}/reports`); await assertOk(response);
  return (await response.json() as ApiReport[]).map((report) => ({ id: report.id, visitId: report.visit_id, patientCode: report.patient_code, displayName: report.display_name, visitDate: report.visit_date, createdAt: report.created_at, pdfUrl: absoluteUrl(report.pdf_url) }));
}

export function mediaUrl(visit: WoundVisit, modality: Modality): string | undefined { return visit.assets[modality]; }

interface ApiPatient { id: string; patient_code: string; display_name: string; age?: number | null; created_at: string; visit_count: number; }
interface ApiAssets { [key: string]: string; }
interface ApiAnalysis { id: string; wound_roi_pixels: number; relative_depth_range: number; mean_depth_variation: number; depth_variation_std: number; thermal_summary: string; created_at: string; }
interface ApiPlan { clinician_assessment: string; medication: string; wound_care_plan: string; follow_up_interval: string; additional_tests: string; escalation_required: boolean; }
interface ApiAiSummary { headline?: string; assessment_summary: string; measured_findings?: { label: string; value: string; interpretation: string }[]; structural_findings: string[]; thermal_findings: string[]; attention_points: string[]; data_quality?: string[]; clinician_summary: string; patient_friendly_summary: string; model_name?: string; reviewed_by_clinician?: boolean; reviewed_at?: string | null; }
interface ApiVisit { id: string; patient_id: string; patient_code: string; display_name: string; age?: number | null; visit_date: string; clinical_notes: string; created_at: string; assets?: ApiAssets; analysis?: ApiAnalysis; ai_summary?: ApiAiSummary; clinical_plan?: ApiPlan; }
interface ApiCurrentAssessment { analysis_id: string; patient_id: string; visit_id: string; assets: ApiAssets; structural_measurements: { wound_roi_pixels: number; relative_depth_range: number; mean_absolute_depth_variation: number; depth_variation_std: number; }; surface_region_label: string; roi_mapping_method: string; segmentation_status: 'success' | 'review_required'; segmentation_score: number; thermal_assistance_used: boolean; }
interface ApiReport { id: string; visit_id: string; patient_code: string; display_name: string; visit_date: string; created_at: string; pdf_url: string; }

function mapPatient(item: ApiPatient): Patient { return { id: item.id, patientCode: item.patient_code, displayName: item.display_name, age: item.age, createdAt: item.created_at, visitCount: item.visit_count }; }
function mapAssets(assets: ApiAssets): Partial<Record<Modality, string>> { return Object.entries(assets).reduce<Partial<Record<Modality, string>>>((result, [key, value]) => { result[key as Modality] = absoluteUrl(value); return result; }, {}); }
function mapAiSummary(item: ApiAiSummary): AiAssessmentSummary { return { headline: item.headline ?? 'Assessment overview', assessmentSummary: item.assessment_summary, measuredFindings: item.measured_findings ?? [], structuralFindings: item.structural_findings, thermalFindings: item.thermal_findings, attentionPoints: item.attention_points, dataQuality: item.data_quality ?? [], clinicianSummary: item.clinician_summary, patientFriendlySummary: item.patient_friendly_summary, modelName: item.model_name, reviewedByClinician: item.reviewed_by_clinician ?? false, reviewedAt: item.reviewed_at }; }
function mapPlan(item: ApiPlan): ClinicalPlan { return { clinicalAssessment: item.clinician_assessment, medicationPrescriptionEnteredByClinician: item.medication, dressingWoundCarePlan: item.wound_care_plan, followUpInterval: item.follow_up_interval, additionalTestsRequested: item.additional_tests, escalationRequired: item.escalation_required }; }
function mapVisit(item: ApiVisit): SavedVisit { return { id: item.id, patientId: item.patient_id, patientCode: item.patient_code, displayName: item.display_name, age: item.age, visitDate: item.visit_date, clinicalNotes: item.clinical_notes, createdAt: item.created_at, assets: item.assets ? mapAssets(item.assets) : undefined, analysis: item.analysis ? { id: item.analysis.id, woundRoiPixels: item.analysis.wound_roi_pixels, relativeDepthRange: item.analysis.relative_depth_range, meanAbsoluteDepthVariation: item.analysis.mean_depth_variation, depthVariationStd: item.analysis.depth_variation_std, thermalSummary: item.analysis.thermal_summary, createdAt: item.analysis.created_at } : undefined, aiSummary: item.ai_summary ? mapAiSummary(item.ai_summary) : undefined, clinicalPlan: item.clinical_plan ? mapPlan(item.clinical_plan) : undefined }; }
function absoluteUrl(value: string): string { return value.startsWith('/') ? `${apiBaseUrl}${value}` : value; }
async function assertOk(response: Response): Promise<void> { if (response.ok) return; let message = `WoundLens API returned ${response.status}.`; try { const data = await response.json() as { detail?: string }; message = data.detail ?? message; } catch {} throw new Error(message); }
async function uploadFormData(uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>): Promise<FormData> { const body = new FormData(); await Promise.all((Object.entries(uploads) as [keyof typeof uploads, UploadedScanInput][]).map(async ([key, upload]) => { const value = Platform.OS === 'web' ? await (await fetch(upload.uri)).blob() : ({ uri: upload.uri, name: upload.fileName, type: upload.mimeType } as unknown as Blob); body.append(`${key}_file`, value, upload.fileName); })); return body; }
