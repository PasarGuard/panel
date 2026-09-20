import { useTheme } from '@/app/providers/theme-provider'
import { Footer } from '@/components/layout/footer'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LoaderButton } from '@/components/ui/loader-button'
import { Switch } from '@/components/ui/switch'
import { PermissionCountBadge, PermissionEditor } from '@/features/admin-roles/components/permission-editor'
import { McpAccessPresets } from '@/features/mcp/components/mcp-access-presets'
import { McpToolsTable } from '@/features/mcp/components/mcp-tools-table'
import { RolePermissionFormMap, limitRolePermissionsToAllowed, sanitizeRolePermissions } from '@/features/admin-roles/forms/admin-role-form'
import { savePendingOAuthRequest } from '@/features/mcp/utils/oauth-request'
import useDirDetection from '@/hooks/use-dir-detection'
import { RolePermissions, useGetCurrentAdmin, useGetMcpOauthRequest, useGetMcpSettings, useListMcpTools, useMcpOauthConsent } from '@/service/api'
import { getAuthToken } from '@/utils/authStorage'
import { getErrorMessage, isAuthenticationError } from '@/utils/error-utils'
import { hasPermission } from '@/utils/rbac'
import { Bot, CircleAlertIcon, KeyRound, ShieldCheck } from 'lucide-react'
import { FC, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'

export const McpAuthorize: FC = () => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const navigate = useNavigate()
  const { resolvedTheme } = useTheme()
  const [searchParams] = useSearchParams()
  const request = searchParams.get('request') || ''
  const [redirecting, setRedirecting] = useState(false)
  const [inheritPermissions, setInheritPermissions] = useState(true)
  const [permissions, setPermissions] = useState<RolePermissionFormMap>({})
  const [consentError, setConsentError] = useState<string | null>(null)
  const [keyName, setKeyName] = useState<string | null>(null)
  const [mcpAccess, setMcpAccess] = useState<{ read_only: boolean; disabled_tools: string[] } | null>(null)
  const hasToken = !!getAuthToken()

  const { data: admin, error: adminError } = useGetCurrentAdmin({ query: { enabled: !!request && hasToken, retry: false } })
  const { data: info, error: requestError, isLoading } = useGetMcpOauthRequest({ request }, { query: { enabled: !!request && hasToken && !!admin, retry: false } })
  const { mutateAsync: consent, isPending } = useMcpOauthConsent()
  const canReadMcp = hasPermission(admin, 'mcp', 'read')
  const { data: mcpSettings } = useGetMcpSettings(undefined, { query: { enabled: !!admin && canReadMcp, retry: false } })
  const { data: mcpTools, isLoading: isToolsLoading } = useListMcpTools(undefined, { query: { enabled: !!admin && canReadMcp, retry: false } })
  const tools = useMemo(() => (mcpTools?.tools ?? []).filter(tool => tool.allowed), [mcpTools])
  // The key starts from the admin's own MCP settings and can only be narrowed
  const access = mcpAccess ?? { read_only: mcpSettings?.read_only ?? false, disabled_tools: mcpSettings?.disabled_tools ?? [] }

  useEffect(() => {
    if (!request) return
    if (!hasToken || isAuthenticationError(adminError)) {
      savePendingOAuthRequest(request)
      navigate('/login', { replace: true })
    }
  }, [request, hasToken, adminError, navigate])

  // Same ceiling as the API key dialog: owners may pick anything, others only what their role has
  const permissionCeiling = useMemo(() => (admin?.role?.is_owner ? undefined : sanitizeRolePermissions(admin?.role?.permissions)), [admin])
  const visiblePermissions = useMemo(() => limitRolePermissionsToAllowed(permissions, permissionCeiling), [permissions, permissionCeiling])

  useEffect(() => {
    if (!inheritPermissions && admin && Object.keys(permissions).length === 0) {
      setPermissions(permissionCeiling ?? sanitizeRolePermissions(admin.role?.permissions))
    }
  }, [inheritPermissions, admin, permissions, permissionCeiling])

  const answer = async (approve: boolean) => {
    setConsentError(null)
    try {
      const response = await consent({
        data: {
          request,
          approve,
          permissions: approve && !inheritPermissions ? (visiblePermissions as RolePermissions) : undefined,
          mcp: approve && mcpSettings ? access : undefined,
          name: approve ? (keyName ?? info?.key_name)?.trim() || undefined : undefined,
        },
      })
      setRedirecting(true)
      window.location.href = response.redirect_url
    } catch (err) {
      setConsentError(getErrorMessage(err))
    }
  }

  const error = !request ? t('mcp.authorize.invalid') : requestError ? getErrorMessage(requestError) : adminError && !isAuthenticationError(adminError) ? getErrorMessage(adminError) : null
  const busy = isPending || redirecting

  return (
    <div dir={dir} className="flex min-h-screen w-full flex-col items-center justify-center px-3 py-4 sm:p-4">
      <div className="flex w-full items-center justify-center">
        <div className="mt-6 w-full max-w-[560px]">
          <div className="flex flex-col items-center gap-2">
            <img src={resolvedTheme === 'dark' ? '/statics/favicon/logo.png' : '/statics/favicon/logo-dark.png'} alt="PasarGuard Logo" className="h-20 w-20 object-contain" />
            <span className="text-2xl font-semibold">{t('mcp.authorize.title')}</span>
            <span className="text-muted-foreground text-center">
              {info ? t('mcp.authorize.description', { client: info.client_name, username: admin?.username }) : isLoading ? t('loading', { defaultValue: 'Loading…' }) : null}
            </span>
          </div>

          <div className="mx-auto w-full pt-6">
            {error ? (
              <Alert variant="destructive">
                <CircleAlertIcon className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : (
              info && (
                <div className="flex flex-col gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="mcp-key-name">{t('mcp.authorize.keyName')}</Label>
                    <Input id="mcp-key-name" value={keyName ?? info.key_name} maxLength={128} disabled={busy} onChange={e => setKeyName(e.target.value)} />
                  </div>

                  <Accordion type="single" collapsible className="flex w-full flex-col gap-y-3">
                    {mcpSettings && (
                      <AccordionItem className="rounded-md border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="mcp">
                        <AccordionTrigger>
                          <div className="flex items-center gap-2">
                            <Bot className="h-4 w-4" />
                            <span>{t('mcp.authorize.access')}</span>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-1 pt-1">
                          <div className="space-y-3">
                            <p className="text-muted-foreground text-xs">{t('mcp.authorize.accessDescription')}</p>
                            <McpAccessPresets value={access} defaultDisabledTools={mcpSettings.default_disabled_tools ?? []} tools={tools} disabled={busy} onChange={setMcpAccess} />
                            <McpToolsTable
                              tools={tools}
                              isLoading={isToolsLoading}
                              disabledTools={access.disabled_tools}
                              defaultDisabledTools={mcpSettings.default_disabled_tools ?? []}
                              readOnlyMode={access.read_only}
                              canUpdate={!busy}
                              onDisabledToolsChange={next => setMcpAccess({ ...access, disabled_tools: next })}
                            />
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    )}
                    <AccordionItem className="rounded-md border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline" value="permissions">
                      <AccordionTrigger>
                        <div className="flex items-center gap-2">
                          <KeyRound className="h-4 w-4" />
                          <span>{t('mcp.authorize.permissions')}</span>
                          {!inheritPermissions && <PermissionCountBadge permissions={visiblePermissions} />}
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-1 pt-1">
                        <div className="space-y-3">
                          <div className="flex cursor-pointer flex-row items-center justify-between gap-3 rounded-lg border p-4" onClick={() => setInheritPermissions(prev => !prev)}>
                            <div className="space-y-0.5">
                              <span className="text-base font-medium">{t('apiKeys.inheritPermissions', { defaultValue: 'Inherit admin permissions' })}</span>
                              <p className="text-muted-foreground text-sm">
                                {t('apiKeys.inheritPermissionsDescription', { defaultValue: "Use the owning admin's current role permissions. Disable to store custom permissions on this key." })}
                              </p>
                            </div>
                            <div onClick={e => e.stopPropagation()}>
                              <Switch checked={inheritPermissions} onCheckedChange={setInheritPermissions} disabled={busy} />
                            </div>
                          </div>
                          {!inheritPermissions && <PermissionEditor permissions={visiblePermissions} onPermissionsChange={setPermissions} allowedPermissions={permissionCeiling} />}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>

                  <div className="bg-muted/40 text-muted-foreground flex items-start gap-2 rounded-lg border p-3 text-sm">
                    <Bot className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{t('mcp.authorize.scope')}</span>
                  </div>
                  {consentError && (
                    <Alert variant="destructive">
                      <CircleAlertIcon className="h-4 w-4" />
                      <AlertDescription>{consentError}</AlertDescription>
                    </Alert>
                  )}
                  <div className="flex flex-col gap-2 sm:flex-row-reverse">
                    <LoaderButton isLoading={busy} className="flex w-full items-center gap-2 sm:flex-1" onClick={() => answer(true)}>
                      <ShieldCheck className="h-4 w-4" />
                      {t('mcp.authorize.approve')}
                    </LoaderButton>
                    <Button type="button" variant="outline" className="w-full sm:flex-1" disabled={busy} onClick={() => answer(false)}>
                      {t('mcp.authorize.deny')}
                    </Button>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      </div>
      <Footer />
    </div>
  )
}

export default McpAuthorize
