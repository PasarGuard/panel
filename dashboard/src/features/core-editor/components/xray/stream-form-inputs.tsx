import { StringArrayPopoverInput } from '@/components/common/string-array-popover-input'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PasswordInput } from '@/components/ui/password-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ignoreValidity } from '@/features/core-editor/components/xray/stream-form-validity'
import { cleanStringList, formatTextInput, parseTrimmedTextInput, syncTypedText } from '@/features/core-editor/kit/stream-form-fields'
import type { ParsedInput, StreamFieldIssue } from '@/features/core-editor/kit/stream-form-fields'
import { cn } from '@/lib/utils'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

/** The i18next `t` the shared stream forms take as a prop (every call passes a literal key and an English `defaultValue`). */
export type StreamFormT = (key: string, options?: Record<string, unknown>) => string

const ISSUE_CLASS: Record<StreamFieldIssue['severity'], string> = {
  error: 'text-destructive',
  warning: 'text-amber-600 dark:text-amber-400',
  info: 'text-muted-foreground',
}

function IssueLines({ issues }: { issues: readonly StreamFieldIssue[] }) {
  if (issues.length === 0) return null
  return (
    <>
      {issues.map((issue, index) => (
        <p key={`${index}:${issue.code}`} className={cn('text-xs leading-relaxed', ISSUE_CLASS[issue.severity])}>
          {issue.message}
        </p>
      ))}
    </>
  )
}

/** The kit issues of one form field, one line each. */
export function FieldMessages({ issues, field }: { issues: readonly StreamFieldIssue[]; field: string }) {
  return <IssueLines issues={issues.filter(issue => issue.field === field)} />
}

/** The kit issues of every field outside `shownFields` (the fields that show their own messages). */
export function OtherFieldMessages({ issues, shownFields }: { issues: readonly StreamFieldIssue[]; shownFields: readonly string[] }) {
  return <IssueLines issues={issues.filter(issue => !shownFields.includes(issue.field))} />
}

const hintClass = 'text-muted-foreground text-xs leading-relaxed'

export interface ParsedTextFieldProps<T> {
  label: string
  hint?: string
  placeholder?: string
  multiline?: boolean
  /** Masks the text (single line only). */
  password?: boolean
  stored: T
  parse: (raw: string) => ParsedInput<T>
  format: (value: T) => string
  invalidMessage: string
  onValue: (value: T) => void
  onValidityChange: (invalid: boolean) => void
  children?: ReactNode
}

/**
 * A text input over a model value. The typed text lives here: it is written through `onValue` only when it parses,
 * and a model update replaces it only when the model now holds something else (`syncTypedText`), so text that does
 * not parse survives parent re-renders and form resets while `onValidityChange(true)` keeps Add/Modify blocked.
 */
export function ParsedTextField<T>({ label, hint, placeholder, multiline, password, stored, parse, format, invalidMessage, onValue, onValidityChange, children }: ParsedTextFieldProps<T>) {
  const id = useId()
  const [text, setText] = useState(() => format(stored))
  const latest = useRef({ stored, parse, format, onValidityChange })
  latest.current = { stored, parse, format, onValidityChange }
  const storedKey = JSON.stringify(stored ?? null)
  useEffect(() => {
    const { stored: current, parse: parseText, format: formatValue } = latest.current
    setText(prev => syncTypedText(prev, current, parseText, formatValue))
  }, [storedKey])
  const invalid = !parse(text).ok
  useEffect(() => {
    latest.current.onValidityChange(invalid)
  }, [invalid])
  // A field that goes away (another service or auth mode) no longer blocks anything.
  useEffect(() => {
    const field = latest
    return () => field.current.onValidityChange(false)
  }, [])

  const change = (raw: string) => {
    setText(raw)
    const parsed = parse(raw)
    if (parsed.ok) onValue(parsed.value)
  }

  return (
    <div className="grid w-full min-w-0 content-start gap-1.5">
      <Label htmlFor={id} className="text-sm">
        {label}
      </Label>
      {multiline ? (
        <Textarea
          id={id}
          dir="ltr"
          rows={4}
          value={text}
          placeholder={placeholder}
          aria-invalid={invalid || undefined}
          className={cn('font-mono text-xs', invalid && 'border-destructive')}
          onChange={event => change(event.target.value)}
        />
      ) : password ? (
        <PasswordInput id={id} dir="ltr" value={text} placeholder={placeholder} autoComplete="new-password" isError={invalid} className="h-10" onChange={event => change(event.target.value)} />
      ) : (
        <Input id={id} dir="ltr" value={text} placeholder={placeholder} isError={invalid} className="h-10" onChange={event => change(event.target.value)} />
      )}
      {hint && <p className={hintClass}>{hint}</p>}
      {invalid && <p className="text-destructive text-xs">{invalidMessage}</p>}
      {children}
    </div>
  )
}

