import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CopyButton } from '@/components/common/copy-button'
import { buildMcpClientSnippets, MCP_KEY_PLACEHOLDER, type McpClientId } from '../utils/mcp-clients'

interface McpClientSnippetsProps {
  mcpUrl: string
  oauthEnabled: boolean
}

export function McpClientSnippets({ mcpUrl, oauthEnabled }: McpClientSnippetsProps) {
  const { t } = useTranslation()
  const snippets = useMemo(() => buildMcpClientSnippets(mcpUrl).filter(snippet => oauthEnabled || !snippet.oauth), [mcpUrl, oauthEnabled])
  const [activeId, setActiveId] = useState<McpClientId | null>(null)
  const active = snippets.find(snippet => snippet.id === activeId) ?? snippets[0]

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-base font-semibold sm:text-lg">{t('mcp.clients.title')}</h3>
          <p className="text-muted-foreground text-xs sm:text-sm">{t('mcp.clients.description', { placeholder: MCP_KEY_PLACEHOLDER })}</p>
        </div>
        <Select value={active.id} onValueChange={value => setActiveId(value as McpClientId)}>
          <SelectTrigger className="w-full sm:w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {snippets.map(snippet => (
              <SelectItem key={snippet.id} value={snippet.id}>
                {t(snippet.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <p className="text-muted-foreground text-xs sm:text-sm">{t(active.hintKey)}</p>
      <div className="relative">
        <pre dir="ltr" className="bg-muted overflow-x-auto rounded-md border p-3 pe-12 font-mono text-xs leading-relaxed whitespace-pre">
          {active.content}
        </pre>
        <div className="absolute end-2 top-2">
          <CopyButton value={active.content} showToast toastSuccessMessage="mcp.clients.copied" />
        </div>
      </div>
    </div>
  )
}
