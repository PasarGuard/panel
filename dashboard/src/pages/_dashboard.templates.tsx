import PageHeader from '@/components/layout/page-header'
import PageTransition from '@/components/layout/page-transition'
import { getDocsUrl } from '@/utils/docs-url'
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
  const [activeTab, setActiveTab] = useState<string>(tabs[0].id)

  useEffect(() => {
    const currentTab = tabs.find(tab => location.pathname === tab.url)
    if (currentTab) {
      setActiveTab(currentTab.id)
    }
  }, [location.pathname])

  const getPageHeaderProps = () => {
    if (location.pathname === '/templates/client') {
      return {
        title: 'clientTemplates.title',
        description: 'clientTemplates.description',
        buttonIcon: Plus,
        buttonText: 'clientTemplates.addTemplate',
        onButtonClick: () => {
          window.dispatchEvent(new CustomEvent('openClientTemplateDialog'))
        },
      }
    }
    return {
      title: 'templates.title',
      description: 'templates.description',
      buttonIcon: Plus,
      buttonText: 'templates.addTemplate',
      onButtonClick: () => {
        window.dispatchEvent(new CustomEvent('openUserTemplateDialog'))
      },
    }
  }

  return (
    <div className="flex w-full flex-col items-start gap-0">
      <PageTransition isContentTransition={true}>
        <PageHeader {...getPageHeaderProps()} tutorialUrl={getDocsUrl(location.pathname)} />
      </PageTransition>
      <div className="w-full">
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
