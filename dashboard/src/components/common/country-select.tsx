import { CountryFlag } from '@/components/common/country-flag'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { getCountryName, getCountryOptions, normalizeCountryCode } from '@/utils/countries'
import { Check, ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

const NONE_VALUE = '__none__'

interface CountrySelectProps {
  value?: string | null
  onChange: (code: string | null) => void
  disabled?: boolean
  className?: string
}

export function CountrySelect({ value, onChange, disabled, className }: CountrySelectProps) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const [open, setOpen] = useState(false)
  const selected = normalizeCountryCode(value)
  const options = useMemo(() => (open ? getCountryOptions(i18n.language) : []), [open, i18n.language])

  const select = (code: string | null) => {
    onChange(code)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" role="combobox" aria-expanded={open} disabled={disabled} className={cn('w-full justify-between px-3 font-normal', className)}>
          <span className="flex min-w-0 items-center gap-2">
            {selected ? (
              <>
                <CountryFlag code={selected} />
                <span className="truncate">{getCountryName(selected, i18n.language)}</span>
              </>
            ) : (
              <span className="text-muted-foreground truncate">{t('nodeModal.countryNone')}</span>
            )}
          </span>
          <ChevronDown className="text-muted-foreground h-4 w-4 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,20rem)] p-1" sideOffset={4} align={dir === 'rtl' ? 'end' : 'start'}>
        <Command>
          <CommandInput placeholder={t('nodeModal.countrySearch')} className="h-8 text-sm" />
          <CommandList>
            <CommandEmpty>
              <div className="text-muted-foreground py-3 text-center text-sm">{t('nodeModal.countryNotFound')}</div>
            </CommandEmpty>
            <CommandItem value={NONE_VALUE} keywords={[t('nodeModal.countryNone')]} onSelect={() => select(null)} className="flex items-center gap-2">
              <span className="text-muted-foreground flex-1 truncate">{t('nodeModal.countryNone')}</span>
              {!selected && <Check className="text-primary h-3 w-3" />}
            </CommandItem>
            {options.map(option => (
              <CommandItem key={option.code} value={option.code} keywords={[option.name, getCountryName(option.code, 'en')]} onSelect={() => select(option.code)} className="flex items-center gap-2">
                <CountryFlag code={option.code} />
                <span className="flex-1 truncate">{option.name}</span>
                {selected === option.code && <Check className="text-primary h-3 w-3" />}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
