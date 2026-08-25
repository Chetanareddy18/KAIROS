/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        teal:  { DEFAULT: '#1E7A78', dark: '#0D3D3C', light: '#EAF5F5' },
        sand:  { DEFAULT: '#D4B896', light: '#F7F5F0' },
      },
    },
  },
  plugins: [],
}
