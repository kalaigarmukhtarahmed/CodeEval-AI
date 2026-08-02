import React from 'react'
import { FileCode, Layers, CheckCircle2, Play, RefreshCw, AlertTriangle, Cpu } from 'lucide-react'

export function HeroSection({
  project,
  evaluation,
  profile,
  report,
  busy,
  onAnalyze,
  onRunStatic,
  onGenerateReport
}) {
  const score = report?.overall?.score
  const scoringVersion = report?.scoring_version || '1.3'
  const measuredCategories = report?.overall?.measured_categories ?? 0
  const totalCategories = report?.overall?.total_categories ?? 6

  // Circular gauge calculations (radius 54)
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const normalizedScore = score !== null && score !== undefined ? Math.max(0, Math.min(100, score)) : 0
  const strokeDashoffset = circumference - (normalizedScore / 100) * circumference

  let scoreColor = 'var(--accent-mint)'
  if (score !== null && score !== undefined) {
    if (score < 60) scoreColor = '#ef4444'
    else if (score < 80) scoreColor = '#eab308'
  }

  const canRun = evaluation?.status === 'planned'
  const canScore = ['completed', 'completed_with_errors'].includes(evaluation?.status)

  return (
    <section className="hero-card">
      <div className="hero-main">
        <div className="hero-meta">
          <span className="badge badge-success">
            <CheckCircle2 size={12} /> Live Workspace
          </span>
          <span className="badge badge-neutral">v{scoringVersion}</span>
          <span className="badge badge-low">
            Coverage {measuredCategories} / {totalCategories}
          </span>
        </div>

        <h1 className="hero-title">{project?.name || 'Repository Workspace'}</h1>

        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Original Snapshot: <code style={{ fontFamily: 'var(--font-mono)' }}>{project?.id}</code>
          {evaluation?.snapshot_id && evaluation.snapshot_id !== project?.id && (
            <span style={{ marginLeft: '12px', color: 'var(--accent-mint-light)' }}>
              · Working Snapshot: <code style={{ fontFamily: 'var(--font-mono)' }}>{evaluation.snapshot_id} (Derived)</code>
            </span>
          )}
        </p>

        {profile && (
          <div className="hero-stats">
            <div className="stat-pill">
              <FileCode size={16} color="var(--accent-mint)" />
              <span>Source files: <strong>{profile.total_source_files}</strong></span>
            </div>
            <div className="stat-pill">
              <Layers size={16} color="var(--accent-blue)" />
              <span>Source lines: <strong>{profile.total_source_lines}</strong></span>
            </div>
            {profile.languages && Object.entries(profile.languages).map(([lang, pct]) => (
              <div className="stat-pill" key={lang}>
                <Cpu size={16} color="var(--accent-purple)" />
                <span>{lang}: <strong>{pct}%</strong></span>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: '24px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          {!evaluation && (
            <button className="btn btn-primary" disabled={busy} onClick={onAnalyze}>
              <Play size={16} />
              {busy ? 'Analyzing Repository...' : 'Analyze Project'}
            </button>
          )}

          {canRun && (
            <button className="btn btn-primary" disabled={busy} onClick={onRunStatic}>
              <Play size={16} />
              {busy ? 'Running Static Analysis...' : 'Run Static Evaluation'}
            </button>
          )}

          {canScore && (
            <button className="btn btn-primary" disabled={busy} onClick={onGenerateReport}>
              <RefreshCw size={16} className={busy ? 'animate-spin' : ''} />
              {busy ? 'Generating Report...' : report ? 'Refresh Report' : 'Generate Full Report'}
            </button>
          )}
        </div>
      </div>

      <div className="score-gauge-container">
        <div className="score-gauge">
          <svg viewBox="0 0 120 120">
            <circle className="score-gauge-bg" cx="60" cy="60" r={radius} />
            <circle
              className="score-gauge-val"
              cx="60"
              cy="60"
              r={radius}
              stroke={scoreColor}
              style={{ strokeDashoffset: score === null || score === undefined ? circumference : strokeDashoffset }}
            />
          </svg>
          <div className="score-gauge-number">
            <strong>{score !== null && score !== undefined ? score : '—'}</strong>
            <span>{score !== null && score !== undefined ? '/ 100' : 'Unmeasured'}</span>
          </div>
        </div>
        <span style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>
          Overall Quality Index
        </span>
      </div>
    </section>
  )
}
