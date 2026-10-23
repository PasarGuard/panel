import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ExternalLink, Settings2 } from 'lucide-react'

import PageHeader from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import { PluginSettingsForm } from '@/features/plugins/components/plugin-settings-form'
import type { JsonSchema } from '@/features/plugins/settings-schema'
import { useGetPlugins, type PluginResponse } from '@/service/api'

export default function PluginsPage() {
  const { t } = useTranslation()
  const { data, isLoading } = useGetPlugins()
  const [editing, setEditing] = useState<PluginResponse | null>(null)
  const plugins = data?.plugins ?? []

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu">
        <PageHeader title="plugins.title" description="plugins.description" />
        <Separator />
      </div>

      <div className="flex w-full flex-col gap-4 p-4">
        {isLoading && <p className="text-muted-foreground text-sm">{t('loading')}</p>}
        {!isLoading && plugins.length === 0 && <p className="text-muted-foreground text-sm">{t('plugins.empty')}</p>}
        {plugins.map(plugin => {
          const loaded = plugin.status === 'loaded'
          return (
            <Card key={plugin.id}>
              <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
                <div className="flex min-w-0 flex-col gap-1">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <span className="truncate">{plugin.name}</span>
                    {plugin.version && (
                      <span dir="ltr" className="text-muted-foreground text-xs font-normal">
                        v{plugin.version}
                      </span>
                    )}
                    <Badge variant={loaded ? 'green' : 'red'}>{t(loaded ? 'plugins.loaded' : 'plugins.failed')}</Badge>
                  </CardTitle>
                  <CardDescription dir="ltr" className="text-xs">
                    {plugin.id}
                  </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  {loaded && plugin.has_ui && (
                    <Button asChild variant="outline" size="sm">
                      <Link to={`/plugins/${encodeURIComponent(plugin.id)}`}>
                        <ExternalLink className="h-4 w-4" />
                        {t('plugins.openPage')}
                      </Link>
                    </Button>
                  )}
                  {loaded && plugin.settings_schema && (
                    <Button variant="outline" size="sm" onClick={() => setEditing(plugin)}>
                      <Settings2 className="h-4 w-4" />
                      {t('plugins.settings')}
                    </Button>
                  )}
                </div>
              </CardHeader>
              {(plugin.description || plugin.error) && (
                <CardContent className="flex flex-col gap-2 text-sm">
                  {plugin.description && <p className="text-muted-foreground">{plugin.description}</p>}
                  {plugin.error && (
                    <p dir="ltr" className="text-destructive font-mono text-xs break-words">
                      {plugin.error}
                    </p>
                  )}
                </CardContent>
              )}
            </Card>
          )
        })}
      </div>

      <Dialog open={!!editing} onOpenChange={open => !open && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t('plugins.settings')}: {editing?.name}
            </DialogTitle>
            <DialogDescription>{t('plugins.settingsDescription')}</DialogDescription>
          </DialogHeader>
          {editing?.settings_schema && <PluginSettingsForm pluginId={editing.id} schema={editing.settings_schema as JsonSchema} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
