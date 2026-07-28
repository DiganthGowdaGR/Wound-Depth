import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';
import { analyzeCurrent, getCaseHistory, getCases, CurrentWoundAssessment, PatientWoundHistory, UploadedScanInput } from './src/services/woundlensApi';
import { BottomNav, Header } from './src/components/Chrome';
import { DashboardScreen } from './src/screens/DashboardScreen';
import { PatientListScreen } from './src/screens/PatientListScreen';
import { PatientDetailScreen } from './src/screens/PatientDetailScreen';
import { WoundHistoryScreen } from './src/screens/WoundHistoryScreen';
import { ScanScreen } from './src/screens/ScanScreen';
import { ResultScreen } from './src/screens/ResultScreen';
import { EmptyModuleScreen } from './src/screens/EmptyModuleScreen';
import { colors, layout, typography } from './src/theme';

export type ScreenKey = 'dashboard' | 'patients' | 'detail' | 'history' | 'reports' | 'profile' | 'scan' | 'result';

export default function App() {
  const [screen, setScreen] = useState<ScreenKey>('scan');
  const [history, setHistory] = useState<PatientWoundHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentAssessment, setCurrentAssessment] = useState<CurrentWoundAssessment | null>(null);

  const loadDataset = useCallback(async () => {
    setLoading(true);
    setError(null);
    await getCases()
      .then(async (availableCases) => {
        const initialCase = availableCases.find((item) => item.caseId === 'case_12') ?? availableCases[0];
        if (!initialCase) {
          setHistory(null);
          return;
        }
        setHistory(await getCaseHistory(initialCase.caseId));
      })
      .catch((loadError: Error) => setError(loadError.message || 'Unable to load the configured WoundLens dataset.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void loadDataset();
  }, [loadDataset]);

  const showCurrentAnalysis = async (uploads: Record<'rgb' | 'thermal' | 'depth', UploadedScanInput>) => {
    const assessment = await analyzeCurrent(uploads);
    setCurrentAssessment(assessment);
    setScreen('result');
  };

  const renderScreen = () => {
    if (loading && screen !== 'scan') {
      return (
        <CenteredState>
          <ActivityIndicator color={colors.primary} size="large" />
          <Text style={styles.stateTitle}>Loading patient analysis</Text>
        </CenteredState>
      );
    }

    if (error && screen !== 'scan') {
      return (
        <CenteredState>
          <Text style={styles.errorTitle}>Analysis unavailable</Text>
          <Text style={styles.errorText}>{error}</Text>
          <Pressable style={styles.retryButton} onPress={() => void loadDataset()}>
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </CenteredState>
      );
    }

    if (!history && screen !== 'scan') {
      return (
        <CenteredState>
          <Text style={styles.stateTitle}>No dataset visits loaded</Text>
          <Text style={styles.errorText}>The model will not run until a baseline and follow-up visit with RGB, thermal, and depth images are available.</Text>
          <Pressable style={styles.retryButton} onPress={() => void loadDataset()}>
            <Text style={styles.retryText}>Check Dataset</Text>
          </Pressable>
        </CenteredState>
      );
    }

    switch (screen) {
      case 'patients':
        return <PatientListScreen />;
      case 'detail':
        return <PatientDetailScreen history={history!} onOpenHistory={() => setScreen('history')} onStartScan={() => setScreen('scan')} />;
      case 'history':
        return <WoundHistoryScreen history={history!} onOpenResult={() => setScreen('scan')} />;
      case 'reports':
        return <EmptyModuleScreen title="Reports" message="No reports generated yet." icon="document-text-outline" />;
      case 'profile':
        return <EmptyModuleScreen title="Profile" message="No profile information is available yet." icon="person-outline" />;
      case 'scan':
        return <ScanScreen history={history ?? undefined} onCurrentAnalyze={showCurrentAnalysis} />;
      case 'result':
        return <ResultScreen history={history ?? undefined} currentAssessment={currentAssessment ?? undefined} onOpenHistory={() => setScreen(history ? 'history' : 'scan')} />;
      case 'dashboard':
      default:
        return <DashboardScreen onStartScan={() => setScreen('scan')} />;
    }
  };

  const isBackScreen = screen === 'detail' || screen === 'history' || screen === 'reports' || screen === 'profile' || screen === 'scan' || screen === 'result';

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <Header showBack={isBackScreen} onBack={() => setScreen(screen === 'detail' ? 'patients' : 'detail')} />
      <View style={styles.body}>{renderScreen()}</View>
      <BottomNav active={screen} onNavigate={setScreen} />
    </SafeAreaView>
  );
}

function CenteredState({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView contentContainerStyle={styles.centeredContent}>
      <View style={styles.stateCard}>{children}</View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.appBackground,
  },
  body: {
    flex: 1,
  },
  centeredContent: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: layout.pagePadding,
  },
  stateCard: {
    width: '100%',
    maxWidth: 460,
    minHeight: 220,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 14,
  },
  stateTitle: {
    ...typography.subtitle,
  },
  errorTitle: {
    ...typography.title,
    color: colors.danger,
  },
  errorText: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: 'center',
  },
  retryButton: {
    backgroundColor: colors.primary,
    paddingHorizontal: 22,
    paddingVertical: 12,
    borderRadius: 8,
  },
  retryText: {
    ...typography.button,
    color: colors.onPrimary,
  },
});
