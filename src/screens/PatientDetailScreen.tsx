import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Patient } from '../services/woundlensApi';
import { Card, PrimaryButton } from '../components/Primitives';
import { colors, layout, typography } from '../theme';

export function PatientDetailScreen({ patient, onOpenHistory, onStartScan }: { patient: Patient; onOpenHistory: () => void; onStartScan: () => void }) { return <ScrollView contentContainerStyle={styles.page}><View style={styles.content}><Card style={styles.card}><Text style={typography.title}>{patient.displayName}</Text><Text style={styles.meta}>Patient ID: {patient.patientCode}</Text>{patient.age !== null && patient.age !== undefined ? <Text style={styles.meta}>Age: {patient.age}</Text> : null}<Text style={styles.meta}>{patient.visitCount} saved visits</Text></Card><PrimaryButton icon="scan-outline" onPress={onStartScan}>Scan Wound</PrimaryButton><PrimaryButton icon="time-outline" onPress={onOpenHistory}>View Visit History</PrimaryButton></View></ScrollView>; }
const styles = StyleSheet.create({ page: { padding: layout.pagePadding, alignItems: 'center' }, content: { width: '100%', maxWidth: 760, gap: 14 }, card: { gap: 8 }, meta: { ...typography.body, color: colors.textMuted } });
