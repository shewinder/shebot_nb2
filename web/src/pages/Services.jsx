import React, { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Tag,
  Switch,
  Select,
  Button,
  message,
  Spin,
  Typography,
  Space,
  Tabs,
  Badge
} from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import {
  getGroupList,
  getLoadedServices,
  getServiceGroups,
  getGroupServices,
  setService
} from '../api'

const { Title, Text } = Typography
const { Option } = Select
const { TabPane } = Tabs

function Services() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [groups, setGroups] = useState([])
  const [services, setServices] = useState([])
  const [serviceGroups, setServiceGroups] = useState({})
  const [groupServices, setGroupServices] = useState({})
  const [selectedService, setSelectedService] = useState(null)
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [activeTab, setActiveTab] = useState('byService')

  useEffect(() => {
    fetchInitialData()
  }, [])

  const fetchInitialData = async () => {
    try {
      const [groupsData, servicesData] = await Promise.all([
        getGroupList(),
        getLoadedServices()
      ])
      setGroups(groupsData || [])
      setServices(servicesData || [])
      
      if (servicesData?.length > 0) {
        setSelectedService(servicesData[0])
        await fetchServiceGroups(servicesData[0])
      }
      if (groupsData?.length > 0) {
        setSelectedGroup(groupsData[0].group_id)
        await fetchGroupServices(groupsData[0].group_id)
      }
    } catch (error) {
      message.error('加载数据失败: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchServiceGroups = async (serviceName) => {
    if (!serviceName) return
    try {
      const data = await getServiceGroups(serviceName)
      setServiceGroups(prev => ({ ...prev, [serviceName]: data }))
    } catch (error) {
      message.error('加载服务群配置失败')
    }
  }

  const fetchGroupServices = async (groupId) => {
    if (!groupId) return
    try {
      const data = await getGroupServices(groupId)
      setGroupServices(prev => ({ ...prev, [groupId]: data }))
    } catch (error) {
      message.error('加载群服务配置失败')
    }
  }

  const handleServiceChange = async (value) => {
    setSelectedService(value)
    if (!serviceGroups[value]) {
      await fetchServiceGroups(value)
    }
  }

  const handleGroupChange = async (value) => {
    setSelectedGroup(value)
    if (!groupServices[value]) {
      await fetchGroupServices(value)
    }
  }

  const handleToggleService = (groupId, checked) => {
    setServiceGroups(prev => ({
      ...prev,
      [selectedService]: prev[selectedService].map(g =>
        g.group_id === groupId ? { ...g, on: checked } : g
      )
    }))
  }

  const handleToggleGroupService = (serviceName, checked) => {
    setGroupServices(prev => ({
      ...prev,
      [selectedGroup]: {
        ...prev[selectedGroup],
        [serviceName]: checked
      }
    }))
  }

  const handleSaveByService = async () => {
    setSaving(true)
    try {
      const data = serviceGroups[selectedService].reduce((acc, g) => {
        if (!acc[g.group_id]) acc[g.group_id] = {}
        acc[g.group_id][selectedService] = g.on
        return acc
      }, {})
      await setService(data)
      message.success('保存成功')
    } catch (error) {
      message.error('保存失败: ' + error.message)
    } finally {
      setSaving(false)
    }
  }

  const handleSaveByGroup = async () => {
    setSaving(true)
    try {
      const data = { [selectedGroup]: groupServices[selectedGroup] }
      await setService(data)
      message.success('保存成功')
    } catch (error) {
      message.error('保存失败: ' + error.message)
    } finally {
      setSaving(false)
    }
  }

  const handleRefresh = async () => {
    setLoading(true)
    await fetchInitialData()
    message.success('刷新成功')
  }

  const serviceColumns = [
    {
      title: '群号',
      dataIndex: 'group_id',
      key: 'group_id',
      width: 120
    },
    {
      title: '群名',
      dataIndex: 'group_name',
      key: 'group_name'
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_, record) => (
        <Badge status={record.on ? 'success' : 'default'} text={record.on ? '已启用' : '已禁用'} />
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Switch
          checked={record.on}
          onChange={(checked) => handleToggleService(record.group_id, checked)}
        />
      )
    }
  ]

  const groupServiceColumns = [
    {
      title: '服务名',
      dataIndex: 'name',
      key: 'name',
      width: 200
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_, record) => (
        <Badge status={record.enabled ? 'success' : 'default'} text={record.enabled ? '已启用' : '已禁用'} />
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Switch
          checked={record.enabled}
          onChange={(checked) => handleToggleGroupService(record.name, checked)}
        />
      )
    }
  ]

  const getGroupServiceData = () => {
    const data = groupServices[selectedGroup]
    if (!data) return []
    return Object.entries(data).map(([name, enabled]) => ({ name, enabled }))
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
      <Title level={2}>服务管理</Title>
      
      <Card
        extra={
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            刷新
          </Button>
        }
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="按服务查看" key="byService">
            <Space style={{ marginBottom: 16 }}>
              <Text>选择服务:</Text>
              <Select
                style={{ width: 200 }}
                value={selectedService}
                onChange={handleServiceChange}
              >
                {services.map(sv => (
                  <Option key={sv} value={sv}>{sv}</Option>
                ))}
              </Select>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                onClick={handleSaveByService}
              >
                保存修改
              </Button>
            </Space>
            
            <Table
              columns={serviceColumns}
              dataSource={serviceGroups[selectedService] || []}
              rowKey="group_id"
              pagination={{ pageSize: 10 }}
              size="small"
            />
          </TabPane>
          
          <TabPane tab="按群查看" key="byGroup">
            <Space style={{ marginBottom: 16 }}>
              <Text>选择群:</Text>
              <Select
                style={{ width: 300 }}
                value={selectedGroup}
                onChange={handleGroupChange}
              >
                {groups.map(g => (
                  <Option key={g.group_id} value={g.group_id}>
                    {g.group_name} ({g.group_id})
                  </Option>
                ))}
              </Select>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                onClick={handleSaveByGroup}
              >
                保存修改
              </Button>
            </Space>
            
            <Table
              columns={groupServiceColumns}
              dataSource={getGroupServiceData()}
              rowKey="name"
              pagination={{ pageSize: 15 }}
              size="small"
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  )
}

export default Services
