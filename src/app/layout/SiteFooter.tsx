import { Link } from 'react-router-dom'
import { ru } from '@/i18n/ru'
import { DevMenu } from './DevMenu'

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[15px] font-semibold tracking-tight">
              Inspector<span className="text-primary">X</span>
            </p>
            <p className="mt-1 max-w-xs text-xs text-muted-foreground">
              {ru.common.tagline}
            </p>
          </div>
          <div className="space-y-1 text-sm">
            <p className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
              {ru.footer.contacts}
            </p>
            <p>
              <a href="mailto:hello@inspectorx.uz" className="hover:underline">
                {ru.footer.email}
              </a>
            </p>
            <p>
              <a
                href="https://t.me/inspectorx_uz"
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                {ru.footer.telegram}
              </a>
            </p>
          </div>
          <div className="max-w-xs space-y-1 text-xs text-muted-foreground">
            <p>{ru.footer.legal}</p>
            <p>{ru.footer.disclaimer}</p>
          </div>
        </div>
        <div className="mt-6 flex items-center justify-between border-t pt-4">
          <p className="font-mono text-[11px] text-muted-foreground">
            {ru.footer.rights}
          </p>
          <div className="flex items-center gap-4">
            <Link
              to="/b"
              className="text-xs text-muted-foreground transition-colors hover:text-primary"
            >
              Дизайн Б →
            </Link>
            <DevMenu />
          </div>
        </div>
      </div>
    </footer>
  )
}
