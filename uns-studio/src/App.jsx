import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useSimStore } from './store/sim.store.js'
import { useAuthStore } from './store/auth.store.js'
import Layout from './components/layout/Layout.jsx'
import SimulatorPage from './components/simulator/SimulatorPage.jsx'
import LoginPage from './components/auth/LoginPage.jsx'

export default function App() {
  const init   = useSimStore((s) => s.init)
  const authed = useAuthStore((s) => s.authed)
  useEffect(() => { if (authed) init() }, [authed, init])

  if (!authed) return <LoginPage />

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/simulator" replace />} />
          <Route path="simulator" element={<SimulatorPage />} />
          <Route path="*" element={<Navigate to="/simulator" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
