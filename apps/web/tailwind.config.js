/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#241b2f",
        plum: "#6d3fc1",
        lavender: "#f2edff",
        cream: "#fbfaf8",
      },
    },
  },
  plugins: [],
};

