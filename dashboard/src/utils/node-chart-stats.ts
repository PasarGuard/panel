/** Ignore historical groups belonging to nodes that no longer exist. */
export const getCurrentNodeStats = <T>(stats: Record<string, T[]>, nodes: readonly { id: number }[], includeUnassigned = false): Record<string, T[]> => {
  const ids = new Set(nodes.map(node => String(node.id)))
  const entries = Object.entries(stats)
  return Object.fromEntries(entries.filter(([id]) => ids.has(id) || (includeUnassigned && id === '0') || (id === '-1' && entries.length === 1)))
}
