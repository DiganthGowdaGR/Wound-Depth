import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card, PrimaryButton } from '../components/Primitives';
import { colors, layout, typography } from '../theme';

export function DashboardScreen({ onStartScan }: { onStartScan: () => void }) {
  return <ScrollView contentContainerStyle={styles.page}><View style={styles.content}><Text style={typography.title}>WoundLens</Text><Text style={styles.subcopy}>Current wound structural assessment</Text><Card style={styles.card}><Text style={typography.sectionTitle}>No saved scans yet.</Text><Text style={styles.message}>Upload RGB, thermal, and depth images to assess one current wound scan.</Text><PrimaryButton icon="scan-outline" onPress={onStartScan}>Scan Wound</PrimaryButton></Card></View></ScrollView>;
}
const styles = StyleSheet.create({ page: { padding: layout.pagePadding, alignItems: 'center' }, content: { width: '100%', maxWidth: 700, gap: 16 }, subcopy: { ...typography.body, color: colors.textMuted, marginTop: -8 }, card: { minHeight: 220, alignItems: 'center', justifyContent: 'center', gap: 14 }, message: { ...typography.body, color: colors.textMuted, textAlign: 'center', maxWidth: 380 } });
