import React, { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

import { Navbar } from './components/Navbar'
import { HeroSection } from './components/HeroSection'
import { ScoreCardGrid } from './components/ScoreCardGrid'
import { Visualizations } from './components/Visualizations'
import { StaticChecks } from './components/StaticChecks'
import { ArchitectureSection } from './components/ArchitectureSection'
import { PerformanceSection } from './components/PerformanceSection'
import { TestingSection } from './components/TestingSection'
import { FindingsSection } from './components/FindingsSection'
import { RecommendationsSection } from './components/RecommendationsSection'
import { AgentTimeline } from './components/AgentTimeline'
import { FixPreviewModal } from './components/FixPreviewModal'
import { BatchPreviewModal } from './components/BatchPreviewModal'
import { HeroSkeleton, ScoreCardsSkeleton } from './components/SkeletonLoaders'
import { EmptyState } from './components/EmptyState'
import { Footer } from './components/Footer'

import {
  UploadCloud, FileArchive, ArrowLeft, LayoutDashboard, Box, Zap,
  TestTube, AlertCircle, Sparkles, Activity
} from 'lucide-react'

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const api = async (path, options) => {
  const response = await fetch(`${API}${path}`, options)
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || 'Request failed.')
  return data
}

function AnalysisTabs({ activeTab, onTabChange, counts = {} }) {
  const tabs = [
    { id: 'overview', label: 'Overview & Visualizations', icon: LayoutDashboard },
    { id: 'architecture', label: 'Architecture', icon: Box },
    { id: 'performance', label: 'Performance', icon: Zap },
    { id: 'testing', label: 'Testing & Coverage', icon: TestTube },
    { id: 'findings', label: `Findings (${counts.findings ?? 0})`, icon: AlertCircle },
    { id: 'recommendations', label: 'Recommendations & Fixes', icon: Sparkles },
    { id: 'activity', label: 'Agent Activity', icon: Activity },
  ]

  return (
    <div className="tabs-container">
      <div className="tab-list">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => onTabChange(tab.id)}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ReportDashboard({ report, findings = [], evaluationId, onContinueFromSnapshot, api }) {
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedRec, setSelectedRec] = useState(null)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [showBatchModal, setShowBatchModal] = useState(false)
  const [appliedFixes, setAppliedFixes] = useState({})
  const [verifications, setVerifications] = useState({})
  const [appliedBatch, setAppliedBatch] = useState(null)
  const [batchVerification, setBatchVerification] = useState(null)

  const toggleSelect = id => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <section className="results-container">
      <AnalysisTabs
        activeTab={activeTab}
        onTabChange={setActiveTab}
        counts={{ findings: findings.length }}
      />

      {activeTab === 'overview' && (
        <>
          <Visualizations categories={report.categories} findings={findings} />
          <ScoreCardGrid
            categories={report.categories}
            performanceAnalysis={report.performance_analysis}
            architectureAnalysis={report.architecture_analysis}
          />
          <StaticChecks checks={report.checks} />
          <FindingsSection findings={findings} />
        </>
      )}

      {activeTab === 'architecture' && (
        <ArchitectureSection architectureAnalysis={report.architecture_analysis} />
      )}

      {activeTab === 'performance' && (
        <PerformanceSection performanceAnalysis={report.performance_analysis} />
      )}

      {activeTab === 'testing' && (
        <TestingSection testRun={report.test_run} />
      )}

      {activeTab === 'findings' && (
        <FindingsSection findings={findings} />
      )}

      {activeTab === 'recommendations' && evaluationId && (
        <RecommendationsSection
          evaluationId={evaluationId}
          findings={findings}
          api={api}
          onPreviewFix={setSelectedRec}
          onOpenBatchModal={() => setShowBatchModal(true)}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          appliedFixes={appliedFixes}
          verifications={verifications}
        />
      )}

      {activeTab === 'activity' && (
        <AgentTimeline items={report.timeline_summary} />
      )}

      {selectedRec && (
        <FixPreviewModal
          recommendation={selectedRec}
          finding={findings.find(f => f.id === selectedRec.finding_id)}
          api={api}
          onClose={() => setSelectedRec(null)}
          onApplied={(recId, result) => {
            setAppliedFixes(prev => ({ ...prev, [recId]: result }))
          }}
          onVerified={(recId, vResult) => {
            setVerifications(prev => ({ ...prev, [recId]: vResult }))
          }}
          appliedFix={appliedFixes[selectedRec.id]}
          verification={verifications[selectedRec.id]}
        />
      )}

      {showBatchModal && (
        <BatchPreviewModal
          evaluationId={evaluationId}
          selectedRecIds={Array.from(selectedIds)}
          api={api}
          onClose={() => setShowBatchModal(false)}
          onAppliedBatch={setAppliedBatch}
          appliedBatch={appliedBatch}
          batchVerification={batchVerification}
          onVerifiedBatch={setBatchVerification}
          onContinueFromSnapshot={onContinueFromSnapshot}
        />
      )}
    </section>
  )
}

