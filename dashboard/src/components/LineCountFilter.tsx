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

  const LINE_COUNT_OPTIONS = [
    { label: i18n.language === 'fa' ? `${toPersianNumerals(50)} خط` : '50 lines', value: 50 },
    { label: i18n.language === 'fa' ? `${toPersianNumerals(100)} خط` : '100 lines', value: 100 },
    { label: i18n.language === 'fa' ? `${toPersianNumerals(200)} خط` : '200 lines', value: 200 },
    { label: i18n.language === 'fa' ? `${toPersianNumerals(500)} خط` : '500 lines', value: 500 },
    { label: i18n.language === 'fa' ? `${toPersianNumerals(1000)} خط` : '1000 lines', value: 1000 },
    { label: i18n.language === 'fa' ? `${toPersianNumerals(2000)} خط` : '2000 lines', value: 2000 },
    { label: i18n.language === 'fa' ? `${toPersianNumerals(5000)} خط` : '5000 lines', value: 5000 },
  ]

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted-foreground">{t('nodes.logs.linesLabel', { defaultValue: 'Lines:' })}</span>
      <Select dir={dir} value={value.toString()} onValueChange={value => onValueChange(Number(value))}>
        <SelectTrigger className="h-9 w-24">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {LINE_COUNT_OPTIONS.map(option => (
            <SelectItem key={option.value} value={option.value.toString()}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
