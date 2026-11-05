import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  Settings2,
  UsersRound,
  Gauge,
  CalendarDays,
  RotateCcw,
  Fingerprint,
  ToggleLeft,
  Layers,
  UserCog,
  StickyNote,
  Repeat,
  Timer,
  AlarmClock,
  Trash2,
  ShieldCheck,
} from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import { hasScopeAll } from '@/utils/rbac'
import { formatBytes } from '@/utils/formatByte'
import {
  bulkEditUsers,
  previewBulkEditUsers,
  useGetGroupsSimple,
  useGetAdminsSimple,
  useGetUserTemplatesSimple,
  type BulkUsersEdit,
  type BulkUsersEditResult,
  type BulkUserEditFilter,
} from '@/service/api'
import { BulkEditField } from '../components/bulk-edit-field'
import { bulkEditFields, buildBulkEditRequest, createBulkEditDraft, type BulkEditFieldName, type BulkEditFieldValue, type BulkEditOperation } from '../forms/bulk-edit-form'

const fieldIcons = {
  data_limit: Gauge,
  expire: CalendarDays,
  data_limit_reset_strategy: RotateCcw,
  hwid_limit: Fingerprint,
  status: ToggleLeft,
  groups: Layers,
  owner: UserCog,
  note: StickyNote,
  next_plan: Repeat,
  on_hold_expire_duration: Timer,
  on_hold_timeout: AlarmClock,
  auto_delete_in_days: Trash2,
  shadowsocks_method: ShieldCheck,
}

interface Props {
  initialScope: 'selected' | 'matching'
  userIds: number[]
  pageIds: number[]
  filters: BulkUserEditFilter
  total: number
  onClose: () => void
  onSuccess: () => void
}

