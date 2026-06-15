import { Language } from '@/components/common/language'
import Snowfall from '@/components/common/snowfall'
import { useTheme } from '@/app/providers/theme-provider'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { GithubStar } from '@/components/layout/github-star'
import { GoalProgress } from '@/components/layout/goal-progress'
import { NavMain } from '@/components/layout/nav-main'
import { NavSecondary } from '@/components/layout/nav-secondary'
import { NavUser } from '@/components/layout/nav-user'
import { SidebarTriggerWithBadge } from '@/components/layout/sidebar-trigger-with-badge'
import { VersionBadge } from '@/components/layout/version-badge'
import { Button } from '@/components/ui/button'
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarRail, useSidebar } from '@/components/ui/sidebar'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DISCUSSION_GROUP, DOCUMENTATION, DONATION_URL, REPO_URL } from '@/constants/Project'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import { useSystemVersion } from '@/hooks/use-system-version'
import { useVersionCheck } from '@/hooks/use-version-check'
import { cn } from '@/lib/utils'
import { canReadResourcePage, hasPermission, hasScopeAll, isOwner } from '@/utils/rbac'
import {
  ArrowUpDown,
  Bell,
  BookOpen,
  Calendar,
  ChevronsLeft,
  ChevronsRight,
  Cpu,
  Database,
  FileCode2,
  FileUser,
  Fingerprint,
  GithubIcon,
  Group,
  Key,
  Layers,
  LayoutDashboardIcon,
  LayoutTemplate,
  LifeBuoy,
  ListTodo,
  Lock,
  Logs,
  Network,
  Palette,
  PieChart,
  RssIcon,
  Send,
  Settings,
  Settings2,
  Share2Icon,
  UserCog,
  UserKey,
  UserPlus,
  UsersIcon,
  Webhook,
} from 'lucide-react'
import * as React from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const isRTL = useDirDetection() === 'rtl'
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const canReadSystem = hasPermission(admin, 'system', 'read')
  const canReadHosts = canReadResourcePage(admin, 'hosts')
  const canReadGroups = canReadResourcePage(admin, 'groups')
  const canReadAdmins = canReadResourcePage(admin, 'admins')
  const canReadApiKeys = canReadResourcePage(admin, 'api_keys')
  const canReadNodes = canReadResourcePage(admin, 'nodes')
  const canReadCores = canReadResourcePage(admin, 'cores')
  const canReadTemplates = canReadResourcePage(admin, 'templates')
  const canReadClientTemplates = canReadResourcePage(admin, 'client_templates')
  const canReadNodeLogs = hasPermission(admin, 'nodes', 'logs')
  const canBulkCreateFromTemplate = hasPermission(admin, 'users', 'create') && canReadTemplates
  const canBulkUpdateUsers = hasScopeAll(admin, 'users', 'update')
  const nodeNavItems = [
    ...(canReadNodes ? [{
      title: 'nodes.title',
      url: '/nodes',
      icon: Share2Icon,
    }] : []),
    ...(canReadCores ? [{
      title: 'settings.cores.title',
      url: '/nodes/cores',
      icon: Cpu,
      matchPrefix: true,
    }] : []),
    ...(canReadNodeLogs ? [{
      title: 'nodes.logs.title',
      url: '/nodes/logs',
      icon: Logs,
    }] : []),
  ]
  const templateNavItems = [
    ...(canReadTemplates ? [{
      title: 'templates.userTemplates',
      url: '/templates/user',
      icon: FileUser,
    }] : []),
    ...(canReadClientTemplates ? [{
      title: 'templates.clientTemplates',
      url: '/templates/client',
      icon: FileCode2,
    }] : []),
  ]
  const { currentVersion: systemVersion } = useSystemVersion({ enabled: canReadSystem })
  const { setOpenMobile, openMobile, state, isMobile, toggleSidebar } = useSidebar()
  const { resolvedTheme } = useTheme()
  const [showCollapseButton, setShowCollapseButton] = useState(false)
  const normalizedVersion = canReadSystem && systemVersion ? systemVersion.replace(/[^0-9.]/g, '') : null
  const displayVersion = canReadSystem && systemVersion ? `(v${systemVersion})` : ''
  const { hasUpdate } = useVersionCheck(normalizedVersion, { enabled: canReadSystem })
  const touchStartX = useRef<number | null>(null)
  const touchEndX = useRef<number | null>(null)
  const minSwipeDistance = 50
  const edgeThreshold = 50 // Distance from edge to detect edge swipe

  const handleTouchStart = (e: TouchEvent) => {
    touchEndX.current = null
    touchStartX.current = e.touches[0].clientX
  }

  const handleTouchMove = (e: TouchEvent) => {
    touchEndX.current = e.touches[0].clientX
  }

  const handleTouchEnd = useCallback(() => {
    if (!touchStartX.current || !touchEndX.current) return

    const distance = touchStartX.current - touchEndX.current
    const isLeftSwipe = distance > minSwipeDistance
    const isRightSwipe = distance < -minSwipeDistance
    const isFromRightEdge = touchStartX.current > window.innerWidth - edgeThreshold

    // Only handle swipes that start from the right edge
    if (isFromRightEdge) {
      if (isLeftSwipe && !openMobile) {
        setOpenMobile(true)
      } else if (isRightSwipe && openMobile) {
        setOpenMobile(false)
      }
    }

    // Reset touch positions
    touchStartX.current = null
    touchEndX.current = null
  }, [openMobile, setOpenMobile])

  useEffect(() => {
    // Add touch event listeners to the document
    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchmove', handleTouchMove, { passive: true })
    document.addEventListener('touchend', handleTouchEnd)

    // Cleanup
    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchmove', handleTouchMove)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchEnd])

  const data = {
    user: {
      name: admin?.username || 'Admin',
    },
    navMain: [
      ...(canReadSystem ? [{
        title: 'dashboard',
        url: '/',
        icon: LayoutDashboardIcon,
      }] : []),
      ...(hasPermission(admin, 'users', 'read') ? [{
        title: 'users',
        url: '/users',
        icon: UsersIcon,
      }] : []),
      ...(hasPermission(admin, 'nodes', 'stats')
        ? [{
            title: 'statistics',
            url: '/statistics',
            icon: PieChart,
          }]
        : []),
      ...(canReadHosts
        ? [{
            title: 'hosts',
            url: '/hosts',
            icon: ListTodo,
          }]
        : []),
      ...(canReadGroups
        ? [{
            title: 'groups',
            url: '/groups',
            icon: Group,
          }]
        : []),
      ...(canReadAdmins
        ? [{
            title: 'admins.title',
            url: '/admins',
            icon: UserCog,
          }]
        : []),
      ...(isOwner(admin)
        ? [{
            title: 'adminRoles.title',
            url: '/admin-roles',
            icon: UserKey,
          }]
        : []),
      ...(canReadApiKeys
        ? [{
            title: 'apiKeys.title',
            url: '/api-keys',
            icon: Key,
          }]
        : []),
      ...(nodeNavItems.length > 0
        ? [{
            title: 'nodes.title',
            url: nodeNavItems[0].url,
            icon: Share2Icon,
            items: nodeNavItems,
          }]
        : []),
      ...(templateNavItems.length > 0
        ? [{
            title: 'templates.title',
            url: templateNavItems[0].url,
            icon: LayoutTemplate,
            items: templateNavItems,
          }]
        : []),
      ...(canBulkCreateFromTemplate || canBulkUpdateUsers
        ? [{
            title: 'bulk.title',
            url: '/bulk',
            icon: Layers,
            items: [
              ...(canBulkCreateFromTemplate ? [{
                title: 'bulk.createUsers',
                url: '/bulk',
                icon: UserPlus,
              }] : []),
              ...(canBulkUpdateUsers ? [{
                title: 'bulk.groups',
                url: '/bulk/groups',
                icon: Group,
              },
              {
                title: 'bulk.expireDate',
                url: '/bulk/expire',
                icon: Calendar,
              },
              {
                title: 'bulk.dataLimit',
                url: '/bulk/data',
                icon: ArrowUpDown,
              },
              {
                title: 'bulk.proxySettings',
                url: '/bulk/proxy',
                icon: Lock,
              },
              {
                title: 'bulk.wireguardPeerIps',
                url: '/bulk/wireguard',
                icon: Network,
              }] : []),
            ],
          }]
        : []),
      {
            title: 'settings.title',
            url: '/settings',
            icon: Settings2,
            items: [
              ...(hasPermission(admin, 'settings', 'read_general') && hasPermission(admin, 'settings', 'update') ? [{
                title: 'settings.general.title',
                url: '/settings/general',
                icon: Settings,
              }] : []),
              ...(hasPermission(admin, 'settings', 'read') && hasPermission(admin, 'settings', 'update') ? [{
                title: 'settings.notifications.title',
                url: '/settings/notifications',
                icon: Bell,
              },
              {
                title: 'settings.subscriptions.title',
                url: '/settings/subscriptions',
                icon: ListTodo,
              },
              {
                title: 'settings.hwid.title',
                url: '/settings/hwid',
                icon: Fingerprint
              },
              {
                title: 'settings.telegram.title',
                url: '/settings/telegram',
                icon: Send,
              },
              {
                title: 'settings.webhook.title',
                url: '/settings/webhook',
                icon: Webhook,
              },
              {
                title: 'settings.cleanup.title',
                url: '/settings/cleanup',
                icon: Database,
              }] : []),
              {
                title: 'theme.title',
                url: '/settings/theme',
                icon: Palette,
              },
            ],
          },
    ],
    navSecondary: [
      {
        title: t('supportUs'),
        url: DONATION_URL,
        icon: LifeBuoy,
        target: '_blank',
      },
    ],
    community: [
      {
        title: 'documentation',
        url: DOCUMENTATION,
        icon: BookOpen,
        target: '_blank',
      },
      {
        title: 'discussionGroup',
        url: DISCUSSION_GROUP,
        icon: RssIcon,
        target: '_blank',
      },
      {
        title: 'github',
        url: REPO_URL,
        icon: GithubIcon,
        target: '_blank',
      },
    ],
  }

  return (
    <>
      <div className="sticky top-0 z-30 lg:hidden">
        <div className="h-[env(safe-area-inset-top)] bg-sidebar" />
        <div className="flex items-center justify-between border-b border-sidebar-border bg-sidebar/80 px-4 py-3 backdrop-blur-md supports-[backdrop-filter]:bg-sidebar/65">
          <Link to="/" className="flex items-center gap-2">
            <img
              src={resolvedTheme === 'dark' ? window.location.pathname + 'statics/favicon/logo.png' : window.location.pathname + 'statics/favicon/logo-dark.png'}
              alt="PasarGuard Logo"
              className="h-8 w-8 object-contain"
            />
            <span dir={isRTL ? 'rtl' : 'ltr'} className="text-sm font-bold">
              {t('pasarguard')}
            </span>
          </Link>
          <SidebarTriggerWithBadge showUpdateBadge={canReadSystem && hasUpdate} />
        </div>
      </div>
      <Sidebar variant="sidebar" collapsible="icon" {...props} className="border-sidebar-border p-0" side={isRTL ? 'right' : 'left'}>
        <Snowfall className="snowfall--sidebar" />
        <SidebarRail />
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              {state === 'collapsed' && !isMobile ? (
                <div className="group relative" onMouseEnter={() => setShowCollapseButton(true)} onMouseLeave={() => setShowCollapseButton(false)}>
                  {/* Badge - always visible, positioned on top layer */}
                  {canReadSystem && (
                    <div className="pointer-events-none absolute inset-0 z-30">
                      <div className="relative h-full w-full">
                        <VersionBadge currentVersion={normalizedVersion} />
                      </div>
                    </div>
                  )}
                  {/* Logo - fades out on hover */}
                  <SidebarMenuButton
                    size="lg"
                    asChild
                    className={cn('relative w-full justify-center !gap-0 transition-opacity duration-200 ease-in-out', showCollapseButton ? 'pointer-events-none opacity-0' : 'opacity-100')}
                  >
                    <a href={REPO_URL} target="_blank">
                      <img
                        src={resolvedTheme === 'dark' ? window.location.pathname + 'statics/favicon/logo.png' : window.location.pathname + 'statics/favicon/logo-dark.png'}
                        alt="PasarGuard Logo"
                        className="h-6 w-6 flex-shrink-0 object-contain"
                      />
                      {canReadSystem && hasUpdate && (
                        <TooltipProvider>
                          <VersionBadge currentVersion={normalizedVersion} />
                        </TooltipProvider>
                      )}
                    </a>
                  </SidebarMenuButton>
                  {/* Expand button - fades in on hover */}
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <SidebarMenuButton
                          size="lg"
                          className={cn(
                            'absolute inset-0 w-full cursor-pointer justify-center !gap-0 rounded-full transition-opacity duration-200 ease-in-out hover:bg-sidebar-accent/70',
                            showCollapseButton ? 'opacity-100' : 'pointer-events-none opacity-0',
                          )}
                          onClick={toggleSidebar}
                        >
                          <ChevronsRight className={cn('h-5 w-5 flex-shrink-0', isRTL && 'scale-x-[-1]')} />
                          <span className="sr-only">Expand Sidebar</span>
                          {canReadSystem && hasUpdate && <VersionBadge currentVersion={normalizedVersion} />}
                        </SidebarMenuButton>
                      </TooltipTrigger>
                      <TooltipContent side={isRTL ? 'left' : 'right'}>
                        <p>{t('sidebar.expand')}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              ) : state !== 'collapsed' && !isMobile ? (
                <div className={cn('relative', isRTL ? 'pl-10' : 'pr-10')}>
                  <SidebarMenuButton size="lg" className={cn('w-full !gap-2')}>
                    <a href={REPO_URL} target="_blank" className="flex min-w-0 flex-1 items-center gap-2">
                      <img
                        src={resolvedTheme === 'dark' ? window.location.pathname + 'statics/favicon/logo.png' : window.location.pathname + 'statics/favicon/logo-dark.png'}
                        alt="PasarGuard Logo"
                        className="h-8 w-8 flex-shrink-0 object-contain"
                      />
                      <div className="flex min-w-0 flex-1 flex-col items-start overflow-hidden">
                        <span className={cn(isRTL ? 'text-right' : 'text-left', 'truncate text-sm font-semibold leading-tight')}>{t('pasarguard')}</span>
                        {canReadSystem && (
                          <div className="flex min-w-0 flex-wrap items-center gap-0.75 leading-none">
                            <span className="max-w-full truncate text-xs leading-none opacity-45">{displayVersion}</span>
                            <div className="max-w-full">
                              <TooltipProvider>
                                <VersionBadge currentVersion={normalizedVersion} className="leading-none" />
                              </TooltipProvider>
                            </div>
                          </div>
                        )}
                      </div>
                    </a>
                  </SidebarMenuButton>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn(
                            'absolute top-1/2 z-10 h-8 w-8 shrink-0 -translate-y-1/2 cursor-pointer rounded-full border border-transparent transition-colors hover:border-sidebar-border hover:bg-sidebar-accent/70',
                            isRTL ? 'left-2' : 'right-2',
                          )}
                          onClick={e => {
                            e.preventDefault()
                            e.stopPropagation()
                            toggleSidebar()
                          }}
                        >
                          <ChevronsLeft className={cn('h-4 w-4', isRTL && 'scale-x-[-1]')} />
                          <span className="sr-only">Collapse Sidebar</span>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side={isRTL ? 'left' : 'right'}>
                        <p>{t('sidebar.collapse')}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              ) : (
                <SidebarMenuButton size="lg" asChild className="!gap-2">
                  <a href={REPO_URL} target="_blank">
                    <img
                      src={resolvedTheme === 'dark' ? window.location.pathname + 'statics/favicon/logo.png' : window.location.pathname + 'statics/favicon/logo-dark.png'}
                      alt="PasarGuard Logo"
                      className="h-8 w-8 flex-shrink-0 object-contain"
                    />
                    <div className="flex min-w-0 flex-col overflow-hidden">
                      <span className={cn(isRTL ? 'text-right' : 'text-left', 'truncate text-sm font-semibold leading-tight')}>{t('pasarguard')}</span>
                      {canReadSystem && (
                        <div className="flex min-w-0 flex-wrap items-center gap-0.75 leading-none">
                          <span className="max-w-full truncate text-xs leading-none opacity-45">{displayVersion}</span>
                          <div className="max-w-full">
                            <TooltipProvider>
                              <VersionBadge currentVersion={normalizedVersion} className="leading-none" />
                            </TooltipProvider>
                          </div>
                        </div>
                      )}
                    </div>
                  </a>
                </SidebarMenuButton>
              )}
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <NavMain items={data.navMain} />
          {isOwner(admin) && <NavSecondary items={data.community} label={t('community')} />}
          <NavSecondary items={data.navSecondary} className="mt-auto" />
          <GoalProgress />
          <div className="flex items-center justify-between px-2 [&>:first-child]:[direction:ltr]">
            {state !== 'collapsed' && <GithubStar />}
            {state !== 'collapsed' && (
              <div className="flex items-start gap-2">
                <Language />
                <ThemeToggle />
              </div>
            )}
            {state === 'collapsed' && isMobile && (
              <>
                <GithubStar />

                <div className="flex items-start gap-2">
                  <Language />
                  <ThemeToggle />
                </div>
              </>
            )}
          </div>
        </SidebarContent>
        <SidebarFooter>
          <NavUser admin={admin} username={data?.user} />
        </SidebarFooter>
      </Sidebar>
    </>
  )
}
