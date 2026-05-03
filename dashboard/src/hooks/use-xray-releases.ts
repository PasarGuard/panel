import { useQuery } from '@tanstack/react-query'

interface Release {
  version: string
  url: string
  isPrerelease?: boolean
}

interface CachedReleases {
  releases: Release[]
  timestamp: number
}

interface XrayReleaseResult {
  latestVersion: string | null
  releaseUrl: string | null
  versions: Release[]
  isLoading: boolean
  hasUpdate: (currentVersion: string | null) => boolean
}

const GITHUB_API_URL = 'https://api.github.com/repos/XTLS/Xray-core/releases?per_page=15'
const CACHE_KEY = 'pg_xray_releases'
const CACHE_DURATION = 10 * 60 * 1000

function compareVersions(current: string, latest: string): number {
  const currentParts = current
    .replace(/^v/, '')
    .split(/[\.-]/)
    .filter(p => !isNaN(Number(p)))
    .map(Number)
  const latestParts = latest
    .replace(/^v/, '')
    .split(/[\.-]/)
    .filter(p => !isNaN(Number(p)))
    .map(Number)

  for (let i = 0; i < Math.max(currentParts.length, latestParts.length); i++) {
    const curr = currentParts[i] || 0
    const lat = latestParts[i] || 0
    if (curr < lat) return -1
    if (curr > lat) return 1
  }
  return 0
}

function getCached(): CachedReleases | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY)
    if (!cached) return null
    return JSON.parse(cached)
  } catch {
    return null
  }
}

function setCache(releases: Release[]): void {
  try {
    const data: CachedReleases = { releases, timestamp: Date.now() }
    localStorage.setItem(CACHE_KEY, JSON.stringify(data))
  } catch {
    return
  }
}

async function fetchXrayReleases(): Promise<Release[]> {
  const cached = getCached()
  if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
    return cached.releases
  }

  try {
    const response = await fetch(GITHUB_API_URL, {
      referrerPolicy: 'no-referrer',
      credentials: 'omit',
      headers: { Accept: 'application/vnd.github.v3+json' },
    })

    if (!response.ok) {
      return cached?.releases || []
    }

    const data = await response.json()
    const releases: Release[] = data
      .filter((release: any) => !release.draft)
      .map((release: any) => ({
        version: release.tag_name?.replace(/^v/, '') || '',
        url: release.html_url || '',
        isPrerelease: !!release.prerelease,
      }))
      .filter((r: Release) => r.version)

    if (releases.length > 0) setCache(releases)
    return releases
  } catch {
    return cached?.releases || []
  }
}

export function useXrayReleases(): XrayReleaseResult {
  const { data, isLoading } = useQuery({
    queryKey: ['github-xray-releases'],
    queryFn: fetchXrayReleases,
    staleTime: CACHE_DURATION,
    gcTime: CACHE_DURATION * 2,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchInterval: CACHE_DURATION,
    retry: 1,
  })

  const releases = data || []
  const latestOfficialRelease = releases.find(r => !r.isPrerelease)
  const latestVersion = latestOfficialRelease?.version || null
  const releaseUrl = latestOfficialRelease?.url || null

  const hasUpdate = (currentVersion: string | null) => {
    if (!currentVersion || !latestVersion) return false
    const cleanCurrent = currentVersion.replace(/^v/, '')
    const cleanLatest = latestVersion.replace(/^v/, '')
    return compareVersions(cleanCurrent, cleanLatest) < 0
  }

  return {
    latestVersion,
    releaseUrl,
    versions: releases,
    isLoading,
    hasUpdate,
  }
}
