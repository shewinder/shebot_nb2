import React, { useEffect, useRef, useState } from 'react'
import {
  Card,
  Button,
  Switch,
  Select,
  Space,
  Typography,
  Tag,
  Badge,
  Divider,
  Tooltip,
  message,
  Input,
} from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ClearOutlined,
  DownloadOutlined,
  ReloadOutlined,
  WifiOutlined,
  DisconnectOutlined,
  SearchOutlined,
} from '@ant-design/icons'

const { Title, Text } = Typography
const { Option } = Select
const { Search } = Input

// 日志级别配置
const levelConfig = {
  DEBUG: { color: '#64748b', bg: '#f1f5f9', icon: '🔍' },
  INFO: { color: '#3b82f6', bg: '#dbeafe', icon: 'ℹ️' },
  SUCCESS: { color: '#10b981', bg: '#d1fae5', icon: '✅' },
  WARNING: { color: '#f59e0b', bg: '#fef3c7', icon: '⚠️' },
  ERROR: { color: '#ef4444', bg: '#fee2e2', icon: '❌' },
  CRITICAL: { color: '#dc2626', bg: '#fecaca', icon: '🔴' },
}

// 日志行组件
function LogLine({ log, isDark }) {
  const config = levelConfig[log.level] || levelConfig.INFO
  const isError = log.level === 'ERROR' || log.level === 'CRITICAL'

  return (
    <div
      style={{
        fontFamily: '"JetBrains Mono", "Fira Code", monospace',
        fontSize: 13,
        padding: '6px 12px',
        borderLeft: `3px solid ${config.color}`,
        background: isError ? (isDark ? 'rgba(239, 68, 68, 0.1)' : '#fef2f2') : 'transparent',
        borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.05)' : '#f1f5f9'}`,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.03)' : '#f8fafc'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = isError ? (isDark ? 'rgba(239, 68, 68, 0.1)' : '#fef2f2') : 'transparent'
      }}
    >
      <span
        style={{
          color: isDark ? '#64748b' : '#94a3b8',
          fontSize: 12,
          minWidth: 70,
          flexShrink: 0,
        }}
      >
        {log.timestamp}
      </span>

      <Tag
        style={{
          fontSize: 11,
          fontWeight: 600,
          padding: '0 6px',
          height: 20,
          lineHeight: '20px',
          border: 'none',
          background: isDark ? `${config.color}30` : config.bg,
          color: config.color,
          minWidth: 70,
          textAlign: 'center',
          flexShrink: 0,
        }}
      >
        {log.level}
      </Tag>

      <span
        style={{
          color: isDark ? '#818cf8' : '#6366f1',
          fontWeight: 500,
          minWidth: 100,
          flexShrink: 0,
        }}
      >
        {log.module}
      </span>

      <span
        style={{
          color: isError ? '#ef4444' : isDark ? '#e2e8f0' : '#1e293b',
          wordBreak: 'break-all',
          flex: 1,
        }}
      >
        {log.message}
      </span>
    </div>
  )
}

