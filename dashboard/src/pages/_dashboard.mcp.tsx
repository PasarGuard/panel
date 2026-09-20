import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { KeyRound } from 'lucide-react'
import PageHeader from '@/components/layout/page-header'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Form } from '@/components/ui/form'
import { SubscriptionFormActions } from '@/features/subscriptions/components/subscription-form-actions'
import ApiKeyModal from '@/features/api-keys/dialogs/api-key-modal'
import { McpServerCard } from '@/features/mcp/components/mcp-server-card'
import { McpEndpointCard } from '@/features/mcp/components/mcp-endpoint-card'
import { McpClientSnippets } from '@/features/mcp/components/mcp-client-snippets'
import { McpTargetSelect, MCP_TARGET_ME } from '@/features/mcp/components/mcp-target-select'
import { McpToolsTable } from '@/features/mcp/components/mcp-tools-table'
import { McpAccessPresets } from '@/features/mcp/components/mcp-access-presets'
import { mcpSettingsDefaultValues, mcpSettingsSchema, toMcpSettingsFormValues, type McpSettingsFormInput } from '@/features/mcp/forms/mcp-settings-form'
import { buildMcpUrl } from '@/features/mcp/utils/mcp-clients'
import { useAdmin } from '@/hooks/use-admin'
import { getErrorMessage } from '@/utils/error-utils'
import { hasPermission } from '@/utils/rbac'
import { getGetMcpSettingsQueryKey, getListMcpToolsQueryKey, useGetMcpSettings, useListApiKeys, useListMcpTools, useModifyMcpSettings } from '@/service/api'