/** Guide scoped bulk editing through field selection, preview and explicit confirmation. */
export default function BulkEditUsersModal({ initialScope, userIds, pageIds, filters, total, onClose, onSuccess }: Props) {
  const { t, i18n } = useTranslation()
  const dir = useDirDetection()
  const { admin } = useAdmin()
  const [scope, setScope] = useState(initialScope === 'selected' && userIds.length ? 'selected' : 'matching')
  const [draft, setDraft] = useState(createBulkEditDraft)
  const [preview, setPreview] = useState<BulkUsersEditResult | null>(null)
  const [request, setRequest] = useState<BulkUsersEdit | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const canSetOwner = hasScopeAll(admin, 'users', 'set_owner')
  const { data: groups, isError: groupsError } = useGetGroupsSimple({ all: true })
  const { data: admins, isError: adminsError } = useGetAdminsSimple({ all: true }, { query: { enabled: canSetOwner } })
  const { data: templates, isError: templatesError } = useGetUserTemplatesSimple({ all: true })
  const selectedFields = bulkEditFields.filter(name => draft[name].operation !== 'keep')
  const count = scope === 'selected' ? userIds.length : scope === 'page' ? pageIds.length : total
  const change = (name: BulkEditFieldName, values: Partial<BulkEditFieldValue>) => {
    setDraft(previous => ({ ...previous, [name]: { ...previous[name], ...values } }))
    setError('')
  }
  const showError = (failure: unknown) => {
    const detail = (failure as { data?: { detail?: unknown }; message?: string })?.data?.detail
    setError(
      typeof detail === 'object' && detail !== null && 'errors' in detail
        ? (detail as { errors: { username: string; detail: string }[] }).errors.map(item => `${item.username}: ${item.detail}`).join('; ')
        : typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map(item => item.msg).join('; ')
            : t((failure as Error)?.message?.startsWith('bulkEdit.') ? (failure as Error).message : 'bulkEdit.failed'),
    )
  }
  const previewChanges = async () => {
    setError('')
    setPending(true)
    try {
      const body = buildBulkEditRequest(draft, scope === 'matching' ? { filters } : { ids: scope === 'page' ? pageIds : userIds })
      const response = await previewBulkEditUsers(body)
      setRequest(body)
      setPreview(response)
      setConfirmed(false)
    } catch (failure) {
      showError(failure)
    } finally {
      setPending(false)
    }
  }
  const applyChanges = async () => {
    if (!preview || !request || !confirmed) return
    setPending(true)
    setError('')
    try {
      const response = await bulkEditUsers({ ...request, preview_revision: preview.revision })
      if (response.sync_pending) toast.warning(t('bulkEdit.syncPending'))
      else toast.success(t('bulkEdit.success', { count: response.changed_users }))
      onSuccess()
      onClose()
    } catch (failure) {
      showError(failure)
      setConfirmed(false)
      // Every failure requires a fresh preview before another write can be attempted.
      setPreview(null)
    } finally {
      setPending(false)
    }
  }
  const options = (name: BulkEditFieldName, values: string[], labels?: string[]) => (
    <Select dir={dir} value={draft[name].value || undefined} onValueChange={value => change(name, { value })}>
      <SelectTrigger aria-label={t(`bulkEdit.fields.${name}`)}>
        <SelectValue placeholder={t('bulkEdit.choose')} />
      </SelectTrigger>
      <SelectContent>
        {values.map((value, index) => (
          <SelectItem key={value} value={value}>
            {labels?.[index] || value}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
  const input = (name: BulkEditFieldName, type = 'number', unit?: string) => (
    <div className="flex items-center gap-3">
      <Input
        type={type}
        className="bg-background"
        min={type === 'number' ? 0 : undefined}
        step={name === 'hwid_limit' || name === 'auto_delete_in_days' ? 1 : 'any'}
        aria-label={t(`bulkEdit.fields.${name}`)}
        value={draft[name].value}
        onChange={event => change(name, { value: event.target.value })}
      />
      {unit && <span className="text-muted-foreground shrink-0 text-sm">{unit}</span>}
    </div>
  )
  const row = (name: BulkEditFieldName, children: React.ReactNode, operations: BulkEditOperation[] = ['set'], description?: string, clearLabel?: string) => (
    <BulkEditField
      icon={fieldIcons[name]}
      label={t(`bulkEdit.fields.${name}`)}
      operation={draft[name].operation}
      operations={operations}
      description={description}
      clearLabel={clearLabel}
      onChange={operation => change(name, { operation, value: name === 'expire' ? '' : draft[name].value })}
    >
      {children}
    </BulkEditField>
  )
  const groupChoices = (remove = false) => {
    const key = remove ? 'removeIds' : 'ids'
    const oppositeKey = remove ? 'ids' : 'removeIds'
    return (
      <div className="bg-background grid max-h-40 gap-2 overflow-auto rounded-lg border p-3 sm:grid-cols-2">
        {groupsError && (
          <p role="alert" className="text-destructive text-sm">
            {t('bulkEdit.loadFailed')}
          </p>
        )}
        {(groups?.groups || []).map(group => (
          <Label key={group.id} className="flex cursor-pointer items-center gap-2 font-normal">
            <Checkbox
              checked={draft.groups[key].includes(group.id)}
              onCheckedChange={checked =>
                change('groups', {
                  [key]: checked ? [...draft.groups[key], group.id] : draft.groups[key].filter(id => id !== group.id),
                  [oppositeKey]: draft.groups[oppositeKey].filter(id => id !== group.id),
                })
              }
            />
            {group.name}
          </Label>
        ))}
        {!groups?.groups.length && !groupsError && <p className="text-muted-foreground text-sm">{t('bulkEdit.noOptions')}</p>}
      </div>
    )
  }
  const display = (field: string, value: unknown): string => {
    if (value === null) return t(field === 'data_limit' || field === 'expire' ? 'bulkEdit.unlimited' : 'bulkEdit.empty')
    if (field === 'data_limit' && typeof value === 'number') return formatBytes(value)
    if (field === 'data_limit_reset_strategy') {
      const labels: Record<string, string> = { no_reset: 'resetStrategyNo', day: 'resetStrategyDaily', week: 'resetStrategyWeekly', month: 'resetStrategyMonthly', year: 'resetStrategyAnnually' }
      return t(`userDialog.${labels[String(value)]}`)
    }
    if (field === 'auto_delete_in_days' && typeof value === 'number') return `${value} ${t('bulkEdit.days')}`
    if (field === 'group_ids' && Array.isArray(value)) return value.map(id => groups?.groups.find(group => group.id === id)?.name || `#${id}`).join(', ') || t('bulkEdit.empty')
    if ((field === 'expire' || field === 'on_hold_timeout') && typeof value === 'string') return new Date(value).toLocaleString(i18n.resolvedLanguage)
    if (field === 'on_hold_expire_duration' && typeof value === 'number') return `${value / 86400} ${t('bulkEdit.days')}`
    if (field === 'next_plan' && typeof value === 'object') {
      const plan = value as { user_template_id?: number; data_limit?: number; expire?: number; add_remaining_traffic?: boolean }
      const label = plan.user_template_id
        ? templates?.templates.find(item => item.id === plan.user_template_id)?.name || `#${plan.user_template_id}`
        : `${plan.data_limit ? formatBytes(plan.data_limit) : t('bulkEdit.unlimited')} / ${plan.expire ? `${plan.expire / 86400} ${t('bulkEdit.days')}` : t('bulkEdit.unlimited')}`
      return plan.add_remaining_traffic ? `${label} / ${t('bulkEdit.addRemaining')}` : label
    }
    if (typeof value === 'object') return String(value)
    if (field === 'status') return t(`status.${value}`, { defaultValue: String(value) })
    return String(value)
  }
  return (
    <Dialog
      open
      onOpenChange={open => {
        if (!open && !pending) onClose()
      }}
    >
      <DialogContent
        dir={dir}
        className="border-border/60 flex max-h-[92dvh] w-[calc(100%-2rem)] max-w-3xl flex-col gap-0 overflow-hidden rounded-xl p-0 shadow-2xl sm:rounded-2xl"
        onInteractOutside={event => {
          if (pending) event.preventDefault()
        }}
        onEscapeKeyDown={event => {
          if (pending) event.preventDefault()
        }}
      >
        <DialogHeader className="bg-muted/20 border-b px-5 py-5 sm:px-7 sm:py-6">
          <div className="text-primary mb-2 flex items-center gap-2 text-xs font-medium">
            <Settings2 aria-hidden className="h-4 w-4" />
            {t('users')}
          </div>
          <DialogTitle className="text-xl sm:text-2xl">{t(preview ? 'bulkEdit.reviewTitle' : 'bulkEdit.title')}</DialogTitle>
          <DialogDescription>{t(preview ? 'bulkEdit.reviewDescription' : 'bulkEdit.description')}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-7 sm:py-6">
          {error && (
            <p role="alert" className="text-destructive border-destructive/30 mb-4 rounded-md border p-3 text-sm">
              {error}
            </p>
          )}
          {!preview ? (
            <fieldset disabled={pending} className="min-w-0 space-y-5">
              <div className="bg-muted/50 flex flex-wrap items-center justify-between gap-3 rounded-lg p-4">
                <div>
                  <p className="flex items-center gap-2 text-base font-semibold">
                    <UsersRound aria-hidden className="text-primary h-5 w-5" />
                    {t('bulkEdit.targetCount', { count })}
                  </p>
                  <p className="text-muted-foreground text-xs">{t('bulkEdit.accessScope')}</p>
                </div>
                <Select dir={dir} value={scope} onValueChange={setScope}>
                  <SelectTrigger aria-label={t('bulkEdit.selection')} className="w-full sm:w-64">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {!!userIds.length && <SelectItem value="selected">{t('bulkEdit.selected', { count: userIds.length })}</SelectItem>}
                    {!!pageIds.length && <SelectItem value="page">{t('bulkEdit.page', { count: pageIds.length })}</SelectItem>}
                    <SelectItem value="matching">{t('bulkEdit.matching', { count: total })}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Tabs dir={dir} defaultValue="limits">
                <TabsList className="bg-muted/25 grid h-12 w-full grid-cols-3 gap-1 rounded-xl border p-1">
                  <TabsTrigger className="data-[state=active]:text-primary h-10 gap-2 rounded-lg px-1 text-xs data-[state=active]:font-semibold sm:px-3 sm:text-sm" value="limits">
                    <Gauge aria-hidden className="hidden h-4 w-4 sm:block" />
                    {t('bulkEdit.limits')}
                  </TabsTrigger>
                  <TabsTrigger className="data-[state=active]:text-primary h-10 gap-2 rounded-lg px-1 text-xs data-[state=active]:font-semibold sm:px-3 sm:text-sm" value="access">
                    <Layers aria-hidden className="hidden h-4 w-4 sm:block" />
                    {t('bulkEdit.access')}
                  </TabsTrigger>
                  <TabsTrigger className="data-[state=active]:text-primary h-10 gap-2 rounded-lg px-1 text-xs data-[state=active]:font-semibold sm:px-3 sm:text-sm" value="advanced">
                    <Settings2 aria-hidden className="hidden h-4 w-4 sm:block" />
                    {t('bulkEdit.advanced')}
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="limits" className="mt-4 overflow-hidden rounded-xl border">
                  {row('data_limit', input('data_limit', 'number', 'GB'), ['set', 'add', 'subtract', 'clear'], t('bulkEdit.relativeTraffic'), t('bulkEdit.unlimited'))}
                  {row(
                    'expire',
                    input('expire', draft.expire.operation === 'set' ? 'datetime-local' : 'number', draft.expire.operation === 'set' ? undefined : t('bulkEdit.days')),
                    ['set', 'add', 'subtract', 'clear'],
                    t('bulkEdit.relativeExpire'),
                    t('bulkEdit.unlimited'),
                  )}
                  {row(
                    'data_limit_reset_strategy',
                    options(
                      'data_limit_reset_strategy',
                      ['no_reset', 'day', 'week', 'month', 'year'],
                      ['resetStrategyNo', 'resetStrategyDaily', 'resetStrategyWeekly', 'resetStrategyMonthly', 'resetStrategyAnnually'].map(value => t(`userDialog.${value}`)),
                    ),
                  )}
                  {row('hwid_limit', input('hwid_limit'), ['set', 'clear'], t('bulkEdit.hwidHint'), t('bulkEdit.useDefault'))}
                </TabsContent>
                <TabsContent value="access" className="mt-4 overflow-hidden rounded-xl border">
                  {row(
                    'status',
                    options(
                      'status',
                      ['active', 'disabled', 'on_hold'],
                      ['active', 'disabled', 'on_hold'].map(value => t(`status.${value}`, { defaultValue: value })),
                    ),
                    ['set'],
                    t('bulkEdit.statusHint'),
                  )}
                  {row(
                    'groups',
                    <div className="space-y-3">
                      {groupChoices()}
                      {draft.groups.operation === 'add' && (
                        <>
                          <p className="text-sm font-medium">{t('bulkEdit.removeGroups')}</p>
                          {groupChoices(true)}
                        </>
                      )}
                    </div>,
                    ['set', 'add', 'remove', 'clear'],
                  )}
                  {canSetOwner &&
                    row(
                      'owner',
                      <>
                        {options(
                          'owner',
                          (admins?.admins || []).map(item => item.username),
                        )}
                        {adminsError && (
                          <p role="alert" className="text-destructive text-sm">
                            {t('bulkEdit.loadFailed')}
                          </p>
                        )}
                      </>,
                    )}
                  {row('note', <Textarea aria-label={t('bulkEdit.fields.note')} maxLength={500} value={draft.note.value} onChange={event => change('note', { value: event.target.value })} />, [
                    'set',
                    'clear',
                  ])}
                </TabsContent>
                <TabsContent value="advanced" className="mt-4 overflow-hidden rounded-xl border">
                  {row(
                    'next_plan',
                    <div className="space-y-3">
                      {options(
                        'next_plan',
                        ['custom', ...(templates?.templates || []).map(item => String(item.id))],
                        [t('bulkEdit.customPlan'), ...(templates?.templates || []).map(item => item.name || `#${item.id}`)],
                      )}
                      {templatesError && (
                        <p role="alert" className="text-destructive text-sm">
                          {t('bulkEdit.loadFailed')}
                        </p>
                      )}
                      {draft.next_plan.value === 'custom' && (
                        <div className="grid gap-3 sm:grid-cols-2">
                          <Label className="space-y-2">
                            {t('bulkEdit.planTraffic')}
                            <Input type="number" min={0} step="any" value={draft.next_plan.planTraffic} onChange={event => change('next_plan', { planTraffic: event.target.value })} />
                          </Label>
                          <Label className="space-y-2">
                            {t('bulkEdit.planDays')}
                            <Input type="number" min={0} step="any" value={draft.next_plan.planDays} onChange={event => change('next_plan', { planDays: event.target.value })} />
                          </Label>
                        </div>
                      )}
                      <Label className="flex items-center gap-2 font-normal">
                        <Checkbox checked={draft.next_plan.addRemaining} onCheckedChange={checked => change('next_plan', { addRemaining: checked === true })} />
                        {t('bulkEdit.addRemaining')}
                      </Label>
                    </div>,
                    ['set', 'clear'],
                  )}
                  {row('on_hold_expire_duration', input('on_hold_expire_duration', 'number', t('bulkEdit.days')), ['set', 'clear'])}
                  {row('on_hold_timeout', input('on_hold_timeout', 'datetime-local'), ['set', 'clear'])}
                  {row('auto_delete_in_days', input('auto_delete_in_days', 'number', t('bulkEdit.days')), ['set', 'clear'])}
                  {row('shadowsocks_method', options('shadowsocks_method', ['aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305', 'xchacha20-poly1305']), ['set'], t('bulkEdit.proxyHint'))}
                </TabsContent>
              </Tabs>
            </fieldset>
          ) : (
            <div className="space-y-5">
              <div className="bg-muted/50 grid grid-cols-3 gap-3 rounded-lg p-4">
                {(['affected_users', 'changed_users', 'unchanged_users'] as const).map(key => (
                  <div key={key} className="px-3 first:ps-0">
                    <p className="text-2xl font-semibold tabular-nums sm:text-3xl">{preview[key].toLocaleString()}</p>
                    <p className="text-muted-foreground text-xs">{t(`bulkEdit.${key}`)}</p>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {selectedFields.map(name => (
                  <span key={name} className="border-primary/15 bg-primary/5 text-primary rounded-full border px-3 py-1 text-xs">
                    {t(`bulkEdit.fields.${name}`)} · {t(`bulkEdit.operations.${draft[name].operation}`)}
                  </span>
                ))}
              </div>
              {!!preview.relative_skipped_users && <p className="text-muted-foreground text-sm">{t('bulkEdit.skipped', { count: preview.relative_skipped_users })}</p>}
              {!!preview.error_count && (
                <div role="alert" className="border-destructive/40 space-y-2 rounded-lg border p-4 text-sm">
                  <p className="text-destructive font-medium">{t('bulkEdit.blocked', { count: preview.error_count })}</p>
                  {preview.errors.map(item => (
                    <p key={item.id}>
                      <strong>{item.username}</strong>: {item.detail}
                    </p>
                  ))}
                </div>
              )}
              <div className="space-y-3">
                <p className="text-muted-foreground text-sm">{t('bulkEdit.samples', { count: preview.samples.length })}</p>
                {preview.samples.map(sample => (
                  <div key={sample.id} className="overflow-hidden rounded-lg border">
                    <p className="bg-muted/20 flex items-center gap-2 border-b px-4 py-3 font-semibold">
                      <UserCog aria-hidden className="text-primary h-4 w-4" />
                      {sample.username}
                    </p>
                    <div className="space-y-2 p-4">
                      {Object.entries(sample.changes).map(([field, value]) => (
                        <div key={field} className="border-border/40 grid gap-1 border-b pb-2 text-sm last:border-0 last:pb-0 sm:grid-cols-[150px_1fr]">
                          <span className="text-muted-foreground">{t(`bulkEdit.fields.${field === 'group_ids' ? 'groups' : field}`)}</span>
                          <span className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="text-muted-foreground break-all">{display(field, value.before)}</span>
                            <ArrowRight aria-hidden className="h-3 w-3 shrink-0 rtl:rotate-180" />
                            <span className="font-medium break-all">{display(field, value.after)}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="bg-muted/15 border-t px-4 py-4 sm:px-7">
          {preview && !preview.error_count && preview.changed_users > 0 && (
            <Label className="mb-4 flex items-start gap-3 text-sm leading-relaxed">
              <Checkbox disabled={pending} checked={confirmed} onCheckedChange={checked => setConfirmed(checked === true)} className="mt-0.5" />
              {t('bulkEdit.confirm', { count: preview.changed_users })}
            </Label>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button
              variant="outline"
              disabled={pending}
              onClick={() => {
                if (preview) {
                  setPreview(null)
                  setConfirmed(false)
                } else onClose()
              }}
            >
              {preview && <ArrowLeft className="me-2 h-4 w-4 rtl:rotate-180" />}
              {t(preview ? 'bulkEdit.back' : 'cancel')}
            </Button>
            <div className="flex items-center gap-3">
              {!preview && <span className="bg-primary/10 text-primary rounded-full px-2.5 py-1 text-xs font-medium">{t('bulkEdit.fieldCount', { count: selectedFields.length })}</span>}
              <Button
                disabled={pending || (preview ? !confirmed || !!preview.error_count || !preview.changed_users : !selectedFields.length || !count)}
                onClick={preview ? applyChanges : previewChanges}
              >
                {pending ? <Loader2 className="me-2 h-4 w-4 animate-spin" /> : preview ? <Check className="me-2 h-4 w-4" /> : null}
                {t(preview ? 'bulkEdit.apply' : 'bulkEdit.preview')}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
