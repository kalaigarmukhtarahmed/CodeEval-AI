import React from 'react'
import { Activity, Clock, AlertTriangle, CheckCircle } from 'lucide-react'

export function StaticChecks({ checks = [] }) {
  if (checks.length === 0) return null

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <Activity size={18} color="var(--accent-mint)" />
          Static Analyzer Pipelines
        </h3>
      </div>

      <div className="checks-grid">
        {checks.map((check) => {
          const isCompleted = check.status === 'completed'
          const isSkipped = check.status === 'skipped'

          return (
            <div className="check-card" key={`${check.tool}-${check.status}`}>
              <div className="check-card-top">
                <span className="check-card-name">{check.tool}</span>
                <span className={`badge ${isCompleted ? 'badge-success' : isSkipped ? 'badge-neutral' : 'badge-high'}`}>
                  {check.status}
                </span>
              </div>

              <div className="check-card-meta">
                <span>Findings: <strong>{check.finding_count}</strong></span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={12} />
                  {check.duration_ms ? `${check.duration_ms} ms` : '—'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
