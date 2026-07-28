import { MaterialCommunityIcons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Patient, UploadedScanInput } from '../services/woundlensApi';
import { Card, Pill, PrimaryButton } from '../components/Primitives';
import { colors, layout, typography } from '../theme';

type UploadModality = 'rgb' | 'thermal' | 'depth';
type Uploads = Partial<Record<UploadModality, UploadedScanInput>>;

export function ScanScreen({ patient, onCurrentAnalyze }: { patient?: Patient; onCurrentAnalyze: (uploads: Record<UploadModality, UploadedScanInput>) => Promise<void> }) {
  const compact = useWindowDimensions().width < 620;
  const [uploads, setUploads] = useState<Uploads>({});
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const complete = Boolean(uploads.rgb && uploads.thermal && uploads.depth);

  const pick = async (modality: UploadModality, camera = false) => {
    setError(null);
    if (camera) {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) { setError('Camera permission is required to capture an RGB image.'); return; }
    }
    const result = camera
      ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 1 })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1 });
    if (result.canceled) return;
    const asset = result.assets[0];
    setUploads((previous) => ({ ...previous, [modality]: { uri: asset.uri, fileName: asset.fileName ?? `${modality}.jpg`, mimeType: asset.mimeType ?? 'image/jpeg' } }));
  };

  const analyze = async () => {
    setError(null);
    if (!patient) { setError('Select or create a patient before analyzing a scan.'); return; }
    if (!complete) { setError('RGB, thermal, and depth images are required.'); return; }
    setAnalyzing(true);
    try { await onCurrentAnalyze(uploads as Record<UploadModality, UploadedScanInput>); }
    catch (analysisError) { setError(analysisError instanceof Error ? analysisError.message : 'Analysis failed. Check the backend and retry.'); }
    finally { setAnalyzing(false); }
  };

  return <ScrollView contentContainerStyle={styles.page}><View style={styles.content}>
    <View><Text style={typography.title}>Scan Wound</Text><Text style={styles.subcopy}>{patient ? `Patient: ${patient.displayName} (${patient.patientCode})` : 'Select a patient from Patients before uploading scans.'}</Text><Text style={styles.subcopy}>Upload RGB, thermal, and depth scans. WoundLens automatically selects the visible wound region for relative surface analysis.</Text></View>
    <View style={[styles.captureGrid, compact && styles.captureStack]}>
      <CaptureCard modality="rgb" icon="camera-iris" title="RGB Image" subtitle="Camera or photo upload" upload={uploads.rgb} onPick={pick} onRemove={() => setUploads((items) => ({ ...items, rgb: undefined }))} />
      <CaptureCard modality="thermal" icon="thermometer" title="Thermal Image" subtitle="Upload thermal scan" upload={uploads.thermal} onPick={pick} onRemove={() => setUploads((items) => ({ ...items, thermal: undefined }))} />
      <CaptureCard modality="depth" icon="layers-triple-outline" title="Depth Image" subtitle="Upload depth scan" upload={uploads.depth} onPick={pick} onRemove={() => setUploads((items) => ({ ...items, depth: undefined }))} />
    </View>
    {error ? <View style={styles.errorBox}><Text style={styles.errorText}>{error}</Text></View> : null}
    <PrimaryButton icon="bar-chart-outline" onPress={() => void analyze()} disabled={analyzing || !complete || !patient}>{analyzing ? 'Analyzing...' : 'Analyze Current Wound'}</PrimaryButton>
    <View style={styles.statusRow}><Pill tone="primary">{Object.keys(uploads).length}/3 modalities ready</Pill>{complete ? <Pill tone="success">AUTOMATIC DETECTION READY</Pill> : null}</View>
  </View></ScrollView>;
}

function CaptureCard({ modality, icon, title, subtitle, upload, onPick, onRemove }: { modality: UploadModality; icon: string; title: string; subtitle: string; upload?: UploadedScanInput; onPick: (modality: UploadModality, camera?: boolean) => Promise<void>; onRemove: () => void }) {
  return <Card style={styles.captureCard}>{upload ? <><Image source={{ uri: upload.uri }} style={styles.preview} resizeMode="cover" /><Text numberOfLines={1} style={styles.fileName}>{upload.fileName}</Text><Pill tone="success">READY</Pill><View style={styles.captureActions}><Pressable onPress={() => void onPick(modality)}><Text style={styles.actionLink}>Replace</Text></Pressable><Pressable onPress={onRemove}><Text style={styles.removeLink}>Remove</Text></Pressable></View></> : <><View style={[styles.captureIcon, modality === 'rgb' ? styles.primaryIcon : styles.successIcon]}><MaterialCommunityIcons name={icon as keyof typeof MaterialCommunityIcons.glyphMap} size={29} color={modality === 'rgb' ? colors.primary : colors.success} /></View><Text style={styles.captureTitle}>{title}</Text><Text style={styles.captureSubtitle}>{subtitle}</Text><View style={styles.captureActions}>{modality === 'rgb' ? <Pressable onPress={() => void onPick(modality, true)}><Text style={styles.actionLink}>Camera</Text></Pressable> : null}<Pressable onPress={() => void onPick(modality)}><Text style={styles.actionLink}>Upload</Text></Pressable></View></>}</Card>;
}

const styles = StyleSheet.create({ page: { padding: layout.pagePadding, alignItems: 'center' }, content: { width: '100%', maxWidth: 760, gap: 16 }, subcopy: { ...typography.body, color: colors.textMuted }, captureGrid: { flexDirection: 'row', gap: 12 }, captureStack: { flexDirection: 'column' }, captureCard: { flex: 1, minHeight: 190, alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: colors.surfaceMuted }, captureIcon: { width: 54, height: 54, borderRadius: 27, alignItems: 'center', justifyContent: 'center' }, primaryIcon: { backgroundColor: colors.primarySoft }, successIcon: { backgroundColor: '#d2efea' }, captureTitle: { ...typography.subtitle }, captureSubtitle: { ...typography.caption, textAlign: 'center' }, captureActions: { flexDirection: 'row', gap: 14, marginTop: 4 }, actionLink: { ...typography.caption, color: colors.primary, fontWeight: '800' }, removeLink: { ...typography.caption, color: colors.danger, fontWeight: '800' }, preview: { width: '100%', height: 88, borderRadius: 6 }, fileName: { ...typography.caption, maxWidth: '100%', paddingHorizontal: 4 }, errorBox: { borderWidth: 1, borderColor: '#ffc8c8', borderRadius: 8, backgroundColor: colors.dangerSoft, padding: 12 }, errorText: { ...typography.body, color: colors.danger }, statusRow: { flexDirection: 'row', justifyContent: 'center', gap: 10, flexWrap: 'wrap' } });
