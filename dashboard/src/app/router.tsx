import { Suspense } from 'react'
import { useAdmin } from '@/hooks/use-admin'
import { getCurrentAdmin } from '@/service/api'
import { createHashRouter, Navigate, RouteObject } from 'react-router'
import { LoadingSpinner } from '@/components/common/loading-spinner'
import { TabbedRouteSuspenseFallback } from '@/components/layout/tabbed-route-suspense-fallback'
import { lazyWithChunkRecovery } from '@/utils/chunk-recovery'
// Replace direct imports with lazy imports for route-level components
const CoresLayout = lazyWithChunkRecovery(() => import('@/pages/_dashboard.nodes.cores'))
const CoresIndex = lazyWithChunkRecovery(() => import('@/pages/_dashboard.nodes.cores._index'))
const CoresCoreEditorRoute = lazyWithChunkRecovery(() => import('@/pages/_dashboard.nodes.cores.editor'))
const ThemePage = lazyWithChunkRecovery(() => import('@/pages/_dashboard.settings.theme'))
const DashboardLayout = lazyWithChunkRecovery(() => import('../pages/_dashboard'))
const Dashboard = lazyWithChunkRecovery(() => import('../pages/_dashboard._index'))
const AdminsPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.admins'))
const BulkPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk'))
const BulkCreatePage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk.create'))
const BulkDataPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk.data'))
const BulkExpirePage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk.expire'))
const BulkGroupsPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk.groups'))
const BulkProxyPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk.proxy'))
const BulkWireguardPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.bulk.wireguard'))
const Groups = lazyWithChunkRecovery(() => import('../pages/_dashboard.groups'))
const Hosts = lazyWithChunkRecovery(() => import('../pages/_dashboard.hosts'))
const Nodes = lazyWithChunkRecovery(() => import('../pages/_dashboard.nodes'))
const NodesPage = lazyWithChunkRecovery(() => import('../pages/_dashboard.nodes._index'))
const NodeLogs = lazyWithChunkRecovery(() => import('../pages/_dashboard.nodes.logs'))
const Settings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings'))
const CleanupSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.cleanup'))
const DiscordSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.discord'))
const GeneralSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.general'))
const HwidSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.hwid'))
const NotificationSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.notifications'))
const SubscriptionSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.subscriptions'))
const TelegramSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.telegram'))
const WebhookSettings = lazyWithChunkRecovery(() => import('../pages/_dashboard.settings.webhook'))
const Statistics = lazyWithChunkRecovery(() => import('../pages/_dashboard.statistics'))
const TemplatesLayout = lazyWithChunkRecovery(() => import('../pages/_dashboard.templates'))
const UserTemplates = lazyWithChunkRecovery(() => import('../pages/_dashboard.templates.user'))
const ClientTemplates = lazyWithChunkRecovery(() => import('../pages/_dashboard.templates.client'))
const Users = lazyWithChunkRecovery(() => import('../pages/_dashboard.users'))
const Login = lazyWithChunkRecovery(() => import('../pages/login'))

// Component to handle default settings routing based on user permissions
function SettingsIndex() {
  const { admin } = useAdmin()
  const is_sudo = admin?.is_sudo || false

  // For sudo admins, default to notifications; for non-sudo admins, default to theme
  const defaultPath = is_sudo ? '/settings/general' : '/settings/theme'

  return <Navigate to={defaultPath} replace />
}

const fetchAdminLoader = async (): Promise<any> => {
  try {
    const response = await getCurrentAdmin()
    return response
  } catch (error) {
    throw Response.redirect('/login')
  }
}

