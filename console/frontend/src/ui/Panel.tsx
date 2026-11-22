import type { ReactNode } from 'react'

export default function Panel({ title, meta, actions, children, className = '' }: {
  title: string; meta?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={`panel ${className}`} aria-label={title}>
      <header className="panel-head">
        <h2>{title}</h2>
        {meta && <span className="panel-meta">{meta}</span>}
        {actions && <div className="panel-actions">{actions}</div>}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  )
}