function Project({ id }) {
  const [project, setProject] = useState(null)
  const [evaluation, setEvaluation] = useState(null)
  const [profile, setProfile] = useState(null)
  const [plan, setPlan] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [checks, setChecks] = useState([])
  const [findings, setFindings] = useState([])
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/projects/${id}`).then(setProject).catch(e => setError(e.message))
  }, [id])

  const loadAnalysis = async evaluationId => {
    const [nextProfile, nextPlan, nextTimeline] = await Promise.all([
      api(`/evaluations/${evaluationId}/profile`),
      api(`/evaluations/${evaluationId}/plan`),
      api(`/evaluations/${evaluationId}/timeline`)
    ])
    setProfile(nextProfile)
    setPlan(nextPlan)
    setTimeline(nextTimeline)
  }

  const analyze = async () => {
    setBusy(true)
    setError('')
    try {
      const next = await api(`/projects/${id}/evaluations`, { method: 'POST' })
      setEvaluation(next)
      await loadAnalysis(next.id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleContinueFromSnapshot = async snapshotId => {
    setBusy(true)
    setError('')
    try {
      const nextEval = await api(`/snapshots/${snapshotId}/evaluations`, { method: 'POST' })
      setEvaluation(nextEval)
      setReport(null)
      setChecks([])
      setFindings([])
      await loadAnalysis(nextEval.id)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const runStatic = async () => {
    setBusy(true)
    setError('')
    try {
      const next = await api(`/evaluations/${evaluation.id}/run`, { method: 'POST' })
      const [nextChecks, nextFindings, nextTimeline] = await Promise.all([
        api(`/evaluations/${evaluation.id}/checks`),
        api(`/evaluations/${evaluation.id}/findings`),
        api(`/evaluations/${evaluation.id}/timeline`)
      ])
      setEvaluation(next)
      setChecks(nextChecks)
      setFindings(nextFindings)
      setTimeline(nextTimeline)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const generateReport = async () => {
    setBusy(true)
    setError('')
    try {
      await api(`/evaluations/${evaluation.id}/score`, { method: 'POST' })
      const [nextReport, nextFindings, nextTimeline] = await Promise.all([
        api(`/evaluations/${evaluation.id}/report`),
        api(`/evaluations/${evaluation.id}/findings`),
        api(`/evaluations/${evaluation.id}/timeline`)
      ])
      setReport(nextReport)
      setFindings(nextFindings)
      setTimeline(nextTimeline)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!project) {
    return (
      <div className="app-container">
        <Navbar />
        <main className="main-content">
          {error ? <div className="badge badge-critical" style={{ padding: '16px' }}>{error}</div> : <HeroSkeleton />}
        </main>
        <Footer />
      </div>
    )
  }

  return (
    <div className="app-container">
      <Navbar
        projectName={project.name}
        status={evaluation?.status}
        onExport={report ? () => window.print() : null}
      />

      <main className="main-content">
        <a href="/" className="btn btn-outline" style={{ marginBottom: '20px' }}>
          <ArrowLeft size={16} /> Back to Upload
        </a>

        {error && (
          <div className="badge badge-critical" style={{ width: '100%', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px' }}>
            {error}
          </div>
        )}

        <HeroSection
          project={project}
          evaluation={evaluation}
          profile={profile}
          report={report}
          busy={busy}
          onAnalyze={analyze}
          onRunStatic={runStatic}
          onGenerateReport={generateReport}
        />

        {report ? (
          <ReportDashboard
            report={report}
            findings={findings}
            evaluationId={evaluation?.id}
            onContinueFromSnapshot={handleContinueFromSnapshot}
            api={api}
          />
        ) : (
          <>
            {checks.length > 0 && <StaticChecks checks={checks} />}
            {timeline.length > 0 && <AgentTimeline items={timeline} />}
          </>
        )}
      </main>

      <Footer />
    </div>
  )
}

function Upload() {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const upload = async () => {
    if (!file) return
    setUploading(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const project = await api('/projects', { method: 'POST', body: form })
      location.assign(`/projects/${project.project_id}`)
    } catch (e) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="app-container">
      <Navbar />

      <main className="main-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 160px)' }}>
        <div style={{ maxWidth: '560px', width: '100%', textAlignment: 'center' }}>
          <div style={{ textAlign: 'center', marginBottom: '32px' }}>
            <div className="brand-logo" style={{ width: '56px', height: '56px', margin: '0 auto 16px', borderRadius: '14px' }}>
              <UploadCloud size={32} />
            </div>
            <h1 style={{ fontSize: '2.25rem', fontWeight: 800, letterSpacing: '-0.03em', marginBottom: '8px' }}>
              CodeEval <span style={{ color: 'var(--accent-mint)' }}>AI</span>
            </h1>
            <p style={{ color: 'var(--text-muted)', fontSize: '1rem' }}>
              Enterprise Autonomous Software Quality Evaluation & Remediation
            </p>
          </div>

          <div style={{ background: 'var(--bg-card)', border: '2px dashed var(--border-color)', borderRadius: '16px', padding: '40px 24px', textAlign: 'center', transition: 'border-color 0.2s ease' }}>
            <input
              id="file"
              type="file"
              accept=".zip"
              onChange={e => setFile(e.target.files[0])}
              style={{ display: 'none' }}
            />
            <label htmlFor="file" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
              <FileArchive size={48} color="var(--accent-mint)" />
              <strong style={{ fontSize: '1.1rem', color: 'var(--text-main)' }}>
                {file ? file.name : 'Select Repository ZIP'}
              </strong>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Drag & drop a .zip archive or click to browse
              </span>
            </label>

            <div style={{ marginTop: '24px' }}>
              <button
                className="btn btn-primary"
                style={{ width: '100%', padding: '12px' }}
                disabled={!file || uploading}
                onClick={upload}
              >
                <UploadCloud size={18} />
                {uploading ? 'Uploading Repository...' : 'Upload & Start Inspection'}
              </button>
            </div>

            {error && <p className="error" style={{ color: '#ef4444', marginTop: '16px', fontSize: '0.875rem' }}>{error}</p>}
          </div>
        </div>
      </main>

      <Footer />
    </div>
  )
}

function App() {
  const match = location.pathname.match(/^\/projects\/([^/]+)$/)
  return match ? <Project id={match[1]} /> : <Upload />
}

createRoot(document.getElementById('root')).render(<App />)
