import { describe, expect, it } from 'bun:test'

import { getDistinctChartColors, getNodeChartColors } from '../src/utils/chart-colors'

const linearRgb = (color: string) => {
  const rgb = Bun.color(color, '[rgb]')!
  return rgb.map(channel => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
}

const luminance = (color: string) => {
  const [r, g, b] = linearRgb(color)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

// Independently measure separation in CIELAB rather than the palette's OKLab space.
const cieLab = (color: string) => {
  const [r, g, b] = linearRgb(color)
  const transform = (value: number) => (value > 216 / 24389 ? Math.cbrt(value) : ((24389 / 27) * value + 16) / 116)
  const x = transform((0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047)
  const y = transform(0.2126729 * r + 0.7151522 * g + 0.072175 * b)
  const z = transform((0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883)
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}

const minimumSeparation = (colors: string[]) => {
  const lab = colors.map(cieLab)
  let minimum = Infinity
  lab.forEach((a, index) => {
    lab.slice(index + 1).forEach(b => {
      minimum = Math.min(minimum, Math.hypot(...a.map((value, channel) => value - b[channel])))
    })
  })
  return minimum
}

describe('chart colors', () => {
  for (const isDark of [false, true]) {
    describe(isDark ? 'dark theme' : 'light theme', () => {
      it('does not repeat after the old 20-color cycle', () => {
        const colors = getDistinctChartColors(128, isDark)
        expect(new Set(colors.map(color => Bun.color(color, 'hex'))).size).toBe(128)
      })

      it('keeps categorical colors perceptually separated', () => {
        expect(minimumSeparation(getDistinctChartColors(20, isDark))).toBeGreaterThan(12)
        expect(minimumSeparation(getDistinctChartColors(64, isDark))).toBeGreaterThan(6)
      })

      it('keeps at least 3:1 contrast with the chart surface', () => {
        const background = luminance(isDark ? '#2a2a2a' : '#f5f5f5')
        for (const color of getDistinctChartColors(128, isDark)) {
          const foreground = luminance(color)
          const contrast = (Math.max(background, foreground) + 0.05) / (Math.min(background, foreground) + 0.05)
          expect(contrast).toBeGreaterThanOrEqual(3)
        }
      })

      it('keeps the palette prefix stable as the node count grows or shrinks', () => {
        const original = getDistinctChartColors(8, isDark)
        expect(getDistinctChartColors(64, isDark).slice(0, 8)).toEqual(original)
        expect(getDistinctChartColors(8, isDark)).toEqual(original)
      })
    })
  }

  it('assigns the first colors to sparse existing IDs without reserving deleted IDs', () => {
    const nodes = [{ id: 7 }, { id: 104 }, { id: 9001 }]
    const colors = getNodeChartColors(nodes)
    expect([...colors.values()]).toEqual(getDistinctChartColors(3))
    expect([...colors.keys()]).toEqual([7, 104, 9001])
    expect(colors.has(1)).toBe(false)
  })

  it('reclaims a deleted node slot and remains consistent across response order', () => {
    const nodes = [{ id: 7 }, { id: 104 }, { id: 9001 }]
    expect(getNodeChartColors([...nodes].reverse())).toEqual(getNodeChartColors(nodes))
    const remaining = getNodeChartColors(nodes.filter(node => node.id !== 104))
    expect([...remaining.values()]).toEqual(getDistinctChartColors(2))
    expect(remaining.has(104)).toBe(false)
    expect(nodes.map(node => node.id)).toEqual([7, 104, 9001])
  })

  it('handles an empty current node list', () => {
    expect(getNodeChartColors([]).size).toBe(0)
    expect(getDistinctChartColors(0)).toEqual([])
  })
})
