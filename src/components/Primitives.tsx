import { ReactNode } from 'react';
import { Pressable, StyleProp, StyleSheet, Text, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography } from '../theme';

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'danger' | 'success' | 'warning' | 'primary' }) {
  return <Text style={[styles.pill, styles[`${tone}Pill`]]}>{children}</Text>;
}

export function PrimaryButton({ children, onPress, icon, disabled }: { children: ReactNode; onPress: () => void; icon?: keyof typeof Ionicons.glyphMap; disabled?: boolean }) {
  return (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[styles.primaryButton, disabled && styles.primaryButtonDisabled]}>
      {icon ? <Ionicons name={icon} size={18} color={colors.onPrimary} /> : null}
      <Text style={styles.primaryButtonText}>{children}</Text>
    </Pressable>
  );
}

export const styles = StyleSheet.create({
  card: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    padding: 18,
  },
  pill: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
    fontSize: 10,
    lineHeight: 12,
    fontWeight: '900',
    overflow: 'hidden',
  },
  neutralPill: {
    color: colors.textMuted,
    backgroundColor: '#eef2f7',
  },
  dangerPill: {
    color: colors.danger,
    backgroundColor: '#ffe3e3',
  },
  successPill: {
    color: colors.success,
    backgroundColor: '#caf7e9',
  },
  warningPill: {
    color: colors.warning,
    backgroundColor: colors.warningSoft,
  },
  primaryPill: {
    color: colors.primary,
    backgroundColor: colors.primarySoft,
  },
  primaryButton: {
    minHeight: 52,
    borderRadius: 8,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 18,
  },
  primaryButtonDisabled: {
    opacity: 0.45,
  },
  primaryButtonText: {
    ...typography.button,
    color: colors.onPrimary,
  },
});
