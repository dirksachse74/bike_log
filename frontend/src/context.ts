import { createContext, useContext } from 'react'
import type { Meta } from './types'

export interface AppCtx {
  meta: Meta
  reloadMeta: () => void
  toast: (msg: string) => void
}

export const Ctx = createContext<AppCtx | null>(null)

export function useApp(): AppCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('App context missing')
  return c
}
