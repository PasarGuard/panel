import { Button } from '@/components/ui/button'
import { FormControl, FormItem, FormLabel } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface TcpHeaderObfuscationFormProps {
  onValueChange: (value: Record<string, unknown>) => void
  currentValue: Record<string, unknown> | null
}

export function TcpHeaderObfuscationForm({ onValueChange, currentValue }: TcpHeaderObfuscationFormProps) {
  const { t } = useTranslation()

  // Parse current header value or initialize with defaults
  const parseHeaderValue = (): { type?: string; request: Record<string, unknown>; response: Record<string, unknown> } => {
    try {
      if (!currentValue || typeof currentValue !== 'object') {
        return {
          type: 'http',
          request: { version: '1.1', method: 'GET', path: ['/'], headers: {} },
          response: { version: '1.1', status: '200', reason: 'OK', headers: {} },
        }
      }
      const parsed = currentValue as Record<string, unknown>
      return {
        type: (parsed.type as string) ?? 'http',
        request: (parsed.request as Record<string, unknown>) ?? { version: '1.1', method: 'GET', path: ['/'], headers: {} },
        response: (parsed.response as Record<string, unknown>) ?? { version: '1.1', status: '200', reason: 'OK', headers: {} },
      }
    } catch {
      return {
        type: 'http',
        request: { version: '1.1', method: 'GET', path: ['/'], headers: {} },
        response: { version: '1.1', status: '200', reason: 'OK', headers: {} },
      }
    }
  }

  const { request, response } = parseHeaderValue()
  const requestHeaders = (request.headers as Record<string, string[]>) || {}
  const responseHeaders = (response.headers as Record<string, string[]>) || {}

  return (
    <div className="space-y-6">
      {/* Request Section */}
      <div className="space-y-4 rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold">{t('coreEditor.inbound.tcp.request.title', { defaultValue: 'Request' })}</h3>

        <div className="grid gap-4 sm:grid-cols-3">
          <FormItem>
            <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tcp.request.version', { defaultValue: 'Version' })}</FormLabel>
            <FormControl>
              <Select
                value={String(request.version ?? '1.1')}
                onValueChange={v => {
                  const updated = { ...currentValue, request: { ...request, version: v } } as Record<string, unknown>
                  onValueChange(updated)
                }}
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1.0">HTTP/1.0</SelectItem>
                  <SelectItem value="1.1">HTTP/1.1</SelectItem>
                  <SelectItem value="2">HTTP/2</SelectItem>
                  <SelectItem value="3">HTTP/3</SelectItem>
                </SelectContent>
              </Select>
            </FormControl>
          </FormItem>

          <FormItem>
            <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tcp.request.method', { defaultValue: 'Method' })}</FormLabel>
            <FormControl>
              <Select
                value={String(request.method ?? 'GET')}
                onValueChange={v => {
                  const updated = { ...currentValue, request: { ...request, method: v } } as Record<string, unknown>
                  onValueChange(updated)
                }}
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="GET">GET</SelectItem>
                  <SelectItem value="POST">POST</SelectItem>
                  <SelectItem value="PUT">PUT</SelectItem>
                  <SelectItem value="DELETE">DELETE</SelectItem>
                  <SelectItem value="HEAD">HEAD</SelectItem>
                  <SelectItem value="OPTIONS">OPTIONS</SelectItem>
                  <SelectItem value="PATCH">PATCH</SelectItem>
                  <SelectItem value="CONNECT">CONNECT</SelectItem>
                </SelectContent>
              </Select>
            </FormControl>
          </FormItem>

          <FormItem>
            <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tcp.request.path', { defaultValue: 'Paths (comma-separated)' })}</FormLabel>
            <FormControl>
              <Input
                className="h-9 text-xs"
                placeholder={t('coreEditor.inbound.tcp.request.pathPlaceholder', { defaultValue: '/, /api, /health' })}
                value={Array.isArray(request.path) ? request.path.join(', ') : String(request.path ?? '')}
                onChange={e => {
                  const paths = e.target.value.split(',').map(p => p.trim()).filter(Boolean)
                  const updated = { ...currentValue, request: { ...request, path: paths.length > 0 ? paths : ['/'] } } as Record<string, unknown>
                  onValueChange(updated)
                }}
              />
            </FormControl>
          </FormItem>
        </div>

        {/* Request Headers */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('coreEditor.inbound.tcp.request.headers', { defaultValue: 'Request Headers' })}
            </h4>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-6 w-6"
              onClick={() => {
                const newKey = `header_${Object.keys(requestHeaders).length}`
                const updated = {
                  ...currentValue,
                  request: {
                    ...request,
                    headers: { ...requestHeaders, [newKey]: [] },
                  },
                } as Record<string, unknown>
                onValueChange(updated)
              }}
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>

          {Object.entries(requestHeaders).map(([key, values]) => (
            <div key={key} className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:flex-nowrap">
              <Input
                placeholder={t('coreEditor.inbound.tcp.header.name', { defaultValue: 'Header name' })}
                className="h-8 min-w-[7rem] flex-1 text-xs sm:min-w-[8rem]"
                defaultValue={key}
                onBlur={e => {
                  if (e.target.value !== key) {
                    const newHeaders = { ...requestHeaders }
                    newHeaders[e.target.value] = newHeaders[key]
                    delete newHeaders[key]
                    const updated = {
                      ...currentValue,
                      request: { ...request, headers: newHeaders },
                    } as Record<string, unknown>
                    onValueChange(updated)
                  }
                }}
              />
              <Input
                placeholder={t('coreEditor.inbound.tcp.header.value', { defaultValue: 'Header value' })}
                className="h-8 min-w-0 flex-[2] text-xs"
                value={Array.isArray(values) ? values.join(', ') : String(values ?? '')}
                onChange={e => {
                  const newValues = e.target.value.split(',').map(v => v.trim())
                  const newHeaders = { ...requestHeaders, [key]: newValues }
                  const updated = {
                    ...currentValue,
                    request: { ...request, headers: newHeaders },
                  } as Record<string, unknown>
                  onValueChange(updated)
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 self-center border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                onClick={() => {
                  const newHeaders = { ...requestHeaders }
                  delete newHeaders[key]
                  const updated = {
                    ...currentValue,
                    request: { ...request, headers: newHeaders },
                  } as Record<string, unknown>
                  onValueChange(updated)
                }}
              >
                <Trash2 className="h-3.5 w-3.5 text-red-500" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      {/* Response Section */}
      <div className="space-y-4 rounded-lg border border-border p-4">
        <h3 className="text-sm font-semibold">{t('coreEditor.inbound.tcp.response.title', { defaultValue: 'Response' })}</h3>

        <div className="grid gap-4 sm:grid-cols-3">
          <FormItem>
            <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tcp.response.version', { defaultValue: 'Version' })}</FormLabel>
            <FormControl>
              <Select
                value={String(response.version ?? '1.1')}
                onValueChange={v => {
                  const updated = { ...currentValue, response: { ...response, version: v } } as Record<string, unknown>
                  onValueChange(updated)
                }}
              >
                <SelectTrigger className="h-9 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1.0">HTTP/1.0</SelectItem>
                  <SelectItem value="1.1">HTTP/1.1</SelectItem>
                  <SelectItem value="2">HTTP/2</SelectItem>
                  <SelectItem value="3">HTTP/3</SelectItem>
                </SelectContent>
              </Select>
            </FormControl>
          </FormItem>

          <FormItem>
            <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tcp.response.status', { defaultValue: 'Status' })}</FormLabel>
            <FormControl>
              <Input
                className="h-9 text-xs"
                placeholder={t('coreEditor.inbound.tcp.response.statusPlaceholder', { defaultValue: '200' })}
                type="number"
                min="100"
                max="599"
                value={String(response.status ?? '')}
                onChange={e => {
                  const updated = { ...currentValue, response: { ...response, status: e.target.value } } as Record<string, unknown>
                  onValueChange(updated)
                }}
              />
            </FormControl>
          </FormItem>

          <FormItem>
            <FormLabel className="text-xs font-medium">{t('coreEditor.inbound.tcp.response.reason', { defaultValue: 'Reason' })}</FormLabel>
            <FormControl>
              <Input
                className="h-9 text-xs"
                placeholder={t('coreEditor.inbound.tcp.response.reasonPlaceholder', { defaultValue: 'OK' })}
                value={String(response.reason ?? '')}
                onChange={e => {
                  const updated = { ...currentValue, response: { ...response, reason: e.target.value } } as Record<string, unknown>
                  onValueChange(updated)
                }}
              />
            </FormControl>
          </FormItem>
        </div>

        {/* Response Headers */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('coreEditor.inbound.tcp.response.headers', { defaultValue: 'Response Headers' })}
            </h4>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-6 w-6"
              onClick={() => {
                const newKey = `header_${Object.keys(responseHeaders).length}`
                const updated = {
                  ...currentValue,
                  response: {
                    ...response,
                    headers: { ...responseHeaders, [newKey]: [] },
                  },
                } as Record<string, unknown>
                onValueChange(updated)
              }}
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>

          {Object.entries(responseHeaders).map(([key, values]) => (
            <div key={key} className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:flex-nowrap">
              <Input
                placeholder={t('coreEditor.inbound.tcp.header.name', { defaultValue: 'Header name' })}
                className="h-8 min-w-[7rem] flex-1 text-xs sm:min-w-[8rem]"
                defaultValue={key}
                onBlur={e => {
                  if (e.target.value !== key) {
                    const newHeaders = { ...responseHeaders }
                    newHeaders[e.target.value] = newHeaders[key]
                    delete newHeaders[key]
                    const updated = {
                      ...currentValue,
                      response: { ...response, headers: newHeaders },
                    } as Record<string, unknown>
                    onValueChange(updated)
                  }
                }}
              />
              <Input
                placeholder={t('coreEditor.inbound.tcp.header.value', { defaultValue: 'Header value' })}
                className="h-8 min-w-0 flex-[2] text-xs"
                value={Array.isArray(values) ? values.join(', ') : String(values ?? '')}
                onChange={e => {
                  const newValues = e.target.value.split(',').map(v => v.trim())
                  const newHeaders = { ...responseHeaders, [key]: newValues }
                  const updated = {
                    ...currentValue,
                    response: { ...response, headers: newHeaders },
                  } as Record<string, unknown>
                  onValueChange(updated)
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 self-center border-red-500/20 transition-colors hover:border-red-500 hover:bg-red-50 dark:hover:bg-red-950/20"
                onClick={() => {
                  const newHeaders = { ...responseHeaders }
                  delete newHeaders[key]
                  const updated = {
                    ...currentValue,
                    response: { ...response, headers: newHeaders },
                  } as Record<string, unknown>
                  onValueChange(updated)
                }}
              >
                <Trash2 className="h-3.5 w-3.5 text-red-500" />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
