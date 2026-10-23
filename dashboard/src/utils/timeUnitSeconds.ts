/**
 * Converts an amount typed in a time unit to whole seconds.
 * The inputs accept decimals and the API fields are integers, so the product is rounded
 * (0.7 days is 60479.99999999999 seconds in floating point, which the API rejects).
 */
export const toWholeSeconds = (amount: number, unitSeconds: number): number => Math.round(amount * unitSeconds)

/**
 * Whole seconds for an amount that must be a positive adjustment, or undefined when it is not one:
 * an amount that rounds below one second (0.1 seconds) would otherwise be sent as a zero second change.
 */
export const toPositiveWholeSeconds = (amount: number, unitSeconds: number): number | undefined => {
  const seconds = toWholeSeconds(amount, unitSeconds)
  return seconds >= 1 ? seconds : undefined
}
