import PageHeader from '@/components/page-header'
import PageTransition from '@/components/PageTransition'
import { NavigationTabs, type Tab } from '@/components/navigation-tabs'
import { Cpu, Share2, Plus, FileText } from 'lucide-react'
import { Outlet, useLocation } from 'react-router'

const tabs: Tab[] = [
  { id: 'nodes.title', label: 'nodes.title', icon: Share2, url: '/nodes' },
  { id: 'core', label: 'core', icon: Cpu, url: '/nodes/cores' },
  { id: 'nodes.logs.title', label: 'nodes.logs.title', icon: FileText, url: '/nodes/logs' },
]

const Settings = () => {
  const location = useLocation()

  const getPageHeaderProps = () => {
    if (location.pathname === '/nodes/cores') {
      return {
        title: 'settings.cores.title',
        description: 'settings.cores.description',
        buttonIcon: Plus,
        buttonText: 'settings.cores.addCore',
        onButtonClick: () => {
          // This will be handled by the child component through context or props
          const event = new CustomEvent('openCoreDialog')
          window.dispatchEvent(event)
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
    <div className="flex w-full flex-col items-start gap-0">
      <PageTransition isContentTransition={true}>
        <PageHeader {...getPageHeaderProps()} />
      </PageTransition>
      <NavigationTabs tabs={tabs} defaultTab={tabs[0]?.id} />
      <div className="px-4">
        <PageTransition isContentTransition={true}>
          <Outlet />
        </PageTransition>
      </div>
    </div>
  )
}

export default Settings
