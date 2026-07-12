import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { NotFoundPage } from './pages/NotFoundPage'
import { CLayout } from './pages/c/CLayout'
import { CCatalogPage } from './pages/c/CCatalogPage'
import { CProductPage } from './pages/c/CProductPage'
import { CServicePage } from './pages/c/CServicePage'
import { CPricingPage } from './pages/c/CPricingPage'
import { CCabinetPage } from './pages/c/CCabinetPage'
import { CAuthPage } from './pages/c/CAuthPage'
import { LandingB } from './pages/landing-b/LandingB'

const router = createBrowserRouter([
  // Лендинг «Один маршрут» — самодостаточный, со своей шапкой и подвалом
  { path: '/', element: <LandingB /> },
  // Кокпит «Маршрут товара» (дизайн C) — продуктовая часть
  {
    element: <CLayout />,
    children: [
      { path: '/catalog', element: <CCatalogPage /> },
      { path: '/product/:productId', element: <CProductPage /> },
      { path: '/service/:serviceId', element: <CServicePage /> },
      { path: '/pricing', element: <CPricingPage /> },
      { path: '/cabinet', element: <CCabinetPage /> },
      { path: '/login', element: <CAuthPage mode="login" /> },
      { path: '/register', element: <CAuthPage mode="register" /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

function App() {
  return <RouterProvider router={router} />
}

export default App
