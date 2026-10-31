import { Clock } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useTranslation } from 'react-i18next'
import useDirDetection from '@/hooks/use-dir-detection'

export type TimeFilter = 'all' | '1m' | '5m' | '15m' | '30m' | '1h' | '2h' | '6h' | '12h' | '24h'

interface SinceLogsFilterProps {
  value: TimeFilter
  onValueChange: (value: TimeFilter) => void
  showTimestamp: boolean
  onTimestampChange: (show: boolean) => void
}

export function SinceLogsFilter({ value, onValueChange, showTimestamp, onTimestampChange }: SinceLogsFilterProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()

  const TIME_FILTER_OPTIONS: { label: string; value: TimeFilter }[] = [
    { label: t('nodes.logs.timeFilters.all'), value: 'all' },
    { label: t('nodes.logs.timeFilters.1m'), value: '1m' },
    { label: t('nodes.logs.timeFilters.5m'), value: '5m' },
    { label: t('nodes.logs.timeFilters.15m'), value: '15m' },
    { label: t('nodes.logs.timeFilters.30m'), value: '30m' },
    { label: t('nodes.logs.timeFilters.1h'), value: '1h' },
    { label: t('nodes.logs.timeFilters.2h'), value: '2h' },
  ]

  return (
    <>
      <div className="flex w-full min-w-0 items-center gap-2 lg:w-auto">
        <span className="text-muted-foreground shrink-0 text-sm whitespace-nowrap">{t('nodes.logs.sinceLabel')}</span>
        <Select value={value} onValueChange={value => onValueChange(value as TimeFilter)}>
          <SelectTrigger className="h-9 min-w-0 flex-1 lg:w-32 lg:flex-none">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIME_FILTER_OPTIONS.map(option => (
              <SelectItem dir={dir} key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex w-full min-w-0 items-center gap-2 lg:w-auto">
        <Clock size={14} className="text-muted-foreground shrink-0" />
        <span className="text-muted-foreground min-w-0 truncate text-sm">{t('nodes.logs.timestamps')}</span>
        <Switch checked={showTimestamp} onCheckedChange={onTimestampChange} className="shrink-0 scale-75" />
      </div>
    </>
  )
}
