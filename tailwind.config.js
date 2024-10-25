/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        gray: {
          50: '#F9FAFB',
          100: '#F3F4F6',
          200: '#E5E7EB',
          500: '#6B7280',
          600: '#4B5563',
          900: '#111827',
        },
        blue: {
          600: '#2563EB',
          700: '#1D4ED8',
        },
        red: {
          50: '#FEF2F2',
          300: '#FCA5A5',
          500: '#EF4444',
          600: '#DC2626',
        },
        green: {
          50: '#F0FDF4',
          300: '#86EFAC',
        },
      },
      spacing: {
        '6': '1.5rem',
        '32': '8rem',
      },
      borderRadius: {
        'lg': '0.5rem',
      },
      animation: {
        'spin': 'spin 1s linear infinite',
      },
      transitionProperty: {
        'colors': 'background-color, border-color, color, fill, stroke',
      },
      transitionDuration: {
        '200': '200ms',
      }
    },
  },
  plugins: [],
}
