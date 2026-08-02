import React from 'react'
import { ShieldCheck, Inbox } from 'lucide-react'

export function EmptyState({ icon: Icon = Inbox, title = 'No Data Available', description = 'There are no items to display at this time.' }) {
  return (
    <div className="empty-state">
      <Icon size={36} color="var(--text-muted)" />
      <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginTop: '8px' }}>{title}</h4>
      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>{description}</p>
    </div>
  )
}
