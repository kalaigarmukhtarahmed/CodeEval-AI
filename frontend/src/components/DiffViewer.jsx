import React from 'react'
import { FileCode } from 'lucide-react'

export function DiffViewer({ diff, filePath }) {
  if (!diff) return <div className="diff-container">No diff available.</div>

  const lines = diff.split('\n')
  return (
    <div style={{ marginTop: '12px' }}>
      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
        <FileCode size={14} color="var(--accent-mint)" />
        <span>UNIFIED DIFF · {filePath}</span>
      </div>
      <div className="diff-container">
        {lines.map((line, idx) => {
          let className = 'diff-line'
          if (line.startsWith('---') || line.startsWith('+++')) className += ' header'
          else if (line.startsWith('-')) className += ' removed'
          else if (line.startsWith('+')) className += ' added'
          else if (line.startsWith('@@')) className += ' hunk'
          return <span key={idx} className={className}>{line || ' '}</span>
        })}
      </div>
    </div>
  )
}
