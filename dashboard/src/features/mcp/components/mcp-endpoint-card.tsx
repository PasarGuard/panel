import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { KeyRound, Link2, ShieldCheck } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { CopyButton } from '@/components/common/copy-button'

interface McpEndpointCardProps {
  mcpUrl: string
  canCreateApiKey: boolean
  canReadApiKeys: boolean
  onCreateApiKey: () => void
}

export function McpEndpointCard({ mcpUrl, canCreateApiKey, canReadApiKeys, onCreateApiKey }: McpEndpointCardProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="text-base font-semibold sm:text-lg">{t('mcp.endpoint.title')}</h3>
        <p className="text-muted-foreground text-xs sm:text-sm">{t('mcp.endpoint.description')}</p>
      </div>

      <div className="space-y-2">
        <label className="flex items-center gap-2 text-xs font-medium sm:text-sm">
          <Link2 className="h-4 w-4" />
          {t('mcp.endpoint.url')}
        </label>
        <div className="flex items-center gap-2">
          <Input value={mcpUrl} readOnly dir="ltr" className="font-mono text-xs sm:text-sm" onFocus={event => event.currentTarget.select()} />
          <CopyButton value={mcpUrl} showToast toastSuccessMessage="mcp.endpoint.copied" />
        </div>
      </div>

      <Alert>
        <ShieldCheck className="h-4 w-4" />
        <AlertTitle className="text-xs sm:text-sm">{t('mcp.endpoint.authTitle')}</AlertTitle>
        <AlertDescription className="text-muted-foreground text-xs sm:text-sm">{t('mcp.endpoint.authDescription')}</AlertDescription>
      </Alert>

      <div className="flex flex-col gap-2 sm:flex-row">
        {canCreateApiKey && (
          <Button type="button" variant="default" size="sm" onClick={onCreateApiKey} className="flex items-center gap-2">
            <KeyRound className="h-4 w-4" />
            {t('mcp.endpoint.createKey')}
          </Button>
        )}
        {canReadApiKeys && (
          <Button type="button" variant="outline" size="sm" asChild>
            <Link to="/api-keys">{t('mcp.endpoint.manageKeys')}</Link>
          </Button>
        )}
      </div>
    </div>
  )
}
