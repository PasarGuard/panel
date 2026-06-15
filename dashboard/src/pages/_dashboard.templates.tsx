import PageHeader from '@/components/layout/page-header'
import PageTransition from '@/components/layout/page-transition'
import { useAdmin } from '@/hooks/use-admin'
import { getDocsUrl } from '@/utils/docs-url'
import { hasPermission } from '@/utils/rbac'
import { FileCode2, FileUser, LucideIcon, Plus } from 'lucide-react'
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
  { id: 'templates.userTemplates', label: 'templates.userTemplates', icon: FileUser, url: '/templates/user' },
  { id: 'templates.clientTemplates', label: 'templates.clientTemplates', icon: FileCode2, url: '/templates/client' },
]

export default function TemplatesLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const canReadUserTemplates = hasPermission(admin, 'templates', 'read')
  const canCreateUserTemplates = hasPermission(admin, 'templates', 'create')
  const canReadClientTemplates = hasPermission(admin, 'client_templates', 'read')
  const canCreateClientTemplates = hasPermission(admin, 'client_templates', 'create')
  const visibleTabs = tabs.filter(tab => {
    if (tab.url === '/templates/user') return canReadUserTemplates
    if (tab.url === '/templates/client') return canReadClientTemplates
    return false
  })
  const [activeTab, setActiveTab] = useState<string>(tabs[0].id)

  useEffect(() => {
    const currentTab = tabs.find(tab => location.pathname === tab.url)
    if (currentTab) {
      setActiveTab(currentTab.id)
    }
  }, [location.pathname])

  useEffect(() => {
    if (visibleTabs.length === 0) return
    const currentTab = visibleTabs.find(tab => location.pathname === tab.url)
    if (!currentTab) {
      navigate(visibleTabs[0].url, { replace: true })
    }
  }, [location.pathname, navigate, visibleTabs])

  const getPageHeaderProps = () => {
    if (location.pathname === '/templates/client') {
      return {
        title: 'clientTemplates.title',
        description: 'clientTemplates.description',
        buttonIcon: canCreateClientTemplates ? Plus : undefined,
        buttonText: canCreateClientTemplates ? 'clientTemplates.addTemplate' : undefined,
        onButtonClick: canCreateClientTemplates
          ? () => {
              window.dispatchEvent(new CustomEvent('openClientTemplateDialog'))
            }
          : undefined,
      }
    }
    return {
      title: 'templates.title',
      description: 'templates.description',
      buttonIcon: canCreateUserTemplates ? Plus : undefined,
      buttonText: canCreateUserTemplates ? 'templates.addTemplate' : undefined,
      onButtonClick: canCreateUserTemplates
        ? () => {
            window.dispatchEvent(new CustomEvent('openUserTemplateDialog'))
          }
        : undefined,
    }
  }

  return (
    <div className="flex w-full flex-col items-start gap-0">
      <PageTransition isContentTransition={true}>
        <PageHeader {...getPageHeaderProps()} tutorialUrl={getDocsUrl(location.pathname)} />
      </PageTransition>
      <div className="w-full">
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
                <span>{t(tab.label, { defaultValue: tab.label === 'templates.userTemplates' ? 'User Templates' : 'Client Templates' })}</span>
              </div>
            </button>
          ))}
        </div>
        <div>
          <PageTransition isContentTransition={true}>
            <Outlet />
          </PageTransition>
        </div>
      </div>
    </div>
  )
}
