import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useDebouncedSearch } from '@/hooks/use-debounced-search'
import { fetcher } from '@/service/http'
import { useQuery } from '@tanstack/react-query'
import { ChevronsUpDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { previewWorkspace, type WorkspacePreview } from './workspace-api'
import { configurationLabel, isRevisionConflict, workspaceErrorDetail, type WorkspaceChange } from './workspace-model'

export function WorkspacePreviewPanel({
  change,
  userAgent,
  canPreview,
  canReadSimple = false,
  draft,
  ready = true,
}: {
  change: WorkspaceChange
  userAgent: string
  canPreview: boolean
  canReadSimple?: boolean
  draft: boolean
  ready?: boolean
}) {
  const { t } = useTranslation()
  const [userId, setUserId] = useState('')
  const [username, setUsername] = useState('')
  const [userPickerOpen, setUserPickerOpen] = useState(false)
  const { debouncedSearch, setSearch } = useDebouncedSearch('', 300)
  const users = useQuery({
    queryKey: ['client-workspace-user-search', canReadSimple, debouncedSearch],
    enabled: canPreview && userPickerOpen,
    retry: false,
    queryFn: async ({ signal }) => {
      const result = await fetcher<{ users: { id: number; username: string }[] }>(canReadSimple ? '/api/users/simple' : '/api/users', {
        query: { search: debouncedSearch || undefined, limit: 8, offset: 0, sort: 'username' },
        signal,
      })
      return result.users.map(({ id, username }) => ({ id, username }))
    },
  })
  const [agent, setAgent] = useState(userAgent)
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  const [requestFingerprint, setRequestFingerprint] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fingerprint = JSON.stringify([change, userId, agent])
  const stale = preview && fingerprint !== requestFingerprint
  const sourceLabels: Record<string, string> = {
    subscription_profile: t('clientSettings.generator', 'Generator'),
    native_template: t('clientSettings.nativeDocument', 'Native document'),
    default_template: t('clientSettings.currentDefault', 'Current default'),
    built_in: t('clientSettings.builtIn', 'Built-in configuration'),
    blocked: t('clientSettings.blocked', 'Access denied'),
  }
  async function run() {
    setBusy(true)
    setError('')
    try {
      const result = await previewWorkspace({ ...change, user_id: Number(userId), user_agent: agent })
      setPreview(result)
      setRequestFingerprint(fingerprint)
    } catch (error) {
      setError(
        isRevisionConflict(error)
          ? t('clientSettings.previewConflict', 'Settings changed on the server. Your draft is preserved; reload after reviewing it.')
          : (workspaceErrorDetail(error) ?? t('clientSettings.previewFailed', 'Could not generate preview. Check user access and configuration validity.')),
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <aside className="bg-card min-w-0 space-y-4 rounded-xl border p-4 lg:sticky lg:top-4 lg:self-start">
      <div>
        <h2 className="font-semibold">{t('clientSettings.previewReceives', 'What the application receives')}</h2>
        <p className="text-muted-foreground mt-1 text-xs">
          {draft
            ? t('clientSettings.draftPreview', 'Preview includes your unsaved changes. Nothing is saved.')
            : t('clientSettings.savedPreview', 'Preview the current subscription response for a user.')}
        </p>
      </div>
      <div className="space-y-1 text-sm">
        <span>{t('clientSettings.previewUserName', 'User')}</span>
        <Popover open={userPickerOpen} onOpenChange={setUserPickerOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between" role="combobox" aria-expanded={userPickerOpen} disabled={!canPreview}>
              <span className="truncate">{username || t('clientSettings.selectUser', 'Select a user')}</span>
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[min(92vw,22rem)] p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput placeholder={t('clientSettings.searchUser', 'Search username')} onValueChange={setSearch} />
              <CommandList>
                {users.isError ? (
                  <p role="alert" className="text-destructive p-3 text-sm">
                    {t('clientSettings.userSearchFailed', 'Could not load users. Try searching again.')}
                  </p>
                ) : users.isFetching ? (
                  <p className="text-muted-foreground p-3 text-sm">{t('loading', 'Loading…')}</p>
                ) : (
                  <>
                    <CommandEmpty>{t('clientSettings.noUsers', 'No users found')}</CommandEmpty>
                    {users.data?.map(user => (
                      <CommandItem
                        key={user.id}
                        value={String(user.id)}
                        onSelect={() => {
                          setUserId(String(user.id))
                          setUsername(user.username)
                          setUserPickerOpen(false)
                        }}
                      >
                        {user.username}
                      </CommandItem>
                    ))}
                  </>
                )}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>
      <label className="block space-y-1 text-sm">
        User-Agent
        <Input value={agent} onChange={e => setAgent(e.target.value)} />
      </label>
      <Button className="w-full" variant="outline" disabled={!canPreview || !ready || busy || !Number.isInteger(Number(userId)) || Number(userId) < 1} onClick={run}>
        {busy ? t('clientSettings.previewing', 'Generating…') : t('clientSettings.previewAction', 'Generate preview')}
      </Button>
      {!ready && <p className="text-muted-foreground text-xs">{t('clientSettings.previewPending', 'Apply pending field changes and fix code errors before previewing.')}</p>}
      {!canPreview && <p className="text-muted-foreground text-xs">{t('clientSettings.previewPermission', 'User read permission is required to preview a subscription.')}</p>}
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
      {stale && (
        <p role="status" className="text-xs text-amber-600">
          {t('clientSettings.previewStale', 'The draft changed. Generate a new preview.')}
        </p>
      )}
      {preview && (
        <div className={`space-y-3 text-sm ${stale ? 'opacity-50' : ''}`}>
          {Boolean(preview.diagnostics?.errors?.length) && (
            <div role="alert" className="text-destructive space-y-2">
              <h3 className="font-medium">{t('clientSettings.generationErrors', 'Generation errors')}</h3>
              <ul className="list-inside list-disc space-y-1">
                {preview.diagnostics.errors.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            </div>
          )}
          {Boolean(preview.diagnostics?.exceptions?.length) && (
            <div className="text-muted-foreground space-y-2">
              <h3 className="font-medium">{t('clientSettings.generationExceptions', 'Excluded items and exceptions')}</h3>
              <ul className="list-inside list-disc space-y-1">
                {preview.diagnostics.exceptions.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            </div>
          )}
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 break-words">
            <dt className="text-muted-foreground">{t('clientSettings.rule', 'Rule')}</dt>
            <dd>{preview.matched_rule ? `#${preview.matched_rule.index + 1}` : '—'}</dd>
            <dt className="text-muted-foreground">{t('clientSettings.format', 'Response format')}</dt>
            <dd>{preview.effective_format ? t(`settings.subscriptions.configFormats.${preview.effective_format}`, configurationLabel(preview.effective_format)) : '—'}</dd>
            <dt className="text-muted-foreground">{t('clientSettings.source', 'Source')}</dt>
            <dd>{(preview.source?.kind === 'built_in' ? preview.happ?.name : null) ?? preview.source?.name ?? sourceLabels[preview.source?.kind ?? ''] ?? '—'}</dd>
            <dt className="text-muted-foreground">{t('clientSettings.status', 'Status')}</dt>
            <dd>{t(`hostsDialog.status.${preview.user_status === 'on_hold' ? 'onHold' : preview.user_status}`, preview.user_status)}</dd>
          </dl>
          {preview.matched_rule && <code className="bg-muted block overflow-auto rounded p-2 text-xs">{preview.matched_rule.pattern}</code>}
          {preview.happ && (
            <details open>
              <summary className="cursor-pointer font-medium">{t('clientSettings.happDecoded', 'Decoded Happ routing')}</summary>
              <pre className="bg-muted mt-2 max-h-72 overflow-auto rounded p-3 text-xs">{JSON.stringify(preview.happ.decoded, null, 2)}</pre>
              <p className="text-muted-foreground mt-2 text-xs">
                {preview.happ.transport} · {preview.happ.action}
              </p>
            </details>
          )}
          {Object.keys(preview.app_headers ?? {}).length > 0 && (
            <details>
              <summary className="cursor-pointer">{t('clientSettings.responseHeaders', 'Response headers (JSON)')}</summary>
              <pre className="bg-muted mt-2 max-h-52 overflow-auto rounded p-3 text-xs">{JSON.stringify(preview.app_headers, null, 2)}</pre>
            </details>
          )}
          <details>
            <summary className="cursor-pointer font-medium">
              {t('clientSettings.responseContent', 'Response content')} · {preview.content_encoding}
            </summary>
            <pre className="bg-muted mt-2 max-h-96 overflow-auto rounded p-3 text-xs">{preview.content ?? '—'}</pre>
          </details>
        </div>
      )}
      <p className="text-muted-foreground border-t pt-3 text-xs">{t('clientSettings.previewBoundary', 'Preview does not register a device or verify HWID access or traffic delivery.')}</p>
    </aside>
  )
}
