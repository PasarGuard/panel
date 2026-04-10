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
    <div className="flex items-center gap-2 w-full sm:w-3/5 md:w-2/6 lg:w-2/8">
      <span className="text-sm text-muted-foreground whitespace-nowrap">{t('nodes.logs.linesLabel')}</span>
      <Select dir={dir} value={value.toString()} onValueChange={value => onValueChange(Number(value))}>
        <SelectTrigger className="h-9">
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
