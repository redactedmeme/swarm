import { useEffect } from 'react'

type Handler = (e: KeyboardEvent) => void

interface Shortcut {
  key: string
  meta?: boolean
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  handler: Handler
}

export function useKeyboard(shortcuts: Shortcut[]) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      for (const s of shortcuts) {
        const metaOk = s.meta ? e.metaKey || e.ctrlKey : true
        const ctrlOk = s.ctrl ? e.ctrlKey : true
        const shiftOk = s.shift ? e.shiftKey : !s.shift || e.shiftKey
        const altOk = s.alt ? e.altKey : true
        if (e.key.toLowerCase() === s.key.toLowerCase() && metaOk && ctrlOk && altOk) {
          const needShift = s.shift === true
          if (needShift && !e.shiftKey) continue
          if (!needShift && s.shift === false && e.shiftKey) continue
          e.preventDefault()
          s.handler(e)
          return
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [shortcuts])
}