export interface TrimmedTextFieldProps {
  label: string
  hint?: string
  placeholder?: string
  multiline?: boolean
  password?: boolean
  /** The model value; anything but a non-empty string shows as empty. */
  stored: unknown
  /** The trimmed text, or `undefined` when it is empty. */
  onValue: (value: string | undefined) => void
  children?: ReactNode
}

/** Free text written trimmed (`parseTrimmedTextInput`); spaces inside a value can be typed because the input keeps the raw text. */
export function TrimmedTextField({ stored, ...props }: TrimmedTextFieldProps) {
  return (
    <ParsedTextField
      {...props}
      stored={typeof stored === 'string' && stored !== '' ? stored : undefined}
      parse={parseTrimmedTextInput}
      format={formatTextInput}
      invalidMessage=""
      onValidityChange={ignoreValidity}
    />
  )
}

export interface StringListFieldProps {
  label: string
  hint?: string
  placeholder: string
  value: string[]
  /** The list with entries trimmed and blanks removed (`cleanStringList`). */
  onChange: (next: string[]) => void
  t: StreamFormT
  children?: ReactNode
}

export function StringListField({ label, hint, placeholder, value, onChange, t, children }: StringListFieldProps) {
  const id = useId()
  return (
    <div className="grid w-full min-w-0 content-start gap-1.5">
      <Label htmlFor={id} className="text-sm">
        {label}
      </Label>
      <StringArrayPopoverInput
        id={id}
        value={value}
        onChange={next => onChange(cleanStringList(next))}
        placeholder={placeholder}
        addPlaceholder={t('arrayInput.addPlaceholder', { defaultValue: 'Type and press Enter to add...' })}
        addButtonLabel={t('arrayInput.addButton', { defaultValue: 'Add' })}
        itemsLabel={t('arrayInput.items', { defaultValue: 'Items' })}
        emptyMessage={t('coreEditor.stringArrayPopover.emptyNoItems', { defaultValue: 'No items added.' })}
        duplicateErrorMessage={t('arrayInput.duplicateError', { defaultValue: 'This item already exists' })}
        clickToEditTitle={t('arrayInput.clickToEdit', { defaultValue: 'Click to edit' })}
        editItemTitle={t('arrayInput.editItem', { defaultValue: 'Edit item' })}
        removeItemTitle={t('arrayInput.removeItem', { defaultValue: 'Remove item' })}
        saveEditTitle={t('arrayInput.saveEdit', { defaultValue: 'Save edit' })}
        cancelEditTitle={t('arrayInput.cancelEdit', { defaultValue: 'Cancel edit' })}
        className="h-10 w-full max-w-none min-w-0"
      />
      {hint && <p className={hintClass}>{hint}</p>}
      {children}
    </div>
  )
}

export interface SelectFieldProps {
  label: string
  hint?: string
  value: string
  options: readonly { value: string; label: string }[]
  onValueChange: (value: string) => void
  disabled?: boolean
  children?: ReactNode
}

export function SelectField({ label, hint, value, options, onValueChange, disabled, children }: SelectFieldProps) {
  const id = useId()
  return (
    <div className="grid w-full min-w-0 content-start gap-1.5">
      <Label htmlFor={id} className="text-sm">
        {label}
      </Label>
      <Select dir="ltr" value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectTrigger id={id} className="h-10 w-full min-w-0" dir="ltr">
          <SelectValue />
        </SelectTrigger>
        <SelectContent dir="ltr">
          {options.map(option => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hint && <p className={hintClass}>{hint}</p>}
      {children}
    </div>
  )
}

/** A muted hint line outside a field. */
export function StreamFormHint({ children }: { children: ReactNode }) {
  return <p className={hintClass}>{children}</p>
}
