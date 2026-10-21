/**
 * Converts an amount typed in a time unit to whole seconds.
 * The inputs accept decimals and the API fields are integers, so the product is rounded
 * (0.7 days is 60479.99999999999 seconds in floating point, which the API rejects).
 */
export const toWholeSeconds = (amount: number, unitSeconds: number): number => Math.round(amount * unitSeconds)
