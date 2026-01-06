import { useQuery } from '@tanstack/react-query'

interface CachedRelease {
  version: string
  url: string
  timestamp: number
}

interface NodeReleaseResult {
  latestVersion: string | null
  releaseUrl: string | null
  isLoading: boolean
  hasUpdate: (currentVersion: string | null) => boolean
}

const GITHUB_API_URL = 'https://api.github.com/repos/PasarGuard/node/releases/latest'
const CACHE_KEY = 'pg_node_release'
const CACHE_DURATION = 10 * 60 * 1000

function compareVersions(current: string, latest: string): number {
  const currentParts = current.replace(/^v/, '').split('.').map(Number)
  const latestParts = latest.replace(/^v/, '').split('.').map(Number)

  for (let i = 0; i < Math.max(currentParts.length, latestParts.length); i++) {
    const curr = currentParts[i] || 0
    const lat = latestParts[i] || 0
    if (curr < lat) return -1
    if (curr > lat) return 1
  }
  return 0
}

function getCached(): CachedRelease | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY)
    if (!cached) return null
    return JSON.parse(cached)
  } catch {
    return null
  }
}

function setCache(version: string, url: string): void {
  try {
    const data: CachedRelease = { version, url, timestamp: Date.now() }
    localStorage.setItem(CACHE_KEY, JSON.stringify(data))
  } catch {
    return
  }
}

async function fetchLatestNodeRelease(): Promise<{ version: string; url: string } | null> {
  const cached = getCached()
  if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
    return { version: cached.version, url: cached.url }
  }

  try {
    const response = await fetch(GITHUB_API_URL, {
      referrerPolicy: 'no-referrer',
      credentials: 'omit',
      headers: { Accept: 'application/vnd.github.v3+json' },
    })

    if (!response.ok) {
      return cached ? { version: cached.version, url: cached.url } : null
    }

    const data = await response.json()
    const version = data.tag_name?.replace(/^v/, '') || ''
    const url = data.html_url || ''

    if (version) setCache(version, url)
    return { version, url }
  } catch {
    return cached ? { version: cached.version, url: cached.url } : null
  }
}

export function useNodeReleases(): NodeReleaseResult {
  const { data, isLoading } = useQuery({
    queryKey: ['github-node-release-check'],
    queryFn: fetchLatestNodeRelease,
    staleTime: CACHE_DURATION,
    gcTime: CACHE_DURATION * 2,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchInterval: CACHE_DURATION,
    retry: 1,
  })

  const hasUpdate = (currentVersion: string | null) => {
    if (!currentVersion || !data?.version) return false
    const cleanCurrent = currentVersion.replace(/^v/, '')
    const cleanLatest = data.version.replace(/^v/, '')
    return compareVersions(cleanCurrent, cleanLatest) < 0
  }

  return {
    latestVersion: data?.version || null,
    releaseUrl: data?.url || null,
    isLoading,
    hasUpdate,
  }
}

