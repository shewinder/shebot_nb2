import React from 'react'
import { Switch, Tooltip } from 'antd'
import { SunOutlined, MoonOutlined } from '@ant-design/icons'

function ThemeToggle({ isDark, onToggle }) {
  return (
    <Tooltip title={isDark ? '切换到亮色主题' : '切换到暗色主题'}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <SunOutlined style={{ color: isDark ? '#64748b' : '#f59e0b' }} />
        <Switch
          checked={isDark}
          onChange={onToggle}
          checkedChildren={<MoonOutlined />}
          unCheckedChildren={<SunOutlined />}
        />
        <MoonOutlined style={{ color: isDark ? '#818cf8' : '#64748b' }} />
      </div>
    </Tooltip>
  )
}

export default ThemeToggle
