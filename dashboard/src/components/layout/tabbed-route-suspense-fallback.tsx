import { Spinner } from '@/components/common/spinner'
import { LoadingSpinner } from '@/components/common/loading-spinner'
import PageHeader from '@/components/layout/page-header'
import { getDocsUrl } from '@/utils/docs-url'
import { useAdmin } from '@/hooks/use-admin'
import { cn } from '@/lib/utils'
import {
  ArrowUpDown,
  Bell,
  Calendar,
  Cpu,
  Database,
  FileCode2,
  FileUser,
  Group,
  ListTodo,
  Lock,
  Logs,
  LucideIcon,
  MessageCircle,
  Network,
  Palette,
  Send,
  Settings as SettingsIcon,
  Share2,
  UserPlus,
  Webhook,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router'

type TabDef = { id: string; labelKey: string; icon: LucideIcon; url: string }

const NODES_TABS: TabDef[] = [
  { id: 'nodes.title', labelKey: 'nodes.title', icon: Share2, url: '/nodes' },
  { id: 'core', labelKey: 'core', icon: Cpu, url: '/nodes/cores' },
  { id: 'nodes.logs.title', labelKey: 'nodes.logs.title', icon: Logs, url: '/nodes/logs' },
]

const SETTINGS_SUDO_TABS: TabDef[] = [
  { id: 'general', labelKey: 'settings.general.title', icon: SettingsIcon, url: '/settings/general' },
  { id: 'notifications', labelKey: 'settings.notifications.title', icon: Bell, url: '/settings/notifications' },
  { id: 'subscriptions', labelKey: 'settings.subscriptions.title', icon: ListTodo, url: '/settings/subscriptions' },
  { id: 'telegram', labelKey: 'settings.telegram.title', icon: Send, url: '/settings/telegram' },
  { id: 'discord', labelKey: 'settings.discord.title', icon: MessageCircle, url: '/settings/discord' },
  { id: 'webhook', labelKey: 'settings.webhook.title', icon: Webhook, url: '/settings/webhook' },
  { id: 'cleanup', labelKey: 'settings.cleanup.title', icon: Database, url: '/settings/cleanup' },
  { id: 'theme', labelKey: 'theme.title', icon: Palette, url: '/settings/theme' },
]

const SETTINGS_NON_SUDO_TABS: TabDef[] = [{ id: 'theme', labelKey: 'theme.title', icon: Palette, url: '/settings/theme' }]

const BULK_SUDO_TABS: TabDef[] = [
  { id: 'create', labelKey: 'bulk.createUsers', icon: UserPlus, url: '/bulk' },
  { id: 'groups', labelKey: 'bulk.groups', icon: Group, url: '/bulk/groups' },
  { id: 'expire', labelKey: 'bulk.expireDate', icon: Calendar, url: '/bulk/expire' },
  { id: 'data', labelKey: 'bulk.dataLimit', icon: ArrowUpDown, url: '/bulk/data' },
  { id: 'proxy', labelKey: 'bulk.proxySettings', icon: Lock, url: '/bulk/proxy' },
  { id: 'wireguard', labelKey: 'bulk.wireguardPeerIps', icon: Network, url: '/bulk/wireguard' },
]

const BULK_NON_SUDO_TABS: TabDef[] = [{ id: 'create', labelKey: 'bulk.createUsers', icon: UserPlus, url: '/bulk' }]

const TEMPLATES_TABS: TabDef[] = [
  { id: 'templates.userTemplates', labelKey: 'templates.userTemplates', icon: FileUser, url: '/templates/user' },
  { id: 'templates.clientTemplates', labelKey: 'templates.clientTemplates', icon: FileCode2, url: '/templates/client' },
]

function nodesActiveTabId(pathname: string): string {
  if (pathname.startsWith('/nodes/cores')) return 'core'
  if (pathname.startsWith('/nodes/logs')) return 'nodes.logs.title'
  return 'nodes.title'
}

function nodesHeader(pathname: string): { title: string; description: string } {
  if (pathname.startsWith('/nodes/cores')) {
    return { title: 'settings.cores.title', description: 'settings.cores.description' }
  }
  if (pathname.startsWith('/nodes/logs')) {
    return { title: 'nodes.logs.title', description: 'nodes.logs.description' }
  }
  return { title: 'nodes.title', description: 'manageNodes' }
}

function settingsActiveTabId(pathname: string, tabs: TabDef[]): string {
  const hit = tabs.find(t => pathname === t.url)
  return hit?.id ?? tabs[0].id
}

function bulkActiveTabId(pathname: string, tabs: TabDef[]): string {
  const hit = tabs.find(tab => {
    if (tab.id === 'create' && pathname === '/bulk/create') return true
    return pathname === tab.url
  })
  return hit?.id ?? tabs[0].id
}

function bulkHeader(pathname: string): { title: string; description: string } {
  const pathToHeader: Record<string, { title: string; description: string }> = {
    '/bulk': { title: 'bulk.createUsers', description: 'bulk.createUsersDesc' },
    '/bulk/create': { title: 'bulk.createUsers', description: 'bulk.createUsersDesc' },
    '/bulk/groups': { title: 'bulk.groups', description: 'bulk.groupsDesc' },
    '/bulk/expire': { title: 'bulk.expireDate', description: 'bulk.expireDateDesc' },
    '/bulk/data': { title: 'bulk.dataLimit', description: 'bulk.dataLimitDesc' },
    '/bulk/proxy': { title: 'bulk.proxySettings', description: 'bulk.proxySettingsDesc' },
    '/bulk/wireguard': { title: 'bulk.wireguardPeerIps', description: 'bulk.wireguardPeerIpsDesc' },
  }
  return pathToHeader[pathname] ?? pathToHeader['/bulk']!
}

function templatesHeader(pathname: string): { title: string; description: string } {
  if (pathname === '/templates/client') {
    return { title: 'clientTemplates.title', description: 'clientTemplates.description' }
  }
  return { title: 'templates.title', description: 'templates.description' }
}

function TabStripPlaceholder({ tabs, activeId }: { tabs: TabDef[]; activeId: string }) {
  const { t } = useTranslation()
  return (
    <div className="scrollbar-hide flex overflow-x-auto border-b px-4 lg:flex-wrap">
      {tabs.map(tab => {
        const Icon = tab.icon
        const isActive = activeId === tab.id
        return (
          <div
            key={tab.id}
            className={cn(
              'relative shrink-0 whitespace-nowrap px-3 py-2 text-sm font-medium',
              isActive ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground',
            )}
          >
            <div className="flex items-center gap-1.5">
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              {tab.id === 'core' ? (
                <>
                  <span className="hidden sm:inline">{t(tab.labelKey)}</span>
                  <span className="sm:hidden">{t('settings.cores.title')}</span>
                </>
              ) : (
                <span>{t(tab.labelKey)}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ContentSpinner() {
  return (
    <div className="flex min-h-48 flex-1 flex-col items-center justify-center gap-3 px-4 py-10">
      <Spinner size="large" />
    </div>
  )
}

function NodesTabbedFallback({ pathname }: { pathname: string }) {
  const header = nodesHeader(pathname)
  const activeId = nodesActiveTabId(pathname)
  return (
    <div className="flex w-full min-h-0 flex-1 flex-col items-start gap-0">
      <PageHeader title={header.title} description={header.description} tutorialUrl={getDocsUrl(pathname)} />
      <div className="flex w-full min-h-0 flex-1 flex-col">
        <TabStripPlaceholder tabs={NODES_TABS} activeId={activeId} />
        <ContentSpinner />
      </div>
    </div>
  )
}

function SettingsTabbedFallback({ pathname, isSudo }: { pathname: string; isSudo: boolean }) {
  const { t } = useTranslation()
  const tabs = isSudo ? SETTINGS_SUDO_TABS : SETTINGS_NON_SUDO_TABS
  const activeId = settingsActiveTabId(pathname, tabs)
  return (
    <div className="flex w-full flex-col items-start gap-0">
      <PageHeader title={t(`settings.${activeId}.title`)} description="manageSettings" tutorialUrl={getDocsUrl(pathname)} />
      <div className="relative w-full">
        <div className="flex w-full min-w-0 flex-col">
          <TabStripPlaceholder tabs={tabs} activeId={activeId} />
          <ContentSpinner />
        </div>
      </div>
    </div>
  )
}

function BulkTabbedFallback({ pathname, isSudo }: { pathname: string; isSudo: boolean }) {
  const tabs = isSudo ? BULK_SUDO_TABS : BULK_NON_SUDO_TABS
  const activeId = bulkActiveTabId(pathname, tabs)
  const header = bulkHeader(pathname)
  return (
    <div className="flex w-full flex-col items-start gap-0">
      <PageHeader title={header.title} description={header.description} tutorialUrl={getDocsUrl(pathname)} />
      <div className="w-full">
        <TabStripPlaceholder tabs={tabs} activeId={activeId} />
        <ContentSpinner />
      </div>
    </div>
  )
}

function TemplatesTabbedFallback({ pathname }: { pathname: string }) {
  const header = templatesHeader(pathname)
  const activeId =
    pathname === '/templates/client' ? 'templates.clientTemplates' : 'templates.userTemplates'
  return (
    <div className="flex w-full flex-col items-start gap-0">
      <PageHeader title={header.title} description={header.description} tutorialUrl={getDocsUrl(pathname)} />
      <div className="w-full">
        <TabStripPlaceholder tabs={TEMPLATES_TABS} activeId={activeId} />
        <ContentSpinner />
      </div>
    </div>
  )
}

/**
 * Suspense fallback for lazy tabbed layouts: real tab chrome + compact spinner (not full-screen).
 * Mirrors `_dashboard.nodes`, `_dashboard.settings`, `_dashboard.bulk`, `_dashboard.templates`.
 */
export function TabbedRouteSuspenseFallback() {
  const { pathname } = useLocation()
  const { admin } = useAdmin()
  /** While admin is still resolving, prefer full tab strip (typical sudo layout). */
  const isSudo = admin?.is_sudo !== false

  if (pathname.startsWith('/nodes')) {
    return <NodesTabbedFallback pathname={pathname} />
  }
  if (pathname.startsWith('/settings')) {
    return <SettingsTabbedFallback pathname={pathname} isSudo={isSudo} />
  }
  if (pathname.startsWith('/bulk')) {
    return <BulkTabbedFallback pathname={pathname} isSudo={isSudo} />
  }
  if (pathname.startsWith('/templates')) {
    return <TemplatesTabbedFallback pathname={pathname} />
  }

  return <LoadingSpinner />
}
