export interface ParsedXrayVersion {
  major: number
  minor: number
  patch: number
}

const VERSION_PATTERN = /^v?(\d+)\.(\d+)\.(\d+)$/

export function parseXrayVersion(v: string | null | undefined): ParsedXrayVersion | null {
  if (!v) return null
  const match = VERSION_PATTERN.exec(v.trim())
  if (!match) return null
  return { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]) }
}

export function compareXrayVersion(a: ParsedXrayVersion, b: ParsedXrayVersion): -1 | 0 | 1 {
  if (a.major !== b.major) return a.major > b.major ? 1 : -1
  if (a.minor !== b.minor) return a.minor > b.minor ? 1 : -1
  if (a.patch !== b.patch) return a.patch > b.patch ? 1 : -1
  return 0
}

/** Fail-open: returns false when `version` can't be parsed (unknown/"latest"/malformed). */
export function isXrayVersionAtLeast(version: string | null | undefined, cutoff: string): boolean {
  const parsedVersion = parseXrayVersion(version)
  const parsedCutoff = parseXrayVersion(cutoff)
  if (!parsedVersion || !parsedCutoff) return false
  return compareXrayVersion(parsedVersion, parsedCutoff) >= 0
}

// Verified directly against the raw XTLS/Xray-core Go source at each pinned tag
// (`infra/conf/transport_internet.go`), not commit ancestry or changelog reading.
//
// echForceQuery is deliberately NOT a gate here: it's a struct field that's fully
// removed (not a Build()-time error) at v26.6.22, and `@pasarguard/xray-config-kit`'s
// per-release parity data already tracks that — check `caps.securityFields.tls.echForceQuery`
// from `getInboundFormCapabilities()` instead of adding a second, hand-maintained cutoff here.
//
//   - allowInsecure (TLSConfig.AllowInsecure): field is never removed from the struct,
//     but Build() rejects `allowInsecure: true` unconditionally starting v26.6.22, and
//     on v26.4.25/v26.5.3 it was only a log warning until 2026-06-01 UTC, after which
//     the same binary starts hard-failing too — that date has already passed, so
//     v26.4.25+ hard-fails on any Xray-core running today regardless of exact patch.
//     This one stays a hand-written gate because it's a Build()-time semantic check,
//     not a schema/struct-presence fact — xray-config-kit's parity data can't see it.
//   - session*->sessionID* rename: still matches 26.6.22, unchanged. Kept here (rather
//     than sourced from caps) because the UI needs to read/write whichever of the two
//     key spellings is already present in a stored raw profile, not just show/hide a field.
export const XRAY_FEATURE_GATES = {
  allowInsecureHardError: '26.4.25',
  sessionIdFieldsRenamed: '26.6.22',
} as const
