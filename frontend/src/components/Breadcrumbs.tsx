import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MAIN, isMain, loadTrail, nextTrail, saveTrail, tabLabel, useLabels } from '../crumbs'

// shown until the page has loaded its name
function fallback(path: string): string {
  if (/\/groupset$/.test(path)) return 'Groupset'
  if (path.startsWith('/bikes/')) return 'Bike'
  if (path.startsWith('/inventory/')) return 'Part'
  return '…'
}

// "Inventory › Installed › Bottom bracket": on every page below a main menu item, each step clickable.
export default function Breadcrumbs() {
  const { pathname, search } = useLocation()
  const here = pathname + search
  const labels = useLabels()
  const [state, setState] = useState(() => ({ at: here, trail: nextTrail(loadTrail(), pathname, search) }))
  let trail = state.trail
  if (state.at !== here) {
    trail = nextTrail(state.trail, pathname, search)
    setState({ at: here, trail })
    saveTrail(trail)
  }
  if (isMain(pathname)) return null
  const crumbs: { to: string; label: string }[] = []
  for (const step of trail) {
    const [path, query = ''] = step.split('?')
    const q = query ? `?${query}` : ''
    crumbs.push({ to: path, label: MAIN[path] ?? labels[path] ?? fallback(path) })
    const tab = tabLabel(path, q)
    if (tab) crumbs.push({ to: path + q, label: tab })
  }
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1
          return (
            <li key={`${i}-${c.to}`}>
              {last ? (
                <span aria-current="page" title={c.label}>
                  {c.label}
                </span>
              ) : (
                <Link to={c.to} title={c.label}>
                  {c.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
