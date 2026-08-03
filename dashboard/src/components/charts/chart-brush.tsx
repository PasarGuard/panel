import type { SVGProps } from 'react'
import { Brush } from 'recharts'

type BrushTravellerProps = {
  x?: number
  y?: number
  width?: number
  height?: number
} & SVGProps<SVGGElement>

/** Ellipse grip handles for resizing the visible candle window. */
function BrushTraveller({ x = 0, y = 0, width = 0, height = 0, ...handlers }: BrushTravellerProps) {
  const cx = x + width / 2
  const cy = y + height / 2
  const rx = Math.max(4, width / 2 - 0.5)
  const ry = Math.min(height * 0.38, 11)

  return (
    <g className="recharts-brush-traveller" style={{ cursor: 'ew-resize' }} {...handlers}>
      <rect x={x} y={y} width={width} height={height} fill="transparent" stroke="none" />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="hsl(var(--background))" stroke="hsl(var(--primary))" strokeWidth={1.5} />
      <circle cx={cx} cy={cy - 3.5} r={1} fill="hsl(var(--muted-foreground))" />
      <circle cx={cx} cy={cy} r={1} fill="hsl(var(--muted-foreground))" />
      <circle cx={cx} cy={cy + 3.5} r={1} fill="hsl(var(--muted-foreground))" />
    </g>
  )
}

type ChartBrushProps = {
  startIndex: number
  endIndex: number
  dataKey?: string
}

/** Theme-aware brush for panning / resizing dense chart viewports. */
export default function ChartBrush({ startIndex, endIndex, dataKey = 'time' }: ChartBrushProps) {
  return (
    <Brush
      dataKey={dataKey}
      height={28}
      travellerWidth={14}
      startIndex={startIndex}
      endIndex={endIndex}
      stroke="hsl(var(--border))"
      fill="hsl(var(--muted))"
      fillOpacity={0.45}
      traveller={props => <BrushTraveller {...props} />}
      alwaysShowText={false}
      padding={{ top: 2, right: 2, bottom: 2, left: 2 }}
    />
  )
}
