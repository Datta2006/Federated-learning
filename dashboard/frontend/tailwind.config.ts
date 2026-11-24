import { type Config } from 'tailwindcss'
import { tailwindcssColors } from './src/lib/tailwind-colors'

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  server: {
    url: 'https://tailwindcss.com',
  },
  theme: {
    extend: {
      colors: {
        // AirFed brand colors
        airfed: tailwindcssColors.airfed,
        // Energy accent (amber)
        energy: tailwindcssColors.energy,
        // Success (emerald/green)
        success: tailwindcssColors.success,
        // Warning (amber/orange)
        warning: tailwindcssColors.warning,
        // Error/destructive (red)
        destructive: tailwindcssColors.destructive,
        // Gateway status colors
        gateway: tailwindcssColors.gateway,
        // FL-specific colors
        fl: tailwindcssColors.fl,
        // Communication status
        comm: tailwindcssColors.comm,
        // Slate neutrals
        slate: tailwindcssColors.slate,
        // Gray neutrals
        gray: tailwindcssColors.gray,
      },
      fontFamily: {
        sans: ['var(--font-geist)', 'Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-jetbrains-mono)', 'JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        xl: 'calc(var(--radius) + 4px)',
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        'spin-around': {
          '0%, 100%': { transform: 'rotate(0deg)' },
          '50%': { transform: 'rotate(-360deg)' },
        },
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(2px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-out': {
          '0%': { opacity: '1', transform: 'translateY(0)' },
          '100%': { opacity: '0', transform: 'translateY(2px)' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 0 0 hsl(20 145 233 / 0.4)' },
          '50%': { boxShadow: '0 0 0 8px hsl(20 145 233 / 0)' },
        },
        'badge-pulse': {
          '0%, 100%': { transform: 'scale(1)', opacity: 1 },
          '50%': { transform: 'scale(1.1)', opacity: 0.8 },
        },
      },
      animation: {
        'spin-around': 'spin-around 1s linear infinite',
        'fade-in': 'fade-in 0.3s ease-out forwards',
        'fade-out': 'fade-out 0.2s ease-in forwards',
        'fade-in-up': 'fade-in-up 0.3s ease-out forwards',
        'pulse-glow': 'pulse-glow 2s infinite',
        'badge-pulse': 'badge-pulse 2s ease-in-out infinite',
      },
    },
  },
  plugins: [
    function ({ addBase, addUtilities }) {
      // Custom base styles
      addBase({
        ':root': {
          '--background': '255 255 255',
          '--foreground': 'hsl(0 0% 9)',
          '--card': '255 255 255',
          '--card-foreground': 'hsl(0 0% 9)',
          '--popover': '255 255 255',
          '--popover-foreground': 'hsl(0 0% 9)',
          '--primary': '14 165 233',
          '--primary-foreground': '255 255 255',
          '--secondary': '244 244 255',
          '--secondary-foreground': 'hsl(0 0% 9)',
          '--muted': '240 240 240',
          '--muted-foreground': 'hsl(0 0% 50)',
          '--accent': '245 158 11',
          '--accent-foreground': 'hsl(0 0% 9)',
          '--destructive': '239 68 68',
          '--destructive-foreground': '255 255 255',
          '--border': '228 228 228',
          '--input': '228 228 228',
          '--ring': '214 222 226',
          '--radius': '0.5rem',
          '--font-sans': '"Inter", system-ui, sans-serif',
        },
        '[data-theme="dark"]': {
          '--background': '15 23 42',
          '--foreground': 'hsl(0 0% 90)',
          '--card': '15 23 42',
          '--card-foreground': 'hsl(0 0% 90)',
          '--popover': '15 23 42',
          '--popover-foreground': 'hsl(0 0% 90)',
          '--primary': '20 145 233',
          '--primary-foreground': '255 255 255',
          '--secondary': '31 41 55',
          '--secondary-foreground': 'hsl(0 0% 90)',
          '--muted': '55 65 81',
          '--muted-foreground': 'hsl(0 0% 50)',
          '--accent': '245 158 11',
          '--accent-foreground': 'hsl(0 0% 9)',
          '--destructive': '239 68 68',
          '--destructive-foreground': '255 255 255',
          '--border': '55 65 81',
          '--input': '55 65 81',
          '--ring': '75 85 99',
          '--font-sans': '"Inter", system-ui, sans-serif',
        },
        'body': {
          color: 'hsl(var(--foreground))',
          backgroundColor: 'hsl(var(--background))',
          fontFamily: 'var(--font-sans)',
          featureSettings: "'liga' 1",
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
      })
    },
  ],
} satisfies Config