import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { useAdmin } from '@/hooks/use-admin'
import { MyHostsPolicy, getGetMyHostsPolicyQueryKey, getGetMyHostsQueryKey } from '@/service/api'
import { isOwner } from '@/utils/rbac'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowUpDown, EyeOff, Pencil, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsContext } from './_dashboard.settings'

const defaults: MyHostsPolicy = { enabled: false, allow_rename: true, allow_reorder: true, allow_disable: true }

export default function MyHostsSettings() {
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()
  const [policy, setPolicy] = useState<MyHostsPolicy>(defaults)
  const [dirty, setDirty] = useState(false)
  const queryClient = useQueryClient()
  useEffect(() => {
    if (!dirty) setPolicy(settings.general?.my_hosts || defaults)
  }, [settings, dirty])
  if (!isOwner(admin)) return <p className="p-4">{t('permissionDenied')}</p>
  if (isLoading) return <Skeleton className="m-4 h-64" />
  if (error)
    return (
      <p role="alert" className="p-4">
        {t('myHosts.loadFailed')}
      </p>
    )
  const save = async () => {
    try {
      await updateSettings({ general: { ...settings.general, my_hosts: policy } })
      await queryClient.invalidateQueries({ queryKey: getGetMyHostsPolicyQueryKey() })
      await queryClient.invalidateQueries({ queryKey: getGetMyHostsQueryKey() })
      setDirty(false)
    } catch {
      /* Settings context displays the API error. */
    }
  }
  return (
    <div className="max-w-4xl space-y-6 p-4 py-6">
      <div className="bg-muted/40 flex gap-3 rounded-lg border p-4">
        <ShieldCheck className="text-primary mt-0.5 h-5 w-5 shrink-0" />
        <div className="space-y-1">
          <h2 className="font-semibold">{t('myHosts.ownerControl')}</h2>
          <p className="text-muted-foreground text-sm">{t('myHosts.ownerDescription')}</p>
        </div>
      </div>
      <label className="flex items-start justify-between gap-5 rounded-lg border p-5">
        <div className="space-y-1">
          <span className="font-medium">{t('myHosts.enable')}</span>
          <p className="text-muted-foreground text-sm">{t('myHosts.enableDescription')}</p>
        </div>
        <Switch
          checked={policy.enabled}
          disabled={isSaving}
          onCheckedChange={enabled => {
            setPolicy(current => ({ ...current, enabled }))
            setDirty(true)
          }}
          aria-label={t('myHosts.enable')}
        />
      </label>
      <div className="space-y-2">
        <h3 className="font-semibold">{t('myHosts.allowedOperations')}</h3>
        <p className="text-muted-foreground text-sm">{t('myHosts.operationsDescription')}</p>
      </div>
      <div className="divide-y rounded-lg border">
        {(
          [
            { key: 'allow_rename', action: 'rename', icon: Pencil },
            { key: 'allow_reorder', action: 'reorder', icon: ArrowUpDown },
            { key: 'allow_disable', action: 'disable', icon: EyeOff },
          ] as const
        ).map(({ key, action, icon: Icon }) => (
          <label key={key} className="flex items-center justify-between gap-4 p-5">
            <div className="flex items-start gap-3">
              <Icon className="text-muted-foreground mt-0.5 h-4 w-4 shrink-0" />
              <div className="space-y-1">
                <span className="text-sm font-medium">{t(`myHosts.${action}`)}</span>
                <p className="text-muted-foreground text-sm">{t(`myHosts.${action}Description`)}</p>
              </div>
            </div>
            <Switch
              checked={policy[key]}
              disabled={!policy.enabled || isSaving}
              onCheckedChange={value => {
                setPolicy(current => ({ ...current, [key]: value }))
                setDirty(true)
              }}
              aria-label={t(`myHosts.${action}`)}
            />
          </label>
        ))}
      </div>
      <p className="text-muted-foreground text-sm">{t('myHosts.revocation')}</p>
      <div className="flex justify-end gap-2 border-t pt-4">
        <Button
          variant="outline"
          disabled={!dirty || isSaving}
          onClick={() => {
            setPolicy(settings.general?.my_hosts || defaults)
            setDirty(false)
          }}
        >
          {t('myHosts.cancel')}
        </Button>
        <Button disabled={!dirty || isSaving} onClick={save}>
          <Save className="h-4 w-4" />
          {t(isSaving ? 'myHosts.saving' : 'myHosts.save')}
        </Button>
      </div>
    </div>
  )
}
