type Color = {
  css: string
  lab: [number, number, number]
  luminance: number
  distance: number
}

type Palette = {
  colors: Color[]
  candidates: Color[]
  generation: number
}

const palettes = new Map<boolean, Palette>()

const createColor = (hue: number, saturation: number, lightness: number): Color => {
  const s = saturation / 100
  const l = lightness / 100
  const a = s * Math.min(l, 1 - l)
  const channel = (offset: number) => {
    const k = (offset + hue / 30) % 12
    const value = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  const r = channel(0)
  const g = channel(8)
  const b = channel(4)
  const long = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const medium = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const short = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)

  return {
    css: `hsl(${hue}, ${saturation}%, ${lightness}%)`,
    lab: [
      0.2104542553 * long + 0.793617785 * medium - 0.0040720468 * short,
      1.9779984951 * long - 2.428592205 * medium + 0.4505937099 * short,
      0.0259040371 * long + 0.7827717662 * medium - 0.808675766 * short,
    ],
    luminance: 0.2126 * r + 0.7152 * g + 0.0722 * b,
    distance: Infinity,
  }
}

const distanceSquared = (a: Color, b: Color) => a.lab.reduce((sum, value, index) => sum + (value - b.lab[index]) ** 2, 0)

const createCandidates = (isDark: boolean, hueOffset: number): Color[] => {
  const candidates: Color[] = []
  // Keep categorical colors visible against both the chart card and the page.
  const backgroundLuminance = isDark ? 0.025 : 0.91
  for (let hue = hueOffset; hue < 360; hue += 2) {
    for (const saturation of [60, 80, 100]) {
      for (const lightness of isDark ? [45, 55, 65, 75] : [30, 40, 50, 60]) {
        const color = createColor(hue, saturation, lightness)
        const contrast = (Math.max(color.luminance, backgroundLuminance) + 0.05) / (Math.min(color.luminance, backgroundLuminance) + 0.05)
        if (contrast >= 3) candidates.push(color)
      }
    }
  }
  return candidates
}

/** Select each new color by its minimum perceptual distance from all previous colors. */
export const getDistinctChartColors = (count: number, isDark = false): string[] => {
  if (count <= 0) return []

  let palette = palettes.get(isDark)
  if (!palette) {
    const first = createColor(214, 80, isDark ? 65 : 40)
    palette = { colors: [first], candidates: createCandidates(isDark, 0).filter(color => color.css !== first.css), generation: 0 }
    palettes.set(isDark, palette)
  }

  while (palette.colors.length < count) {
    if (palette.candidates.length === 0) {
      // Refine the hue grid instead of cycling through an exhausted palette.
      palette.generation += 1
      palette.candidates = createCandidates(isDark, 2 ** -palette.generation)
      for (const candidate of palette.candidates) {
        candidate.distance = Math.min(...palette.colors.map(color => distanceSquared(candidate, color)))
      }
    }

    const previous = palette.colors[palette.colors.length - 1]
    let bestIndex = 0
    palette.candidates.forEach((candidate, index) => {
      candidate.distance = Math.min(candidate.distance, distanceSquared(candidate, previous))
      if (candidate.distance > palette.candidates[bestIndex].distance) bestIndex = index
    })
    palette.colors.push(palette.candidates.splice(bestIndex, 1)[0])
  }

  return palette.colors.slice(0, count).map(color => color.css)
}

/** IDs identify nodes; only their position in the current list consumes a color. */
export const getNodeChartColors = (nodes: readonly { id: number }[], isDark = false): Map<number, string> => {
  const ids = [...new Set(nodes.map(node => node.id))].sort((a, b) => a - b)
  const colors = getDistinctChartColors(ids.length, isDark)
  return new Map(ids.map((id, index) => [id, colors[index]]))
}
