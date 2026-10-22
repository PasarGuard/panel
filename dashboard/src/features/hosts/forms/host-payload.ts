import type { TransportSettings } from '@/service/api'
import type { HostFormValues } from './host-form'

/** Translate UI field names into the API's serialized XMux aliases. */
export function serializeTransportSettings(settings: HostFormValues['transport_settings']): TransportSettings | undefined {
  if (!settings) return undefined
  const xhttp = settings.xhttp_settings
  const xmux = xhttp?.xmux
  return {
    ...settings,
    xhttp_settings: xhttp
      ? {
          ...xhttp,
          xmux: xmux
            ? {
                maxConcurrency: xmux.max_concurrency,
                maxConnections: xmux.max_connections,
                cMaxReuseTimes: xmux.c_max_reuse_times,
                hMaxReusableSecs: xmux.h_max_reusable_secs,
                hMaxRequestTimes: xmux.h_max_request_times,
                hKeepAlivePeriod: xmux.h_keep_alive_period,
              }
            : undefined,
        }
      : undefined,
  }
}
