import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { fetcher } from '@/service/http'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fingerprint, Loader2, RefreshCw, Trash2, Users } from 'lucide-react'
import { useState, type ComponentType } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

type HWIDDevice = {
  id: number
  user_id: number
  username?: string
  hwid_hash: string
  device_os?: string
  os_version?: string
  device_model?: string
  user_agent?: string
  request_ip?: string
  first_seen_at: string
  last_seen_at: string
}

type HWIDListResponse = {
  items: HWIDDevice[]
  total: number
}

type HWIDStatsResponse = {
  total_devices: number
  users_with_devices: number
}

type SettingsResponse = {
  subscription?: {
    hwid_device_limit_enabled?: boolean
    hwid_fallback_device_limit?: number
  }
}

function StatTile({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: ComponentType<{ className?: string }>
  label: string
  value: number
  loading: boolean
}) {
  return (
    <div className="flex gap-3 rounded-xl border border-border/80 bg-muted/20 p-4 shadow-sm">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {loading ? (
          <Skeleton className="mt-1 h-8 w-16" />
        ) : (
          <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
        )}
      </div>
    </div>
  )
}

export default function SettingsHWIDPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [userIdFilter, setUserIdFilter] = useState<string>('')
  const [newDeviceUserId, setNewDeviceUserId] = useState('')
  const [newDeviceHwid, setNewDeviceHwid] = useState('')

  const listQuery = useQuery({
    queryKey: ['hwid-devices', userIdFilter],
    queryFn: () =>
      fetcher<HWIDListResponse>('/api/hwid/devices', {
        params: userIdFilter ? { user_id: Number.parseInt(userIdFilter, 10) || undefined } : {},
      }),
  })

  const statsQuery = useQuery({
    queryKey: ['hwid-devices-stats'],
    queryFn: () => fetcher<HWIDStatsResponse>('/api/hwid/devices/stats'),
  })
  const settingsQuery = useQuery({
    queryKey: ['settings-hwid-summary'],
    queryFn: () => fetcher<SettingsResponse>('/api/settings'),
  })

  const hwidEnabled = !!settingsQuery.data?.subscription?.hwid_device_limit_enabled
  const fallbackLimit = settingsQuery.data?.subscription?.hwid_fallback_device_limit ?? 0

  const deleteDeviceMutation = useMutation({
    mutationFn: (payload: { user_id: number; hwid_hash: string }) =>
      fetcher('/api/hwid/devices/delete', { method: 'POST', body: payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hwid-devices'] })
      queryClient.invalidateQueries({ queryKey: ['hwid-devices-stats'] })
      toast.success(t('settings.hwid.deviceDeleted', { defaultValue: 'HWID device deleted' }))
    },
    onError: (error: any) => {
      toast.error(t('settings.hwid.deleteFailed', { defaultValue: 'Failed to delete HWID device' }), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const deleteAllMutation = useMutation({
    mutationFn: (payload: { user_id: number }) => fetcher('/api/hwid/devices/delete-all', { method: 'POST', body: payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hwid-devices'] })
      queryClient.invalidateQueries({ queryKey: ['hwid-devices-stats'] })
      toast.success(t('settings.hwid.devicesDeleted', { defaultValue: 'All HWID devices deleted for user' }))
    },
    onError: (error: any) => {
      toast.error(t('settings.hwid.deleteFailed', { defaultValue: 'Failed to delete HWID devices' }), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })
  const addDeviceMutation = useMutation({
    mutationFn: (payload: { user_id: number; hwid: string }) => fetcher('/api/hwid/devices', { method: 'POST', body: payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hwid-devices'] })
      queryClient.invalidateQueries({ queryKey: ['hwid-devices-stats'] })
      queryClient.invalidateQueries({ queryKey: ['settings-hwid-summary'] })
      setNewDeviceHwid('')
      toast.success(t('settings.hwid.deviceAdded', { defaultValue: 'HWID device added' }))
    },
    onError: (error: any) => {
      toast.error(t('settings.hwid.addFailed', { defaultValue: 'Failed to add HWID device' }), {
        description: error?.data?.detail || error?.message || '',
      })
    },
  })

  const devices = listQuery.data?.items || []
  const listLoading = listQuery.isLoading || listQuery.isFetching
  const statsLoading = statsQuery.isLoading || statsQuery.isFetching
  const parsedNewDeviceUserId = Number.parseInt(newDeviceUserId, 10)
  const isValidNewDeviceUserId = Number.isInteger(parsedNewDeviceUserId) && parsedNewDeviceUserId > 0
  const parsedUserIdFilter = Number.parseInt(userIdFilter, 10)
  const isValidUserIdFilter = Number.isInteger(parsedUserIdFilter) && parsedUserIdFilter > 0

  const refetchAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['hwid-devices'] })
    void queryClient.invalidateQueries({ queryKey: ['hwid-devices-stats'] })
    void queryClient.invalidateQueries({ queryKey: ['settings-hwid-summary'] })
  }

  return (
    <div className="w-full space-y-6 px-4 pb-10 pt-1">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">{t('settings.hwid.description', { defaultValue: 'Inspect and manage registered HWID devices' })}</p>
        <Button type="button" variant="outline" size="sm" className="shrink-0 gap-2" onClick={() => refetchAll()} disabled={listLoading || statsLoading}>
          <RefreshCw className={cn('h-4 w-4', (listLoading || statsLoading) && 'animate-spin')} />
          {t('settings.hwid.reload', { defaultValue: 'Refresh' })}
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="border-border/80 shadow-sm lg:col-span-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('settings.hwid.globalConfig', { defaultValue: 'Global HWID Config' })}</CardTitle>
            <CardDescription>{t('settings.hwid.globalConfigHint', { defaultValue: 'Toggle and fallback limit live under Subscription settings.' })}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {settingsQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-32" />
                <Skeleton className="h-6 w-24" />
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-muted-foreground">{t('settings.hwid.globalEnabled', { defaultValue: 'HWID limit enabled' })}</span>
                  <Badge variant={hwidEnabled ? 'default' : 'secondary'}>
                    {hwidEnabled ? t('status.enable', { defaultValue: 'On' }) : t('status.disabled', { defaultValue: 'Off' })}
                  </Badge>
                </div>
                <div className="text-sm">
                  <span className="text-muted-foreground">{t('settings.hwid.globalFallback', { defaultValue: 'Fallback device limit' })}: </span>
                  <span className="font-medium tabular-nums text-foreground">{fallbackLimit}</span>
                </div>
                <Button variant="secondary" size="sm" className="w-full sm:w-auto" onClick={() => navigate('/settings/subscriptions')}>
                  {t('settings.hwid.openSubscriptionsSettings', { defaultValue: 'Open subscription settings' })}
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          <StatTile
            icon={Fingerprint}
            label={t('settings.hwid.totalDevices', { defaultValue: 'Total devices' })}
            value={statsQuery.data?.total_devices ?? 0}
            loading={statsLoading}
          />
          <StatTile
            icon={Users}
            label={t('settings.hwid.usersWithDevices', { defaultValue: 'Users with devices' })}
            value={statsQuery.data?.users_with_devices ?? 0}
            loading={statsLoading}
          />
        </div>
      </div>

      <Card className="border-border/80 shadow-sm">
        <CardHeader>
          <CardTitle>{t('settings.hwid.inspector', { defaultValue: 'HWID Inspector' })}</CardTitle>
          <CardDescription>{t('settings.hwid.inspectorHint', { defaultValue: 'Register a device from a raw HWID (hashed on the server), filter by user, or delete rows.' })}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="rounded-xl border border-dashed border-border/80 bg-muted/15 p-4">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('settings.hwid.addSection', { defaultValue: 'Manual register' })}</p>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
              <div className="grid flex-1 gap-3 sm:grid-cols-2">
                <Input
                  placeholder={t('settings.hwid.addUserId', { defaultValue: 'User ID' })}
                  value={newDeviceUserId}
                  onChange={e => setNewDeviceUserId(e.target.value)}
                  className="font-mono text-sm"
                />
                <Input
                  placeholder={t('settings.hwid.addHwid', { defaultValue: 'Raw HWID value' })}
                  value={newDeviceHwid}
                  onChange={e => setNewDeviceHwid(e.target.value)}
                  className="font-mono text-sm"
                />
              </div>
              <Button
                className="shrink-0 gap-2"
                disabled={!isValidNewDeviceUserId || !newDeviceHwid.trim() || addDeviceMutation.isPending}
                onClick={() =>
                  addDeviceMutation.mutate({
                    user_id: parsedNewDeviceUserId,
                    hwid: newDeviceHwid.trim(),
                  })
                }
              >
                {addDeviceMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {t('settings.hwid.addDevice', { defaultValue: 'Add device' })}
              </Button>
            </div>
          </div>

          <Separator />

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              placeholder={t('settings.hwid.userIdFilter', { defaultValue: 'Filter by user ID' })}
              value={userIdFilter}
              onChange={e => setUserIdFilter(e.target.value)}
              className="max-w-xs font-mono text-sm"
            />
            <Button
              variant="destructive"
              disabled={!isValidUserIdFilter || deleteAllMutation.isPending}
              onClick={() => deleteAllMutation.mutate({ user_id: parsedUserIdFilter })}
            >
              {t('settings.hwid.deleteAllForUser', { defaultValue: 'Delete all for user' })}
            </Button>
          </div>

          <div className="overflow-hidden rounded-xl border border-border/80">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="sticky top-0 z-[1] bg-muted/80 backdrop-blur-sm">
                  <tr className="border-b text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <th className="whitespace-nowrap px-3 py-3">{t('settings.hwid.columns.user', { defaultValue: 'User' })}</th>
                    <th className="whitespace-nowrap px-3 py-3">{t('settings.hwid.columns.username', { defaultValue: 'Username' })}</th>
                    <th className="whitespace-nowrap px-3 py-3">{t('settings.hwid.columns.hwidHash', { defaultValue: 'HWID Hash' })}</th>
                    <th className="min-w-[140px] px-3 py-3">{t('settings.hwid.columns.device', { defaultValue: 'Device' })}</th>
                    <th className="whitespace-nowrap px-3 py-3">{t('settings.hwid.columns.lastSeen', { defaultValue: 'Last Seen' })}</th>
                    <th className="whitespace-nowrap px-3 py-3 text-right">{t('settings.hwid.columns.action', { defaultValue: 'Action' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {listLoading && devices.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-10 text-center text-muted-foreground">
                        <Loader2 className="mx-auto h-6 w-6 animate-spin opacity-60" />
                      </td>
                    </tr>
                  ) : devices.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-12 text-center text-sm text-muted-foreground">
                        {t('settings.hwid.emptyDevices', { defaultValue: 'No devices match this filter.' })}
                      </td>
                    </tr>
                  ) : (
                    devices.map((item, idx) => (
                      <tr
                        key={item.id}
                        className={cn('border-b border-border/60 transition-colors hover:bg-muted/25', idx % 2 === 1 && 'bg-muted/[0.12]')}
                      >
                        <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs">{item.user_id}</td>
                        <td className="max-w-[120px] truncate px-3 py-2.5">{item.username || '—'}</td>
                        <td className="max-w-[200px] px-3 py-2.5 font-mono text-xs">
                          <span className="block truncate" title={item.hwid_hash}>
                            {item.hwid_hash}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground">
                          {[item.device_os, item.os_version, item.device_model].filter(Boolean).join(' · ') || '—'}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted-foreground">{item.last_seen_at}</td>
                        <td className="px-3 py-2.5 text-right">
                          <Button
                            size="sm"
                            variant="destructive"
                            className="h-8"
                            disabled={deleteDeviceMutation.isPending}
                            onClick={() => deleteDeviceMutation.mutate({ user_id: item.user_id, hwid_hash: item.hwid_hash })}
                          >
                            <Trash2 className="mr-1 h-3.5 w-3.5" />
                            {t('delete', { defaultValue: 'Delete' })}
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
