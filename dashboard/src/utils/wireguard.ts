import { generateKeyPair, scalarMultBase } from '@stablelib/x25519'

const bytesToBase64 = (bytes: Uint8Array) => {
  let binary = ''
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary)
}

const base64ToBytes = (value: string) => {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

export const generateWireGuardKeyPair = () => {
  const keyPair = generateKeyPair()
  return {
    privateKey: bytesToBase64(keyPair.secretKey),
    publicKey: bytesToBase64(keyPair.publicKey),
  }
}

export const getWireGuardPublicKey = (privateKey: string) => {
  const trimmedKey = privateKey.trim()
  if (!trimmedKey) {
    return ''
  }

  try {
    const privateKeyBytes = base64ToBytes(trimmedKey)
    if (privateKeyBytes.length !== 32) {
      return ''
    }
    return bytesToBase64(scalarMultBase(privateKeyBytes))
  } catch {
    return ''
  }
}