export default function McpPage() {
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const queryClient = useQueryClient()
  const canUpdate = hasPermission(admin, 'mcp', 'update')
  const canCreateApiKey = hasPermission(admin, 'api_keys', 'create')
  const canReadApiKeys = hasPermission(admin, 'api_keys', 'read')
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false)
  const [target, setTarget] = useState(MCP_TARGET_ME)

  const apiKeyId = target === MCP_TARGET_ME ? undefined : Number(target)
  const params = apiKeyId ? { api_key_id: apiKeyId } : undefined

  const { data: settings, isLoading: isSettingsLoading, error: settingsError } = useGetMcpSettings(params)
  const { data: toolsResponse, isLoading: isToolsLoading } = useListMcpTools(params)
  const { data: apiKeysResponse } = useListApiKeys({ limit: 200, status: 'active' }, { query: { enabled: canReadApiKeys } })
  const apiKeys = useMemo(() => (apiKeysResponse?.api_keys ?? []).filter(key => key.admin_id === admin?.id), [apiKeysResponse, admin?.id])

  const form = useForm<McpSettingsFormInput>({
    resolver: zodResolver(mcpSettingsSchema),
    defaultValues: mcpSettingsDefaultValues,
  })

  useEffect(() => {
    if (settings) form.reset(toMcpSettingsFormValues(settings))
  }, [settings, form])

  const { mutateAsync: modifySettings, isPending: isSaving } = useModifyMcpSettings({
    mutation: {
      onSuccess: updated => {
        toast.success(t('mcp.saveSuccess'))
        queryClient.setQueryData(getGetMcpSettingsQueryKey(params), updated)
        queryClient.invalidateQueries({ queryKey: getGetMcpSettingsQueryKey(params) })
        queryClient.invalidateQueries({ queryKey: getListMcpToolsQueryKey(params) })
      },
      onError: (error: unknown) => {
        toast.error(t('mcp.saveFailed'), { description: getErrorMessage(error) })
      },
    },
  })

  const onSubmit = async (values: McpSettingsFormInput) => {
    if (!canUpdate) return
    try {
      await modifySettings({
        params,
        data: {
          enable: values.enable ?? false,
          oauth: apiKeyId ? undefined : (values.oauth ?? true),
          read_only: values.read_only ?? false,
          disabled_tools: values.disabled_tools ?? [],
        },
      })
    } catch {
      return
    }
  }

  const handleCancel = () => {
    form.reset(toMcpSettingsFormValues(settings))
    toast.success(t('mcp.cancelSuccess'))
  }

  const mcpUrl = useMemo(() => buildMcpUrl(settings?.endpoint_path ?? '/mcp'), [settings?.endpoint_path])
  const tools = useMemo(() => (toolsResponse?.tools ?? []).filter(tool => tool.allowed), [toolsResponse])
  const disabledTools = form.watch('disabled_tools') ?? []
  const readOnlyMode = !!form.watch('read_only')
  const toolsEnabled = tools.filter(tool => !disabledTools.includes(tool.name) && !(readOnlyMode && !tool.read_only)).length

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full transform-gpu">
        <PageHeader
          title="mcp.title"
          description="mcp.description"
          buttonIcon={canCreateApiKey ? KeyRound : undefined}
          buttonText={canCreateApiKey ? 'mcp.endpoint.createKey' : undefined}
          onButtonClick={canCreateApiKey ? () => setIsApiKeyModalOpen(true) : undefined}
        />
        <Separator />
      </div>

      <div className="w-full p-4">
        {isSettingsLoading && !settings ? (
          <div className="space-y-4">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-40" />
          </div>
        ) : settingsError ? (
          <div className="flex min-h-[300px] items-center justify-center">
            <p className="text-sm text-red-500">{t('mcp.loadFailed')}</p>
          </div>
        ) : (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-6 sm:gap-8">
              {apiKeys.length > 0 && <McpTargetSelect value={target} apiKeys={apiKeys} disabled={isSaving} onChange={setTarget} />}

              <McpServerCard form={form} disabled={!canUpdate} forApiKey={!!apiKeyId} toolsEnabled={toolsEnabled} toolsTotal={tools.length} />

              <McpEndpointCard mcpUrl={mcpUrl} canCreateApiKey={canCreateApiKey} canReadApiKeys={canReadApiKeys} onCreateApiKey={() => setIsApiKeyModalOpen(true)} />

              <McpClientSnippets mcpUrl={mcpUrl} oauthEnabled={!!form.watch('oauth')} />

              <div className="space-y-3">
                <div className="space-y-1">
                  <h3 className="text-base font-semibold sm:text-lg">{t('mcp.presets.title')}</h3>
                  <p className="text-muted-foreground text-xs sm:text-sm">{t('mcp.presets.description')}</p>
                </div>
                <McpAccessPresets
                  value={{ read_only: readOnlyMode, disabled_tools: disabledTools }}
                  defaultDisabledTools={settings?.default_disabled_tools ?? []}
                  tools={tools}
                  disabled={!canUpdate}
                  onChange={next => {
                    form.setValue('read_only', next.read_only, { shouldDirty: true })
                    form.setValue('disabled_tools', next.disabled_tools, { shouldDirty: true })
                  }}
                />
              </div>

              <div className="space-y-3">
                <div className="space-y-1">
                  <h3 className="text-base font-semibold sm:text-lg">{t('mcp.tools.title')}</h3>
                  <p className="text-muted-foreground text-xs sm:text-sm">{t('mcp.tools.description')}</p>
                </div>
                <McpToolsTable
                  tools={tools}
                  isLoading={isToolsLoading}
                  disabledTools={disabledTools}
                  defaultDisabledTools={settings?.default_disabled_tools ?? []}
                  readOnlyMode={readOnlyMode}
                  canUpdate={canUpdate}
                  onDisabledToolsChange={next => form.setValue('disabled_tools', next, { shouldDirty: true })}
                />
              </div>

              {canUpdate && (
                <div className="bg-background/80 sticky bottom-0 z-10 -mx-4 -mb-4 px-4 pb-4 backdrop-blur-md">
                  <SubscriptionFormActions onCancel={handleCancel} isSaving={isSaving} className="mt-0 sm:mt-0" />
                </div>
              )}
            </form>
          </Form>
        )}
      </div>

      {canCreateApiKey && <ApiKeyModal isDialogOpen={isApiKeyModalOpen} onOpenChange={setIsApiKeyModalOpen} editingApiKey={null} />}
    </div>
  )
}
