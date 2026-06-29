import App from '@/app/App'
import { installChunkLoadRecovery } from '@/utils/chunk-recovery'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

installChunkLoadRecovery()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
