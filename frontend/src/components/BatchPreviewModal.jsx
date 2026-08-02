import React, { useState, useEffect } from 'react'
import { X, Layers, CheckCircle2 } from 'lucide-react'
import { DiffViewer } from './DiffViewer'
import { VerificationResultCard } from './VerificationResultCard'

export function BatchPreviewModal({
  evaluationId,
  selectedRecIds = [],
  api,
  onClose,
  onAppliedBatch,
  appliedBatch,
  batchVerification,
  onVerifiedBatch,
  onContinueFromSnapshot
}) {
  const [batch, setBatch] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [applying, setApplying] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [appliedResult, setAppliedResult] = useState(appliedBatch)
  const [verificationResult, setVerificationResult] = useState(batchVerification)

  useEffect(() => {
    const fetchBatch = async () => {
      setLoading(true)
      setError('')
      try {
        const b = await api(`/evaluations/${evaluationId}/fix-batches/preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recommendation_ids: selectedRecIds })
        })
        setBatch(b)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchBatch()
  }, [evaluationId, selectedRecIds])

  const handleApplyBatch = async () => {
    if (!batch) return
    setApplying(true)
    setError('')
    try {
      const result = await api(`/fix-batches/${batch.id}/apply`, { method: 'POST' })
      setAppliedResult(result)
      if (onAppliedBatch) onAppliedBatch(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setApplying(false)
    }
  }

  const handleVerifyBatch = async () => {
    const batchId = appliedResult?.batch_id || batch?.id
    if (!batchId) return
    setVerifying(true)
    setError('')
    try {
      const vResult = await api(`/fix-batches/${batchId}/verify`, { method: 'POST' })
      setVerificationResult(vResult)
      if (onVerifiedBatch) onVerifiedBatch(vResult)
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
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Batch Fix Proposal & Verification</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{selectedRecIds.length} Automatic Fixes Selected</p>
          </div>
          <button className="btn btn-outline" style={{ padding: '6px' }} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {loading && <p style={{ color: 'var(--text-muted)' }}>Generating batch fix preview...</p>}
        {error && <p className="error" style={{ color: '#ef4444', marginBottom: '16px' }}>{error}</p>}

        {batch && !appliedResult && !verificationResult && (
          <>
            <div style={{ background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px', fontSize: '0.85rem', color: '#93c5fd' }}>
              <strong>PREVIEW ONLY — NO FILES MODIFIED ON DISK.</strong> All {batch.fix_count} selected fixes will be applied together to ONE new derived snapshot.
            </div>

            <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              <span>Fixes: <code>{batch.fix_count}</code></span>
              <span>Files Changed: <code>{batch.files_changed_count}</code></span>
            </div>

            {batch.changes_json.map(change => (
              <DiffViewer key={change.file_path} diff={change.diff} filePath={change.file_path} />
            ))}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
              <button className="btn btn-secondary" disabled={applying} onClick={onClose}>Cancel</button>
              <button className="btn btn-primary" disabled={applying} onClick={handleApplyBatch}>
                {applying ? 'Applying Batch...' : `Apply ${batch.fix_count} Fixes`}
              </button>
            </div>
          </>
        )}

        {appliedResult && !verificationResult && (
          <>
            <div style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px', fontSize: '0.85rem', color: '#6ee7b7' }}>
              <strong>Changes applied to derived snapshot. Verification pending.</strong>
            </div>

            {batch && batch.changes_json.map(change => (
              <DiffViewer key={change.file_path} diff={change.diff} filePath={change.file_path} />
            ))}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
              <button className="btn btn-secondary" onClick={onClose}>Close</button>
              <button className="btn btn-primary" disabled={verifying} onClick={handleVerifyBatch}>
                {verifying ? 'Verifying Batch...' : 'Verify Changes'}
              </button>
            </div>
          </>
        )}

        {verificationResult && (
          <>
            <VerificationResultCard verification={verificationResult} />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
              <button className="btn btn-secondary" onClick={onClose}>Close</button>
              {onContinueFromSnapshot && (
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    onContinueFromSnapshot(verificationResult.derived_snapshot_id)
                    onClose()
                  }}
                >
                  Continue From This Snapshot →
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
