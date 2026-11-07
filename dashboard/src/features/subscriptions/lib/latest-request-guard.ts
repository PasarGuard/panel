export interface LatestRequestGuard {
  begin: () => number
  invalidate: () => void
  isCurrent: (requestId: number) => boolean
}

export function createLatestRequestGuard(): LatestRequestGuard {
  let currentRequestId = 0

  return {
    begin: () => ++currentRequestId,
    invalidate: () => {
      currentRequestId += 1
    },
    isCurrent: requestId => requestId === currentRequestId,
  }
}
