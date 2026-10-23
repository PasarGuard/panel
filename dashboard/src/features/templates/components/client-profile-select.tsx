import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from 'react-i18next'
import { useClientProfileOptions } from './use-client-profile-options'

const NONE_VALUE = 'none'

interface ClientProfileSelectProps {
  value: number | null | undefined
  onChange: (value: number | null) => void
  /** Load the list only while the surrounding dialog is open. */
  enabled?: boolean
  disabled?: boolean
  /** Label of the empty option; defaults to "No profile". */
  noneLabel?: string
}

export function ClientProfileSelect({ value, onChange, enabled = true, disabled, noneLabel }: ClientProfileSelectProps) {
  const { t } = useTranslation()
  const { profiles, isLoading } = useClientProfileOptions(enabled)
  const current = value == null ? NONE_VALUE : String(value)
  const hasCurrent = current === NONE_VALUE || profiles.some(profile => String(profile.id) === current)

  return (
    <Select value={current} onValueChange={next => onChange(next === NONE_VALUE ? null : Number(next))} disabled={disabled || isLoading}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE_VALUE}>{noneLabel ?? t('clientProfiles.none', { defaultValue: 'No profile (default settings)' })}</SelectItem>
        {!hasCurrent && <SelectItem value={current}>{`#${current}`}</SelectItem>}
        {profiles.map(profile => (
          <SelectItem key={profile.id} value={String(profile.id)}>
            {profile.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
