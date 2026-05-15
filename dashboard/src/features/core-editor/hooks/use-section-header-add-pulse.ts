import { useEffect, useRef } from 'react'

/** Emitted by the core editor PageHeader "+ Add" so only the active Xray section reacts. */
export type SectionHeaderAddPulse = { target: string; n: number }

/**
 * Opens "add" UI only for a deliberate header click on this section.
 * Bumps to {@link epoch} when the user changes core section/kind so a stale pulse cannot
 * fire after switching tabs (child useEffects run before a token reset would apply).
 */
export function useSectionHeaderAddPulseEffect(
  pulse: SectionHeaderAddPulse | undefined,
  epoch: number | undefined,
  sectionTarget: string,
  onPulse: () => void,
) {
  const epochRef = useRef(-1)
  const lastNRef = useRef(0)

  useEffect(() => {
    const ep = epoch ?? 0
    const p = pulse ?? { target: '', n: 0 }
    if (ep !== epochRef.current) {
      epochRef.current = ep
      lastNRef.current = p.n
      return
    }
    if (p.target !== sectionTarget) return
    if (!p.n || p.n === lastNRef.current) return
    lastNRef.current = p.n
    onPulse()
  }, [pulse, epoch, sectionTarget, onPulse])
}
