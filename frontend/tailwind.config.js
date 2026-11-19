/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: '#04070d',
          900: '#070b12',
          850: '#0b101a',
          800: '#101726',
          750: '#151e30',
          700: '#1c2840',
        },
        trade: {
          buy: '#10b981',
          'buy-muted': 'rgba(16, 185, 129, 0.15)',
          sell: '#f43f5e',
          'sell-muted': 'rgba(244, 63, 94, 0.15)',
          poc: '#f59e0b',
          'poc-muted': 'rgba(245, 158, 11, 0.15)',
          va: '#6366f1',
          'va-muted': 'rgba(99, 102, 241, 0.1)',
        }
      },
      fontFamily: {
        mono: [
          'JetBrains Mono',
          'Fira Code',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace'
        ],
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif'
        ]
      },
      boxShadow: {
        'glow-indigo': '0 0 20px -3px rgba(99, 102, 241, 0.35)',
        'glow-emerald': '0 0 20px -3px rgba(16, 185, 129, 0.35)',
        'glow-rose': '0 0 20px -3px rgba(244, 63, 94, 0.35)',
        'glow-amber': '0 0 20px -3px rgba(245, 158, 11, 0.35)',
      }
    },
  },
  plugins: [],
}
