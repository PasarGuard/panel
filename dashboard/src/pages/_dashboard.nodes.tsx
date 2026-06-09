import PageHeader from '@/components/layout/page-header'
import PageTransition from '@/components/layout/page-transition'
import { useAdmin } from '@/hooks/use-admin'
import { getDocsUrl } from '@/utils/docs-url'
import { hasPermission } from '@/utils/rbac'
import { Cpu, LucideIcon, Share2, Plus, Logs } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router'

interface Tab {
  id: string
  label: string
  icon: LucideIcon
  url: string
}

const tabs: Tab[] = [
  { id: 'nodes.title', label: 'nodes.title', icon: Share2, url: '/nodes' },
  { id: 'core', label: 'core', icon: Cpu, url: '/nodes/cores' },
  { id: 'nodes.logs.title', label: 'nodes.logs.title', icon: Logs, url: '/nodes/logs' },
]

const Settings = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const canReadNodes = hasPermission(admin, 'nodes', 'read')
  const canCreateNodes = hasPermission(admin, 'nodes', 'create')
  const canReadCores = hasPermission(admin, 'cores', 'read')
  const canCreateCores = hasPermission(admin, 'cores', 'create')
  const canReadNodeLogs = hasPermission(admin, 'nodes', 'logs')
  const visibleTabs = tabs.filter(tab => {
    if (tab.url === '/nodes') return canReadNodes
    if (tab.url === '/nodes/cores') return canReadCores
    if (tab.url === '/nodes/logs') return canReadNodeLogs
    return false
  })
  const [activeTab, setActiveTab] = useState<string>(tabs[0].id)
  const isCoreEditorPage = /^\/nodes\/cores\/[^/]+$/.test(location.pathname)

  useEffect(() => {
    if (location.pathname.startsWith('/nodes/cores')) {
      setActiveTab('core')
      return
    }
    const currentTab = tabs.find(tab => location.pathname === tab.url)
    if (currentTab) {
      setActiveTab(currentTab.id)
    }
  }, [location.pathname])

  useEffect(() => {
    if (isCoreEditorPage || visibleTabs.length === 0) return
    const currentTab = visibleTabs.find(tab => location.pathname === tab.url)
    if (!currentTab) {
      navigate(visibleTabs[0].url, { replace: true })
    }
  }, [isCoreEditorPage, location.pathname, navigate, visibleTabs])

  const getPageHeaderProps = () => {
    if (location.pathname.startsWith('/nodes/cores')) {
      return {
        title: 'settings.cores.title',
        description: 'settings.cores.description',
        buttonIcon: canCreateCores ? Plus : undefined,
        buttonText: canCreateCores ? 'settings.cores.addCore' : undefined,
        onButtonClick: canCreateCores
          ? () => {
              navigate('/nodes/cores/new')
            }
          : undefined,
      }
    }
    if (location.pathname === '/nodes/logs') {
      return {
        title: 'nodes.logs.title',
        description: 'nodes.logs.description',
        buttonIcon: undefined,
        buttonText: undefined,
        onButtonClick: undefined,
      }
    }
    return {
      title: 'nodes.title',
      description: 'manageNodes',
      buttonIcon: canCreateNodes ? Plus : undefined,
      buttonText: canCreateNodes ? 'nodes.addNode' : undefined,
      onButtonClick: canCreateNodes
        ? () => {
            const event = new CustomEvent('openNodeDialog')
            window.dispatchEvent(event)
          }
        : undefined,
    }
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col items-start gap-0">
      {!isCoreEditorPage && (
        <PageTransition isContentTransition={true}>
          <PageHeader {...getPageHeaderProps()} tutorialUrl={getDocsUrl(location.pathname)} />
        </PageTransition>
      )}
      <div className="flex min-h-0 w-full flex-1 flex-col">
        {!isCoreEditorPage && (
          <div className="flex border-b px-4">
            {visibleTabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => navigate(tab.url)}
                className={`relative px-3 py-2 text-sm font-medium transition-colors ${
                  activeTab === tab.id ? 'border-primary text-foreground border-b-2' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <tab.icon className="h-4 w-4" />
                  {tab.id === 'core' ? (
                    <>
                      <span className="hidden sm:inline">{t(tab.label)}</span>
                      <span className="sm:hidden">{t('settings.cores.title')}</span>
                    </>
                  ) : (
                    <span>{t(tab.label)}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
        <PageTransition isContentTransition={true} className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </PageTransition>
      </div>
    </div>
  )
}

export default Settings
