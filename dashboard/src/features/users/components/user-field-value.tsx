import type { UserListItem } from '@/service/api'
import { formatBytes } from '@/utils/formatByte'
import { dateUtils } from '@/utils/dateFormatter'
import { useTranslation } from 'react-i18next'
import type { UserFieldId } from './user-view-preferences'

/**
 * Format seconds using translated hours for values at least 3600 or at most zero,
 * minutes for values from 60 to under 3600, and seconds for smaller positive values.
 * Counts are rounded to one decimal; a positive seconds count rounded to zero becomes 1.
 * Null or undefined returns an em dash. Errors from the translation callback propagate.
 */
export function formatUserDuration(seconds: number | null | undefined, t: (key: string, options?: { count?: number }) => string) {
  if (seconds == null) return '—'
  if (seconds <= 0 || seconds >= 3600) {
    return t('usersView.durationHours', { count: Math.round((seconds / 3600) * 10) / 10 })
  }
  if (seconds >= 60) {
    return t('usersView.durationMinutes', { count: Math.round((seconds / 60) * 10) / 10 })
  }
  return t('usersView.durationSeconds', { count: Math.round(seconds * 10) / 10 || 1 })
}

export function UserFieldValue({ user, field, groupNames }: { user: UserListItem; field: UserFieldId; groupNames?: ReadonlyMap<number, string> }) {
  const { t } = useTranslation()
  const unlimited = t('usersView.unlimited')
  const date = (value: string | number | null | undefined) => (value ? dateUtils.toDayjs(value).format('YYYY/MM/DD HH:mm') : '—')
  const bytes = (value: number | null | undefined) => (value == null ? '—' : formatBytes(value))
  const duration = (seconds: number | null | undefined) => formatUserDuration(seconds, t)
  switch (field) {
    case 'created_at':
      return <span dir="ltr">{date(user.created_at)}</span>
    case 'edit_at':
      return <span dir="ltr">{date(user.edit_at)}</span>
    case 'remaining_traffic':
      return <span dir="ltr">{user.data_limit ? bytes(Math.max(0, user.data_limit - user.used_traffic)) : unlimited}</span>
    case 'groups':
      return <span className="break-words whitespace-normal">{user.group_ids?.map(id => groupNames?.get(id) || `#${id}`).join(', ') || '—'}</span>
    case 'note':
      return (
        <span className="line-clamp-2 max-w-64 break-words whitespace-pre-wrap" title={user.note || undefined}>
          {user.note || '—'}
        </span>
      )
    case 'hwid_count':
      return <span>{user.hwid_count ?? '—'}</span>
    case 'hwid_limit':
      return <span>{user.hwid_limit == null ? t('default') : user.hwid_limit === 0 ? unlimited : user.hwid_limit}</span>
    case 'data_limit_reset_strategy':
      return <span>{user.data_limit_reset_strategy ? t(`usersView.reset.${user.data_limit_reset_strategy}`) : '—'}</span>
    case 'on_hold_timeout':
      return <span dir="ltr">{date(user.on_hold_timeout)}</span>
    case 'on_hold_expire_duration':
      return <span>{duration(user.on_hold_expire_duration)}</span>
    case 'auto_delete_in_days':
      return (
        <span>{user.auto_delete_in_days == null ? t('default') : user.auto_delete_in_days < 0 ? t('usersView.reset.no_reset') : t('usersView.durationDays', { count: user.auto_delete_in_days })}</span>
      )
    case 'next_plan':
      return user.next_plan ? (
        <span className="flex flex-wrap gap-x-2 text-xs">
          {user.next_plan.user_template_id != null && (
            <span>
              {t('usersView.template')} #{user.next_plan.user_template_id}
            </span>
          )}
          <span>
            {user.next_plan.user_template_id == null && user.next_plan.data_limit != null
              ? user.next_plan.data_limit
                ? bytes(user.next_plan.data_limit)
                : unlimited
              : '—'}
          </span>
          <span>
            {user.next_plan.user_template_id != null
              ? '—'
              : user.next_plan.expire
                ? duration(user.next_plan.expire)
                : unlimited}
          </span>
        </span>
      ) : (
        <span>—</span>
      )
  }
}
