import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/app/theme'
import { ru } from '@/i18n/ru'

export function ThemeToggle() {
  const { resolved, toggle } = useTheme()
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      aria-label={ru.header.themeToggle}
      title={ru.header.themeToggle}
    >
      {resolved === 'dark' ? <Sun /> : <Moon />}
    </Button>
  )
}
