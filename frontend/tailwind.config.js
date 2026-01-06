/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        toss: {
          blue: "#3182F6",    // Toss Brand Blue
          bg: "#F2F4F6",      // Light Gray Background
          text: "#191F28",    // Main Text
          grey: "#B0B8C1",    // Sub Text
          red: "#F04452",     // Error/Alert
        }
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
