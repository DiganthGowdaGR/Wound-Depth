import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { ScreenKey } from '../../App';
import { colors, layout, typography } from '../theme';

type NavItem = {
  key: ScreenKey;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
};

const navItems: NavItem[] = [
  { key: 'dashboard', label: 'Home', icon: 'home-outline' },
  { key: 'patients', label: 'Patients', icon: 'people-outline' },
  { key: 'scan', label: 'Scan', icon: 'scan-circle-outline' },
  { key: 'reports', label: 'Reports', icon: 'document-text-outline' },
  { key: 'profile', label: 'Profile', icon: 'person-outline' },
];

export function Header({ showBack, onBack }: { showBack?: boolean; onBack?: () => void }) {
  return (
    <View style={styles.header}>
      <View style={styles.headerLeft}>
        {showBack ? (
          <Pressable accessibilityRole="button" onPress={onBack} style={styles.backButton}>
            <Ionicons name="arrow-back" size={24} color={colors.primary} />
          </Pressable>
        ) : (
          <MaterialCommunityIcons name="dots-grid" size={28} color={colors.primary} />
        )}
        <Text style={styles.brand}>WoundLens</Text>
      </View>
      <View style={styles.avatar}><Ionicons name="person-outline" size={18} color={colors.primary} /></View>
    </View>
  );
}

export function BottomNav({ active, onNavigate }: { active: ScreenKey; onNavigate: (key: ScreenKey) => void }) {
  return (
    <View style={styles.nav}>
      {navItems.map((item) => {
        const isActive = active === item.key || (active === 'result' && item.key === 'scan');
        return (
          <Pressable key={item.key} accessibilityRole="button" onPress={() => onNavigate(item.key)} style={styles.navItem}>
            <View style={[styles.navIcon, isActive && styles.activeNavIcon]}>
              <Ionicons name={item.icon} size={22} color={isActive ? colors.onPrimary : colors.slate} />
            </View>
            <Text style={[styles.navLabel, isActive && styles.activeNavLabel]}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    height: 62,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 18,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: '#edf1f6',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  brand: {
    ...typography.brand,
  },
  backButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.primarySoft,
    borderWidth: 2,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  nav: {
    height: layout.bottomNavHeight,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: 12,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: '#edf1f6',
  },
  navItem: {
    minWidth: 64,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  navIcon: {
    width: 42,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
  activeNavIcon: {
    backgroundColor: colors.primaryBright,
  },
  navLabel: {
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '700',
    color: colors.slate,
  },
  activeNavLabel: {
    color: colors.primary,
  },
});
