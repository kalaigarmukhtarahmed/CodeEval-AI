import React, { useState } from 'react'
import { Filter, ChevronDown, ChevronUp, AlertCircle, FileCode } from 'lucide-react'

export function FindingsSection({ findings = [] }) {
  const [filter, setFilter] = useState('all')
  const [expandedId, setExpandedId] = useState(null)

  const categories = ['all', 'architecture', 'security', 'maintainability', 'performance', 'testing', 'correctness']

  const visibleFindings = findings.filter(f => filter === 'all' || f.category === filter)

  const toggleExpand = (id) => {
    setExpandedId(prev => (prev === id ? null : id))
  }

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <AlertCircle size={18} color="var(--accent-mint)" />
          Detected Findings ({visibleFindings.length})
        </h3>
      </div>

      <div className="filter-bar">
        {categories.map((cat) => (
          <button
            key={cat}
            className={`filter-pill ${filter === cat ? 'active' : ''}`}
            onClick={() => setFilter(cat)}
          >
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </button>
        ))}
      </div>

      {visibleFindings.length === 0 ? (
        <div className="empty-state">
          <AlertCircle size={32} />
          <p>No findings detected for this filter.</p>
        </div>
      ) : (
        <div className="findings-list">
          {visibleFindings.map((finding) => {
            const isExpanded = expandedId === finding.id
            const sev = finding.severity?.toLowerCase() || 'medium'

            return (
              <div className="finding-card" key={finding.id}>
                <div className="finding-header" onClick={() => toggleExpand(finding.id)}>
                  <div className="finding-main">
                    <span className={`badge badge-${sev}`}>
                      {finding.severity}
                    </span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                      {finding.category} · {finding.tool} · {finding.rule_id}
                    </span>
                    <span className="finding-title">{finding.message}</span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <code className="finding-path">
                      {finding.file_path}{finding.line_start ? `:${finding.line_start}` : ''}
                    </code>
                    {isExpanded ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
                  </div>
                </div>

                {isExpanded && (
                  <div className="finding-details">
                    <div>
                      <strong>Rule ID:</strong> <code>{finding.rule_id}</code> | <strong>Tool:</strong> <span>{finding.tool}</span>
                    </div>
                    <div>
                      <strong>Message:</strong> <p style={{ color: 'var(--text-main)', marginTop: '4px' }}>{finding.message}</p>
                    </div>
                    {finding.evidence && (
                      <div>
                        <strong>Evidence:</strong>
                        <pre style={{ background: 'var(--bg-dark)', padding: '8px', borderRadius: '6px', fontSize: '0.8rem', marginTop: '4px', overflowX: 'auto' }}>
                          {finding.evidence}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
