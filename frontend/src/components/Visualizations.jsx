import React from 'react'
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
  info: '#9ca3af'
}

export function Visualizations({ categories = [], findings = [] }) {
  // Radar data
  const radarData = categories.map(c => ({
    category: c.category.charAt(0).toUpperCase() + c.category.slice(1),
    score: c.score !== null && c.score !== undefined ? c.score : 0
  }))

  // Bar data (findings count by category)
  const categoryCounts = {}
  findings.forEach(f => {
    categoryCounts[f.category] = (categoryCounts[f.category] || 0) + 1
  })
  const barData = Object.entries(categoryCounts).map(([cat, count]) => ({
    category: cat.charAt(0).toUpperCase() + cat.slice(1),
    findings: count
  }))

  // Pie data (findings count by severity)
  const severityCounts = {}
  findings.forEach(f => {
    const sev = f.severity?.toLowerCase() || 'info'
    severityCounts[sev] = (severityCounts[sev] || 0) + 1
  })
  const pieData = Object.entries(severityCounts).map(([sev, count]) => ({
    name: sev.toUpperCase(),
    value: count,
    color: SEVERITY_COLORS[sev] || '#9ca3af'
  }))

  if (categories.length === 0 && findings.length === 0) return null

  return (
    <div className="charts-grid">
      <div className="chart-card">
        <h4>Category Score Radar</h4>
        <div style={{ width: '100%', height: 260 }}>
          <ResponsiveContainer>
            <RadarChart data={radarData}>
              <PolarGrid stroke="var(--border-color)" />
              <PolarAngleAxis dataKey="category" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
              <PolarRadiusAxis angle={30} domain={[0, 100]} stroke="var(--border-color)" />
              <Radar name="Score" dataKey="score" stroke="var(--accent-mint)" fill="var(--accent-mint)" fillOpacity={0.3} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {barData.length > 0 && (
        <div className="chart-card">
          <h4>Findings Per Category</h4>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={barData}>
                <XAxis dataKey="category" stroke="var(--text-muted)" tick={{ fontSize: 11 }} />
                <YAxis stroke="var(--text-muted)" tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip contentStyle={{ backgroundColor: 'var(--bg-card)', borderColor: 'var(--border-color)', color: 'var(--text-main)', borderRadius: '8px' }} />
                <Bar dataKey="findings" fill="var(--accent-blue)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {pieData.length > 0 && (
        <div className="chart-card">
          <h4>Severity Breakdown</h4>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="value">
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: 'var(--bg-card)', borderColor: 'var(--border-color)', color: 'var(--text-main)', borderRadius: '8px' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
