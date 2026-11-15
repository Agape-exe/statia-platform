import { ChartNoAxesCombined, LoaderCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
export function Brand() {
  return (
    <Link to="/" className="brand" aria-label="Statia Platform, inicio">
      <span className="brand-icon">
        <ChartNoAxesCombined size={23} />
      </span>
      statia<span className="brand-sub">PLATFORM</span>
    </Link>
  )
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} /> Cargando…
    </div>
  )
}
export function Alert({ children }: { children: ReactNode }) {
  return (
    <div className="alert" role="alert">
      {children}
    </div>
  )
}
