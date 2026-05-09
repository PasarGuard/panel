import { Input, type InputProps } from '@/components/ui/input'
import * as React from 'react'

type DecimalInputValue = number | null | undefined

export interface DecimalInputProps extends Omit<InputProps, 'value' | 'onChange' | 'onBlur' | 'type' | 'inputMode'> {
  value: DecimalInputValue
  onValueChange: (value: number | undefined) => void
  emptyValue?: number
  zeroValue?: number
  minimumValue?: number
  keepZeroOnBlur?: boolean
  toDisplayValue?: (value: number) => number | undefined
  toValue?: (displayValue: number) => number | undefined
  formatDisplayValue?: (displayValue: number) => string
  normalizeDisplayValueOnBlur?: (displayValue: number) => number
  onBlur?: React.FocusEventHandler<HTMLInputElement>
}

const DECIMAL_DRAFT_PATTERN = /^-?\d*\.?\d*$/

const isEmptyDraft = (value: string) => value === '' || value === '.' || value === '-' || value === '-.'

const defaultToDisplayValue = (value: number) => value
const defaultToValue = (value: number) => value
const defaultFormatDisplayValue = (value: number) => String(value)

export const DecimalInput = React.forwardRef<HTMLInputElement, DecimalInputProps>(
  (
    {
      value,
      onValueChange,
      emptyValue,
      zeroValue = emptyValue,
      minimumValue = 0,
      keepZeroOnBlur = false,
      toDisplayValue = defaultToDisplayValue,
      toValue = defaultToValue,
      formatDisplayValue = defaultFormatDisplayValue,
      normalizeDisplayValueOnBlur,
      onBlur,
      ...props
    },
    ref,
  ) => {
    const [rawInput, setRawInput] = React.useState('')
    const [isEditing, setIsEditing] = React.useState(false)

    const externalDisplayValue = React.useMemo(() => {
      if (value === null || value === undefined) return ''

      const displayValue = toDisplayValue(value)
      if (displayValue === undefined || !Number.isFinite(displayValue) || displayValue <= 0) return ''

      return formatDisplayValue(displayValue)
    }, [formatDisplayValue, toDisplayValue, value])

    React.useEffect(() => {
      if (isEditing) return
      if (keepZeroOnBlur && rawInput === '0' && externalDisplayValue === '') return
      if (rawInput !== '' && rawInput !== externalDisplayValue) {
        setRawInput('')
      }
    }, [externalDisplayValue, isEditing, keepZeroOnBlur, rawInput])

    const getStoredValue = React.useCallback(
      (displayValue: number) => {
        if (displayValue === 0) return zeroValue
        return toValue(displayValue) ?? emptyValue
      },
      [emptyValue, toValue, zeroValue],
    )

    const commitEmptyValue = React.useCallback(() => {
      onValueChange(emptyValue)
    }, [emptyValue, onValueChange])

    const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
      const nextRawInput = event.target.value.trim()

      if (!DECIMAL_DRAFT_PATTERN.test(nextRawInput)) return

      setRawInput(nextRawInput)
      setIsEditing(true)

      if (isEmptyDraft(nextRawInput)) {
        commitEmptyValue()
        return
      }

      const parsedValue = parseFloat(nextRawInput)
      if (!Number.isFinite(parsedValue) || parsedValue < minimumValue) return

      onValueChange(getStoredValue(parsedValue))
    }

    const handleBlur = (event: React.FocusEvent<HTMLInputElement>) => {
      const nextRawInput = rawInput.trim()
      setIsEditing(false)

      if (isEmptyDraft(nextRawInput)) {
        setRawInput('')
        commitEmptyValue()
        onBlur?.(event)
        return
      }

      const parsedValue = parseFloat(nextRawInput)
      if (!Number.isFinite(parsedValue) || parsedValue < minimumValue) {
        setRawInput('')
        commitEmptyValue()
        onBlur?.(event)
        return
      }

      const normalizedValue = normalizeDisplayValueOnBlur ? normalizeDisplayValueOnBlur(parsedValue) : parsedValue
      if (!Number.isFinite(normalizedValue) || normalizedValue < minimumValue) {
        setRawInput('')
        commitEmptyValue()
        onBlur?.(event)
        return
      }

      if (normalizedValue === 0 && !keepZeroOnBlur) {
        setRawInput('')
        commitEmptyValue()
        onBlur?.(event)
        return
      }

      setRawInput(formatDisplayValue(normalizedValue))
      onValueChange(getStoredValue(normalizedValue))
      onBlur?.(event)
    }

    const shouldKeepZeroDisplay = keepZeroOnBlur && rawInput === '0' && externalDisplayValue === ''
    const displayValue = isEditing || shouldKeepZeroDisplay ? rawInput : externalDisplayValue

    return <Input ref={ref} type="text" inputMode="decimal" value={displayValue} onChange={handleChange} onBlur={handleBlur} {...props} />
  },
)

DecimalInput.displayName = 'DecimalInput'
