// Categorical series must stay distinct independently of the UI accent color.
// Paired shades keep the same hue in light and dark mode.
const SERIES_COLORS = [
  { light: '#2563eb', dark: '#60a5fa' }, // Blue
  { light: '#c2410c', dark: '#fb923c' }, // Orange
  { light: '#059669', dark: '#34d399' }, // Emerald
  { light: '#7c3aed', dark: '#a78bfa' }, // Violet
  { light: '#db2777', dark: '#f472b6' }, // Pink
  { light: '#a16207', dark: '#facc15' }, // Yellow
  { light: '#0891b2', dark: '#22d3ee' }, // Cyan
  { light: '#4d7c0f', dark: '#a3e635' }, // Lime
  { light: '#dc2626', dark: '#f87171' }, // Red
  { light: '#4f46e5', dark: '#818cf8' }, // Indigo
] as const

export function getChartSeriesColor(index: number, isDark: boolean): string {
  const color = SERIES_COLORS[index]
  if (color) return isDark ? color.dark : color.light

  // Spread additional series around the hue wheel instead of repeating the palette.
  const hue = (index * 137.508) % 360
  return `hsl(${hue.toFixed(2)}, ${isDark ? 70 : 65}%, ${isDark ? 65 : 40}%)`
}
