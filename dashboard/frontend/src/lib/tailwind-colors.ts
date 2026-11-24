// AirFed Color Scheme - Distinctive visual identity
// Primary: Electric Blue (TEALS) - represents technology and trust
// Secondary: Amber - represents energy and innovation
// Accent: Emerald - represents success and growth
// Neutral: Slate - professional and clean

export const tailwindcssColors = {
  // AirFed brand colors
  airfed: {
    50: '#e8f5ff',
    100: '#d0ebf5',
    200: '#a6d6ea',
    300: '#70c3db',
    400: '#24a2db',
    500: '#0ea5e9', // Primary electric blue
    600: '#0284c7',
    700: '#0369a1',
    800: '#075985',
    900: '#0c4a6e',
  },
  // Energy accent (amber)
  energy: {
    50: '#fffbeb',
    100: '#fef3c7',
    200: '#fde68a',
    300: '#fcd34d',
    400: '#fbbf24',
    500: '#f59e0b', // Primary amber
    600: '#d97706',
    700: '#b45309',
    800: '#92400e',
    900: '#78350f',
  },
  // Success (emerald/green)
  success: {
    50: '#ecfdf5',
    100: '#d1fae5',
    200: '#a7f3d0',
    300: '#6ee7b7',
    400: '#22c55e',
    500: '#10b981', // Primary emerald
    600: '#059669',
    700: '#047857',
    800: '#065f46',
    900: '#064e3b',
  },
  // Warning (amber/orange)
  warning: {
    50: '#fff7ed',
    100: '#ffedd5',
    200: '#fef3c7',
    300: '#fcd34d',
    400: '#fbbf24',
    500: '#f59e0b',
    600: '#d97706',
    700: '#b45309',
    800: '#92400e',
    900: '#78350f',
  },
  // Error (red)
  destructive: {
    50: '#fef2f2',
    100: '#fce4e4',
    200: '#f9d4d4',
    300: '#f4b4b4',
    400: '#f43f5e',
    500: '#ef4444',
    600: '#dc2626',
    700: '#b91c1c',
    800: '#991b1b',
    900: '#7f1d1d',
  },
  // Network/Gateway status colors
  gateway: {
    online: '#10b981',
    offline: '#6b7280',
    warning: '#f59e0b',
    critical: '#ef4444',
  },
  // FL-specific colors
  fl: {
    convergence: '#059669',
    divergence: '#ef4444',
    unstable: '#f59e0b',
  },
  // Communication status
  comm: {
    idle: '#6b7280',
    active: '#3b82f6',
    saturated: '#8b5cf6',
  },
  // Extended slate palette for neutrals
  slate: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
  },
  // Gray (alternative neutral)
  gray: {
    50: '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827',
  },
}

// CSS custom properties for runtime access
export const cssVars = `
:root {
  --airfed-primary: 20 145 233;
  --airfed-primary-dark: 2 132 199;
  --energy-accent: 245 158 11;
  --success-primary: 16 185 129;
  --warning: 245 158 11;
  --error: 239 68 68;
  --gateway-online: 16 185 129;
  --gateway-offline: 107 114 128;
  --fl-convergence: 5 150 105;
  --fl-divergence: 239 68 68;
  --comm-active: 59 130 246;
  --comm-saturated: 139 92 246;
  --border: 214 222 226;
  --background: 255 255 255;
  --foreground: 24 24 24;
  --muted: 240 240 240;
}

:root[data-theme="dark"] {
  --airfed-primary: 20 145 233;
  --airfed-primary-dark: 2 132 199;
  --energy-accent: 245 158 11;
  --success-primary: 16 185 129;
  --warning: 245 158 11;
  --error: 239 68 68;
  --gateway-online: 16 185 129;
  --gateway-offline: 107 114 128;
  --fl-convergence: 5 150 105;
  --fl-divergence: 239 68 68;
  --comm-active: 59 130 246;
  --comm-saturated: 139 92 246;
  --border: 55 65 81;
  --background: 15 23 42;
  --foreground: 225 228 234;
  --muted: 31 41 55;
}
`