import React from 'react'
import { CheckCircle2, AlertTriangle, XCircle, ArrowRight } from 'lucide-react'

export function VerificationResultCard({ verification }) {
  if (!verification) return null

  const { status, target_details, scores } = verification
  const isVerified = status === 'verified'
  const isRegression = status === 'regression'
  const isPartiallyResolved = status === 'partially_resolved'

  return (
    <div style={{ background: 'var(--bg-card-subtle)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '24px', marginBottom: '24px' }}>
      <div style={{ marginBottom: '16px' }}>
        <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1.1rem', fontWeight: 700, color: isVerified ? 'var(--accent-mint)' : '#ef4444' }}>
          {isVerified && <CheckCircle2 size={20} />}
          {isRegression && <AlertTriangle size={20} />}
          {isPartiallyResolved && <AlertTriangle size={20} />}
          {!isVerified && !isRegression && !isPartiallyResolved && <XCircle size={20} />}
          {isVerified && '✓ Verified Resolved'}
          {isRegression && '⚠️ Regressions Detected'}
          {isPartiallyResolved && '⚠️ Partially Resolved'}
          {!isVerified && !isRegression && !isPartiallyResolved && '❌ Fix Not Resolved'}
        </h4>

        <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '4px' }}>
          {isVerified && 'All targeted findings were confirmed resolved with zero regressions after re-evaluation against the derived snapshot.'}
          {isRegression && 'The targeted finding(s) were resolved, but new findings were introduced by the patch.'}
          {isPartiallyResolved && 'Some targeted findings were resolved, but others persist after analysis.'}
          {!isVerified && !isRegression && !isPartiallyResolved && 'The targeted finding(s) still persist after re-evaluation.'}
        </p>

        {target_details && target_details.length > 0 && (
          <div style={{ marginTop: '12px' }}>
            <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase' }}>TARGETED FINDINGS ({target_details.length}):</label>
            <ul style={{ marginTop: '4px', paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text-main)' }}>
              {target_details.map((t, i) => (
                <li key={i}>
                  <strong>{t.rule_id}</strong> (<code>{t.file_path}</code>) — {t.status === 'resolved' ? <span style={{ color: 'var(--accent-mint)' }}>✓ Resolved</span> : <span style={{ color: '#ef4444' }}>❌ Not Resolved</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {scores && (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '16px' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', display: 'block', marginBottom: '8px' }}>
            BEFORE / AFTER DASHBOARD SCORE COMPARISON
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '1.25rem', fontWeight: 800 }}>
            <span style={{ color: 'var(--text-muted)' }}>{scores.before?.overall ?? 'N/A'}</span>
            <ArrowRight size={18} color="var(--accent-mint)" />
            <span style={{ color: 'var(--accent-mint)' }}>{scores.after?.overall ?? 'N/A'}</span>
          </div>
        </div>
      )}
    </div>
  )
}
