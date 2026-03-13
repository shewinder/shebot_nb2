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
  message
} from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ClearOutlined,
  DownloadOutlined,
  SettingOutlined,
  ReloadOutlined,
  WifiOutlined,
  DisconnectOutlined
} from '@ant-design/icons'

const { Title, Text } = Typography
const { Option } = Select

// 日志级别颜色映射
const levelColors = {
  DEBUG: 'default',
  INFO: 'blue',
  SUCCESS: 'green',
  WARNING: 'orange',
  ERROR: 'red',
  CRITICAL: 'red'
}

// 日志行组件
function LogLine({ log }) {
  return (
    <div style={{ 
      fontFamily: 'monospace', 
      fontSize: 13, 
      padding: '2px 0',
      borderBottom: '1px solid #f0f0f0'
    }}>
      <span style={{ color: '#999' }}>[{log.timestamp}]</span>
      {' '}
      <Tag color={levelColors[log.level] || 'default'} style={{ fontSize: 11, lineHeight: '16px' }}>
        {log.level}
      </Tag>
      {' '}
      <Text strong style={{ color: '#666' }}>{log.module}:</Text>
      {' '}
      <span style={{ 
        color: log.level === 'ERROR' || log.level === 'CRITICAL' ? '#cf1322' : '#333'
      }}>
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
  const [maxLines, setMaxLines] = useState(500)
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const logContainerRef = useRef(null)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)

  // WebSocket 连接
  const connectWebSocket = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }
    
    setConnecting(true)
    
    // 使用当前页面 host，支持相对路径
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/ws/logs`
    
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        setConnecting(false)
        message.success('日志 WebSocket 已连接')
        
        // 发送心跳保活
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
        if (ws.pingInterval) {
          clearInterval(ws.pingInterval)
        }
        
        // 自动重连
        if (isRunning) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('WebSocket 断开，尝试重连...')
            connectWebSocket()
          }, 3000)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setConnecting(false)
      }

      ws.onmessage = (event) => {
        try {
          const log = JSON.parse(event.data)
          
          // 处理心跳响应
          if (log.type === 'pong') {
            return
          }
          
          // 添加到日志列表
          setLogs(prev => {
            const newLogs = [...prev, log]
            if (newLogs.length > maxLines) {
              return newLogs.slice(newLogs.length - maxLines)
            }
            return newLogs
          })
        } catch (e) {
          console.error('解析日志消息失败:', e)
        }
      }
    } catch (error) {
      console.error('创建 WebSocket 失败:', error)
      setConnecting(false)
    }
  }

  // 断开 WebSocket
  const disconnectWebSocket = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      if (wsRef.current.pingInterval) {
        clearInterval(wsRef.current.pingInterval)
      }
      wsRef.current.close()
      wsRef.current = null
    }
    setConnected(false)
  }

  // 启动/暂停
  useEffect(() => {
    if (isRunning) {
      connectWebSocket()
    } else {
      disconnectWebSocket()
    }
    
    return () => {
      disconnectWebSocket()
    }
  }, [isRunning])

  // 自动滚动
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const handleClear = () => {
    setLogs([])
  }

  const handleDownload = () => {
    const content = logs.map(log => 
      `[${log.timestamp}] [${log.level}] ${log.module}: ${log.message}`
    ).join('\n')
    
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

  // 根据级别过滤日志
  const filteredLogs = filterLevel === 'ALL' 
    ? logs 
    : logs.filter(log => log.level === filterLevel)

  return (
    <div>
      <Title level={2}>日志监控</Title>
      
      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
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
            下载日志
          </Button>
          
          <Button 
            icon={<ReloadOutlined spin={connecting} />} 
            onClick={handleReconnect}
            disabled={connecting}
          >
            重连
          </Button>
          
          <Divider type="vertical" />
          
          <Switch
            checked={autoScroll}
            onChange={setAutoScroll}
            checkedChildren="自动滚动"
            unCheckedChildren="自动滚动"
          />
          
          <Select
            value={filterLevel}
            onChange={setFilterLevel}
            style={{ width: 100 }}
          >
            <Option value="ALL">全部级别</Option>
            <Option value="DEBUG">DEBUG</Option>
            <Option value="INFO">INFO</Option>
            <Option value="SUCCESS">SUCCESS</Option>
            <Option value="WARNING">WARNING</Option>
            <Option value="ERROR">ERROR</Option>
          </Select>
          
          <Select
            value={maxLines}
            onChange={(val) => {
              setMaxLines(val)
              // 截断现有日志
              setLogs(prev => prev.slice(-val))
            }}
            style={{ width: 120 }}
          >
            <Option value={100}>100 行</Option>
            <Option value={500}>500 行</Option>
            <Option value={1000}>1000 行</Option>
            <Option value={5000}>5000 行</Option>
          </Select>
          
          <Divider type="vertical" />
          
          <Badge 
            status={connected ? 'success' : 'error'} 
            text={
              <Space>
                {connected ? <WifiOutlined /> : <DisconnectOutlined />}
                {connecting ? '连接中...' : (connected ? '已连接' : '未连接')}
              </Space>
            } 
          />
        </Space>

        <div
          ref={logContainerRef}
          style={{
            height: 500,
            overflowY: 'auto',
            background: '#fafafa',
            border: '1px solid #d9d9d9',
            borderRadius: 6,
            padding: 12
          }}
        >
          {filteredLogs.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#999', padding: '100px 0' }}>
              {connected ? '暂无日志' : 'WebSocket 未连接'}
            </div>
          ) : (
            filteredLogs.map((log, index) => (
              <LogLine key={index} log={log} />
            ))
          )}
        </div>
        
        <div style={{ marginTop: 8, textAlign: 'right' }}>
          <Text type="secondary">
            显示 {filteredLogs.length} / {logs.length} 条日志
            {connected && ' | 实时接收中...'}
          </Text>
        </div>
      </Card>
    </div>
  )
}

export default Logs
