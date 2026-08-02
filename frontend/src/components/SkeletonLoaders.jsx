import React from 'react'

export function SkeletonLoader({ height = '40px', width = '100%', borderRadius = '8px', className = '' }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ height, width, borderRadius, marginBottom: '12px' }}
    />
  )
}

export function HeroSkeleton() {
  return (
    <div className="hero-card">
      <div style={{ flex: 1 }}>
        <SkeletonLoader height="24px" width="200px" />
        <SkeletonLoader height="36px" width="400px" />
        <SkeletonLoader height="16px" width="300px" />
      </div>
      <SkeletonLoader height="130px" width="130px" borderRadius="50%" />
    </div>
  )
}

export function ScoreCardsSkeleton() {
  return (
    <div className="score-grid">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <div className="score-card" key={i}>
          <SkeletonLoader height="20px" width="100px" />
          <SkeletonLoader height="32px" width="60px" />
          <SkeletonLoader height="6px" width="100%" />
        </div>
      ))}
    </div>
  )
}
