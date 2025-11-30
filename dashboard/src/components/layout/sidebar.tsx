import { GithubStar } from '@/components/layout/github-star'
import { GoalProgress } from '@/components/layout/goal-progress'
import { VersionBadge } from '@/components/layout/version-badge'
import { SidebarTriggerWithBadge } from '@/components/layout/sidebar-trigger-with-badge'
import { Language } from '@/components/common/language'
import { NavMain } from '@/components/layout/nav-main'
import { NavSecondary } from '@/components/layout/nav-secondary'
import { NavUser } from '@/components/layout/nav-user'
import { useTheme } from '@/components/common/theme-provider'
import { ThemeToggle } from '@/components/common/theme-toggle'
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarRail, useSidebar } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Link } from 'react-router'
import { DISCUSSION_GROUP, DOCUMENTATION, DONATION_URL, REPO_URL } from '@/constants/Project'
import { useAdmin } from '@/hooks/use-admin'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { getSystemStats } from '@/service/api'
import {
  ArrowUpDown,
  Bell,
  BookOpen,
  Calendar,
  Cpu,
  Database,
  FileText,
  GithubIcon,
  Layers,
  LayoutDashboardIcon,
  LayoutTemplate,
  LifeBuoy,
  ListTodo,
  Lock,
  MessageCircle,
  Palette,
  PieChart,
  RssIcon,
  Send,
  Settings,
  Settings2,
  Share2Icon,
  UserCog,
  UserPlus,
  Users2,
  UsersIcon,
  Webhook,
} from 'lucide-react'
import * as React from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const isRTL = useDirDetection() === 'rtl'
  const { t } = useTranslation()
  const [version, setVersion] = useState<string>('')
  const { admin } = useAdmin()
  const { setOpenMobile, openMobile, state, isMobile } = useSidebar()
  const { resolvedTheme } = useTheme()
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

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const data = await getSystemStats()
        if (data?.version) {
          setVersion(` (v${data.version})`)
        }
      } catch (error) {
        console.error('Failed to fetch version:', error)
      }
    }
    fetchVersion()
  }, [])

  const data = {
    user: {
      name: admin?.username || 'Admin',
    },
    navMain: [
      {
        title: 'dashboard',
        url: '/',
        icon: LayoutDashboardIcon,
      },
      {
        title: 'users',
        url: '/users',
        icon: UsersIcon,
      },
      ...(admin?.is_sudo
        ? [
            {
              title: 'statistics',
              url: '/statistics',
              icon: PieChart,
            },
            {
              title: 'hosts',
              url: '/hosts',
              icon: ListTodo,
            },
            {
              title: 'groups',
              url: '/groups',
              icon: Users2,
            },
            {
              title: 'admins.title',
              url: '/admins',
              icon: UserCog,
            },
            {
              title: 'nodes.title',
              url: '/nodes',
              icon: Share2Icon,
              items: [
                {
                  title: 'nodes.title',
                  url: '/nodes',
                  icon: Share2Icon,
                },
                {
                  title: 'settings.cores.title',
                  url: '/nodes/cores',
                  icon: Cpu,
                },
                {
                  title: 'nodes.logs.title',
                  url: '/nodes/logs',
                  icon: FileText,
                },
              ],
            },
            {
              title: 'templates.title',
              url: '/templates',
              icon: LayoutTemplate,
            },
            {
              title: 'bulk.title',
              url: '/bulk',
              icon: Layers,
              items: [
                {
                  title: 'bulk.createUsers',
                  url: '/bulk',
                  icon: UserPlus,
                },
                {
                  title: 'bulk.groups',
                  url: '/bulk/groups',
                  icon: Users2,
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
              ],
            },
            {
              title: 'settings.title',
              url: '/settings',
              icon: Settings2,
              items: [
                {
                  title: 'settings.general.title',
                  url: '/settings/general',
                  icon: Settings,
                },
                {
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
                  title: 'settings.telegram.title',
                  url: '/settings/telegram',
                  icon: Send,
                },
                {
                  title: 'settings.discord.title',
                  url: '/settings/discord',
                  icon: MessageCircle,
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
                },
                {
                  title: 'theme.title',
                  url: '/settings/theme',
                  icon: Palette,
                },
              ],
            },
          ]
        : [
            // For non-sudo admins, show only theme settings
            {
              title: 'settings.title',
              url: '/settings',
              icon: Settings2,
              items: [
                {
                  title: 'theme.title',
                  url: '/settings/theme',
                  icon: Palette,
                },
              ],
            },
          ]),
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
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-sidebar-border bg-neutral-200/75 px-4 py-3 backdrop-blur dark:bg-neutral-900/75 lg:hidden">
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
        <SidebarTriggerWithBadge />
      </div>
      <Sidebar variant="sidebar" collapsible="icon" {...props} className="border-sidebar-border p-0" side={isRTL ? 'right' : 'left'}>
        <SidebarRail />
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              {state === 'collapsed' && !isMobile ? (
                <SidebarMenuButton size="lg" asChild className="relative">
                  <a href={REPO_URL} target="_blank" className="justify-center !gap-0">
                    <img
                      src={resolvedTheme === 'dark' ? window.location.pathname + 'statics/favicon/logo.png' : window.location.pathname + 'statics/favicon/logo-dark.png'}
                      alt="PasarGuard Logo"
                      className="h-6 w-6 flex-shrink-0 object-contain"
                    />
                    <TooltipProvider>
                      <VersionBadge currentVersion={version.replace(/[^0-9.]/g, '')} />
                    </TooltipProvider>
                  </a>
                </SidebarMenuButton>
              ) : (
                <SidebarMenuButton size="lg" asChild>
                  <a href={REPO_URL} target="_blank" className="!gap-2">
                    <img
                      src={resolvedTheme === 'dark' ? window.location.pathname + 'statics/favicon/logo.png' : window.location.pathname + 'statics/favicon/logo-dark.png'}
                      alt="PasarGuard Logo"
                      className="h-8 w-8 flex-shrink-0 object-contain"
                    />
                    <div className="flex flex-col overflow-hidden">
                      <span className={cn(isRTL ? 'text-right' : 'text-left', 'truncate text-sm font-semibold leading-tight')}>{t('pasarguard')}</span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs opacity-45">{version}</span>
                        <TooltipProvider>
                          <VersionBadge currentVersion={version.replace(/[^0-9.]/g, '')} />
                        </TooltipProvider>
                      </div>
                    </div>
                  </a>
                </SidebarMenuButton>
              )}
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <NavMain items={data.navMain} />
          {admin?.is_sudo && <NavSecondary items={data.community} label={t('community')} />}
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