function Logs() {
  const [logs, setLogs] = useState([])
  const [isRunning, setIsRunning] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)
  const [filterLevel, setFilterLevel] = useState('ALL')
  const [searchText, setSearchText] = useState('')
  const [maxLines, setMaxLines] = useState(500)
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [isDark, setIsDark] = useState(false)
  const logContainerRef = useRef(null)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)

  // 检测主题
  useEffect(() => {
    const checkTheme = () => {
      setIsDark(document.documentElement.getAttribute('data-theme') === 'dark')
    }
    checkTheme()
    const observer = new MutationObserver(checkTheme)
    observer.observe(document.documentElement, { attributes: true })
    return () => observer.disconnect()
  }, [])

  // WebSocket 连接
  const connectWebSocket = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setConnecting(true)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/ws/logs`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        setConnecting(false)
        message.success('日志 WebSocket 已连接')

        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }))
          } else {
            clearInterval(pingInterval)
          }
        }, 30000)
        ws.pingInterval = pingInterval
      }

      ws.onclose = () => {
        setConnected(false)
        setConnecting(false)
        if (ws.pingInterval) clearInterval(ws.pingInterval)
        if (isRunning) {
          reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000)
        }
      }

      ws.onerror = () => setConnecting(false)

      ws.onmessage = (event) => {
        try {
          const log = JSON.parse(event.data)
          if (log.type === 'pong') return
          setLogs((prev) => {
            const newLogs = [...prev, log]
            return newLogs.length > maxLines ? newLogs.slice(-maxLines) : newLogs
          })
        } catch (e) {
          console.error('解析日志失败:', e)
        }
      }
    } catch (error) {
      console.error('WebSocket 创建失败:', error)
      setConnecting(false)
    }
  }

  const disconnectWebSocket = () => {
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
    if (wsRef.current) {
      if (wsRef.current.pingInterval) clearInterval(wsRef.current.pingInterval)
      wsRef.current.close()
      wsRef.current = null
    }
    setConnected(false)
  }

  useEffect(() => {
    if (isRunning) connectWebSocket()
    else disconnectWebSocket()
    return () => disconnectWebSocket()
  }, [isRunning])

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const handleClear = () => setLogs([])

  const handleDownload = () => {
    const content = logs
      .map((log) => `[${log.timestamp}] [${log.level}] ${log.module}: ${log.message}`)
      .join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `bot-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleReconnect = () => {
    disconnectWebSocket()
    setTimeout(connectWebSocket, 100)
  }

  // 过滤日志
  const filteredLogs = logs.filter((log) => {
    const matchLevel = filterLevel === 'ALL' || log.level === filterLevel
    const matchSearch =
      !searchText ||
      log.message.toLowerCase().includes(searchText.toLowerCase()) ||
      log.module.toLowerCase().includes(searchText.toLowerCase())
    return matchLevel && matchSearch
  })

  // 级别统计
  const levelCounts = logs.reduce((acc, log) => {
    acc[log.level] = (acc[log.level] || 0) + 1
    return acc
  }, {})

  return (
    <div>
      <Title level={2} style={{ marginBottom: 24 }}>
        日志监控
      </Title>

      <Card
        style={{
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
        }}
        bodyStyle={{ padding: 0 }}
      >
        {/* 工具栏 */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`,
            background: isDark ? 'rgba(30, 41, 59, 0.5)' : '#f8fafc',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 12,
            alignItems: 'center',
          }}
        >
          <Button
            type={isRunning ? 'default' : 'primary'}
            icon={isRunning ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            onClick={() => setIsRunning(!isRunning)}
          >
            {isRunning ? '暂停' : '开始'}
          </Button>

          <Button icon={<ClearOutlined />} onClick={handleClear}>
            清空
          </Button>

          <Button icon={<DownloadOutlined />} onClick={handleDownload}>
            下载
          </Button>

          <Button
            icon={<ReloadOutlined spin={connecting} />}
            onClick={handleReconnect}
            disabled={connecting}
          >
            重连
          </Button>

          <Divider type="vertical" style={{ margin: '0 4px' }} />

          <Switch
            checked={autoScroll}
            onChange={setAutoScroll}
            checkedChildren="自动滚动"
            unCheckedChildren="自动滚动"
          />

          <Select value={filterLevel} onChange={setFilterLevel} style={{ width: 100 }}>
            <Option value="ALL">全部</Option>
            <Option value="DEBUG">DEBUG</Option>
            <Option value="INFO">INFO</Option>
            <Option value="WARNING">WARNING</Option>
            <Option value="ERROR">ERROR</Option>
          </Select>

          <Search
            placeholder="搜索日志..."
            allowClear
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            prefix={<SearchOutlined />}
          />

          <div style={{ marginLeft: 'auto' }}>
            <Badge
              status={connected ? 'success' : 'error'}
              text={
                <Space>
                  {connected ? <WifiOutlined /> : <DisconnectOutlined />}
                  <Text style={{ color: isDark ? '#94a3b8' : '#64748b' }}>
                    {connecting ? '连接中...' : connected ? '已连接' : '未连接'}
                  </Text>
                </Space>
              }
            />
          </div>
        </div>

        {/* 级别统计 */}
        <div
          style={{
            padding: '8px 20px',
            borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.05)' : '#f1f5f9'}`,
            display: 'flex',
            gap: 16,
            background: isDark ? 'rgba(15, 23, 42, 0.3)' : '#fff',
          }}
        >
          {Object.entries(levelConfig).map(([level, config]) => (
            <Tooltip key={level} title={`${level}: ${levelCounts[level] || 0} 条`}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  cursor: 'pointer',
                  opacity: filterLevel === 'ALL' || filterLevel === level ? 1 : 0.4,
                }}
                onClick={() => setFilterLevel(filterLevel === level ? 'ALL' : level)}
              >
                <span style={{ fontSize: 12 }}>{config.icon}</span>
                <Text style={{ fontSize: 12, color: config.color, fontWeight: 600 }}>
                  {levelCounts[level] || 0}
                </Text>
              </div>
            </Tooltip>
          ))}
        </div>

        {/* 日志列表 */}
        <div
          ref={logContainerRef}
          style={{
            height: 500,
            overflowY: 'auto',
            background: isDark ? '#0f172a' : '#fff',
            fontFamily: 'monospace',
          }}
        >
          {filteredLogs.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                color: isDark ? '#475569' : '#94a3b8',
                padding: '100px 0',
              }}
            >
              <div style={{ fontSize: 48, marginBottom: 16 }}>📋</div>
              <Text style={{ color: isDark ? '#64748b' : '#94a3b8' }}>
                {connected ? '暂无日志' : 'WebSocket 未连接'}
              </Text>
            </div>
          ) : (
            filteredLogs.map((log, index) => <LogLine key={index} log={log} isDark={isDark} />)
          )}
        </div>

        {/* 底部状态 */}
        <div
          style={{
            padding: '8px 20px',
            borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`,
            background: isDark ? 'rgba(30, 41, 59, 0.5)' : '#f8fafc',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            显示 {filteredLogs.length.toLocaleString()} / {logs.length.toLocaleString()} 条日志
          </Text>
          {connected && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              ● 实时接收中
            </Text>
          )}
        </div>
      </Card>
    </div>
  )
}

export default Logs
