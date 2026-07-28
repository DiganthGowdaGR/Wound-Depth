import { TextStyle } from 'react-native';

export const colors = {
  appBackground: '#f4f7fb',
  surface: '#ffffff',
  surfaceMuted: '#f8fafc',
  primary: '#0b57d0',
  primaryBright: '#2f6df3',
  primarySoft: '#dce8ff',
  border: '#d7dee9',
  borderStrong: '#bfcbda',
  text: '#0c1222',
  textMuted: '#546179',
  danger: '#d92d2d',
  dangerSoft: '#fff1f1',
  success: '#007f72',
  successSoft: '#d8fbf3',
  warning: '#b45309',
  warningSoft: '#fff7ed',
  tealSoft: '#d7f7f3',
  slate: '#687387',
  onPrimary: '#ffffff',
};

export const layout = {
  pagePadding: 20,
  maxContent: 960,
  bottomNavHeight: 72,
};

export const typography = {
  brand: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
    color: colors.primary,
  } satisfies TextStyle,
  title: {
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '800',
    color: colors.text,
  } satisfies TextStyle,
  sectionTitle: {
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '800',
    color: colors.text,
  } satisfies TextStyle,
  subtitle: {
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '700',
    color: colors.text,
  } satisfies TextStyle,
  body: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '400',
    color: colors.text,
  } satisfies TextStyle,
  caption: {
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '500',
    color: colors.textMuted,
  } satisfies TextStyle,
  label: {
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
    color: colors.textMuted,
    textTransform: 'uppercase',
  } satisfies TextStyle,
  button: {
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '800',
  } satisfies TextStyle,
};
