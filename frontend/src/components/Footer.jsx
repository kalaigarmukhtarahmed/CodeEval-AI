import React from 'react'
import { ShieldCheck } from 'lucide-react'

export function Footer() {
  return (
    <footer className="footer">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '8px' }}>
        <ShieldCheck size={16} color="var(--accent-mint)" />
        <span style={{ fontWeight: 700, color: 'var(--text-main)' }}>CodeEval AI</span>
        <span>· Enterprise Software Quality Platform</span>
      </div>
      <p style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>
        Deterministic Static Evaluation · 6 Categories · Version 1.3
      </p>
    </footer>
  )
}
