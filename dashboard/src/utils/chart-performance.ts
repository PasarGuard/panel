/** Soft limits for keeping Recharts responsive with dense candle data. */
export const CHART_ANIMATION_POINT_LIMIT = 48
export const CHART_CELL_RADIUS_POINT_LIMIT = 36
export const CHART_ANIMATION_CELL_LIMIT = 180
export const CHART_CELL_RADIUS_CELL_LIMIT = 120
/** Suggest switching theme chart view to Area above this candle count. */
export const CHART_AREA_SUGGESTION_POINT_LIMIT = 300
/** Only window the viewport when stacked SVG cells would get extreme. */
export const CHART_BRUSH_CELL_LIMIT = 4000
export const CHART_BRUSH_MIN_WINDOW = 240

export type ChartRenderFlags = {
  /** Disable entrance animations when the chart is dense. */
  isAnimationActive: boolean
  /** Skip per-bar Cell radius mapping; use a flat bar radius instead. */
  usePerBarRadius: boolean
  /** Recharts accessibility layer adds listeners; skip it on dense charts. */
  useAccessibilityLayer: boolean
  /** Linear paths are cheaper than monotone for dense area charts. */
  areaCurveType: 'monotone' | 'linear'
}

export const getChartRenderFlags = (pointCount: number, seriesCount = 1): ChartRenderFlags => {
  const safePoints = Math.max(0, pointCount)
  const safeSeries = Math.max(1, seriesCount)
  const cellCount = safePoints * safeSeries
  const dense = safePoints > 80 || cellCount > 240

  return {
    isAnimationActive: safePoints <= CHART_ANIMATION_POINT_LIMIT && cellCount <= CHART_ANIMATION_CELL_LIMIT,
    usePerBarRadius: safePoints <= CHART_CELL_RADIUS_POINT_LIMIT && cellCount <= CHART_CELL_RADIUS_CELL_LIMIT,
    useAccessibilityLayer: !dense,
    areaCurveType: dense ? 'linear' : 'monotone',
  }
}

export type ChartBrushWindow = {
  startIndex: number
  endIndex: number
}

/**
 * Keep every candle in the dataset. Only add a Brush viewport when stacked
 * series would create an extreme number of SVG cells.
 */
export const getChartBrushWindow = (pointCount: number, seriesCount = 1): ChartBrushWindow | null => {
  const safePoints = Math.max(0, pointCount)
  const safeSeries = Math.max(1, seriesCount)
  const cellCount = safePoints * safeSeries

  if (cellCount <= CHART_BRUSH_CELL_LIMIT) return null

  const maxVisible = Math.max(CHART_BRUSH_MIN_WINDOW, Math.floor(CHART_BRUSH_CELL_LIMIT / safeSeries))
  if (safePoints <= maxVisible) return null

  return {
    startIndex: Math.max(0, safePoints - maxVisible),
    endIndex: safePoints - 1,
  }
}
