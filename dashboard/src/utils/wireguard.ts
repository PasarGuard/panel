import { generateKeyPair } from '@stablelib/x25519'

const bytesToBase64 = (bytes: Uint8Array) => {
  let binary = ''
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary)
}

export const generateWireGuardKeyPair = () => {
  const keyPair = generateKeyPair()
  return {
    privateKey: bytesToBase64(keyPair.secretKey),
    publicKey: bytesToBase64(keyPair.publicKey),
  }
}
