'use client'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useSidebar } from '@/components/ui/sidebar'
import { type AdminDetails } from '@/service/api'
import { ChevronsUpDown, KeyRound, LogOut, UserRoundKey, UsersIcon, UserCircle, ChartPie, ChartNoAxesColumn, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { formatBytes } from '@/utils/formatByte'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { removeAuthToken } from '@/utils/authStorage'
import { queryClient } from '@/utils/query-client'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { Language } from '@/components/common/language'
import { isOwner, roleLabel } from '@/utils/rbac'
import { statusColors } from '@/constants/UserSettings'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { deleteAdminPasskeyForAdmin, getAdminPasskeyRegistrationOptionsForAdmin, getAdminPasskeysForAdmin, registerAdminPasskeyForAdmin } from '@/service/api'
import { fromBase64Url, serializeCredential } from '@/utils/passkeys'
import { LoaderCircle, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

type EffectiveLimits = {
  dataLimit: number | null
  maxUsers: number | null
}

const getEffectiveLimits = (admin: AdminDetails | null): EffectiveLimits => {
  if (!admin) return { dataLimit: null, maxUsers: null }
  const overrides = admin.permission_overrides ?? null
  const roleLimits = admin.role?.limits ?? null
  const maxUsersOverride = overrides?.max_users
  const maxUsersRole = roleLimits?.max_users
  const maxUsers = maxUsersOverride != null ? maxUsersOverride : maxUsersRole != null ? maxUsersRole : null
  return {
    dataLimit: admin.data_limit ?? null,
    maxUsers,
  }
}

const isLimitActive = (limit: number | null | undefined): limit is number => typeof limit === 'number' && limit > 0

const getProgressPct = (used: number, total: number) => {
  if (total <= 0) return 0
  return Math.min(100, Math.max(0, (used / total) * 100))
}

export function NavUser({
  username,
  admin,
}: {
  username: {
    name: string
  }
  admin: AdminDetails | null
}) {
  const { t } = useTranslation()
  const { state, isMobile } = useSidebar()
  const navigate = useNavigate()
  const RoleIcon = isOwner(admin) ? UserRoundKey : UserRound
  const { dataLimit, maxUsers } = getEffectiveLimits(admin)
  const hasDataLimit = isLimitActive(dataLimit)
  const hasUserLimit = isLimitActive(maxUsers)
  const usedTraffic = admin?.used_traffic ?? 0
  const totalUsers = admin?.total_users ?? 0
  const sliderColor = statusColors[admin?.status ?? 'active']?.sliderColor

  const handleLogout = (e: React.MouseEvent) => {
    e.preventDefault()
    // Cancel all ongoing queries
    queryClient.cancelQueries()
    // Remove auth token
    removeAuthToken()
    // Clear React Query cache
    queryClient.clear()
    // Navigate to login
    navigate('/login', { replace: true })
  }

  // Collapsed state (desktop only) - admin icon with popover
  // On mobile, always use expanded UI since there's no collapsed sidebar concept
  if (state === 'collapsed' && !isMobile) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-md">
                <UserCircle className="text-sidebar-foreground h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-3" side="right" align="start">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <UserCircle className="text-primary h-4 w-4" />
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{username.name}</span>
                    {admin && (
                      <Badge variant={isOwner(admin) ? 'secondary' : 'outline'} className="h-4 px-1 py-0 text-[10px]">
                        <RoleIcon className="mr-1 size-3" />
                        {roleLabel(admin)}
                      </Badge>
                    )}
                  </div>
                </div>

                {admin && (
                  <div className="space-y-2">
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">{t('admins.used.traffic')}</span>
                        <span className="font-medium">
                          <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                            {formatBytes(usedTraffic)}
                            {hasDataLimit ? ` / ${formatBytes(dataLimit)}` : ''}
                          </span>
                        </span>
                      </div>
                      {hasDataLimit && <Progress indicatorClassName={sliderColor} value={getProgressPct(usedTraffic, dataLimit)} className="h-1" />}
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{t('statistics.totalUsage')}</span>
                      <span className="font-medium">
                        <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                          {formatBytes(admin?.lifetime_used_traffic || 0)}
                        </span>
                      </span>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">{t('admins.total.users')}</span>
                        <span className="font-medium">
                          <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                            {totalUsers}
                            {hasUserLimit ? ` / ${maxUsers}` : ''}
                          </span>
                        </span>
                      </div>
                      {hasUserLimit && <Progress indicatorClassName={sliderColor} value={getProgressPct(totalUsers, maxUsers)} className="h-1" />}
                    </div>
                  </div>
                )}

                {/* Theme and Language Controls */}
                <div className="flex gap-1 border-t pt-2">
                  <ThemeToggle />
                  <Language />
                </div>

                {admin?.id != null && <SelfPasskeyDialog admin={admin} compact />}

                <Button variant="destructive" size="sm" onClick={handleLogout} className="mt-2 w-full">
                  <LogOut className="mr-2 h-4 w-4" />
                  {t('header.logout')}
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  // Expanded state - full dropdown
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground pl-3">
              <div className="grid flex-1 text-left text-sm leading-tight">
                <div className="flex items-center gap-2">
                  <span className="truncate font-semibold">{username.name}</span>
                  {admin && (
                    <Badge variant={isOwner(admin) ? 'secondary' : 'outline'} className="hidden h-4 px-1 py-0 text-[10px] lg:hidden">
                      <RoleIcon className="mr-1 size-3" />
                      {roleLabel(admin)}
                    </Badge>
                  )}
                </div>
                {admin && (
                  <div className="text-muted-foreground flex items-center gap-2 text-xs">
                    <ChartPie className="size-3" />
                    <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                      {formatBytes(usedTraffic)}
                      {hasDataLimit ? ` / ${formatBytes(dataLimit)}` : ''}
                    </span>
                  </div>
                )}
              </div>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg" side={'bottom'} align="end" sideOffset={4}>
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex flex-col gap-2 px-1 py-1.5 text-left text-sm">
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold">{username.name}</span>
                    {admin && (
                      <Badge variant={isOwner(admin) ? 'secondary' : 'outline'} className="flex h-4 items-center gap-2 py-0 text-[10px]">
                        <RoleIcon className="size-3" />
                        <span>{roleLabel(admin)}</span>
                      </Badge>
                    )}
                  </div>
                </div>
                {admin && (
                  <div className="text-muted-foreground flex flex-col gap-1 text-xs">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <ChartPie className="size-3" />
                        <span>
                          {t('admins.used.traffic')}:{' '}
                          <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                            {formatBytes(usedTraffic)}
                            {hasDataLimit ? ` / ${formatBytes(dataLimit)}` : ''}
                          </span>
                        </span>
                      </div>
                      {hasDataLimit && <Progress indicatorClassName={sliderColor} value={getProgressPct(usedTraffic, dataLimit)} className={cn('h-1')} />}
                    </div>
                    <div className="flex items-center gap-2">
                      <ChartNoAxesColumn className="size-3" />
                      <span>
                        {t('statistics.totalUsage')}:{' '}
                        <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                          {formatBytes(admin?.lifetime_used_traffic || 0)}
                        </span>
                      </span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <UsersIcon className="size-3" />
                        <span>
                          {t('admins.total.users')}:{' '}
                          <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                            {totalUsers}
                            {hasUserLimit ? ` / ${maxUsers}` : ''}
                          </span>
                        </span>
                      </div>
                      {hasUserLimit && <Progress indicatorClassName={sliderColor} value={getProgressPct(totalUsers, maxUsers)} className={cn('h-1')} />}
                    </div>
                  </div>
                )}
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {admin?.id != null && <SelfPasskeyDialog admin={admin} />}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive cursor-pointer">
              <LogOut className="mr-2 size-4" />
              {t('header.logout')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

function SelfPasskeyDialog({ admin, compact = false }: { admin: AdminDetails; compact?: boolean }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [passkeys, setPasskeys] = useState<Array<{ id: number; name: string }> | null>(null)

  useEffect(() => {
    if (!open || admin.id == null) return
    setPasskeys(null)
    getAdminPasskeysForAdmin(admin.id).then(setPasskeys).catch(() => setPasskeys([]))
  }, [open, admin.id])

  const addPasskey = async () => {
    if (admin.id == null || !window.PublicKeyCredential) {
      toast.error(t('admins.passkeyUnsupported', { defaultValue: 'Passkeys are not supported in this browser.' }))
      return
    }
    setBusy(true)
    try {
      const options: any = await getAdminPasskeyRegistrationOptionsForAdmin(admin.id)
      options.challenge = fromBase64Url(options.challenge)
      options.user.id = fromBase64Url(options.user.id)
      options.excludeCredentials = options.excludeCredentials?.map((item: any) => ({ ...item, id: fromBase64Url(item.id) }))
      const credential = await navigator.credentials.create({ publicKey: options })
      if (!credential) throw new Error('No passkey was created')
      await registerAdminPasskeyForAdmin(admin.id, { credential: serializeCredential(credential) })
      setPasskeys(await getAdminPasskeysForAdmin(admin.id))
      toast.success(t('admins.passkeyAdded', { defaultValue: 'Passkey added successfully' }))
    } catch (error: any) {
      toast.error(t('admins.passkeyAddFailed', { defaultValue: 'Could not add passkey' }), { description: error?.data?.detail || error?.message })
    } finally {
      setBusy(false)
    }
  }

  const removePasskey = async (passkeyId: number) => {
    if (admin.id == null) return
    setBusy(true)
    try {
      await deleteAdminPasskeyForAdmin(admin.id, passkeyId)
      setPasskeys(current => current.filter(passkey => passkey.id !== passkeyId))
      toast.success(t('admins.passkeyRemoved', { defaultValue: 'Passkey removed' }))
    } catch (error: any) {
      toast.error(t('admins.passkeyRemoveFailed', { defaultValue: 'Could not remove passkey' }), { description: error?.data?.detail || error?.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {compact ? (
        <Button type="button" variant="outline" size="sm" className="w-full justify-start" onClick={() => setOpen(true)}>
          <KeyRound className="mr-2 h-4 w-4" />
          {t('admins.manageOwnPasskeys', { defaultValue: 'Manage my passkeys' })}
        </Button>
      ) : (
        <DropdownMenuItem onSelect={event => { event.preventDefault(); setOpen(true) }} className="cursor-pointer">
          <KeyRound className="mr-2 size-4" />
          {t('admins.manageOwnPasskeys', { defaultValue: 'Manage my passkeys' })}
        </DropdownMenuItem>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[calc(100dvh-1rem)] max-w-[calc(100vw-1rem)] overflow-y-auto p-4 sm:max-w-xl sm:p-6">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base sm:text-lg"><KeyRound className="text-primary h-4 w-4" />{t('admins.manageOwnPasskeys', { defaultValue: 'Manage my passkeys' })}</DialogTitle>
            <DialogDescription>{t('admins.passkeySelfServiceHint', { defaultValue: 'Add multiple devices so you can sign in without a password.' })}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-muted/20 flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <ShieldCheck className="h-5 w-5 shrink-0 text-emerald-500" />
                <div>
                  <p className="text-sm font-semibold">{passkeys === null ? '—' : passkeys.length} {t('admins.passkeys', { defaultValue: 'Passkeys' })}</p>
                  <p className="text-muted-foreground text-xs">{t('admins.passkeyReady', { defaultValue: 'Ready for password-free sign-in' })}</p>
                </div>
              </div>
              <Button type="button" size="sm" className="w-full sm:w-auto" onClick={addPasskey} disabled={busy || passkeys === null}>
                {busy ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                {t('admins.addPasskey', { defaultValue: 'Add passkey' })}
              </Button>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between"><p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{t('admins.passkeyDevicesTitle', { defaultValue: 'Sign-in devices' })}</p><span className="text-muted-foreground text-xs">{passkeys?.length ?? '—'}</span></div>
              {passkeys === null ? <div className="grid gap-2 sm:grid-cols-2"><Skeleton className="h-14" /><Skeleton className="h-14" /></div> : passkeys.length > 0 ? <div className="grid gap-2 sm:grid-cols-2">{passkeys.map((passkey, index) => (
                <div key={passkey.id} className="bg-muted/20 group flex min-w-0 items-center justify-between gap-3 rounded-md border p-3 transition-colors hover:bg-muted/40">
                  <div className="flex min-w-0 items-center gap-2.5"><KeyRound className="text-primary h-4 w-4 shrink-0" /><div className="min-w-0"><p className="truncate text-sm font-medium">{passkey.name || `${t('admins.passkey', { defaultValue: 'Passkey' })} ${index + 1}`}</p><p className="text-muted-foreground text-[11px]">{t('admins.passkeyReady', { defaultValue: 'Ready for sign-in' })}</p></div></div>
                  <Button type="button" variant="ghost" size="icon" className="text-muted-foreground hover:text-destructive h-8 w-8 shrink-0 opacity-70 transition-opacity group-hover:opacity-100" onClick={() => removePasskey(passkey.id)} disabled={busy} aria-label={t('remove', { defaultValue: 'Remove' })}><Trash2 className="h-4 w-4" /></Button>
                </div>
              ))}</div> : <div className="text-muted-foreground rounded-md border border-dashed px-4 py-6 text-center text-sm">{t('admins.passkeyEmptyHint', { defaultValue: 'No passkeys have been added yet.' })}</div>}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
