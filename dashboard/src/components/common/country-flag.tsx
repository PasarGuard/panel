import { cn } from '@/lib/utils'
import { getCountryFlag, getCountryName, normalizeCountryCode } from '@/utils/countries'
import { useTranslation } from 'react-i18next'

interface CountryFlagProps {
  code?: string | null
  className?: string
  showCode?: boolean
}

// Flag emoji plus the code, since Windows renders regional indicators as plain letters
export function CountryFlag({ code, className, showCode = true }: CountryFlagProps) {
  const { i18n } = useTranslation()
  const normalized = normalizeCountryCode(code)
  if (!normalized) return null

  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 text-xs', className)} title={getCountryName(normalized, i18n.language)} dir="ltr">
      <span aria-hidden="true">{getCountryFlag(normalized)}</span>
      {showCode && <span className="text-muted-foreground font-mono">{normalized}</span>}
    </span>
  )
}
