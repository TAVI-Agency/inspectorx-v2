import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { Layout } from './app/layout/Layout'
import { LandingPage } from './pages/landing/LandingPage'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { ProductPage } from './pages/product/ProductPage'
import { PricingPage } from './pages/pricing/PricingPage'
import { CabinetPage } from './pages/cabinet/CabinetPage'
import { AuthPage } from './pages/auth/AuthPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { BLayout } from './pages/b/BLayout'
import { BCatalogPage } from './pages/b/BCatalogPage'
import { BProductPage } from './pages/b/BProductPage'
import { BPricingPage } from './pages/b/BPricingPage'
import { BCabinetPage } from './pages/b/BCabinetPage'
import { BAuthPage } from './pages/b/BAuthPage'
import { BAdminPage } from './pages/b/BAdminPage'
import { CLayout } from './pages/c/CLayout'
import { CCatalogPage } from './pages/c/CCatalogPage'
import { CProductPage } from './pages/c/CProductPage'
import { CPricingPage } from './pages/c/CPricingPage'
import { CCabinetPage } from './pages/c/CCabinetPage'
import { CAuthPage } from './pages/c/CAuthPage'

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <LandingPage /> },
      { path: '/catalog', element: <CatalogPage /> },
      { path: '/product/:productId', element: <ProductPage /> },
      { path: '/pricing', element: <PricingPage /> },
      { path: '/app', element: <CabinetPage /> },
      { path: '/login', element: <AuthPage mode="login" /> },
      { path: '/register', element: <AuthPage mode="register" /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    path: '/b',
    element: <BLayout />,
    children: [
      { index: true, element: <BCatalogPage /> },
      { path: 'product/:productId', element: <BProductPage /> },
      { path: 'pricing', element: <BPricingPage /> },
      { path: 'cabinet', element: <BCabinetPage /> },
      { path: 'admin', element: <BAdminPage /> },
      { path: 'login', element: <BAuthPage mode="login" /> },
      { path: 'register', element: <BAuthPage mode="register" /> },
    ],
  },
  {
    path: '/c',
    element: <CLayout />,
    children: [
      { index: true, element: <CCatalogPage /> },
      { path: 'product/:productId', element: <CProductPage /> },
      { path: 'pricing', element: <CPricingPage /> },
      { path: 'cabinet', element: <CCabinetPage /> },
      { path: 'login', element: <CAuthPage mode="login" /> },
      { path: 'register', element: <CAuthPage mode="register" /> },
    ],
  },
])

function App() {
  return <RouterProvider router={router} />
}

export default App
