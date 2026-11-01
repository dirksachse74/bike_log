// Breadcrumb trail (DECISIONS 104): the way you came to a page below a main menu item, e.g.
// Inventory › Installed › Bottom bracket, or Bikes › TIME NXR › Groupset › Rear derailleur.
// Every page you open from another page is added; going back to a page in the trail (a crumb, the browser's
// back button) cuts the trail there; a main menu item starts a new trail. Opened directly (a bookmark, a
// fresh start), a page gets the trail of where it lives. Pages name themselves with useCrumb().
import { useEffect, useSyncExternalStore } from 'react'

export const MAIN: Record<string, string> = {
  '/': 'Overview',
  '/bikes': 'Bikes',
  '/maintenance': 'Maintenance',
  '/rides': 'Rides',
  '/inventory': 'Inventory',
  '/settings': 'Settings',
}

export const INVENTORY_TABS: [string, string][] = [
  ['available', 'Available spares'],
  ['service', 'Needs prep / repair'],
  ['installed', 'Installed'],
  ['shopping', 'Shopping list'],
  ['history', 'History'],
  ['life', 'Part life'],
  ['chains', 'Chains'],
  ['supplies', 'Supplies'],
  ['all', 'All parts'],
]

export const BIKE_TABS: [string, string][] = [
  ['overview', 'Parts and service'],
  ['rides', 'Rides'],
  ['incidents', 'Incidents'],
  ['maintenance', 'Maintenance'],
  ['costs', 'Costs'],
  ['history', 'Journal and history'],
]

// the tab a page was on is a crumb of its own (Inventory › Installed), so going back opens that tab again
export function tabLabel(pathname: string, search: string): string | null {
  const tab = new URLSearchParams(search).get('tab')
  if (!tab) return null
  const tabs = pathname === '/inventory' ? INVENTORY_TABS : /^\/bikes\/\d+$/.test(pathname) ? BIKE_TABS : null
  return tabs?.find(([k]) => k === tab)?.[1] ?? null
}

export const isMain = (pathname: string) => pathname in MAIN

// where a page lives when it was opened directly
function home(pathname: string): string[] {
  const parts = pathname.split('/').filter(Boolean)
  const up = parts.map((_, i) => '/' + parts.slice(0, i + 1).join('/'))
  return up.filter((p) => p !== pathname && (isMain(p) || /^\/bikes\/\d+$/.test(p) || /^\/inventory\/\d+$/.test(p)))
}

const MAX = 7 // main item + 6 pages; older steps drop out of the middle

export function nextTrail(trail: string[], pathname: string, search: string): string[] {
  const here = pathname + search
  if (isMain(pathname)) return [here]
  const at = trail.findIndex((t) => t.split('?')[0] === pathname)
  if (at >= 0) return [...trail.slice(0, at), here] // back to a page in the trail (its tab may have changed)
  const up = home(pathname)
  // nothing yet, or only the main item the page lives under: the trail of where it lives
  const base = trail.length === 0 || (trail.length === 1 && trail[0].split('?')[0] === up[0] && up.length > 1) ? up.map((p, i) => (i === 0 && trail.length ? trail[0] : p)) : trail
  const next = [...base, here]
  return next.length > MAX ? [next[0], ...next.slice(next.length - MAX + 1)] : next
}

// page names, by path; shared so a crumb keeps its name after you leave the page
type Labels = Record<string, string>
const KEY = 'bikelog.crumbs'
let labels: Labels = {}
try {
  labels = JSON.parse(sessionStorage.getItem(KEY + '.labels') ?? '{}') as Labels
} catch {
  labels = {}
}
const listeners = new Set<() => void>()

function setLabels(more: Labels) {
  if (Object.entries(more).every(([k, v]) => labels[k] === v)) return
  labels = { ...labels, ...more }
  try {
    sessionStorage.setItem(KEY + '.labels', JSON.stringify(labels))
  } catch {
    /* only a convenience */
  }
  listeners.forEach((l) => l())
}

export function useLabels(): Labels {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => labels,
  )
}

// A page names itself (and, if it knows them, the pages above it) once its data has loaded.
export function useCrumb(pathname: string, label: string | null | undefined, parents?: Labels) {
  const extra = JSON.stringify(parents ?? {})
  useEffect(() => {
    if (label) setLabels({ ...(JSON.parse(extra) as Labels), [pathname]: label })
  }, [pathname, label, extra])
}

export function loadTrail(): string[] {
  try {
    const t = JSON.parse(sessionStorage.getItem(KEY) ?? '[]')
    return Array.isArray(t) ? (t as string[]) : []
  } catch {
    return []
  }
}

export function saveTrail(t: string[]) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(t))
  } catch {
    /* only a convenience */
  }
}