// Wrap all route elements in <Suspense fallback={<LoadingSpinner />}>
export const router = createHashRouter([
  {
    hydrateFallbackElement: <LoadingSpinner />,
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <DashboardLayout />
      </Suspense>
    ),
    errorElement: (
      <Suspense fallback={<LoadingSpinner />}>
        <Login />
      </Suspense>
    ),
    loader: fetchAdminLoader,
    children: [
      {
        path: '/',
        index: true,
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <Dashboard />
          </Suspense>
        ),
      },
      {
        path: '/users',
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <Users />
          </Suspense>
        ),
      },
      {
        path: '/statistics',
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <Statistics />
          </Suspense>
        ),
      },
      {
        path: '/hosts',
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <Hosts />
          </Suspense>
        ),
      },
      {
        path: '/nodes',
        element: (
          <Suspense fallback={<TabbedRouteSuspenseFallback />}>
            <Nodes />
          </Suspense>
        ),
        children: [
          {
            path: '/nodes',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <NodesPage />
              </Suspense>
            ),
          },
          {
            path: '/nodes/cores',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <CoresLayout />
              </Suspense>
            ),
            children: [
              {
                index: true,
                element: (
                  <Suspense fallback={<LoadingSpinner />}>
                    <CoresIndex />
                  </Suspense>
                ),
              },
              {
                path: ':coreId',
                element: (
                  <Suspense fallback={<LoadingSpinner />}>
                    <CoresCoreEditorRoute />
                  </Suspense>
                ),
              },
            ],
          },
          {
            path: '/nodes/logs',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <NodeLogs />
              </Suspense>
            ),
          },
        ],
      },
      {
        path: '/groups',
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <Groups />
          </Suspense>
        ),
      },
      {
        path: '/templates',
        element: (
          <Suspense fallback={<TabbedRouteSuspenseFallback />}>
            <TemplatesLayout />
          </Suspense>
        ),
        children: [
          {
            index: true,
            element: <Navigate to="/templates/user" replace />,
          },
          {
            path: '/templates/user',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <UserTemplates />
              </Suspense>
            ),
          },
          {
            path: '/templates/client',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <ClientTemplates />
              </Suspense>
            ),
          },
        ],
      },
      {
        path: '/admins',
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <AdminsPage />
          </Suspense>
        ),
      },
      {
        path: '/settings',
        element: (
          <Suspense fallback={<TabbedRouteSuspenseFallback />}>
            <Settings />
          </Suspense>
        ),
        children: [
          {
            path: '/settings',
            index: true,
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <SettingsIndex />
              </Suspense>
            ),
          },
          {
            path: '/settings/general',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <GeneralSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/notifications',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <NotificationSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/subscriptions',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <SubscriptionSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/hwid',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <HwidSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/telegram',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <TelegramSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/discord',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <DiscordSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/webhook',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <WebhookSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/cleanup',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <CleanupSettings />
              </Suspense>
            ),
          },
          {
            path: '/settings/theme',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <ThemePage />
              </Suspense>
            ),
          },
        ],
      },
      {
        path: '/bulk',
        element: (
          <Suspense fallback={<TabbedRouteSuspenseFallback />}>
            <BulkPage />
          </Suspense>
        ),
        children: [
          {
            path: '/bulk',
            index: true,
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkCreatePage />
              </Suspense>
            ),
          },
          {
            path: '/bulk/groups',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkGroupsPage />
              </Suspense>
            ),
          },
          {
            path: '/bulk/create',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkCreatePage />
              </Suspense>
            ),
          },
          {
            path: '/bulk/proxy',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkProxyPage />
              </Suspense>
            ),
          },
          {
            path: '/bulk/expire',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkExpirePage />
              </Suspense>
            ),
          },
          {
            path: '/bulk/data',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkDataPage />
              </Suspense>
            ),
          },
          {
            path: '/bulk/wireguard',
            element: (
              <Suspense fallback={<LoadingSpinner />}>
                <BulkWireguardPage />
              </Suspense>
            ),
          },
        ],
      },
      {
        path: 'theme',
        element: (
          <Suspense fallback={<LoadingSpinner />}>
            <ThemePage />
          </Suspense>
        ),
      },
    ],
  },
  {
    path: '/login',
    hydrateFallbackElement: <LoadingSpinner />,
    element: (
      <Suspense fallback={<LoadingSpinner />}>
        <Login />
      </Suspense>
    ),
  },
] as RouteObject[])
