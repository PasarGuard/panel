import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { PluginFrame } from '@/features/plugins/components/plugin-frame'
import { useGetPlugins } from '@/service/api'

export default function PluginPage() {
  const { t } = useTranslation()
  const { pluginId = '' } = useParams()
  const { data, isLoading } = useGetPlugins()
  const plugin = data?.plugins?.find(item => item.id === pluginId)
  const available = plugin?.status === 'loaded' && plugin.has_ui

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu">
        <PageHeader title={plugin?.name ?? pluginId} description={plugin?.description || undefined} />
        <Separator />
      </div>
      <div className="w-full p-4">
        {isLoading ? (
          <p className="text-muted-foreground text-sm">{t('loading')}</p>
        ) : available ? (
          <PluginFrame pluginId={plugin.id} title={plugin.name} />
        ) : (
          <p className="text-muted-foreground text-sm">{t('plugins.notFound')}</p>
        )}
      </div>
    </div>
  )
}
