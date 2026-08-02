import React, { useState } from 'react'
import { Download, FileText, CheckCircle2, X, Loader2, Printer } from 'lucide-react'
import { exportReportToPdf } from '../utils/pdfExporter'

export function PdfExportModal({ project, evaluation, report, onClose }) {
  const [generating, setGenerating] = useState(false)
  const [progressMsg, setProgressMsg] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const handleGenerate = async () => {
    setGenerating(true)
    setError('')
    setDone(false)
    try {
      const name = `${project?.name || 'Project'}-CodeEval-Report.pdf`.replace(/[^a-zA-Z0-9._-]/g, '_')
      await exportReportToPdf({
        elementId: 'pdf-report-root',
        fileName: name,
        onProgress: (msg) => setProgressMsg(msg)
      })
      setDone(true)
    } catch (e) {
      setError(e.message || 'Failed to generate PDF report.')
    } finally {
      setGenerating(false)
    }
  }

  const handleQuickPrint = () => {
    onClose()
    setTimeout(() => {
      window.print()
    }, 100)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '12px', borderBottom: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <FileText size={20} color="var(--accent-mint)" />
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Export Evaluation PDF Report</h3>
          </div>
          <button className="btn btn-outline" style={{ padding: '6px' }} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '24px', lineHeight: 1.6 }}>
          Choose your preferred PDF export format below:
        </div>

        <div style={{ display: 'grid', gap: '16px', marginBottom: '24px' }}>
          {/* Option 1: Quick Browser Print to PDF */}
          <div style={{ background: 'var(--bg-card-subtle)', border: '1px solid var(--border-color)', borderRadius: '12px', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
            <div>
              <strong style={{ fontSize: '0.95rem', color: 'var(--text-main)', display: 'block', marginBottom: '4px' }}>
                Option 1: Quick Browser Print / PDF
              </strong>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Uses browser native print dialog (`window.print()`) to quickly print or save as PDF.
              </p>
            </div>
            <button className="btn btn-secondary" onClick={handleQuickPrint} style={{ whiteSpace: 'nowrap' }}>
              <Printer size={15} /> Quick Print
            </button>
          </div>

          {/* Option 2: Executive Multi-Page PDF Download */}
          <div style={{ background: 'var(--bg-card-subtle)', border: '1px solid var(--accent-mint)', borderRadius: '12px', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
            <div>
              <strong style={{ fontSize: '0.95rem', color: 'var(--accent-mint-light)', display: 'block', marginBottom: '4px' }}>
                Option 2: Multi-Page Executive PDF Report
              </strong>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Generates a multi-page PDF with cover page, executive summary, charts & findings register.
              </p>
            </div>
            <button className="btn btn-primary" disabled={generating} onClick={handleGenerate} style={{ whiteSpace: 'nowrap' }}>
              <Download size={15} /> {generating ? 'Generating...' : 'Download PDF'}
            </button>
          </div>
        </div>

        {generating && (
          <div style={{ background: 'var(--bg-card-subtle)', padding: '16px', borderRadius: '8px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Loader2 size={20} className="animate-spin" color="var(--accent-mint)" />
            <span style={{ fontSize: '0.85rem', color: 'var(--accent-mint-light)', fontWeight: 600 }}>
              {progressMsg || 'Generating multi-page PDF...'}
            </span>
          </div>
        )}

        {done && (
          <div style={{ background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', color: '#6ee7b7', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} />
            <span>Executive PDF report downloaded successfully!</span>
          </div>
        )}

        {error && (
          <div style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', color: '#fca5a5', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-outline" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
