'use client'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useSidebar } from '@/components/ui/sidebar'
import { type AdminDetails } from '@/service/api'
import { ChevronsUpDown, LogOut, UserRoundKey, UsersIcon, UserCircle, ChartPie, ChartNoAxesColumn, UserRound } from 'lucide-react'
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
