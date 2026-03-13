import React, { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, List, Tag, Spin, Typography } from 'antd'
import {
  TeamOutlined,
  AppstoreOutlined,
  FileOutlined,
  ApiOutlined
} from '@ant-design/icons'
import { getGroupList, getLoadedServices, getLoadedPlugins, getProjectInfo } from '../api'

const { Title } = Typography

function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({
    groups: [],
    services: [],
    plugins: [],
    projectInfo: null
  })

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [groups, services, plugins, projectInfo] = await Promise.all([
        getGroupList(),
        getLoadedServices(),
        getLoadedPlugins(),
        getProjectInfo()
      ])
      setStats({ groups, services, plugins, projectInfo })
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

  return (
    <div>
      <Title level={2}>仪表盘</Title>
      
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="已加入群数"
              value={stats.groups?.length || 0}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="服务数量"
              value={stats.services?.length || 0}
              prefix={<AppstoreOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="插件数量"
              value={stats.plugins?.length || 0}
              prefix={<FileOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="运行状态"
              value="正常"
              prefix={<ApiOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="群列表" extra={<Tag color="blue">{stats.groups?.length || 0} 个群</Tag>}>
            <List
              size="small"
              dataSource={stats.groups?.slice(0, 10) || []}
              renderItem={item => (
                <List.Item>
                  <List.Item.Meta
                    title={item.group_name}
                    description={`群号: ${item.group_id}`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="已加载插件" extra={<Tag color="purple">{stats.plugins?.length || 0} 个插件</Tag>}>
            <List
              size="small"
              dataSource={stats.plugins?.slice(0, 10) || []}
              renderItem={item => (
                <List.Item>
                  <List.Item.Meta
                    title={item.name}
                    description={item.module}
                  />
                  <Tag color="cyan">{item.matcher} 个匹配器</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      {stats.projectInfo && (
        <Card title="项目信息" style={{ marginTop: 24 }}>
          <p><strong>项目名称:</strong> {stats.projectInfo.name}</p>
          <p><strong>项目目录:</strong> <code>{stats.projectInfo.dir}</code></p>
        </Card>
      )}
    </div>
  )
}

export default Dashboard
