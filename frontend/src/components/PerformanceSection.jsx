import React from 'react'
import { Zap, Cpu, Repeat, ShieldCheck, Gauge } from 'lucide-react'

export function PerformanceSection({ performanceAnalysis }) {
  if (!performanceAnalysis) return null

  const metrics = performanceAnalysis.metrics || {}
  const benchmarkInfo = performanceAnalysis.benchmark_information || {}
  const findings = performanceAnalysis.findings || []

  const isBenchmarkEnabled = benchmarkInfo.benchmark_enabled || performanceAnalysis.execution_mode === 'benchmark'
  const modeDisplay = isBenchmarkEnabled ? 'Benchmark Execution Enabled' : 'Static Analysis Only'

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <Zap size={18} color="var(--accent-mint)" />
          Performance & Complexity Analysis
        </h3>
        <span className="badge badge-neutral">
          <ShieldCheck size={12} /> {modeDisplay}
        </span>
      </div>

      <div className="metrics-grid">
        <div className="metric-box">
          <label>Functions</label>
          <span>{metrics.functions ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Loops</label>
          <span>{metrics.loops ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Nested Loops</label>
          <span style={{ color: (metrics.nested_loops ?? 0) > 0 ? '#ef4444' : 'var(--accent-mint)' }}>
            {metrics.nested_loops ?? 0}
          </span>
        </div>
        <div className="metric-box">
          <label>Average Complexity</label>
          <span>{metrics.average_complexity ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Performance Score</label>
          <span style={{ color: (performanceAnalysis.score ?? 100) >= 80 ? 'var(--accent-mint)' : '#eab308' }}>
            {performanceAnalysis.score ?? '—'} <small style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>/ 100</small>
          </span>
        </div>
        <div className="metric-box">
          <label>Benchmark Mode</label>
          <span style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-muted)' }}>
            {modeDisplay}
          </span>
        </div>
      </div>

      {findings.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '8px' }}>PERFORMANCE FINDINGS ({findings.length})</h4>
          <div className="findings-list">
            {findings.map((f) => (
              <div className="finding-card" key={f.id || `${f.rule}-${f.line}`}>
                <div className="finding-header" style={{ cursor: 'default' }}>
                  <div className="finding-main">
                    <span className={`badge badge-${f.severity?.toLowerCase() || 'medium'}`}>
                      {f.severity}
                    </span>
                    <span className="finding-title">{f.rule}: {f.message}</span>
                    <span style={{ fontSize: '0.8rem', color: '#ef4444', fontWeight: 600 }}>Penalty -{f.penalty}</span>
                  </div>
                  <code className="finding-path">{f.file_path}{f.line ? `:${f.line}` : ''}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
