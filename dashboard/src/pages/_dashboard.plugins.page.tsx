import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import PageHeader from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { PluginFrame } from '@/features/plugins/components/plugin-frame'
import { useGetPlugins } from '@/service/api'
import { getErrorMessage } from '@/utils/error-utils'

export default function PluginPage() {
  const { t } = useTranslation()
  const { pluginId = '' } = useParams()
  const { data, isLoading, isError, error, refetch } = useGetPlugins()
  const plugin = data?.plugins?.find(item => item.id === pluginId)
  const available = plugin?.status === 'loaded' && plugin.has_ui

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu">
        <PageHeader title={plugin?.name ?? pluginId} description={plugin?.description || undefined} translate={false} />
        <Separator />
      </div>
      <div className="w-full p-4">
        {isLoading ? (
          <p className="text-muted-foreground text-sm">{t('loading')}</p>
        ) : isError && !data ? (
          <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-destructive">
              {t('error')}: {getErrorMessage(error)}
            </span>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              {t('errorPage.actions.tryAgain')}
            </Button>
          </div>
        ) : available ? (
          // A new frame per plugin, so switching plugins never loads the next UI with the old cookie
          <PluginFrame key={plugin.id} pluginId={plugin.id} title={plugin.name} />
        ) : (
          <p className="text-muted-foreground text-sm">{t('plugins.notFound')}</p>
        )}
      </div>
    </div>
  )
}
