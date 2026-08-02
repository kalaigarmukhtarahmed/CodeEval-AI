import React, { useState, useEffect } from 'react'
import { X, Wrench, ShieldCheck, CheckCircle2 } from 'lucide-react'
import { DiffViewer } from './DiffViewer'
import { VerificationResultCard } from './VerificationResultCard'

export function FixPreviewModal({ recommendation, finding, api, onClose, onApplied, onVerified, appliedFix, verification }) {
  const [proposal, setProposal] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [applying, setApplying] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [appliedResult, setAppliedResult] = useState(appliedFix)
  const [vResult, setVResult] = useState(verification)

  useEffect(() => {
    const fetchFix = async () => {
      setLoading(true)
      setError('')
      try {
        const prop = await api(`/recommendations/${recommendation.id}/preview`, { method: 'POST' })
        setProposal(prop)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchFix()
  }, [recommendation.id])

  const handleApply = async () => {
    if (!proposal) return
    setApplying(true)
    setError('')
    try {
      const res = await api(`/fixes/${proposal.id}/apply`, { method: 'POST' })
      setAppliedResult(res)
      if (onApplied) onApplied(recommendation.id, res)
    } catch (e) {
      setError(e.message)
    } finally {
      setApplying(false)
    }
  }

  const handleVerify = async () => {
    if (!proposal) return
    setVerifying(true)
    setError('')
    try {
      const v = await api(`/fixes/${proposal.id}/verify`, { method: 'POST' })
      setVResult(v)
      if (onVerified) onVerified(recommendation.id, v)
    } catch (e) {
      setError(e.message)
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '12px', borderBottom: '1px solid var(--border-color)' }}>
          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Single Fix Proposal Preview</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{recommendation.title}</p>
          </div>
          <button className="btn btn-outline" style={{ padding: '6px' }} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {loading && <p style={{ color: 'var(--text-muted)' }}>Generating fix patch preview...</p>}
        {error && <p className="error" style={{ color: '#ef4444', marginBottom: '16px' }}>{error}</p>}

        {proposal && !appliedResult && !vResult && (
          <>
            <div style={{ background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px', fontSize: '0.85rem', color: '#93c5fd' }}>
              <strong>PREVIEW ONLY — NO FILES MODIFIED ON DISK.</strong> Click Apply to create a new derived snapshot.
            </div>

            <DiffViewer diff={proposal.diff} filePath={proposal.file_path} />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
              <button className="btn btn-secondary" disabled={applying} onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={applying} onClick={handleApply}>
                {applying ? 'Applying...' : 'Apply Fix to Derived Snapshot'}
              </button>
            </div>
          </>
        )}

        {appliedResult && !vResult && (
          <>
            <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px', fontSize: '0.85rem', color: '#6ee7b7' }}>
              <strong>Fix applied to derived snapshot. Verification pending.</strong>
            </div>

            {proposal && <DiffViewer diff={proposal.diff} filePath={proposal.file_path} />}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
              <button className="btn btn-secondary" onClick={onClose}>Close</button>
              <button className="btn btn-primary" disabled={verifying} onClick={handleVerify}>
                {verifying ? 'Verifying...' : 'Verify Fix'}
              </button>
            </div>
          </>
        )}

        {vResult && (
          <>
            <VerificationResultCard verification={vResult} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
              <button className="btn btn-secondary" onClick={onClose}>Close</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
