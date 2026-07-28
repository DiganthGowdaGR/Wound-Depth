import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, View } from 'react-native';
import { analyzeCurrent, createPatient, CurrentWoundAssessment, getPatientVisits, getPatients, getReports, Patient, SavedReport, SavedVisit, UploadedScanInput } from './src/services/woundlensApi';
import { BottomNav, Header } from './src/components/Chrome';
import { DashboardScreen } from './src/screens/DashboardScreen';
import { PatientListScreen } from './src/screens/PatientListScreen';
import { PatientDetailScreen } from './src/screens/PatientDetailScreen';
import { WoundHistoryScreen } from './src/screens/WoundHistoryScreen';
import { ScanScreen } from './src/screens/ScanScreen';
import { ResultScreen } from './src/screens/ResultScreen';
import { ReportsScreen } from './src/screens/ReportsScreen';
import { EmptyModuleScreen } from './src/screens/EmptyModuleScreen';
import { colors, typography } from './src/theme';

export type ScreenKey = 'dashboard' | 'patients' | 'detail' | 'history' | 'reports' | 'profile' | 'scan' | 'result';

export default function App() {
  const [screen, setScreen] = useState<ScreenKey>('patients'); const [patients, setPatients] = useState<Patient[]>([]); const [reports, setReports] = useState<SavedReport[]>([]); const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null); const [visits, setVisits] = useState<SavedVisit[]>([]); const [assessment, setAssessment] = useState<CurrentWoundAssessment | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const [savedPatients, savedReports] = await Promise.all([getPatients(), getReports()]);
        if (!mounted) return;
        setPatients(savedPatients);
        setReports(savedReports);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : 'Unable to connect to WoundLens backend.');
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);
  const selectPatient = async (patient: Patient) => { setSelectedPatient(patient); setLoading(true); try { setVisits(await getPatientVisits(patient.id)); setScreen('detail'); } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load patient visits.'); } finally { setLoading(false); } };
  const addPatient = async (input: { patientCode: string; displayName: string; age?: number }) => { const patient = await createPatient(input); setPatients((items) => [patient, ...items]); await selectPatient(patient); };
  const runAnalysis = async (uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>) => { if (!selectedPatient) throw new Error('Select a patient before analyzing a scan.'); const result = await analyzeCurrent(selectedPatient.id, uploads); setAssessment(result); setVisits(await getPatientVisits(selectedPatient.id)); setReports(await getReports()); setScreen('result'); };
  const openVisit = (visit: SavedVisit) => { if (!visit.analysis || !visit.assets) return; setAssessment({ analysisId: visit.analysis.id, patientId: visit.patientId, visitId: visit.id, assets: visit.assets, woundRoiPixels: visit.analysis.woundRoiPixels, relativeDepthRange: visit.analysis.relativeDepthRange, meanAbsoluteDepthVariation: visit.analysis.meanAbsoluteDepthVariation, depthVariationStd: visit.analysis.depthVariationStd, surfaceRegionLabel: '3D Wound Surface - Automatic ROI', roiMappingMethod: 'Automatic RGB/thermal wound mask in original image coordinates', segmentationStatus: 'success', segmentationScore: 0, thermalAssistanceUsed: true }); setScreen('result'); };
  const content = () => { if (loading && screen !== 'scan') return <View style={styles.state}><ActivityIndicator color={colors.primary} size="large" /><Text style={styles.stateText}>Loading saved WoundLens data</Text></View>; if (error && screen !== 'scan') return <View style={styles.state}><Text style={styles.error}>{error}</Text></View>; switch (screen) { case 'patients': return <PatientListScreen patients={patients} onCreate={addPatient} onOpen={(patient) => void selectPatient(patient)} />; case 'detail': return selectedPatient ? <PatientDetailScreen patient={selectedPatient} onOpenHistory={() => setScreen('history')} onStartScan={() => setScreen('scan')} /> : <PatientListScreen patients={patients} onCreate={addPatient} onOpen={(patient) => void selectPatient(patient)} />; case 'history': return <WoundHistoryScreen visits={visits} onOpenVisit={openVisit} />; case 'reports': return <ReportsScreen reports={reports} />; case 'scan': return <ScanScreen patient={selectedPatient ?? undefined} onCurrentAnalyze={runAnalysis} />; case 'result': return <ResultScreen currentAssessment={assessment ?? undefined} onOpenHistory={() => setScreen('scan')} />; case 'profile': return <EmptyModuleScreen title="Profile" message="Profile information is not configured." icon="person-outline" />; default: return <DashboardScreen onStartScan={() => setScreen('scan')} />; } };
  const isBackScreen = ['detail', 'history', 'reports', 'profile', 'scan', 'result'].includes(screen);
  return <SafeAreaView style={styles.safeArea}><StatusBar style="dark" /><Header showBack={isBackScreen} onBack={() => setScreen(screen === 'detail' ? 'patients' : selectedPatient ? 'detail' : 'patients')} /><View style={styles.body}>{content()}</View><BottomNav active={screen} onNavigate={setScreen} /></SafeAreaView>;
}
const styles = StyleSheet.create({ safeArea: { flex: 1, backgroundColor: colors.appBackground }, body: { flex: 1 }, state: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24 }, stateText: { ...typography.body, color: colors.textMuted }, error: { ...typography.body, color: colors.danger, textAlign: 'center' } });
