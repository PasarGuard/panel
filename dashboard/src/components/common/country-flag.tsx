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
  const name = getCountryName(normalized, i18n.language)

  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 text-xs', className)} title={`${name} (${normalized})`} dir="ltr">
      {hasFlag && <span aria-hidden="true">{getCountryFlag(normalized)}</span>}
      {(showCode || !hasFlag) && <span className="text-muted-foreground font-mono">{normalized}</span>}
      {/* The emoji is aria-hidden and title is not read out, so give screen readers the name */}
      {hasFlag && !showCode && <span className="sr-only">{name}</span>}
    </span>
  )
}
