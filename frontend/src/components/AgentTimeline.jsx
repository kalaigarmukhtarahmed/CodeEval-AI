import React from 'react'
import { Activity, CheckCircle2, Clock } from 'lucide-react'

export function AgentTimeline({ items = [] }) {
  if (items.length === 0) return null

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <Activity size={18} color="var(--accent-mint)" />
          Agent Execution Activity Timeline
        </h3>
      </div>

      <div className="timeline">
        {items.map((item, idx) => {
          const msg = typeof item === 'string' ? item : item.message || String(item)
          return (
            <div className="timeline-item" key={idx}>
              <div className="timeline-dot" />
              <CheckCircle2 size={15} color="var(--accent-mint)" />
              <span style={{ fontWeight: 500, color: 'var(--text-main)' }}>{msg}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
