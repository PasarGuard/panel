import PageHeader from '@/components/layout/page-header'
import PageTransition from '@/components/layout/page-transition'
import { getDocsUrl } from '@/utils/docs-url'
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

  const getPageHeaderProps = () => {
    if (location.pathname.startsWith('/nodes/cores')) {
      return {
        title: 'settings.cores.title',
        description: 'settings.cores.description',
        buttonIcon: Plus,
        buttonText: 'settings.cores.addCore',
        onButtonClick: () => {
          navigate('/nodes/cores/new')
        },
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
      buttonIcon: Plus,
      buttonText: 'nodes.addNode',
      onButtonClick: () => {
        // This will be handled by the child component through context or props
        const event = new CustomEvent('openNodeDialog')
        window.dispatchEvent(event)
      },
    }
  }

  return (
    <div className="flex w-full flex-1 min-h-0 flex-col items-start gap-0">
      {!isCoreEditorPage && (
        <PageTransition isContentTransition={true}>
          <PageHeader {...getPageHeaderProps()} tutorialUrl={getDocsUrl(location.pathname)} />
        </PageTransition>
      )}
      <div className="flex w-full min-h-0 flex-1 flex-col">
        {!isCoreEditorPage && (
          <div className="flex border-b px-4">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => navigate(tab.url)}
                className={`relative px-3 py-2 text-sm font-medium transition-colors ${
                  activeTab === tab.id ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground hover:text-foreground'
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
