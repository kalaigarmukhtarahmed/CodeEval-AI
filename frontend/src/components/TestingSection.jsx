import React from 'react'
import { TestTube, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'

export function TestingSection({ testRun }) {
  if (!testRun) return null

  const failures = testRun.failures || []

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <TestTube size={18} color="var(--accent-mint)" />
          Python Test Execution ({testRun.framework || 'pytest'})
        </h3>
        <span className={`badge ${testRun.status === 'completed' ? 'badge-success' : 'badge-high'}`}>
          Status: {testRun.status}
        </span>
      </div>

      <div className="metrics-grid">
        <div className="metric-box">
          <label>Collected</label>
          <span>{testRun.tests_collected ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Passed</label>
          <span style={{ color: 'var(--accent-mint)' }}>{testRun.tests_passed ?? 0}</span>
        </div>
        <div className="metric-box">
          <label>Failed</label>
          <span style={{ color: (testRun.tests_failed ?? 0) > 0 ? '#ef4444' : 'var(--text-main)' }}>
            {testRun.tests_failed ?? 0}
          </span>
        </div>
        <div className="metric-box">
          <label>Errors</label>
          <span style={{ color: (testRun.tests_errors ?? 0) > 0 ? '#ef4444' : 'var(--text-main)' }}>
            {testRun.tests_errors ?? 0}
          </span>
        </div>
        <div className="metric-box">
          <label>Coverage</label>
          <span>
            {testRun.coverage_percent !== null && testRun.coverage_percent !== undefined ? `${testRun.coverage_percent}%` : 'N/A'}
          </span>
        </div>
        <div className="metric-box">
          <label>Duration</label>
          <span>{testRun.duration_ms ? `${(testRun.duration_ms / 1000).toFixed(2)} s` : '—'}</span>
        </div>
      </div>

      {testRun.blocked_reason && (
        <div className="badge badge-medium" style={{ width: '100%', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px', justifyContent: 'flex-start' }}>
          <AlertTriangle size={16} />
          <span>{testRun.blocked_reason}</span>
        </div>
      )}

      {failures.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '0.9rem', color: '#ef4444', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <XCircle size={14} /> FAILED TESTS ({failures.length})
          </h4>
          <div className="findings-list">
            {failures.map((fail) => (
              <div className="finding-card" key={fail.id || fail.node_id}>
                <div className="finding-header" style={{ cursor: 'default' }}>
                  <div className="finding-main">
                    <span className="badge badge-critical">FAILED</span>
                    <span className="finding-title">{fail.node_id} · {fail.failure_type || 'Test Failure'}</span>
                  </div>
                  <code className="finding-path">{fail.file_path}</code>
                </div>
                <div className="finding-details">
                  <p style={{ color: '#f87171', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{fail.message}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
