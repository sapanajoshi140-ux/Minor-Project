/**
 * ThemeContext.jsx
 * -----------------
 * Reusable dark / light mode context.
 * Drop this anywhere in your project.
 *
 * Usage:
 *   1. Wrap your app:  <ThemeProvider> ... </ThemeProvider>
 *   2. Consume:        const { theme, toggleTheme, isDark } = useTheme();
 *
 * The chosen theme is persisted to localStorage under the key "rwe-theme".
 * A "dark" or "light" class is added to <html> so you can use Tailwind's
 * `dark:` variant or your own CSS selectors.
 */

import React, { createContext, useContext, useEffect, useState } from 'react';

// ── Context ──────────────────────────────────────────────────────────────────
const ThemeContext = createContext({
  theme: 'dark',
  isDark: true,
  toggleTheme: () => {},
  setTheme: () => {},
});

// ── CSS variable sets ─────────────────────────────────────────────────────────
const THEMES = {
  dark: {
    '--bg-primary':      '#171717',   // neutral-900
    '--bg-secondary':    'rgba(255,255,255,0.05)',
    '--bg-tertiary':     'rgba(255,255,255,0.08)',
    '--border-color':    'rgba(255,255,255,0.10)',
    '--text-primary':    '#ffffff',
    '--text-secondary':  'rgba(255,255,255,0.60)',
    '--text-muted':      'rgba(255,255,255,0.35)',
    '--text-faint':      'rgba(255,255,255,0.20)',
    '--accent':          '#6ea8fe',   // blue-400-ish
    '--accent-warm':     '#fbbf24',   // amber-400
    '--sidebar-bg':      'rgba(0,0,0,0.20)',
    '--card-hover':      'rgba(255,255,255,0.08)',
    '--input-bg':        'rgba(255,255,255,0.05)',
    '--scrollbar-thumb': 'rgba(255,255,255,0.15)',
  },
  light: {
    '--bg-primary':      '#f5f5f4',   // stone-100
    '--bg-secondary':    'rgba(0,0,0,0.04)',
    '--bg-tertiary':     'rgba(0,0,0,0.06)',
    '--border-color':    'rgba(0,0,0,0.10)',
    '--text-primary':    '#1c1917',   // stone-900
    '--text-secondary':  'rgba(0,0,0,0.60)',
    '--text-muted':      'rgba(0,0,0,0.40)',
    '--text-faint':      'rgba(0,0,0,0.22)',
    '--accent':          '#2563eb',   // blue-600
    '--accent-warm':     '#d97706',   // amber-600
    '--sidebar-bg':      'rgba(255,255,255,0.70)',
    '--card-hover':      'rgba(0,0,0,0.05)',
    '--input-bg':        'rgba(0,0,0,0.04)',
    '--scrollbar-thumb': 'rgba(0,0,0,0.18)',
  },
};

// ── Inject CSS vars + html class ─────────────────────────────────────────────
function applyTheme(theme) {
  const root = document.documentElement;
  const vars = THEMES[theme] || THEMES.dark;
  Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v));
  root.classList.remove('dark', 'light');
  root.classList.add(theme);
}

// ── Provider ──────────────────────────────────────────────────────────────────
export function ThemeProvider({ children, defaultTheme = 'dark' }) {
  const [theme, setThemeState] = useState(() => {
    try {
      return localStorage.getItem('rwe-theme') || defaultTheme;
    } catch {
      return defaultTheme;
    }
  });

  useEffect(() => {
    applyTheme(theme);
    try { localStorage.setItem('rwe-theme', theme); } catch {}
  }, [theme]);

  const setTheme = (t) => {
    if (THEMES[t]) setThemeState(t);
  };

  const toggleTheme = () => setThemeState(prev => prev === 'dark' ? 'light' : 'dark');

  return (
    <ThemeContext.Provider value={{ theme, isDark: theme === 'dark', toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// ── Hook ─────────────────────────────────────────────────────────────────────
export function useTheme() {
  return useContext(ThemeContext);
}

// ── Standalone toggle button (optional convenience component) ─────────────────
export function ThemeToggleButton({ className = '' }) {
  const { isDark, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      className={`relative inline-flex items-center gap-2 px-3 py-1.5 rounded-full border transition-all text-sm font-medium ${
        isDark
          ? 'bg-white/10 border-white/15 text-white hover:bg-white/15'
          : 'bg-black/8 border-black/12 text-stone-800 hover:bg-black/12'
      } ${className}`}
    >
      <span className="text-base leading-none">{isDark ? '☀️' : '🌙'}</span>
      <span>{isDark ? 'Light mode' : 'Dark mode'}</span>
    </button>
  );
}

export default ThemeContext;