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

type Rgb = [number, number, number]
type Lab = [number, number, number]

function toOklab([red, green, blue]: Rgb): Lab {
  const linear = [red, green, blue].map(channel => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  const l = Math.cbrt(0.4122214708 * linear[0] + 0.5363325363 * linear[1] + 0.0514459929 * linear[2])
  const m = Math.cbrt(0.2119034982 * linear[0] + 0.6806995451 * linear[1] + 0.1073969566 * linear[2])
  const s = Math.cbrt(0.0883024619 * linear[0] + 0.2817188376 * linear[1] + 0.6299787005 * linear[2])
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s]
}

function hexToLab(hex: string): Lab {
  return toOklab([1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16)) as Rgb)
}

function hslToLab(hue: number, saturation: number, lightness: number): Lab {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation
  const second = chroma * (1 - Math.abs(((hue / 60) % 2) - 1))
  const offset = lightness - chroma / 2
  const channels: Rgb =
    hue < 60 ? [chroma, second, 0] : hue < 120 ? [second, chroma, 0] : hue < 180 ? [0, chroma, second] : hue < 240 ? [0, second, chroma] : hue < 300 ? [second, 0, chroma] : [chroma, 0, second]
  return toOklab(channels.map(channel => (channel + offset) * 255) as Rgb)
}

function distanceSquared(a: Lab, b: Lab): number {
  return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
}

const colors: { light: string; dark: string; lightLab: Lab; darkLab: Lab }[] = SERIES_COLORS.map(({ light, dark }) => ({ light, dark, lightLab: hexToLab(light), darkLab: hexToLab(dark) }))

const candidates = Array.from({ length: 72 }, (_, index) => (index * 137.508) % 360).flatMap(hue =>
  [
    [65, 40, 70, 65],
    [80, 32, 75, 58],
    [55, 50, 65, 73],
    [85, 45, 85, 68],
  ].map(([lightSaturation, lightLightness, darkSaturation, darkLightness]) => ({
    light: `hsl(${hue.toFixed(2)}, ${lightSaturation}%, ${lightLightness}%)`,
    dark: `hsl(${hue.toFixed(2)}, ${darkSaturation}%, ${darkLightness}%)`,
    lightLab: hslToLab(hue, lightSaturation / 100, lightLightness / 100),
    darkLab: hslToLab(hue, darkSaturation / 100, darkLightness / 100),
  })),
)
const maxColors = colors.length + candidates.length

export function getChartSeriesColor(index: number, isDark: boolean): string {
  const colorIndex = index % maxColors
  while (colors.length <= colorIndex) {
    let bestIndex = 0
    let bestDistance = -1

    candidates.forEach((candidate, candidateIndex) => {
      // Maximize the shortest perceptual distance in both themes, including the fixed palette.
      let nearest = Infinity
      for (const color of colors) {
        nearest = Math.min(nearest, distanceSquared(candidate.lightLab, color.lightLab), distanceSquared(candidate.darkLab, color.darkLab))
      }
      if (nearest > bestDistance) {
        bestDistance = nearest
        bestIndex = candidateIndex
      }
    })

    colors.push(candidates.splice(bestIndex, 1)[0])
  }

  const color = colors[colorIndex]
  return isDark ? color.dark : color.light
}
