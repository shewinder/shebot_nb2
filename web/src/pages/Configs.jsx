import React, { useEffect, useState } from 'react'
import {
  Card,
  Select,
  Button,
  message,
  Spin,
  Typography,
  Space,
  Empty,
  Tag,
  Alert
} from 'antd'
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons'
import { getPluginConfig, setPluginConfig } from '../api'

const { Title, Text } = Typography
const { Option } = Select

// 简单的 JSON 编辑器组件
function JsonEditor({ value, onChange }) {
  const [text, setText] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    setText(JSON.stringify(value, null, 2))
  }, [value])

  const handleChange = (e) => {
    const newText = e.target.value
    setText(newText)
    try {
      const parsed = JSON.parse(newText)
      setError(null)
      onChange(parsed)
    } catch (err) {
      setError('JSON 格式错误: ' + err.message)
    }
  }

  return (
    <div>
      <textarea
        value={text}
        onChange={handleChange}
        style={{
          width: '100%',
          minHeight: 400,
          fontFamily: 'monospace',
          fontSize: 14,
          padding: 12,
          border: `1px solid ${error ? '#ff4d4f' : '#d9d9d9'}`,
          borderRadius: 6,
          resize: 'vertical'
        }}
      />
      {error && (
        <Alert
          message={error}
          type="error"
          style={{ marginTop: 8 }}
          showIcon
        />
      )}
    </div>
  )
}

// 简单的键值编辑器
function KeyValueEditor({ value, onChange }) {
  const handleChange = (key, newValue) => {
    onChange({ ...value, [key]: newValue })
  }

  const handleDelete = (key) => {
    const newValue = { ...value }
    delete newValue[key]
    onChange(newValue)
  }

  const handleAdd = () => {
    const newKey = `new_key_${Date.now()}`
    onChange({ ...value, [newKey]: '' })
  }

  return (
    <div>
      {Object.entries(value).map(([key, val]) => (
        <Space key={key} style={{ display: 'flex', marginBottom: 8 }}>
          <input
            value={key}
            onChange={(e) => {
              const newValue = { ...value }
              delete newValue[key]
              newValue[e.target.value] = val
              onChange(newValue)
            }}
            style={{ width: 200, padding: 8, border: '1px solid #d9d9d9', borderRadius: 4 }}
            placeholder="键"
          />
          <input
            value={String(val)}
            onChange={(e) => handleChange(key, e.target.value)}
            style={{ width: 300, padding: 8, border: '1px solid #d9d9d9', borderRadius: 4 }}
            placeholder="值"
          />
          <Button danger onClick={() => handleDelete(key)}>删除</Button>
        </Space>
      ))}
      <Button onClick={handleAdd} type="dashed">添加字段</Button>
    </div>
  )
}

function Configs() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [configs, setConfigs] = useState({})
  const [selectedConfig, setSelectedConfig] = useState(null)
  const [editValue, setEditValue] = useState(null)

  useEffect(() => {
    fetchConfigs()
  }, [])

  const fetchConfigs = async () => {
    try {
      const data = await getPluginConfig()
      setConfigs(data || {})
      const keys = Object.keys(data || {})
      if (keys.length > 0) {
        setSelectedConfig(keys[0])
        setEditValue(data[keys[0]])
      }
    } catch (error) {
      message.error('加载配置失败: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  const handleConfigChange = (value) => {
    setSelectedConfig(value)
    setEditValue(configs[value])
  }

  const handleSave = async () => {
    if (!selectedConfig || !editValue) return
    setSaving(true)
    try {
      await setPluginConfig(selectedConfig, editValue)
      setConfigs(prev => ({ ...prev, [selectedConfig]: editValue }))
      message.success('保存成功')
    } catch (error) {
      message.error('保存失败: ' + error.message)
    } finally {
      setSaving(false)
    }
  }

  const handleRefresh = async () => {
    setLoading(true)
    await fetchConfigs()
    message.success('刷新成功')
  }

  const renderValueType = (value) => {
    if (value === null) return <Tag>null</Tag>
    if (typeof value === 'boolean') return <Tag color={value ? 'green' : 'red'}>{String(value)}</Tag>
    if (typeof value === 'number') return <Tag color="blue">{value}</Tag>
    if (typeof value === 'string') return <Tag color="cyan">"{value}"</Tag>
    if (Array.isArray(value)) return <Tag color="purple">Array({value.length})</Tag>
    if (typeof value === 'object') return <Tag color="orange">Object</Tag>
    return <Tag>{String(value)}</Tag>
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" />
      </div>
    )
  }

  const configKeys = Object.keys(configs)

  return (
    <div>
      <Title level={2}>配置管理</Title>
      
      <Card
        extra={
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            刷新
          </Button>
        }
      >
        {configKeys.length === 0 ? (
          <Empty description="暂无插件配置" />
        ) : (
          <>
            <Space style={{ marginBottom: 24 }}>
              <Text>选择配置:</Text>
              <Select
                style={{ width: 250 }}
                value={selectedConfig}
                onChange={handleConfigChange}
              >
                {configKeys.map(key => (
                  <Option key={key} value={key}>{key}</Option>
                ))}
              </Select>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                onClick={handleSave}
              >
                保存修改
              </Button>
            </Space>

            {selectedConfig && editValue && (
              <div>
                <Card
                  type="inner"
                  title={`${selectedConfig} 配置`}
                  style={{ marginBottom: 16 }}
                >
                  {typeof editValue === 'object' && editValue !== null ? (
                    <div style={{ marginBottom: 16 }}>
                      <Text type="secondary">当前字段概览:</Text>
                      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {Object.entries(editValue).map(([key, val]) => (
                          <Tag key={key}>
                            {key}: {renderValueType(val)}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  
                  <JsonEditor
                    value={editValue}
                    onChange={setEditValue}
                  />
                </Card>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}

export default Configs
