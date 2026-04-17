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
import { removeAuthToken } from '@/utils/authStorage'
import { queryClient } from '@/utils/query-client'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { Language } from '@/components/common/language'

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
                <UserCircle className="h-4 w-4 text-sidebar-foreground" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-3" side="right" align="start">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <UserCircle className="h-4 w-4 text-primary" />
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{username.name}</span>
                    {admin && (
                      <Badge variant={admin.is_sudo ? 'secondary' : 'outline'} className="h-4 px-1 py-0 text-[10px]">
                        {admin.is_sudo ? (
                          <>
                            <UserRoundKey className="mr-1 size-3" />
                            {t('sudo')}
                          </>
                        ) : (
                          <>
                            <UserRound className="mr-1 size-3" />
                            {t('admin')}
                          </>
                        )}
                      </Badge>
                    )}
                  </div>
                </div>

                {admin && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{t('admins.used.traffic')}</span>
                      <span className="font-medium">
                        <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                          {formatBytes(admin?.used_traffic || 0)}
                        </span>
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{t('statistics.totalUsage')}</span>
                      <span className="font-medium">
                        <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                          {formatBytes(admin?.lifetime_used_traffic || 0)}
                        </span>
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{t('admins.total.users')}</span>
                      <span className="font-medium">{admin?.total_users || 0}</span>
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
            <SidebarMenuButton size="lg" className="pl-3 data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground">
              <div className="grid flex-1 text-left text-sm leading-tight">
                <div className="flex items-center gap-2">
                  <span className="truncate font-semibold">{username.name}</span>
                  {admin && (
                    <Badge variant={admin.is_sudo ? 'secondary' : 'outline'} className="hidden h-4 px-1 py-0 text-[10px] lg:hidden">
                      {admin.is_sudo ? (
                        <>
                          <UserRoundKey className="mr-1 size-3" />
                          {t('sudo')}
                        </>
                      ) : (
                        <>
                          <UserRound className="mr-1 size-3" />
                          {t('admin')}
                        </>
                      )}
                    </Badge>
                  )}
                </div>
                {admin && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <ChartPie className="size-3" />
                    <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                      {formatBytes(admin?.used_traffic || 0)}
                    </span>
                  </div>
                )}
              </div>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg" side={'bottom'} align="end" sideOffset={4}>
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex flex-col gap-2 px-1 py-1.5 text-left text-sm">
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold">{username.name}</span>
                    {admin && (
                      <Badge variant={admin.is_sudo ? 'secondary' : 'outline'} className="flex h-4 items-center gap-2 py-0 text-[10px]">
                        {admin.is_sudo ? (
                          <>
                            <UserRoundKey className="size-3" />
                            <span>{t('sudo')}</span>
                          </>
                        ) : (
                          <>
                            <UserRound className="size-3" />
                            <span>{t('admin')}</span>
                          </>
                        )}
                      </Badge>
                    )}
                  </div>
                </div>
                {admin && (
                  <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <ChartPie className="size-3" />
                      <span>
                        {t('admins.used.traffic')}:{' '}
                        <span dir="ltr" style={{ unicodeBidi: 'isolate' }}>
                          {formatBytes(admin?.used_traffic || 0)}
                        </span>
                      </span>
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
                    <div className="flex items-center gap-2">
                      <UsersIcon className="size-3" />
                      <span>
                        {t('admins.total.users')}: {admin?.total_users || 0}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} className="cursor-pointer text-destructive focus:text-destructive">
              <LogOut className="mr-2 size-4" />
              {t('header.logout')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
