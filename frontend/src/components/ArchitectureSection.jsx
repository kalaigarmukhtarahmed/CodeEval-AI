import React from 'react'
import { Box, GitFork, RefreshCw, FileText, AlertCircle } from 'lucide-react'

export function ArchitectureSection({ architectureAnalysis }) {
  if (!architectureAnalysis) return null

  const metrics = architectureAnalysis.metrics || {}
  const findings = architectureAnalysis.findings || []

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <Box size={18} color="var(--accent-mint)" />
          Architecture & Dependency Structure
        </h3>
        <span className="badge badge-success">
          Status: {architectureAnalysis.status}
        </span>
      </div>

      <div className="metrics-grid">
        <div className="metric-box">
          <label>Modules</label>
          <span>{metrics.module_count ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Packages</label>
          <span>{metrics.package_count ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Dependency Edges</label>
          <span>{metrics.dependency_edge_count ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Circular Dependencies</label>
          <span style={{ color: (metrics.circular_dependency_count ?? 0) > 0 ? '#ef4444' : 'var(--accent-mint)' }}>
            {metrics.circular_dependency_count ?? 0}
          </span>
        </div>
        <div className="metric-box">
          <label>Largest Module</label>
          <span>{metrics.largest_file_lines ?? 0} <small style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>lines</small></span>
        </div>
        <div className="metric-box">
          <label>Docs Status</label>
          <span>{metrics.architecture_docs_present ? 'Present' : 'Missing'}</span>
        </div>
      </div>

      {architectureAnalysis.explanation && (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '16px', fontStyle: 'italic' }}>
          {architectureAnalysis.explanation}
        </p>
      )}

      {findings.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '8px' }}>ARCHITECTURE FINDINGS ({findings.length})</h4>
          <div className="findings-list">
            {findings.map((f) => (
              <div className="finding-card" key={f.id || f.rule_id}>
                <div className="finding-header" style={{ cursor: 'default' }}>
                  <div className="finding-main">
                    <span className={`badge badge-${f.severity?.toLowerCase() || 'medium'}`}>
                      {f.severity}
                    </span>
                    <span className="finding-title">{f.rule_id}: {f.message}</span>
                  </div>
                  <code className="finding-path">{f.file_path}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
