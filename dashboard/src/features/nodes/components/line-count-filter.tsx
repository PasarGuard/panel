import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from 'react-i18next'
import { toPersianNumerals } from '@/utils/formatByte'
import useDirDetection from '@/hooks/use-dir-detection'

interface LineCountFilterProps {
  value: number
  onValueChange: (value: number) => void
}

export function LineCountFilter({ value, onValueChange }: LineCountFilterProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()

  const LINE_COUNT_OPTIONS = [50, 100, 200, 500, 1000, 2000, 5000]

  const getLineCountLabel = (count: number) => {
    const label = t('nodes.logs.linesCount', { count })
    return i18n.language === 'fa' ? toPersianNumerals(label) : label
  }

  return (
    <div className="flex w-full min-w-0 items-center gap-2 lg:w-auto">
      <span className="text-muted-foreground shrink-0 text-sm whitespace-nowrap">{t('nodes.logs.linesLabel')}</span>
      <Select dir={dir} value={value.toString()} onValueChange={value => onValueChange(Number(value))}>
        <SelectTrigger className="h-9 min-w-0 flex-1 lg:w-32 lg:flex-none">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {LINE_COUNT_OPTIONS.map(option => (
            <SelectItem key={option} value={option.toString()}>
              {getLineCountLabel(option)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
