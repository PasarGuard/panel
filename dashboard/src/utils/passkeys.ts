export const fromBase64Url = (value: string) =>
  Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (value.length % 4)) % 4)), char => char.charCodeAt(0))

export const toBase64Url = (value: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

export const serializeCredential = (credential: any) => ({
  id: credential.id,
  rawId: toBase64Url(credential.rawId),
  type: credential.type,
  response: Object.fromEntries(
    ['clientDataJSON', 'attestationObject', 'authenticatorData', 'signature', 'userHandle']
      .filter(key => credential.response[key])
      .map(key => [key, toBase64Url(credential.response[key])]),
  ),
})

export const getDefaultPasskeyName = () => {
  const userAgent = navigator.userAgent
  const browser = userAgent.includes('Edg/') ? 'Edge' : userAgent.includes('Chrome/') ? 'Chrome' : userAgent.includes('Firefox/') ? 'Firefox' : userAgent.includes('Safari/') ? 'Safari' : 'Browser'
  const platform = navigator.platform?.replace(/^Win\w+/, 'Windows').replace(/^Mac\w+/, 'macOS') || 'device'
  return `${browser} on ${platform}`
}
