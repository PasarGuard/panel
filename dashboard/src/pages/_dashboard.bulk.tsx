import PageHeader from '@/components/layout/page-header'
import { useAdmin } from '@/hooks/use-admin'
import PageTransition from '@/components/layout/page-transition'
import { getDocsUrl } from '@/utils/docs-url'
import { ArrowUpDown, Calendar, Lock, Group, UserPlus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { canReadResourcePage, hasPermission, hasScopeAll } from '@/utils/rbac'

const allTabs = [
  { id: 'create', label: 'bulk.createUsers', icon: UserPlus, url: '/bulk' },
  { id: 'groups', label: 'bulk.groups', icon: Group, url: '/bulk/groups' },
  { id: 'expire', label: 'bulk.expireDate', icon: Calendar, url: '/bulk/expire' },
  { id: 'data', label: 'bulk.dataLimit', icon: ArrowUpDown, url: '/bulk/data' },
  { id: 'proxy', label: 'bulk.proxySettings', icon: Lock, url: '/bulk/proxy' },
]

const BulkPage = () => {
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const canCreateUsers = hasPermission(admin, 'users', 'create')
  const canReadUserTemplates = canReadResourcePage(admin, 'templates')
  const canBulkUpdate = hasScopeAll(admin, 'users', 'update')
  const tabs = allTabs.filter(tab => (tab.id === 'create' ? canCreateUsers && canReadUserTemplates : canBulkUpdate))
  const navigate = useNavigate()
  const location = useLocation()
  const [activeTab, setActiveTab] = useState(allTabs[0].id)

  useEffect(() => {
    if (tabs.length === 0) {
      navigate('/settings/theme', { replace: true })
      return
    }
    const currentTab = tabs.find(tab => {
      if (tab.id === 'create' && location.pathname === '/bulk/create') {
        return true
      }
      return location.pathname === tab.url
    })
    if (currentTab) {
      setActiveTab(currentTab.id)
      return
    }

    // Keep non-sudo admins on the only allowed bulk page.
    setActiveTab(tabs[0].id)
    navigate(tabs[0].url, { replace: true })
  }, [location.pathname, navigate, tabs])

  if (tabs.length === 0) return null

  const getPageHeaderProps = () => {
    const pathToHeader: Record<string, { title: string; description: string }> = {
      '/bulk': { title: 'bulk.createUsers', description: 'bulk.createUsersDesc' },
      '/bulk/create': { title: 'bulk.createUsers', description: 'bulk.createUsersDesc' },
      '/bulk/groups': { title: 'bulk.groups', description: 'bulk.groupsDesc' },
      '/bulk/expire': { title: 'bulk.expireDate', description: 'bulk.expireDateDesc' },
      '/bulk/data': { title: 'bulk.dataLimit', description: 'bulk.dataLimitDesc' },
      '/bulk/proxy': { title: 'bulk.proxySettings', description: 'bulk.proxySettingsDesc' },
    }

    const header = pathToHeader[location.pathname] || pathToHeader['/bulk']
    return {
      title: header.title,
      description: header.description,
    }
  }

  return (
    <div className="flex w-full flex-col items-start gap-0">
      <PageTransition isContentTransition={true}>
        <PageHeader {...getPageHeaderProps()} tutorialUrl={getDocsUrl(location.pathname)} />
      </PageTransition>
      <div className="w-full">
        <div className="scrollbar-hide flex overflow-x-auto border-b px-4 lg:flex-wrap">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => navigate(tab.url)}
              className={`relative flex-shrink-0 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors ${activeTab === tab.id ? 'border-primary text-foreground border-b-2' : 'text-muted-foreground hover:text-foreground'}`}
            >
              <div className="flex items-center gap-1.5">
                <tab.icon className="h-4 w-4" />
                <span>{t(tab.label)}</span>
              </div>
            </button>
          ))}
        </div>
        <div className="px-4 py-6 lg:px-6">
          <PageTransition isContentTransition={true}>
            <Outlet />
          </PageTransition>
        </div>
      </div>
    </div>
  )
}

export default BulkPage
