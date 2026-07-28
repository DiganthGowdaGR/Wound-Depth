import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SavedReport } from '../services/woundlensApi';
import { Card } from '../components/Primitives';
import { colors, layout, typography } from '../theme';

export function ReportsScreen({ reports }: { reports: SavedReport[] }) { return <ScrollView contentContainerStyle={styles.page}><View style={styles.content}><Text style={typography.title}>Reports</Text>{reports.length ? reports.map((report) => <Pressable key={report.id} onPress={() => void Linking.openURL(report.pdfUrl)}><Card style={styles.card}><Text style={typography.subtitle}>{report.displayName}</Text><Text style={styles.meta}>{report.patientCode} | {new Date(report.visitDate).toLocaleString()}</Text><Text style={styles.open}>Open PDF report</Text></Card></Pressable>) : <Card><Text style={styles.meta}>No reports generated yet.</Text></Card>}</View></ScrollView>; }
const styles = StyleSheet.create({ page: { padding: layout.pagePadding, alignItems: 'center' }, content: { width: '100%', maxWidth: 760, gap: 14 }, card: { gap: 6 }, meta: { ...typography.body, color: colors.textMuted }, open: { ...typography.body, color: colors.primary, fontWeight: '800' } });
