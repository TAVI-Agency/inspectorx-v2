import { useLocation } from 'react-router-dom'
import {
  Camera,
  Compass,
  FileCheck,
  FileText,
  MessageCircle,
  Package,
  Scale,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import { useMyLawyerProfile, useNotificationCenter } from '@/data/hooks'
import { ru } from '@/i18n/ru'

export interface NavItem {
  to: string
  end?: boolean
  label: string
  icon: LucideIcon
  badge?: number
  soon?: boolean
}

export interface NavSection {
  label?: string
  items: NavItem[]
}

/** Секции сайдбара: частое → «Проверки» (скоро) → «Кабинет юриста» (только verified) */
export function useNavSections(): NavSection[] {
  const { changesUnread } = useNotificationCenter()
  const { data: lawyerProfile } = useMyLawyerProfile()
  const verified = lawyerProfile?.status === 'verified'

  return [
    {
      items: [
        { to: '/catalog', end: true, label: ru.nav.registry, icon: Compass },
        { to: '/products', label: ru.nav.products, icon: Package, badge: changesUnread },
        { to: '/changes', label: ru.nav.changes, icon: TrendingUp, badge: changesUnread },
        { to: '/questions', label: ru.nav.questions, icon: MessageCircle },
      ],
    },
    {
      label: ru.nav.checksSection,
      items: [
        { to: '/checks/packaging', label: ru.nav.packaging, icon: Camera },
        { to: '/checks/documents', label: ru.nav.documents, icon: FileCheck, soon: true },
      ],
    },
    ...(verified
      ? [
          {
            label: ru.nav.lawyerSection,
            items: [
              { to: '/lawyer/queue', label: ru.nav.lawyerQueue, icon: Scale },
              { to: '/lawyer/reviews', label: ru.nav.lawyerReviews, icon: FileText },
            ],
          },
        ]
      : []),
  ]
}

const CRUMBS: [prefix: string, label: string][] = [
  ['/catalog', ru.nav.crumb.registry],
  ['/products', ru.nav.crumb.products],
  ['/changes', ru.nav.crumb.changes],
  ['/questions', ru.nav.crumb.questions],
  ['/checks/packaging', ru.nav.crumb.packaging],
  ['/checks/documents', ru.nav.crumb.documents],
  ['/lawyer/queue', ru.nav.crumb.lawyerQueue],
  ['/lawyer/reviews', ru.nav.crumb.lawyerReviews],
  ['/settings', ru.nav.crumb.settings],
  ['/help', ru.nav.crumb.help],
  ['/pricing', ru.nav.crumb.pricing],
  ['/product/', ru.nav.crumb.product],
  ['/service/', ru.nav.crumb.service],
  ['/login', ru.nav.crumb.login],
  ['/register', ru.nav.crumb.register],
  ['/auth/', ru.nav.crumb.login],
  ['/forgot-password', ru.nav.crumb.login],
  ['/cabinet', ru.nav.crumb.products],
]

/** Контекст страницы для минимальной шапки */
export function useRouteCrumb(): string {
  const { pathname } = useLocation()
  const hit = CRUMBS.find(([prefix]) => pathname.startsWith(prefix))
  return hit ? hit[1] : ru.nav.crumb.notFound
}
