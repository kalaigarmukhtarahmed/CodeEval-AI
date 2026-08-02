import React from 'react'
import { Box, Shield, Wrench, Zap, TestTube, CheckCircle2, AlertCircle } from 'lucide-react'

const CATEGORY_ICONS = {
  architecture: Box,
  security: Shield,
  maintainability: Wrench,
  performance: Zap,
  testing: TestTube,
  correctness: CheckCircle2
}

export function ScoreCardGrid({ categories = [], performanceAnalysis, architectureAnalysis }) {
  const getCardMetrics = (scoreObj) => {
    const summary = scoreObj.evidence_summary || {}
    switch (scoreObj.category) {
      case 'correctness':
        return (
          <>
            <span>Passed: <strong>{summary.tests_passed ?? 0}</strong></span>
            <span>Failed: <strong>{summary.tests_failed ?? 0}</strong></span>
            <span>Errors: <strong>{summary.tests_errors ?? 0}</strong></span>
          </>
        )
      case 'testing':
        return (
          <>
            <span>Tests: <strong>{summary.tests_collected ?? 0}</strong></span>
            <span>Coverage: <strong>{summary.coverage_percent !== null && summary.coverage_percent !== undefined ? `${summary.coverage_percent}%` : 'N/A'}</strong></span>
          </>
        )
      case 'architecture':
        return (
          <>
            <span>Modules: <strong>{summary.module_count ?? architectureAnalysis?.metrics?.module_count ?? 0}</strong></span>
            <span>Edges: <strong>{summary.dependency_edge_count ?? architectureAnalysis?.metrics?.dependency_edge_count ?? 0}</strong></span>
            <span>Cycles: <strong style={{ color: (summary.circular_dependency_count || architectureAnalysis?.metrics?.circular_dependency_count) > 0 ? '#ef4444' : 'inherit' }}>{summary.circular_dependency_count ?? architectureAnalysis?.metrics?.circular_dependency_count ?? 0}</strong></span>
          </>
        )
      case 'performance':
        return (
          <>
            <span>Nested Loops: <strong style={{ color: (summary.nested_loops || performanceAnalysis?.metrics?.nested_loops) > 0 ? '#ef4444' : 'inherit' }}>{summary.nested_loops ?? performanceAnalysis?.metrics?.nested_loops ?? 0}</strong></span>
            <span>DB Queries: <strong>{summary.db_queries ?? 0}</strong></span>
            <span>Avg Complexity: <strong>{summary.average_complexity ?? performanceAnalysis?.metrics?.average_complexity ?? 0}</strong></span>
          </>
        )
      default:
        return (
          <>
            <span>Findings: <strong>{summary.finding_count ?? 0}</strong></span>
            <span>Penalty: <strong>-{summary.penalty ?? 0}</strong></span>
          </>
        )
    }
  }

  return (
    <div className="score-grid">
      {categories.map((scoreObj) => {
        const IconComponent = CATEGORY_ICONS[scoreObj.category] || AlertCircle
        const isMeasured = scoreObj.status === 'measured' && scoreObj.score !== null
        const val = isMeasured ? scoreObj.score : 0

        let progressColor = 'var(--accent-mint)'
        if (isMeasured) {
          if (val < 60) progressColor = '#ef4444'
          else if (val < 80) progressColor = '#eab308'
        }

        return (
          <article className="score-card" key={scoreObj.category}>
            <div className="score-card-header">
              <span className="score-card-title">{scoreObj.category}</span>
              <IconComponent size={18} color="var(--accent-mint)" />
            </div>

            <div className="score-card-body">
              <span className="score-card-val" style={{ color: isMeasured ? 'var(--text-main)' : 'var(--text-dim)' }}>
                {isMeasured ? scoreObj.score : 'N/A'}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {isMeasured ? '/ 100' : 'Unmeasured'}
              </span>
            </div>

            <div className="score-progress-bar">
              <div
                className="score-progress-fill"
                style={{
                  width: `${isMeasured ? val : 0}%`,
                  backgroundColor: progressColor
                }}
              />
            </div>

            <div className="score-card-metrics">
              {isMeasured ? getCardMetrics(scoreObj) : <span style={{ color: 'var(--text-dim)' }}>{scoreObj.explanation}</span>}
            </div>
          </article>
        )
      })}
    </div>
  )
}
