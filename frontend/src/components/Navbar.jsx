import React from 'react'
import { ShieldCheck, Search, Moon, Sun, Download, User, Code2, Sparkles } from 'lucide-react'

export function Navbar({ projectName, status, onExport }) {
  return (
    <header className="navbar">
      <div className="navbar-inner">
        <a href="/" className="navbar-brand">
          <div className="brand-logo">
            <ShieldCheck size={20} />
          </div>
          <span>CodeEval <span style={{ color: 'var(--accent-mint)' }}>AI</span></span>
        </a>

        {projectName && (
          <div className="navbar-project-title">
            <Code2 size={14} color="var(--accent-mint)" />
            <span>{projectName}</span>
            {status && (
              <span className={`badge ${status === 'completed' ? 'badge-success' : 'badge-low'}`}>
                {status}
              </span>
            )}
          </div>
        )}

        <div className="navbar-actions">
          {onExport && (
            <button className="btn btn-outline" onClick={onExport} title="Export Evaluation Report">
              <Download size={15} />
              <span>Export Report</span>
            </button>
          )}

          <div style={{ width: '1px', height: '20px', background: 'var(--border-color)' }} />

          <button className="btn btn-outline" style={{ padding: '8px' }} title="Toggle Theme">
            <Moon size={16} />
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 10px', background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '20px' }}>
            <User size={14} color="var(--text-muted)" />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 500 }}>Enterprise User</span>
          </div>
        </div>
      </div>
    </header>
  )
}
