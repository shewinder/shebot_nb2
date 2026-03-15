import React, { useState, useEffect } from 'react'
import { Card } from 'antd'

function StatCard({ 
  title, 
  value, 
  prefix, 
  suffix,
  icon, 
  color = '#6366f1',
  gradient = false,
  delay = 0 
}) {
  const [displayValue, setDisplayValue] = useState(0)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(true)
    }, delay)
    return () => clearTimeout(timer)
  }, [delay])

  useEffect(() => {
    if (!isVisible) return
    
    const duration = 1000
    const steps = 30
    const increment = (value - displayValue) / steps
    let current = displayValue
    
    const timer = setInterval(() => {
      current += increment
      if ((increment > 0 && current >= value) || (increment < 0 && current <= value)) {
        setDisplayValue(value)
        clearInterval(timer)
      } else {
        setDisplayValue(Math.floor(current))
      }
    }, duration / steps)

    return () => clearInterval(timer)
  }, [value, isVisible])

  const cardStyle = gradient ? {
    background: `linear-gradient(135deg, ${color}20 0%, ${color}05 100%)`,
    border: `1px solid ${color}30`,
  } : {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-color)',
  }

  return (
    <Card
      className="hover-lift"
      style={{
        ...cardStyle,
        borderRadius: 'var(--radius-lg)',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
        transition: 'all var(--transition-slow)',
      }}
      bodyStyle={{ padding: '20px' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 'var(--radius-md)',
            background: gradient ? color : `${color}15`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 24,
            color: gradient ? '#fff' : color,
          }}
        >
          {icon}
        </div>
        <div>
          <div style={{ 
            fontSize: 14, 
            color: 'var(--text-secondary)',
            marginBottom: 4 
          }}>
            {title}
          </div>
          <div style={{ 
            fontSize: 28, 
            fontWeight: 600,
            color: 'var(--text-primary)',
            lineHeight: 1.2,
          }}>
            {prefix}{displayValue.toLocaleString()}{suffix}
          </div>
        </div>
      </div>
    </Card>
  )
}

export default StatCard
