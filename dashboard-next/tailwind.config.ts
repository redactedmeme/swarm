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
          primary: '#080808',
          card: '#0f0f0f',
          hover: '#161616',
        },
        border: {
          DEFAULT: '#1c1c1c',
          glow: 'rgba(184,147,74,0.25)',
        },
        text: {
          primary: '#ececec',
          secondary: '#888888',
          muted: '#444444',
        },
        accent: {
          DEFAULT: '#b8934a',
          bright: '#d4aa62',
          dim: 'rgba(184,147,74,0.1)',
        },
        pos: '#4a9e6b',
        neg: '#a85050',
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
          '20%': { opacity: '1' },
          '80%': { opacity: '1' },
          '100%': { top: '110%', opacity: '0' },
        },
        arrowPulse: {
          '0%, 100%': { opacity: '0.4', transform: 'translateY(0)' },
          '50%': { opacity: '1', transform: 'translateY(2px)' },
        },
        volPulse: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.6', transform: 'scale(1.4)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        pulse2: 'pulse2 2s infinite',
        flowDown: 'flowDown 1.2s linear infinite',
        arrowPulse: 'arrowPulse 1.2s ease-in-out infinite',
        volPulse: 'volPulse 2s ease-in-out infinite',
        shimmer: 'shimmer 2s linear infinite',
      },
    },
  },
  plugins: [],
}

export default config
