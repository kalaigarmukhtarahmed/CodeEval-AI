import React, { useState, useEffect } from 'react'
import { Sparkles, CheckSquare, Wrench, ShieldAlert, ArrowRight, CheckCircle2 } from 'lucide-react'

export function RecommendationsSection({
  evaluationId,
  findings = [],
  api,
  onPreviewFix,
  onOpenBatchModal,
  selectedIds,
  onToggleSelect,
  appliedFixes,
  verifications
}) {
  const [recommendations, setRecommendations] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchRecommendations = async () => {
    setLoading(true)
    setError('')
    try {
      const recs = await api(`/evaluations/${evaluationId}/recommendations`)
      setRecommendations(recs)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const generateRecommendations = async () => {
    setLoading(true)
    setError('')
    try {
      const recs = await api(`/evaluations/${evaluationId}/recommendations`, { method: 'POST' })
      setRecommendations(recs)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (evaluationId) {
      fetchRecommendations()
    }
  }, [evaluationId])

  const findingsMap = React.useMemo(() => {
    const map = {}
    findings.forEach(f => { map[f.id] = f })
    return map
  }, [findings])

  return (
    <div style={{ marginBottom: '32px' }}>
      <div className="section-header">
        <h3 className="section-title">
          <Sparkles size={18} color="var(--accent-mint)" />
          Automated & Guided Remediation
        </h3>
        <button
          className="btn btn-primary"
          disabled={loading}
          onClick={generateRecommendations}
        >
          <Sparkles size={15} />
          {loading ? 'Generating...' : recommendations.length > 0 ? 'Regenerate Recommendations' : 'Generate Recommendations'}
        </button>
      </div>

      {error && <p className="error" style={{ color: '#ef4444', marginBottom: '16px' }}>{error}</p>}

      {recommendations.length === 0 && !loading && (
        <div className="empty-state">
          <Wrench size={32} />
          <p>No recommendations generated yet. Click "Generate Recommendations" above to create automated remediations.</p>
        </div>
      )}

      <div className="rec-grid">
        {recommendations.map((rec) => {
          const finding = findingsMap[rec.finding_id]
          const isAutomatic = rec.fixability === 'automatic'
          const isManual = rec.fixability === 'manual'
          const isSelected = selectedIds.has(rec.id)
          const appliedFix = appliedFixes[rec.id]
          const verification = verifications[rec.id]

          return (
            <article className="rec-card" key={rec.id}>
              <div className="rec-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  {isAutomatic && (
                    <input
                      type="checkbox"
                      checked={isSelected || false}
                      onChange={() => onToggleSelect(rec.id)}
                      style={{ width: '18px', height: '18px', cursor: 'pointer', accentColor: 'var(--accent-mint)' }}
                    />
                  )}
                  <div className="rec-title-area">
                    <h4>{rec.title}</h4>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                      <span className={`badge ${isAutomatic ? 'badge-success' : isManual ? 'badge-medium' : 'badge-neutral'}`}>
                        {isAutomatic && 'Automatic fix available'}
                        {isManual && 'Manual fix recommended'}
                        {!isAutomatic && !isManual && 'Automatic fix unavailable'}
                      </span>
                      {verification && (
                        <span className={`badge ${verification.status === 'verified' ? 'badge-success' : 'badge-high'}`}>
                          {verification.status === 'verified' && '✓ VERIFIED RESOLVED'}
                          {verification.status === 'regression' && '⚠️ REGRESSION'}
                          {verification.status === 'not_resolved' && '❌ NOT RESOLVED'}
                        </span>
                      )}
                      {finding && (
                        <>
                          <span className={`badge badge-${finding.severity?.toLowerCase() || 'medium'}`}>{finding.severity}</span>
                          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{rec.tool} · {rec.rule_id}</span>
                          <code className="finding-path">{finding.file_path}{finding.line_start ? `:${finding.line_start}` : ''}</code>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {isAutomatic && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => onPreviewFix(rec)}
                  >
                    {verification ? 'View Verification' : appliedFix ? 'Verify Fix' : 'Preview Fix'}
                    <ArrowRight size={14} />
                  </button>
                )}
              </div>

              <div className="rec-content-grid">
                <div className="rec-box">
                  <label>Problem</label>
                  <p>{rec.description}</p>
                </div>
                <div className="rec-box">
                  <label>Why It Matters</label>
                  <p>{rec.why_it_matters}</p>
                </div>
                <div className="rec-box">
                  <label>Recommended Action</label>
                  <p>{rec.recommended_action}</p>
                </div>
              </div>
            </article>
          )
        })}
      </div>

      {selectedIds.size > 0 && (
        <div style={{ position: 'sticky', bottom: '24px', zIndex: 90, marginTop: '24px', background: 'var(--bg-card)', border: '1px solid var(--accent-mint)', borderRadius: '12px', padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 8px 32px rgba(0,0,0,0.5)' }}>
          <span style={{ fontWeight: 600, color: 'var(--accent-mint-light)' }}>
            {selectedIds.size} automatic fix{selectedIds.size > 1 ? 'es' : ''} selected
          </span>
          <button className="btn btn-primary" onClick={onOpenBatchModal}>
            Preview Selected Fixes ({selectedIds.size})
          </button>
        </div>
      )}
    </div>
  )
}
