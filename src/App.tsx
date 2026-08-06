import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { NotFoundPage } from './pages/NotFoundPage'
import { CLayout } from './pages/c/CLayout'
import { CCatalogPage } from './pages/c/CCatalogPage'
import { CProductsPage } from './pages/c/CProductsPage'
import { CChangesPage } from './pages/c/CChangesPage'
import { CQuestionsPage } from './pages/c/CQuestionsPage'
import { CCheckAnnouncePage } from './pages/c/CCheckAnnouncePage'
import { CPackagingCheckPage, CPackagingReportPage } from './pages/c/checks/CPackagingCheckPage'
import { CSettingsPage } from './pages/c/CSettingsPage'
import { CHelpPage } from './pages/c/CHelpPage'
import { CProductPage } from './pages/c/CProductPage'
import { CServicePage } from './pages/c/CServicePage'
import { CPricingPage } from './pages/c/CPricingPage'
import { CLawyerQueuePage } from './pages/c/CLawyerQueuePage'
import { CLawyerReviewsPage } from './pages/c/CLawyerReviewsPage'
import { CAuthPage } from './pages/c/CAuthPage'
import { CConfirmEmailPage } from './pages/c/CConfirmEmailPage'
import { CForgotPasswordPage } from './pages/c/CForgotPasswordPage'
import { CResetPasswordPage } from './pages/c/CResetPasswordPage'
import { LandingB } from './pages/landing-b/LandingB'

const router = createBrowserRouter([
  // Лендинг «Один маршрут» — самодостаточный, со своей шапкой и подвалом
  { path: '/', element: <LandingB /> },
  // Кокпит «Маршрут товара» (дизайн C) — продуктовая часть
  {
    element: <CLayout />,
    children: [
      { path: '/catalog', element: <CCatalogPage /> },
      { path: '/products', element: <CProductsPage /> },
      { path: '/changes', element: <CChangesPage /> },
      { path: '/questions', element: <CQuestionsPage /> },
      { path: '/checks/packaging', element: <CPackagingCheckPage /> },
      { path: '/checks/packaging/:inspectionId', element: <CPackagingReportPage /> },
      { path: '/checks/documents', element: <CCheckAnnouncePage check="documents" /> },
      { path: '/settings', element: <CSettingsPage /> },
      { path: '/help', element: <CHelpPage /> },
      { path: '/product/:productId', element: <CProductPage /> },
      { path: '/service/:serviceId', element: <CServicePage /> },
      { path: '/pricing', element: <CPricingPage /> },
      // Старый кабинет разобран на разделы — ведём в портфель
      { path: '/cabinet', element: <Navigate to="/products" replace /> },
      { path: '/lawyer/queue', element: <CLawyerQueuePage /> },
      { path: '/lawyer/reviews', element: <CLawyerReviewsPage /> },
      { path: '/login', element: <CAuthPage mode="login" /> },
      { path: '/register', element: <CAuthPage mode="register" /> },
      { path: '/auth/confirm', element: <CConfirmEmailPage /> },
      { path: '/auth/reset', element: <CResetPasswordPage /> },
      { path: '/forgot-password', element: <CForgotPasswordPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

function App() {
  return <RouterProvider router={router} />
}

export default App
