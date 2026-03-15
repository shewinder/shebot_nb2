import React, { useEffect, useState } from 'react'
import { Card, Row, Col, List, Tag, Spin, Typography, Badge, Space } from 'antd'
import {
  TeamOutlined,
  AppstoreOutlined,
  FileOutlined,
  ApiOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import { getGroupList, getLoadedServices, getLoadedPlugins, getProjectInfo } from '../api'
import StatCard from '../components/StatCard'

const { Title, Text } = Typography

function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({
    groups: [],
    services: [],
    plugins: [],
    projectInfo: null,
    uptime: '0d 0h 0m',
  })

  useEffect(() => {
    fetchData()
    // 模拟运行时间
    const startTime = Date.now()
    const interval = setInterval(() => {
      const diff = Date.now() - startTime
      const days = Math.floor(diff / (1000 * 60 * 60 * 24))
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
      setStats(prev => ({
        ...prev,
        uptime: `${days}d ${hours}h ${minutes}m`,
      }))
    }, 60000)
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [groups, services, plugins, projectInfo] = await Promise.all([
        getGroupList(),
        getLoadedServices(),
        getLoadedPlugins(),
        getProjectInfo(),
      ])
      setStats(prev => ({
        ...prev,
        groups: groups || [],
        services: services || [],
        plugins: plugins || [],
        projectInfo: projectInfo,
      }))
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" />
      </div>
    )
  }

  const statItems = [
    {
      title: '已加入群数',
      value: stats.groups?.length || 0,
      icon: <TeamOutlined />,
      color: '#10b981',
      gradient: true,
    },
    {
      title: '服务数量',
      value: stats.services?.length || 0,
      icon: <AppstoreOutlined />,
      color: '#6366f1',
      gradient: true,
    },
    {
      title: '插件数量',
      value: stats.plugins?.length || 0,
      icon: <FileOutlined />,
      color: '#8b5cf6',
      gradient: true,
    },
    {
      title: '运行状态',
      value: '正常',
      suffix: '',
      icon: <ApiOutlined />,
      color: '#06b6d4',
      gradient: true,
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={2} style={{ margin: 0, marginBottom: 8 }}>
          <span className="gradient-text">仪表盘</span>
        </Title>
        <Text type="secondary">
          <ClockCircleOutlined style={{ marginRight: 8 }} />
          运行时间: {stats.uptime}
        </Text>
      </div>

      <Row gutter={[16, 16]}>
        {statItems.map((item, index) => (
          <Col xs={24} sm={12} lg={6} key={item.title}>
            <StatCard {...item} delay={index * 100} />
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <TeamOutlined style={{ color: '#6366f1' }} />
                <span>群列表</span>
              </Space>
            }
            extra={<Tag color="blue">{stats.groups?.length || 0} 个群</Tag>}
            style={{ 
              borderRadius: 'var(--radius-lg)',
              height: '100%',
            }}
          >
            <List
              size="small"
              dataSource={stats.groups?.slice(0, 10) || []}
              renderItem={(item) => (
                <List.Item
                  style={{
                    padding: '12px 0',
                    borderBottom: '1px solid var(--border-light)',
                  }}
                >
                  <List.Item.Meta
                    title={<Text strong>{item.group_name}</Text>}
                    description={
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        群号: {item.group_id}
                      </Text>
                    }
                  />
                  <Badge status="success" text="在线" />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <FileOutlined style={{ color: '#8b5cf6' }} />
                <span>已加载插件</span>
              </Space>
            }
            extra={<Tag color="purple">{stats.plugins?.length || 0} 个插件</Tag>}
            style={{ 
              borderRadius: 'var(--radius-lg)',
              height: '100%',
            }}
          >
            <List
              size="small"
              dataSource={stats.plugins?.slice(0, 10) || []}
              renderItem={(item) => (
                <List.Item
                  style={{
                    padding: '12px 0',
                    borderBottom: '1px solid var(--border-light)',
                  }}
                >
                  <List.Item.Meta
                    title={<Text strong>{item.name}</Text>}
                    description={
                      <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                        {item.module}
                      </Text>
                    }
                  />
                  <Tag color="cyan">{item.matcher} 个匹配器</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {stats.projectInfo && (
        <Card
          title="项目信息"
          style={{ 
            marginTop: 24,
            borderRadius: 'var(--radius-lg)',
          }}
        >
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12}>
              <Text type="secondary">项目名称:</Text>
              <div style={{ marginTop: 4 }}>
                <Text strong style={{ fontSize: 16 }}>
                  {stats.projectInfo.name}
                </Text>
              </div>
            </Col>
            <Col xs={24} sm={12}>
              <Text type="secondary">项目目录:</Text>
              <div style={{ marginTop: 4 }}>
                <code style={{ 
                  background: 'var(--bg-tertiary)',
                  padding: '4px 8px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                }}>
                  {stats.projectInfo.dir}
                </code>
              </div>
            </Col>
          </Row>
        </Card>
      )}
    </div>
  )
}

export default Dashboard
