import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

// A real viewport lets the existing responsive cells render exactly as they do
// on the users page, including components with their own sm/md styles.
export function UserTablePreview({ mobile, children, title }: { mobile: boolean; children: ReactNode; title: string }) {
  const container = useRef<HTMLDivElement>(null)
  const [frameDocument, setFrameDocument] = useState<Document | null>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  const [contentHeight, setContentHeight] = useState(160)
  const width = mobile ? 390 : 1100
  const height = mobile ? 480 : 320
  const scale = Math.min(1, (containerWidth || width) / width)

  useEffect(() => {
    if (!container.current) return
    const observer = new ResizeObserver(entries => setContainerWidth(entries[0].contentRect.width))
    observer.observe(container.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!frameDocument) return
    const syncStyles = () => {
      frameDocument.head.replaceChildren(...Array.from(document.querySelectorAll('style, link[rel="stylesheet"]')).map(node => node.cloneNode(true)))
      frameDocument.documentElement.className = document.documentElement.className
      frameDocument.documentElement.dir = document.documentElement.dir
      frameDocument.documentElement.lang = document.documentElement.lang
    }
    syncStyles()
    const styles = new MutationObserver(syncStyles)
    styles.observe(document.head, { childList: true, subtree: true, characterData: true })
    const theme = new MutationObserver(syncStyles)
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'dir', 'lang'] })
    const root = frameDocument.getElementById('preview-root')!
    const size = new ResizeObserver(() => setContentHeight(Math.min(height, root.getBoundingClientRect().height + 16)))
    size.observe(root)
    return () => {
      styles.disconnect()
      theme.disconnect()
      size.disconnect()
    }
  }, [frameDocument, height])

  return (
    <div ref={container} className="overflow-hidden rounded-xl border" dir="ltr">
      <div inert className="pointer-events-none relative mx-auto" style={{ width: width * scale, height: contentHeight * scale }}>
        <iframe
          key={mobile ? 'mobile' : 'desktop'}
          title={title}
          tabIndex={-1}
          sandbox="allow-same-origin"
          srcDoc={'<!doctype html><html><head></head><body style="margin:0;padding:8px"><div id="preview-root"></div></body></html>'}
          onLoad={event => setFrameDocument(event.currentTarget.contentDocument)}
          className="absolute top-0 left-0 border-0"
          style={{ width, height, transform: `scale(${scale})`, transformOrigin: 'top left' }}
        />
      </div>
      {frameDocument?.getElementById('preview-root') && createPortal(children, frameDocument.getElementById('preview-root')!)}
    </div>
  )
}
