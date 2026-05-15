'use client'
import { Language } from '@/components/common/language'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/components/ui/sidebar'
import { type AdminDetails } from '@/service/api'
import { clearAuthSession } from '@/utils/authSession'
import { formatBytes } from '@/utils/formatByte'
import { ChartNoAxesColumn, ChartPie, ChevronsUpDown, LogOut, UserCircle, UserRound, UserRoundKey, UsersIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

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

  const handleLogout = async (e: React.MouseEvent) => {
    e.preventDefault()
    await clearAuthSession()
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
            <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground pl-3">
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
                  <div className="text-muted-foreground flex items-center gap-2 text-xs">
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
          <DropdownMenuContent className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg" side={'bottom'} align="end" sideOffset={4}>
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
                  <div className="text-muted-foreground flex flex-col gap-1 text-xs">
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
