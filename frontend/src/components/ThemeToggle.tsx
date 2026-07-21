import { useEffect, useState } from 'react'
import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Three-state cycle: system → light → dark → system. The icon shows the
 * *currently rendered* theme (resolvedTheme), the click moves to the next.
 *
 * Renders a placeholder on the very first paint so SSR-style hydration
 * mismatch warnings stay quiet on cold load.
 */
export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  if (!mounted) {
    return <Button variant="ghost" size="icon" className="h-8 w-8" aria-hidden="true" />
  }

  const next = theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system'
  const Icon = resolvedTheme === 'dark' ? Moon : Sun

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      onClick={() => setTheme(next)}
      aria-label={`Switch theme (currently ${theme})`}
      title={`Theme: ${theme} (click for ${next})`}
    >
      <Icon className="h-4 w-4" />
    </Button>
  )
}
