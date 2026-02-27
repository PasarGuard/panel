import { useEffect, useState } from 'react'
import { CHART_VIEW_TYPE_CHANGE_EVENT, getChartViewTypePreference, type ChartViewType } from '@/utils/userPreferenceStorage'

export const useChartViewType = () => {
  const [chartViewType, setChartViewType] = useState<ChartViewType>(() => getChartViewTypePreference())

  useEffect(() => {
    const syncChartViewType = () => {
      setChartViewType(getChartViewTypePreference())
    }

    window.addEventListener('storage', syncChartViewType)
    window.addEventListener(CHART_VIEW_TYPE_CHANGE_EVENT, syncChartViewType as EventListener)

    return () => {
      window.removeEventListener('storage', syncChartViewType)
      window.removeEventListener(CHART_VIEW_TYPE_CHANGE_EVENT, syncChartViewType as EventListener)
    }
  }, [])

  return chartViewType
}
