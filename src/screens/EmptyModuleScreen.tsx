import { Ionicons } from '@expo/vector-icons';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card } from '../components/Primitives';
import { colors, layout, typography } from '../theme';

export function EmptyModuleScreen({ title, message, icon }: { title: string; message: string; icon: keyof typeof Ionicons.glyphMap }) {
  return <ScrollView contentContainerStyle={styles.page}><View style={styles.content}><Card style={styles.card}><Ionicons name={icon} size={30} color={colors.primary} /><Text style={typography.sectionTitle}>{title}</Text><Text style={styles.message}>{message}</Text></Card></View></ScrollView>;
}
const styles = StyleSheet.create({ page: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: layout.pagePadding }, content: { width: '100%', maxWidth: 520 }, card: { minHeight: 190, alignItems: 'center', justifyContent: 'center', gap: 12 }, message: { ...typography.body, color: colors.textMuted, textAlign: 'center' } });
