import { FormEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CircleCheck, CircleHelp, CircleX, Loader2, ScanSearch } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { RealityScanResult, scanRealityTarget } from '@/service/reality-scan'
import dayjs from '@/lib/dayjs'
import { dateUtils } from '@/utils/dateFormatter'
import { cn } from '@/lib/utils'

interface RealityScanDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTarget?: string
  initialSni?: string
}

const getErrorMessage = (error: unknown, fallback: string) => {
  if (!error || typeof error !== 'object') return fallback
  const maybeError = error as { data?: { detail?: string }; message?: string }
  return maybeError.data?.detail || maybeError.message || fallback
}

type TriState = boolean | null | undefined

function CheckRow({ status, label, detail }: { status: TriState; label: string; detail?: string }) {
  const icon =
    status === true ? (
      <CircleCheck className="h-4 w-4 shrink-0 text-green-500" />
    ) : status === false ? (
      <CircleX className="text-destructive h-4 w-4 shrink-0" />
    ) : (
      <CircleHelp className="text-muted-foreground h-4 w-4 shrink-0" />
    )
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        {icon}
        <span className="min-w-0 truncate text-sm">{label}</span>
      </div>
      {detail ? (
        <span className="text-muted-foreground shrink-0 font-mono text-xs" dir="ltr">
          {detail}
        </span>
      ) : null}
    </div>
  )
}

