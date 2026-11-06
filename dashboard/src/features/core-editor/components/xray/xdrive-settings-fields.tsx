import { FormLabel } from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import {
  FieldMessages,
  OtherFieldMessages,
  ParsedTextField,
  SelectField,
  StreamFormHint,
  StringListField,
  TrimmedTextField,
  type StreamFormT,
} from '@/features/core-editor/components/xray/stream-form-inputs'
import { useInvalidFieldsReporter } from '@/features/core-editor/components/xray/stream-form-validity'
import { cleanStringList, formatJsonObjectInput, formatNumberInput, isPlainObject, parseJsonObjectInput, setRecordKey, type ParsedInput } from '@/features/core-editor/kit/stream-form-fields'
import type { StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'
import {
  applyXdriveService,
  isXdriveGoogleDriveService,
  parseXdriveNumberInput,
  setXdriveGoogleDriveSecret,
  setXdriveS3Config,
  setXdriveS3Secret,
  XDRIVE_TUNING_FIELDS,
  xdriveGoogleDriveSecrets,
  xdriveS3Config,
  xdriveS3Secrets,
  xdriveServiceSelectOptions,
  type XdriveTuningField,
} from '@/features/core-editor/kit/xdrive-fields'
import { XDRIVE_DEFAULTS, XDRIVE_LIMITS, type XDriveService } from '@pasarguard/xray-config-kit'

export interface XdriveSettingsFieldsProps {
  /** the xdrive transport model (inbound, keeps `type`) or `streamSettings.xdriveSettings` (outbound) */
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  issues: readonly StreamFieldIssue[]
  onInvalidInputsChange: (fields: readonly string[]) => void
  t: StreamFormT
  /** Issue fields the surrounding form shows under its own inputs (for example `transport` and `security` under the outbound stream selects); the box does not repeat them. */
  shownElsewhere?: readonly string[]
}

function tuningLabel(field: XdriveTuningField, t: StreamFormT): string {
  switch (field) {
    case 'segmentBytes':
      return t('coreEditor.xdrive.segmentBytes', { defaultValue: 'Segment size (bytes)' })
    case 'flushIntervalMs':
      return t('coreEditor.xdrive.flushIntervalMs', { defaultValue: 'Flush interval (ms)' })
    case 'pollIntervalMs':
      return t('coreEditor.xdrive.pollIntervalMs', { defaultValue: 'Poll interval (ms)' })
    case 'maxPollIntervalMs':
      return t('coreEditor.xdrive.maxPollIntervalMs', { defaultValue: 'Max poll interval (ms)' })
    case 'sessionTtlSeconds':
      return t('coreEditor.xdrive.sessionTtlSeconds', { defaultValue: 'Session TTL (seconds)' })
    case 'concurrency':
      return t('coreEditor.xdrive.concurrency', { defaultValue: 'Concurrency' })
    case 'eagerWindowMs':
      return t('coreEditor.xdrive.eagerWindowMs', { defaultValue: 'Eager window (ms)' })
    case 'holeTimeoutMs':
      return t('coreEditor.xdrive.holeTimeoutMs', { defaultValue: 'Hole timeout (ms)' })
  }
}

function tuningHint(field: XdriveTuningField, t: StreamFormT): string | undefined {
  if (field === 'segmentBytes') return t('coreEditor.xdrive.capHint', { max: XDRIVE_LIMITS.segmentBytes, defaultValue: 'Xray caps this at {{max}}.' })
  if (field === 'concurrency') return t('coreEditor.xdrive.capHint', { max: XDRIVE_LIMITS.concurrency, defaultValue: 'Xray caps this at {{max}}.' })
  return undefined
}

function withEmptyObjectUnset(parsed: ParsedInput<Record<string, unknown> | undefined>): ParsedInput<Record<string, unknown> | undefined> {
  if (parsed.ok && parsed.value !== undefined && Object.keys(parsed.value).length === 0) return { ok: true, value: undefined }
  return parsed
}

const parseXmuxInput = (raw: string) => withEmptyObjectUnset(parseJsonObjectInput(raw))

/** XDrive transport settings shared by the inbound and outbound forms (XDrive runs on VLESS only). */
export function XdriveSettingsFields({ value, onChange, issues, onInvalidInputsChange, t, shownElsewhere = [] }: XdriveSettingsFieldsProps) {
  const report = useInvalidFieldsReporter(onInvalidInputsChange)
  const service = typeof value.service === 'string' ? value.service : ''
  const isGoogleDrive = isXdriveGoogleDriveService(service)
  const isTemplate = service === 'template'
  const isS3 = service === 's3'
  const secrets = xdriveGoogleDriveSecrets(value)
  const s3 = xdriveS3Config(value)
  const s3Secrets = xdriveS3Secrets(value)
  const shownFields = [
    'service',
    'remoteFolder',
    ...(isGoogleDrive || isTemplate || isS3 ? ['secrets'] : []),
    ...(isTemplate ? ['template'] : []),
    ...(isS3 ? ['s3', 's3.endpoint', 's3.region', 's3.bucket', 's3.pathStyle'] : []),
    'xmux',
    ...XDRIVE_TUNING_FIELDS,
    ...shownElsewhere,
  ]

  const serviceLabel = (option: string): string => {
    if (option === 'local') return t('coreEditor.xdrive.serviceLocal', { defaultValue: 'Local folder (local)' })
    if (option === 'template') return t('coreEditor.xdrive.serviceTemplate', { defaultValue: 'Custom template (template)' })
    if (option === 's3') return t('coreEditor.xdrive.serviceS3', { defaultValue: 'Amazon S3 / S3-compatible (s3)' })
    // Xray's own service name, in either spelling.
    if (isXdriveGoogleDriveService(option)) return 'Google Drive'
    return option
  }

  let folderLabel: string
  let folderHint: string | undefined
  if (service === 'local') {
    folderLabel = t('coreEditor.xdrive.folderLocal', { defaultValue: 'Folder path' })
    folderHint = t('coreEditor.xdrive.folderLocalHint', { defaultValue: 'A directory both sides can reach, mostly for testing.' })
  } else if (isGoogleDrive) {
    folderLabel = t('coreEditor.xdrive.folderGoogleDrive', { defaultValue: 'Folder ID' })
    folderHint = t('coreEditor.xdrive.folderGoogleDriveHint', { defaultValue: 'The ID of the Drive folder both sides share.' })
  } else if (isS3) {
    folderLabel = t('coreEditor.xdrive.folderS3', { defaultValue: 'Bucket Path / Prefix' })
    folderHint = t('coreEditor.xdrive.folderS3Hint', { defaultValue: 'Relative path or prefix inside the bucket.' })
  } else {
    folderLabel = t('coreEditor.xdrive.folderTemplate', { defaultValue: 'Folder' })
    folderHint = isTemplate ? t('coreEditor.xdrive.folderTemplateHint', { defaultValue: 'Optional. The template reads it as {folder}.' }) : undefined
  }

  const setKey = (key: string, next: unknown) => onChange(setRecordKey(value, key, next))
  const setSecret = (index: 0 | 1 | 2, text: string | undefined) => onChange(setXdriveGoogleDriveSecret(value, index, text))

  return (
    <div className="grid w-full min-w-0 gap-3 rounded-md border p-3 sm:col-span-2">
      <div className="grid gap-1">
        <p className="text-sm font-medium">{t('coreEditor.xdrive.title', { defaultValue: 'XDrive' })}</p>
        <StreamFormHint>{t('coreEditor.xdrive.tlsHint', { defaultValue: 'With XDrive, TLS settings only shape the HTTPS client that talks to the storage API.' })}</StreamFormHint>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label={t('coreEditor.xdrive.service', { defaultValue: 'Storage service' })}
          value={service}
          options={xdriveServiceSelectOptions(value.service).map(option => ({ value: option, label: serviceLabel(option) }))}
          onValueChange={next => {
            // The options other than the stored one all come from the kit's service list.
            if (next !== service) onChange(applyXdriveService(value, next as XDriveService))
          }}
        >
          <FieldMessages issues={issues} field="service" />
        </SelectField>
        <TrimmedTextField label={folderLabel} hint={folderHint} stored={value.remoteFolder} onValue={next => setKey('remoteFolder', next)}>
          <FieldMessages issues={issues} field="remoteFolder" />
        </TrimmedTextField>
      </div>

      {isGoogleDrive && (
        <div className="grid w-full min-w-0 gap-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <TrimmedTextField label={t('coreEditor.xdrive.clientId', { defaultValue: 'Client ID' })} stored={secrets[0]} onValue={next => setSecret(0, next)} />
            <TrimmedTextField label={t('coreEditor.xdrive.clientSecret', { defaultValue: 'Client secret' })} password stored={secrets[1]} onValue={next => setSecret(1, next)} />
            <TrimmedTextField label={t('coreEditor.xdrive.refreshToken', { defaultValue: 'Refresh token' })} password stored={secrets[2]} onValue={next => setSecret(2, next)} />
          </div>
          <StreamFormHint>{t('coreEditor.xdrive.googleDriveHint', { defaultValue: 'OAuth credentials of the Google account that owns the folder.' })}</StreamFormHint>
          <FieldMessages issues={issues} field="secrets" />
        </div>
      )}

      {isTemplate && (
        <>
          <StringListField
            label={t('coreEditor.xdrive.secrets', { defaultValue: 'Secrets' })}
            hint={t('coreEditor.xdrive.secretsHint', { defaultValue: 'The template reads them as {secret0}, {secret1} and so on.' })}
            placeholder={t('coreEditor.stringArrayPopover.noValuesPlaceholder', { defaultValue: 'No values' })}
            value={cleanStringList(value.secrets)}
            onChange={list => setKey('secrets', list.length > 0 ? list : undefined)}
            t={t}
          >
            <FieldMessages issues={issues} field="secrets" />
          </StringListField>
          <ParsedTextField
            label={t('coreEditor.xdrive.template', { defaultValue: 'Template (JSON object)' })}
            hint={t('coreEditor.xdrive.templateHint', { defaultValue: 'Describes the storage API requests.' })}
            multiline
            stored={isPlainObject(value.template) ? value.template : undefined}
            parse={parseJsonObjectInput}
            format={formatJsonObjectInput}
            invalidMessage={t('coreEditor.xdrive.templateInvalid', { defaultValue: 'The template must be a JSON object.' })}
            onValue={next => setKey('template', next)}
            onValidityChange={invalid => report('template', invalid)}
          >
            <FieldMessages issues={issues} field="template" />
          </ParsedTextField>
        </>
      )}

      {isS3 && (
        <div className="grid w-full min-w-0 gap-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <TrimmedTextField
              label={t('coreEditor.xdrive.s3Endpoint', { defaultValue: 'Endpoint URL' })}
              placeholder="https://s3.us-east-1.amazonaws.com"
              stored={s3.endpoint}
              onValue={next => onChange(setXdriveS3Config(value, 'endpoint', next ?? ''))}
            >
              <FieldMessages issues={issues} field="s3/endpoint" />
            </TrimmedTextField>
            <TrimmedTextField
              label={t('coreEditor.xdrive.s3Region', { defaultValue: 'Region' })}
              placeholder="us-east-1"
              stored={s3.region}
              onValue={next => onChange(setXdriveS3Config(value, 'region', next ?? ''))}
            >
              <FieldMessages issues={issues} field="s3/region" />
            </TrimmedTextField>
            <TrimmedTextField
              label={t('coreEditor.xdrive.s3Bucket', { defaultValue: 'Bucket Name' })}
              placeholder="my-bucket"
              stored={s3.bucket}
              onValue={next => onChange(setXdriveS3Config(value, 'bucket', next ?? ''))}
            >
              <FieldMessages issues={issues} field="s3/bucket" />
            </TrimmedTextField>
          </div>
          <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
            <div>
              <FormLabel className="text-sm font-medium">{t('coreEditor.xdrive.s3PathStyle', { defaultValue: 'Path-style addressing' })}</FormLabel>
              <StreamFormHint>{t('coreEditor.xdrive.s3PathStyleHint', { defaultValue: 'Use path-style URLs (endpoint/bucket) rather than virtual-hosted style.' })}</StreamFormHint>
            </div>
            <Switch
              checked={s3.pathStyle}
              onCheckedChange={checked => onChange(setXdriveS3Config(value, 'pathStyle', checked))}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <TrimmedTextField
              label={t('coreEditor.xdrive.s3AccessKeyId', { defaultValue: 'Access Key ID' })}
              stored={s3Secrets[0]}
              onValue={next => onChange(setXdriveS3Secret(value, 0, next))}
            />
            <TrimmedTextField
              label={t('coreEditor.xdrive.s3SecretAccessKey', { defaultValue: 'Secret Access Key' })}
              password
              stored={s3Secrets[1]}
              onValue={next => onChange(setXdriveS3Secret(value, 1, next))}
            />
            <TrimmedTextField
              label={t('coreEditor.xdrive.s3SessionToken', { defaultValue: 'Session Token (optional)' })}
              password
              stored={s3Secrets[2]}
              onValue={next => onChange(setXdriveS3Secret(value, 2, next))}
            />
          </div>
          <StreamFormHint>{t('coreEditor.xdrive.s3Hint', { defaultValue: 'Provide credentials and bucket configuration for S3 storage.' })}</StreamFormHint>
          <FieldMessages issues={issues} field="s3" />
          <FieldMessages issues={issues} field="secrets" />
        </div>
      )}

      <ParsedTextField
        label={t('coreEditor.xdrive.xmux', { defaultValue: 'XMUX (JSON object)' })}
        hint={t('coreEditor.xdrive.xmuxHint', {
          defaultValue: 'Optional connection reuse limits, as in XHTTP. Set maxConnections or maxConcurrency, not both.',
        })}
        multiline
        stored={isPlainObject(value.xmux) ? (value.xmux as Record<string, unknown>) : undefined}
        parse={parseXmuxInput}
        format={formatJsonObjectInput}
        invalidMessage={t('coreEditor.xdrive.xmuxInvalid', { defaultValue: 'XMUX must be a JSON object.' })}
        onValue={next => setKey('xmux', next)}
        onValidityChange={invalid => report('xmux', invalid)}
      >
        <FieldMessages issues={issues} field="xmux" />
      </ParsedTextField>

      <div className="grid gap-1">
        <p className="text-sm font-medium">{t('coreEditor.xdrive.tuning', { defaultValue: 'Tuning' })}</p>
        <StreamFormHint>{t('coreEditor.xdrive.tuningHint', { defaultValue: 'Empty or 0 uses the Xray default shown in each field.' })}</StreamFormHint>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {XDRIVE_TUNING_FIELDS.map(field => (
          <ParsedTextField
            key={field}
            label={tuningLabel(field, t)}
            hint={tuningHint(field, t)}
            placeholder={String(XDRIVE_DEFAULTS[field])}
            stored={typeof value[field] === 'number' ? (value[field] as number) : undefined}
            parse={parseXdriveNumberInput}
            format={formatNumberInput}
            invalidMessage={t('coreEditor.xdrive.numberInvalid', { defaultValue: 'Enter a whole number from 0 to 4294967295.' })}
            onValue={next => setKey(field, next)}
            onValidityChange={invalid => report(field, invalid)}
          >
            <FieldMessages issues={issues} field={field} />
          </ParsedTextField>
        ))}
      </div>

      <OtherFieldMessages issues={issues} shownFields={shownFields} />
    </div>
  )
}
