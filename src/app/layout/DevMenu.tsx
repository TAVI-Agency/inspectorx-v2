import { Wrench } from 'lucide-react'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { useAppMode } from '@/app/app-mode'
import { ru } from '@/i18n/ru'

/** Дискретное dev-меню в футере: мок-режим «я подписчик» для демо клиенту */
export function DevMenu() {
  const { mockSubscriber, setMockSubscriber } = useAppMode()
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground/50 hover:text-muted-foreground"
            aria-label={ru.dev.menuTitle}
          />
        }
      >
        <Wrench />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72">
        <p className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
          {ru.dev.menuTitle}
        </p>
        <div className="mt-3 flex items-start gap-3">
          <Switch
            id="mock-subscriber"
            checked={mockSubscriber}
            onCheckedChange={setMockSubscriber}
          />
          <div className="space-y-1">
            <Label htmlFor="mock-subscriber">{ru.dev.mockSubscriber}</Label>
            <p className="text-xs text-muted-foreground">
              {ru.dev.mockSubscriberHint}
            </p>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