export function RealityScanDialog({ open, onOpenChange, initialTarget, initialSni }: RealityScanDialogProps) {
  const { t } = useTranslation()
  const [target, setTarget] = useState('')
  const [sni, setSni] = useState('')
  const [timeoutInput, setTimeoutInput] = useState('10')
  const [result, setResult] = useState<RealityScanResult | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (open) {
      abortRef.current?.abort()
      abortRef.current = null
      setTarget(initialTarget?.trim() ?? '')
      setSni(initialSni?.trim() ?? '')
      setResult(null)
      setErrorMessage(null)
      setIsScanning(false)
    }
  }, [open, initialTarget, initialSni])

  useEffect(() => () => abortRef.current?.abort(), [])

  const runScan = async () => {
    const trimmed = target.trim()
    if (!trimmed) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setIsScanning(true)
    setErrorMessage(null)
    try {
      const parsedTimeout = Number(timeoutInput)
      const response = await scanRealityTarget(
        {
          target: trimmed,
          sni: sni.trim() || undefined,
          timeout: Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : undefined,
        },
        controller.signal,
      )
      if (controller.signal.aborted) return
      setResult(response)
    } catch (error) {
      if (controller.signal.aborted) return
      setResult(null)
      setErrorMessage(getErrorMessage(error, t('coreEditor.realityScan.errorDescription', { defaultValue: 'Unable to scan this target.' })))
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
        setIsScanning(false)
      }
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    runScan()
  }

  const canScan = !!target.trim() && !isScanning

  const keyExchangeDetail =
    result?.curve ??
    (result?.x25519 === null ? t('coreEditor.realityScan.unknown', { defaultValue: 'Unknown' }) : result?.x25519 ? 'X25519' : t('coreEditor.realityScan.other', { defaultValue: 'Other' }))

  const formatExpiry = (iso: string | null) => {
    if (!iso) return null
    const d = dayjs(iso)
    if (!d.isValid()) return iso
    return `${d.fromNow()} (${dateUtils.formatDate(d.unix())})`
  }

  return (
    <CoreEditorFormDialog
      isDialogOpen={open}
      onOpenChange={onOpenChange}
      title={t('coreEditor.realityScan.title', { defaultValue: 'Scan Reality target' })}
      leadingIcon={<ScanSearch className="h-5 w-5 shrink-0" />}
      size="lg"
      inlinePersistValidation={false}
      footerExtra={
        <Button type="submit" form="reality-scan-form" disabled={!canScan}>
          {isScanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
          <span>{t('coreEditor.realityScan.scan', { defaultValue: 'Scan' })}</span>
        </Button>
      }
    >
      <div className="space-y-4">
        <p className="text-muted-foreground text-sm">
          {t('coreEditor.realityScan.description', {
            defaultValue: 'Probe a target to check it works as a REALITY decoy. REALITY needs HTTP/2 and TLS 1.3.',
          })}
        </p>

        <form id="reality-scan-form" onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_140px]">
          <div className="flex min-w-0 flex-col gap-2">
            <Label>{t('coreEditor.realityScan.target', { defaultValue: 'Target (host or host:port)' })}</Label>
            <Input
              className="h-10"
              value={target}
              onChange={event => {
                setTarget(event.target.value)
                setSni('')
              }}
              placeholder="www.microsoft.com:443"
              disabled={isScanning}
              dir="ltr"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <Label>{t('coreEditor.realityScan.timeout', { defaultValue: 'Timeout (s)' })}</Label>
            <Input className="h-10" value={timeoutInput} onChange={event => setTimeoutInput(event.target.value)} inputMode="numeric" type="number" min={1} max={20} disabled={isScanning} dir="ltr" />
          </div>
        </form>

        {errorMessage && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        )}

        <div>
          {isScanning && !result ? (
            <div className="flex min-h-48 items-center justify-center rounded-md border border-dashed">
              <div className="text-muted-foreground flex items-center gap-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('coreEditor.realityScan.loading', { defaultValue: 'Scanning target...' })}
              </div>
            </div>
          ) : result ? (
            <div className="space-y-4">
              <div
                className={cn(
                  'flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between',
                  result.feasible ? 'border-green-500/30 bg-green-500/10' : 'border-destructive/30 bg-destructive/10',
                )}
              >
                <div className="flex min-w-0 items-center gap-2">
                  {result.feasible ? <CircleCheck className="h-5 w-5 shrink-0 text-green-500" /> : <CircleX className="text-destructive h-5 w-5 shrink-0" />}
                  <span className="text-sm font-semibold">
                    {result.feasible
                      ? t('coreEditor.realityScan.feasible', { defaultValue: 'Suitable Reality target' })
                      : t('coreEditor.realityScan.notFeasible', { defaultValue: 'Not a suitable Reality target' })}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-muted-foreground truncate font-mono text-xs" dir="ltr">
                    {result.host}
                    {result.ip ? ` (${result.ip})` : ''}:{result.port}
                  </span>
                  {result.latency_ms !== null ? (
                    <Badge dir="ltr" variant="outline" className="shrink-0 font-mono text-xs">
                      {result.latency_ms} ms
                    </Badge>
                  ) : null}
                </div>
              </div>

              {result.reason ? (
                <Alert>
                  <AlertDescription dir="ltr" className="font-mono text-xs">
                    {result.reason}
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="divide-border rounded-md border px-3">
                <CheckRow status={result.tls13} label={t('coreEditor.realityScan.tls13', { defaultValue: 'TLS 1.3' })} detail={result.tls_version ? `TLS ${result.tls_version}` : undefined} />
                <Separator />
                <CheckRow status={result.h2} label={t('coreEditor.realityScan.h2', { defaultValue: 'HTTP/2 (ALPN)' })} detail={result.alpn ?? undefined} />
                <Separator />
                <CheckRow
                  status={result.x25519}
                  label={t('coreEditor.realityScan.keyExchange', { defaultValue: 'X25519 key exchange' })}
                  detail={keyExchangeDetail ?? undefined}
                />
                <Separator />
                <CheckRow
                  status={result.post_quantum}
                  label={t('coreEditor.realityScan.postQuantum', { defaultValue: 'Post-quantum (X25519MLKEM768)' })}
                  detail={
                    result.post_quantum === null
                      ? t('coreEditor.realityScan.unknown', { defaultValue: 'Unknown' })
                      : result.post_quantum
                        ? t('coreEditor.realityScan.supported', { defaultValue: 'Supported' })
                        : t('coreEditor.realityScan.notAdvertised', { defaultValue: 'Not offered' })
                  }
                />
                <Separator />
                <CheckRow
                  status={result.h3}
                  label={t('coreEditor.realityScan.h3', { defaultValue: 'HTTP/3 (advertised)' })}
                  detail={result.h3 ? t('coreEditor.realityScan.advertised', { defaultValue: 'Alt-Svc' }) : t('coreEditor.realityScan.notAdvertised', { defaultValue: 'Not advertised' })}
                />
                <Separator />
                <CheckRow
                  status={result.cert_valid}
                  label={t('coreEditor.realityScan.certificate', { defaultValue: 'Valid certificate' })}
                  detail={result.cert_issuer ?? undefined}
                />
              </div>

              <div className="text-muted-foreground grid gap-2 text-xs sm:grid-cols-2">
                {result.cert_subject ? (
                  <div className="min-w-0">
                    <span>{t('coreEditor.realityScan.subject', { defaultValue: 'Subject' })}: </span>
                    <span className="text-foreground break-all" dir="ltr">
                      {result.cert_subject}
                    </span>
                  </div>
                ) : null}
                {result.not_after ? (
                  <div className="min-w-0">
                    <span>{t('coreEditor.realityScan.expires', { defaultValue: 'Expires' })}: </span>
                    <span className="text-foreground" dir="ltr">
                      {formatExpiry(result.not_after)}
                    </span>
                  </div>
                ) : null}
              </div>

              {result.server_names.length ? (
                <div className="space-y-2">
                  <div className="text-muted-foreground text-xs font-medium">
                    {t('coreEditor.realityScan.serverNames', { defaultValue: 'Certificate server names (valid SNIs)' })}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {result.server_names.map(name => (
                      <Badge key={name} dir="ltr" variant="secondary" className="font-mono text-xs">
                        {name}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="text-muted-foreground flex min-h-48 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm">
              {t('coreEditor.realityScan.empty', { defaultValue: 'Enter a target host and run the scan.' })}
            </div>
          )}
        </div>
      </div>
    </CoreEditorFormDialog>
  )
}
