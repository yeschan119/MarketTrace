import type { Config } from "tailwindcss";

// A color remapped to a CSS variable holding "R G B" channels. Using the
// <alpha-value> placeholder keeps Tailwind opacity modifiers (e.g. bg-x/40)
// working. Values flip between light and dark in globals.css via `html.dark`.
const v = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces / dark bubbles — decoupled from the inverted gray ramp so
        // `bg-surface` (was bg-white) darkens while `text-white` stays light.
        surface: v("surface"),
        ink: v("ink"),

        gray: {
          50: v("gray-50"),
          100: v("gray-100"),
          200: v("gray-200"),
          300: v("gray-300"),
          400: v("gray-400"),
          500: v("gray-500"),
          600: v("gray-600"),
          700: v("gray-700"),
          800: v("gray-800"),
          900: v("gray-900"),
        },
        indigo: {
          50: v("indigo-50"),
          100: v("indigo-100"),
          200: v("indigo-200"),
          300: v("indigo-300"),
          400: v("indigo-400"),
          500: v("indigo-500"),
          600: v("indigo-600"),
          700: v("indigo-700"),
          800: v("indigo-800"),
        },
        emerald: {
          50: v("emerald-50"),
          100: v("emerald-100"),
          200: v("emerald-200"),
          400: v("emerald-400"),
          500: v("emerald-500"),
          600: v("emerald-600"),
          700: v("emerald-700"),
          800: v("emerald-800"),
        },
        amber: {
          50: v("amber-50"),
          100: v("amber-100"),
          200: v("amber-200"),
          300: v("amber-300"),
          400: v("amber-400"),
          500: v("amber-500"),
          600: v("amber-600"),
          700: v("amber-700"),
          800: v("amber-800"),
          900: v("amber-900"),
        },
        red: {
          50: v("red-50"),
          100: v("red-100"),
          200: v("red-200"),
          400: v("red-400"),
          500: v("red-500"),
          600: v("red-600"),
          700: v("red-700"),
          800: v("red-800"),
        },
        sky: {
          50: v("sky-50"),
          200: v("sky-200"),
          800: v("sky-800"),
        },
        blue: {
          50: v("blue-50"),
          700: v("blue-700"),
        },
        purple: {
          50: v("purple-50"),
          500: v("purple-500"),
          700: v("purple-700"),
        },
      },
    },
  },
  plugins: [],
};

export default config;
