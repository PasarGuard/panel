import { useTranslation } from 'react-i18next'
import { KeyRound, UserRound } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { APIKeyResponse } from '@/service/api'

export const MCP_TARGET_ME = 'me'

interface McpTargetSelectProps {
  value: string
  apiKeys: APIKeyResponse[]
  disabled?: boolean
  onChange: (value: string) => void
}

export function McpTargetSelect({ value, apiKeys, disabled = false, onChange }: McpTargetSelectProps) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-1">
        <h3 className="text-base font-semibold sm:text-lg">{t('mcp.target.title')}</h3>
        <p className="text-muted-foreground text-xs sm:text-sm">{t('mcp.target.description')}</p>
      </div>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger className="w-full sm:w-[260px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={MCP_TARGET_ME}>
            <span className="flex items-center gap-2">
              <UserRound className="h-4 w-4" />
              {t('mcp.target.me')}
            </span>
          </SelectItem>
          {apiKeys.map(key => (
            <SelectItem key={key.id} value={String(key.id)}>
              <span className="flex items-center gap-2">
                <KeyRound className="h-4 w-4" />
                {key.name}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
