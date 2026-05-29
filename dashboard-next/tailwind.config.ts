import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './context/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0f',
          card: '#121218',
          hover: '#1a1a22',
        },
        border: {
          DEFAULT: '#242430',
          glow: 'rgba(0,220,255,0.15)',
        },
        text: {
          primary: '#f0f0f7',
          secondary: '#a0a0b0',
          muted: '#606070',
        },
        accent: {
          DEFAULT: '#00dcff',
          bright: '#00ffff',
          dim: 'rgba(0,220,255,0.12)',
        },
        purple: '#b844ff',
        amber: '#ff9d00',
        pos: '#00ff88',
        neg: '#ff4444',
      },
      fontFamily: {
        mono: ['SF Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
      keyframes: {
        pulse2: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.4', transform: 'scale(0.8)' },
        },
        flowDown: {
          '0%': { top: '-40%', opacity: '0' },
          '15%': { opacity: '1' },
          '85%': { opacity: '1' },
          '100%': { top: '105%', opacity: '0' },
        },
        arrowPulse: {
          '0%, 100%': { opacity: '0.5', transform: 'translateY(-1px)' },
          '50%': { opacity: '1', transform: 'translateY(2px)' },
        },
        volPulse: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.6', transform: 'scale(1.4)' },
        },
        blinkOrange: {
          '0%, 100%': { background: 'rgba(255,157,0,0.4)', boxShadow: '0 0 8px rgba(255,157,0,0.6)' },
          '50%': { background: '#ff9d00', boxShadow: '0 0 16px rgba(255,157,0,1)' },
        },
        blinkGreen: {
          '0%, 100%': { background: 'rgba(0,255,136,0.4)', boxShadow: '0 0 8px rgba(0,255,136,0.6)' },
          '50%': { background: '#00ff88', boxShadow: '0 0 16px rgba(0,255,136,1)' },
        },
        heroCardGlow: {
          '0%, 100%': { borderColor: 'rgba(184,68,255,0.4)', boxShadow: '0 0 24px rgba(184,68,255,0.2), inset 0 0 24px rgba(184,68,255,0.05)' },
          '50%': { borderColor: 'rgba(184,68,255,0.8)', boxShadow: '0 0 48px rgba(184,68,255,0.4), inset 0 0 32px rgba(184,68,255,0.1)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        spin: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
      animation: {
        pulse2: 'pulse2 2s infinite',
        flowDown: 'flowDown 1.1s linear infinite',
        arrowPulse: 'arrowPulse 1.1s ease-in-out infinite',
        volPulse: 'volPulse 2s ease-in-out infinite',
        blinkOrange: 'blinkOrange 1.4s ease-in-out infinite',
        blinkGreen: 'blinkGreen 1.4s ease-in-out infinite',
        heroCardGlow: 'heroCardGlow 2.5s ease-in-out infinite',
        shimmer: 'shimmer 2s linear infinite',
        fadeIn: 'fadeIn 0.3s ease-out',
        slideUp: 'slideUp 0.3s ease-out',
        spin: 'spin 1s linear infinite',
      },
    },
  },
  plugins: [],
}

export default config
