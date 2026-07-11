import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { Layout } from './app/layout/Layout'
import { LandingPage } from './pages/landing/LandingPage'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { ProductPage } from './pages/product/ProductPage'
import { PricingPage } from './pages/pricing/PricingPage'
import { CabinetPage } from './pages/cabinet/CabinetPage'
import { AuthPage } from './pages/auth/AuthPage'
import { NotFoundPage } from './pages/NotFoundPage'

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
])

function App() {
  return <RouterProvider router={router} />
}

export default App
