import React from 'react'

export const PdfReportTemplate = React.forwardRef(({ project, evaluation, profile, report, findings = [] }, ref) => {
  if (!report) return null

  const overallScore = report.overall?.score ?? 'N/A'
  const scoringVersion = report.scoring_version || '1.3'
  const measuredCount = report.overall?.measured_categories ?? 6
  const totalCategories = report.overall?.total_categories ?? 6
  const timestamp = new Date().toLocaleString()

  const categories = report.categories || []
  const checks = report.checks || []
  const arch = report.architecture_analysis
  const perf = report.performance_analysis
  const testRun = report.test_run
  const timeline = report.timeline_summary || []

  // Count findings by severity
  const severityCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  findings.forEach(f => {
    const s = f.severity?.toLowerCase() || 'info'
    if (severityCounts[s] !== undefined) severityCounts[s]++
  })

  return (
    <div style={{ position: 'absolute', left: '-9999px', top: '-9999px' }}>
      <div ref={ref} id="pdf-report-root" style={{ width: '800px', backgroundColor: '#0b0f12', color: '#f3f4f6', fontFamily: 'Inter, sans-serif', padding: '0' }}>
        
        {/* PAGE 1: COVER PAGE */}
        <div className="pdf-page" style={{ height: '1130px', padding: '60px 48px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderBottom: '2px solid #10b981', position: 'relative' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '40px' }}>
              <div style={{ width: '40px', height: '40px', background: 'linear-gradient(135deg, #10b981, #059669)', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: '20px' }}>
                ✓
              </div>
              <span style={{ fontSize: '24px', fontWeight: 800, letterSpacing: '-0.02em' }}>
                CodeEval <span style={{ color: '#10b981' }}>AI</span>
              </span>
            </div>

            <div style={{ marginTop: '80px' }}>
              <div style={{ display: 'inline-block', padding: '6px 14px', background: 'rgba(16,185,129,0.15)', color: '#34d399', borderRadius: '20px', fontSize: '13px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px' }}>
                Enterprise Quality & Security Evaluation
              </div>
              <h1 style={{ fontSize: '36px', fontWeight: 800, lineHeight: 1.2, letterSpacing: '-0.03em', marginBottom: '16px' }}>
                {project?.name || 'Software Repository'}
              </h1>
              <p style={{ fontSize: '16px', color: '#9ca3af', maxWidth: '600px', lineHeight: 1.6 }}>
                Comprehensive multi-category static inspection, architectural lineage, AST performance auditing, and test execution report.
              </p>
            </div>

            <div style={{ marginTop: '60px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', background: '#13191f', padding: '24px', borderRadius: '12px', border: '1px solid #222d37' }}>
              <div>
                <label style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Original Snapshot</label>
                <code style={{ fontFamily: 'monospace', fontSize: '13px', color: '#f3f4f6' }}>{project?.id || '—'}</code>
              </div>
              <div>
                <label style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Working Snapshot</label>
                <code style={{ fontFamily: 'monospace', fontSize: '13px', color: '#34d399' }}>{evaluation?.snapshot_id || '—'}</code>
              </div>
              <div>
                <label style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Scoring Version</label>
                <span style={{ fontSize: '14px', fontWeight: 700, color: '#f3f4f6' }}>v{scoringVersion}</span>
              </div>
              <div>
                <label style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase', display: 'block', marginBottom: '4px' }}>Assessment Coverage</label>
                <span style={{ fontSize: '14px', fontWeight: 700, color: '#10b981' }}>{measuredCount} / {totalCategories} Categories</span>
              </div>
            </div>
          </div>

          <div style={{ background: 'linear-gradient(135deg, #13191f, #182028)', padding: '32px', borderRadius: '16px', border: '1px solid #222d37', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <span style={{ fontSize: '12px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Overall Quality Index</span>
              <div style={{ fontSize: '48px', fontWeight: 800, color: overallScore >= 80 ? '#10b981' : overallScore >= 60 ? '#eab308' : '#ef4444', lineHeight: 1, marginTop: '4px' }}>
                {overallScore} <span style={{ fontSize: '20px', color: '#6b7280', fontWeight: 500 }}>/ 100</span>
              </div>
            </div>
            <div style={{ textAlign: 'right', fontSize: '12px', color: '#9ca3af' }}>
              <div>Generated: <strong>{timestamp}</strong></div>
              <div style={{ marginTop: '4px' }}>Environment: <strong>Trusted Sandbox</strong></div>
            </div>
          </div>
        </div>

        {/* PAGE 2: EXECUTIVE SUMMARY & SCORECARD */}
        <div className="pdf-page" style={{ height: '1130px', padding: '60px 48px', borderBottom: '1px solid #222d37' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #222d37', paddingBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700, textTransform: 'uppercase' }}>Executive Summary & Scorecard</span>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>CodeEval AI v{scoringVersion}</span>
          </div>

          <h2 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '16px' }}>Executive Summary</h2>
          <p style={{ fontSize: '14px', color: '#d1d5db', lineHeight: 1.6, marginBottom: '24px' }}>
            Repository <strong>{project?.name}</strong> underwent an evaluation across six foundational dimensions: Architecture, Security, Maintainability, Performance, Testing, and Correctness. Overall quality score is <strong>{overallScore}/100</strong> with <strong>{measuredCount}/{totalCategories}</strong> categories measured.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '32px' }}>
            <div style={{ background: '#13191f', padding: '16px', borderRadius: '8px', border: '1px solid #222d37' }}>
              <span style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase' }}>Total Findings</span>
              <div style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}>{findings.length}</div>
            </div>
            <div style={{ background: '#13191f', padding: '16px', borderRadius: '8px', border: '1px solid #222d37' }}>
              <span style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase' }}>Critical / High Risks</span>
              <div style={{ fontSize: '24px', fontWeight: 800, color: (severityCounts.critical + severityCounts.high) > 0 ? '#ef4444' : '#10b981', marginTop: '4px' }}>
                {severityCounts.critical + severityCounts.high}
              </div>
            </div>
            <div style={{ background: '#13191f', padding: '16px', borderRadius: '8px', border: '1px solid #222d37' }}>
              <span style={{ fontSize: '11px', color: '#6b7280', textTransform: 'uppercase' }}>Source Lines</span>
              <div style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}>{profile?.total_source_lines || 0}</div>
            </div>
          </div>

          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Category Evaluation Scorecard</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: '#13191f', borderBottom: '1px solid #222d37', color: '#9ca3af' }}>
                <th style={{ padding: '12px' }}>Category</th>
                <th style={{ padding: '12px' }}>Status</th>
                <th style={{ padding: '12px' }}>Score</th>
                <th style={{ padding: '12px' }}>Explanation</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.category} style={{ borderBottom: '1px solid #1a222a' }}>
                  <td style={{ padding: '12px', fontWeight: 700, textTransform: 'capitalize' }}>{c.category}</td>
                  <td style={{ padding: '12px' }}>
                    <span style={{ padding: '2px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: 700, background: c.status === 'measured' ? 'rgba(16,185,129,0.15)' : 'rgba(156,163,175,0.15)', color: c.status === 'measured' ? '#34d399' : '#9ca3af' }}>
                      {c.status}
                    </span>
                  </td>
                  <td style={{ padding: '12px', fontWeight: 800, color: c.score >= 80 ? '#10b981' : c.score >= 60 ? '#eab308' : c.score !== null ? '#ef4444' : '#6b7280' }}>
                    {c.score !== null ? `${c.score} / 100` : 'N/A'}
                  </td>
                  <td style={{ padding: '12px', color: '#9ca3af', fontSize: '12px' }}>{c.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* PAGE 3: STATIC PIPELINES & ARCHITECTURE */}
        <div className="pdf-page" style={{ height: '1130px', padding: '60px 48px', borderBottom: '1px solid #222d37' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #222d37', paddingBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700, textTransform: 'uppercase' }}>Static Pipelines & Architecture</span>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>CodeEval AI v{scoringVersion}</span>
          </div>

          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Static Analyzer Pipeline Results</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left', marginBottom: '32px' }}>
            <thead>
              <tr style={{ background: '#13191f', borderBottom: '1px solid #222d37', color: '#9ca3af' }}>
                <th style={{ padding: '10px' }}>Tool / Analyzer</th>
                <th style={{ padding: '10px' }}>Status</th>
                <th style={{ padding: '10px' }}>Findings</th>
                <th style={{ padding: '10px' }}>Duration</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((chk) => (
                <tr key={chk.tool} style={{ borderBottom: '1px solid #1a222a' }}>
                  <td style={{ padding: '10px', fontWeight: 700 }}>{chk.tool}</td>
                  <td style={{ padding: '10px' }}>{chk.status}</td>
                  <td style={{ padding: '10px' }}>{chk.finding_count}</td>
                  <td style={{ padding: '10px', color: '#9ca3af' }}>{chk.duration_ms ? `${chk.duration_ms} ms` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {arch && (
            <>
              <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Static Architecture Analysis</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
                <div style={{ background: '#13191f', padding: '14px', borderRadius: '8px', border: '1px solid #222d37' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Modules</span>
                  <div style={{ fontSize: '20px', fontWeight: 800 }}>{arch.metrics?.module_count || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '14px', borderRadius: '8px', border: '1px solid #222d37' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Dependency Edges</span>
                  <div style={{ fontSize: '20px', fontWeight: 800 }}>{arch.metrics?.dependency_edge_count || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '14px', borderRadius: '8px', border: '1px solid #222d37' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Circular Dependencies</span>
                  <div style={{ fontSize: '20px', fontWeight: 800, color: (arch.metrics?.circular_dependency_count || 0) > 0 ? '#ef4444' : '#10b981' }}>
                    {arch.metrics?.circular_dependency_count || 0}
                  </div>
                </div>
              </div>

              {arch.findings && arch.findings.length > 0 && (
                <div style={{ background: '#13191f', padding: '16px', borderRadius: '8px', border: '1px solid #222d37' }}>
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#f3f4f6' }}>Architecture Findings:</span>
                  <ul style={{ paddingLeft: '20px', marginTop: '8px', fontSize: '12px', color: '#9ca3af' }}>
                    {arch.findings.map((af, i) => (
                      <li key={i}>[{af.rule_id}] <strong>{af.file_path}</strong> — {af.message}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        {/* PAGE 4: PERFORMANCE & TESTING */}
        <div className="pdf-page" style={{ height: '1130px', padding: '60px 48px', borderBottom: '1px solid #222d37' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #222d37', paddingBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700, textTransform: 'uppercase' }}>Performance & Test Execution</span>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>CodeEval AI v{scoringVersion}</span>
          </div>

          {perf && (
            <div style={{ marginBottom: '32px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Performance & Complexity Analysis</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Functions</span>
                  <div style={{ fontSize: '18px', fontWeight: 800 }}>{perf.metrics?.functions || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Loops</span>
                  <div style={{ fontSize: '18px', fontWeight: 800 }}>{perf.metrics?.loops || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Nested Loops</span>
                  <div style={{ fontSize: '18px', fontWeight: 800, color: (perf.metrics?.nested_loops || 0) > 0 ? '#ef4444' : '#10b981' }}>
                    {perf.metrics?.nested_loops || 0}
                  </div>
                </div>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Avg Complexity</span>
                  <div style={{ fontSize: '18px', fontWeight: 800 }}>{perf.metrics?.average_complexity || 0}</div>
                </div>
              </div>
            </div>
          )}

          {testRun && (
            <div>
              <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Test Execution Results ({testRun.framework})</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Collected</span>
                  <div style={{ fontSize: '18px', fontWeight: 800 }}>{testRun.tests_collected || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Passed</span>
                  <div style={{ fontSize: '18px', fontWeight: 800, color: '#10b981' }}>{testRun.tests_passed || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Failed</span>
                  <div style={{ fontSize: '18px', fontWeight: 800, color: (testRun.tests_failed || 0) > 0 ? '#ef4444' : '#f3f4f6' }}>{testRun.tests_failed || 0}</div>
                </div>
                <div style={{ background: '#13191f', padding: '12px', borderRadius: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Coverage</span>
                  <div style={{ fontSize: '18px', fontWeight: 800 }}>{testRun.coverage_percent ? `${testRun.coverage_percent}%` : 'N/A'}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* PAGE 5: FINDINGS REGISTER */}
        <div className="pdf-page" style={{ minHeight: '1130px', padding: '60px 48px', borderBottom: '1px solid #222d37' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #222d37', paddingBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700, textTransform: 'uppercase' }}>Structured Findings Register</span>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>CodeEval AI v{scoringVersion}</span>
          </div>

          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Detected Findings ({findings.length})</h3>
          {findings.length === 0 ? (
            <p style={{ color: '#9ca3af', fontSize: '14px' }}>No findings detected in this evaluation.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: '#13191f', borderBottom: '1px solid #222d37', color: '#9ca3af' }}>
                  <th style={{ padding: '8px' }}>Sev</th>
                  <th style={{ padding: '8px' }}>Rule</th>
                  <th style={{ padding: '8px' }}>Category</th>
                  <th style={{ padding: '8px' }}>Location</th>
                  <th style={{ padding: '8px' }}>Message</th>
                </tr>
              </thead>
              <tbody>
                {findings.slice(0, 25).map((f, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #1a222a' }}>
                    <td style={{ padding: '8px', fontWeight: 700, color: f.severity === 'critical' ? '#ef4444' : f.severity === 'high' ? '#f97316' : '#eab308' }}>
                      {f.severity?.toUpperCase()}
                    </td>
                    <td style={{ padding: '8px', fontWeight: 700 }}>{f.rule_id || f.rule}</td>
                    <td style={{ padding: '8px', color: '#9ca3af' }}>{f.category}</td>
                    <td style={{ padding: '8px', fontFamily: 'monospace', color: '#34d399' }}>{f.file_path}{f.line_start ? `:${f.line_start}` : ''}</td>
                    <td style={{ padding: '8px', color: '#d1d5db' }}>{f.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* PAGE 6: AGENT TIMELINE & APPENDIX */}
        <div className="pdf-page" style={{ height: '1130px', padding: '60px 48px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #222d37', paddingBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700, textTransform: 'uppercase' }}>Agent Activity & Appendix</span>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>CodeEval AI v{scoringVersion}</span>
          </div>

          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Agent Activity Timeline</h3>
          <ul style={{ paddingLeft: '20px', fontSize: '12px', color: '#9ca3af', marginBottom: '40px', lineHeight: 1.8 }}>
            {timeline.map((msg, idx) => (
              <li key={idx} style={{ color: '#d1d5db' }}>✓ {msg}</li>
            ))}
          </ul>

          <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>Appendix: Evaluation Metadata</h3>
          <div style={{ background: '#13191f', padding: '20px', borderRadius: '10px', border: '1px solid #222d37', fontSize: '12px', color: '#9ca3af', lineHeight: 1.8 }}>
            <div><strong>Evaluation ID:</strong> {evaluation?.id}</div>
            <div><strong>Project ID:</strong> {project?.id}</div>
            <div><strong>Snapshot ID:</strong> {evaluation?.snapshot_id}</div>
            <div><strong>Scoring Engine:</strong> Deterministic Static Evaluator v{scoringVersion}</div>
            <div><strong>Execution Mode:</strong> Safe Sandbox (Static Default)</div>
            <div><strong>Compliance:</strong> Academic, Portfolio, Enterprise & Executive Ready</div>
          </div>
        </div>

      </div>
    </div>
  )
})
