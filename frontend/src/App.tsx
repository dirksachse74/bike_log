import { useCallback, useEffect, useState } from 'react'
import { versionProblem } from './version'
import { HashRouter, NavLink, Route, Routes } from 'react-router-dom'
import { ErrorBox, Loading } from './components/ui'
import { Ctx } from './context'
import { setTimezone } from './format'
import { useApi } from './hooks'
import { BikeDetailPage, BikesPage } from './pages/Bikes'
import InventoryPage, { ComponentDetailPage } from './pages/Inventory'
import MaintenancePage from './pages/Maintenance'
import OverviewPage from './pages/Overview'
import RidesPage from './pages/Rides'
import SettingsPage from './pages/Settings'
import type { Meta } from './types'

const NAV = [
  ['/', 'Overview', '◎'],
  ['/bikes', 'Bikes', '🚲'],
  ['/maintenance', 'Maintenance', '🔧'],
  ['/rides', 'Rides', '↗'],
  ['/inventory', 'Inventory', '▤'],
  ['/settings', 'Settings', '⚙'],
] as const

export default function App() {
  const meta = useApi<Meta>('/meta')
  const [toastMsg, setToastMsg] = useState<string | null>(null)
  const toast = useCallback((m: string) => setToastMsg(m), [])
  useEffect(() => {
    if (!toastMsg) return
    const t = setTimeout(() => setToastMsg(null), 5000)
    return () => clearTimeout(t)
  }, [toastMsg])
  useEffect(() => {
    if (meta.data) setTimezone(meta.data.settings.timezone)
  }, [meta.data])

  if (meta.loading && !meta.data)
    return (
      <div className="boot">
        <Loading what="Starting Bike Log" />
      </div>
    )
  if (!meta.data)
    return (
      <div className="boot">
        <ErrorBox error={meta.error ?? 'No data'} onRetry={meta.reload} />
      </div>
    )
  return (
    <Ctx.Provider value={{ meta: meta.data, reloadMeta: meta.reload, toast }}>
      <HashRouter>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <img src="./logo.svg" alt="" width={32} height={32} />
              <span>Bike Log</span>
            </div>
            <nav aria-label="Main">
              {NAV.map(([to, label, icon]) => (
                <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}>
                  <span className="navicon" aria-hidden>
                    {icon}
                  </span>
                  <span className="navlabel">{label}</span>
                </NavLink>
              ))}
            </nav>
          </aside>
          <main className="main">
            {versionProblem(meta.data) && (
              <div className="demo-banner version-banner" role="alert">
                {versionProblem(meta.data)}
              </div>
            )}
            {meta.data.demo && <div className="demo-banner">Demo mode: sample data in a separate demo database. Your own data is not touched.</div>}
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/bikes" element={<BikesPage />} />
              <Route path="/bikes/:id" element={<BikeDetailPage />} />
              <Route path="/maintenance" element={<MaintenancePage />} />
              <Route path="/rides" element={<RidesPage />} />
              <Route path="/inventory" element={<InventoryPage />} />
              <Route path="/inventory/:id" element={<ComponentDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<p>Page not found.</p>} />
            </Routes>
          </main>
        </div>
        {toastMsg && (
          <div className="toast" role="status" onClick={() => setToastMsg(null)}>
            {toastMsg}
          </div>
        )}
      </HashRouter>
    </Ctx.Provider>
  )
}
