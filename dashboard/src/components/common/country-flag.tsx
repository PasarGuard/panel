import { cn } from '@/lib/utils'
import { getCountryFlag, getCountryName, normalizeCountryCode, supportsFlagEmoji } from '@/utils/countries'
import { useTranslation } from 'react-i18next'

interface CountryFlagProps {
  code?: string | null
  className?: string
  showCode?: boolean
}

// Flag emoji (plus the code when asked); platforms without flag glyphs (Windows) get the code alone
export function CountryFlag({ code, className, showCode = true }: CountryFlagProps) {
  const { i18n } = useTranslation()
  const normalized = normalizeCountryCode(code)
  if (!normalized) return null
  const hasFlag = supportsFlagEmoji()

  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 text-xs', className)} title={`${getCountryName(normalized, i18n.language)} (${normalized})`} dir="ltr">
      {hasFlag && <span aria-hidden="true">{getCountryFlag(normalized)}</span>}
      {(showCode || !hasFlag) && <span className="text-muted-foreground font-mono">{normalized}</span>}
    </span>
  )
}
