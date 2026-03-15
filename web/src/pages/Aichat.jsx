import React, { useEffect, useState } from 'react'
import {
  Card,
  Select,
  Button,
  message,
  Spin,
  Typography,
  Space,
  Tag,
  Input,
  Tabs,
  Descriptions,
  Empty,
  List,
  Popconfirm,
  Divider,
  Alert,
  Modal
} from 'antd'
import {
  SaveOutlined,
  ReloadOutlined,
  RobotOutlined,
  UserOutlined,
  TeamOutlined,
  GlobalOutlined,
  DeleteOutlined,
  PlusOutlined,
  EyeOutlined
} from '@ant-design/icons'
import * as aichatApi from '../api'

const { Title, Text } = Typography
const { TextArea } = Input
const { Option } = Select
const { TabPane } = Tabs

function Aichat() {
  const [loading, setLoading] = useState(true)
  const [models, setModels] = useState([])
  const [currentModel, setCurrentModel] = useState(null)
  const [selectedModel, setSelectedModel] = useState(null)
  
  // 人格相关
  const [personas, setPersonas] = useState({})
  const [globalPersona, setGlobalPersona] = useState('')
  const [groupPersonaInput, setGroupPersonaInput] = useState({ group_id: '', content: '' })
  const [userIdInput, setUserIdInput] = useState('')
  const [userPersonaInfo, setUserPersonaInfo] = useState(null)
  const [groups, setGroups] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState(null)
  
  // 已保存的人格
  const [savedPersonas, setSavedPersonas] = useState([])
  const [savedPersonaUserId, setSavedPersonaUserId] = useState('')
  const [newPersonaName, setNewPersonaName] = useState('')
  const [newPersonaContent, setNewPersonaContent] = useState('')
  const [viewPersonaModalVisible, setViewPersonaModalVisible] = useState(false)
  const [viewingPersona, setViewingPersona] = useState(null)
  
  // 配置相关
  const [config, setConfig] = useState(null)

  useEffect(() => {
    fetchInitialData()
  }, [])

  const fetchInitialData = async () => {
    setLoading(true)
    try {
      await Promise.all([
        fetchModels(),
        fetchPersonas(),
        fetchConfig(),
        fetchSuperusers(),
        fetchGroups()
      ])
    } catch (error) {
      message.error('加载数据失败: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchModels = async () => {
    try {
      const [modelsData, currentData] = await Promise.all([
        aichatApi.getAichatModels(),
        aichatApi.getCurrentModel()
      ])
      setModels(modelsData || [])
      setCurrentModel(currentData)
      if (currentData) {
        setSelectedModel(currentData.id)
      }
    } catch (error) {
      message.error('加载模型列表失败: ' + error.message)
    }
  }

  const fetchPersonas = async () => {
    try {
      const data = await aichatApi.getAichatPersonas()
      setPersonas(data || {})
      // 始终更新 globalPersona，即使没有设置（为空）
      setGlobalPersona(data?.global || '')
    } catch (error) {
      message.error('加载人格设置失败: ' + error.message)
    }
  }

  const fetchConfig = async () => {
    try {
      const data = await aichatApi.getAichatConfig()
      setConfig(data)
    } catch (error) {
      // 配置文件可能不存在，不显示错误
    }
  }

  const fetchGroups = async () => {
    try {
      const data = await aichatApi.getAichatGroups()
      setGroups(data || [])
    } catch (error) {
      // 不显示错误
    }
  }

  const fetchSuperusers = async () => {
    try {
      const data = await aichatApi.getSuperusers()
      const firstSu = data?.first_superuser
      // 将第一个超级用户填入用户ID输入框作为默认值
      if (firstSu) {
        if (!userIdInput) {
          setUserIdInput(String(firstSu))
        }
        if (!savedPersonaUserId) {
          setSavedPersonaUserId(String(firstSu))
        }
      }
    } catch (error) {
      // 不显示错误，因为可能没有权限
    }
  }

  const handleSwitchModel = async () => {
    if (!selectedModel || selectedModel === currentModel?.id) {
      message.info('请选择不同的模型')
      return
    }
    try {
      const result = await aichatApi.switchModel(selectedModel)
      message.success(result)
      await fetchModels()
    } catch (error) {
      message.error('切换模型失败: ' + error.message)
    }
  }

  const handleSetGlobalPersona = async () => {
    console.log('[handleSetGlobalPersona] 开始设置全局人格')
    try {
      const result = await aichatApi.setGlobalPersona(globalPersona)
      console.log('[handleSetGlobalPersona] 设置成功:', result)
      console.log('[handleSetGlobalPersona] 设置成功:', result)
      message.success(result)
      console.log('[handleSetGlobalPersona] 开始刷新personas')
      await fetchPersonas()
      console.log('[handleSetGlobalPersona] 刷新完成')
    } catch (error) {
      console.error('[handleSetGlobalPersona] 设置失败:', error.message)
      message.error('设置全局人格失败: ' + error.message)
    }
  }

  const handleClearGlobalPersona = async () => {
    try {
      const result = await aichatApi.clearPersona('global')
      message.success(result)
      setGlobalPersona('')
      await fetchPersonas()
    } catch (error) {
      message.error('清除全局人格失败: ' + error.message)
    }
  }

  const handleSetGroupPersona = async () => {
    if (!groupPersonaInput.group_id) {
      message.error('请输入群组ID')
      return
    }
    try {
      const result = await aichatApi.setGroupPersona(
        parseInt(groupPersonaInput.group_id),
        groupPersonaInput.content
      )
      message.success(result)
      setGroupPersonaInput({ group_id: '', content: '' })
    } catch (error) {
      message.error('设置群组人格失败: ' + error.message)
    }
  }

  const handleQueryUserPersona = async () => {
    if (!userIdInput) {
      message.error('请输入用户ID')
      return
    }
    try {
      const data = await aichatApi.getAichatPersonas(null, parseInt(userIdInput))
      setUserPersonaInfo(data)
    } catch (error) {
      message.error('查询用户人格失败: ' + error.message)
    }
  }

  const handleFetchSavedPersonas = async () => {
    if (!savedPersonaUserId) {
      message.error('请输入用户ID')
      return
    }
    try {
      const data = await aichatApi.getSavedPersonas(parseInt(savedPersonaUserId))
      setSavedPersonas(data || [])
    } catch (error) {
      message.error('获取已保存人格失败: ' + error.message)
    }
  }

  const handleSavePersona = async () => {
    if (!savedPersonaUserId || !newPersonaName || !newPersonaContent) {
      message.error('请填写完整信息')
      return
    }
    try {
      const result = await aichatApi.savePersona(
        parseInt(savedPersonaUserId),
        newPersonaName,
        newPersonaContent
      )
      message.success(result)
      setNewPersonaName('')
      setNewPersonaContent('')
      await handleFetchSavedPersonas()
    } catch (error) {
      message.error('保存人格失败: ' + error.message)
    }
  }

  const handleDeleteSavedPersona = async (name) => {
    try {
      const result = await aichatApi.deleteSavedPersona(parseInt(savedPersonaUserId), name)
      message.success(result)
      await handleFetchSavedPersonas()
    } catch (error) {
      message.error('删除人格失败: ' + error.message)
    }
  }

  const handleViewPersona = (persona) => {
    setViewingPersona(persona)
    setViewPersonaModalVisible(true)
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
      <Title level={2}>
        <RobotOutlined /> AI 聊天管理
      </Title>

      <Tabs defaultActiveKey="models">
        <TabPane
          tab={<span><RobotOutlined /> 模型管理</span>}
          key="models"
        >
          <Card
            title="当前模型"
            extra={
              <Button icon={<ReloadOutlined />} onClick={fetchModels}>
                刷新
              </Button>
            }
          >
            {currentModel ? (
              <Descriptions bordered column={2}>
                <Descriptions.Item label="模型名称">
                  <Tag color="blue">{currentModel.name}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="模型ID">
                  <code>{currentModel.id}</code>
                </Descriptions.Item>
                <Descriptions.Item label="模型类型">{currentModel.model}</Descriptions.Item>
                <Descriptions.Item label="API 地址">{currentModel.api_base}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  {currentModel.is_current && <Tag color="green">当前使用</Tag>}
                  {currentModel.is_default && <Tag color="orange">默认</Tag>}
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty description="未配置模型" />
            )}
          </Card>

          <Card title="切换模型" style={{ marginTop: 16 }}>
            <Space>
              <Text>选择模型:</Text>
              <Select
                style={{ width: 250 }}
                value={selectedModel}
                onChange={setSelectedModel}
                placeholder="请选择模型"
              >
                {models.map(model => (
                  <Option key={model.id} value={model.id}>
                    {model.name} ({model.model})
                    {model.is_current && ' [当前]'}
                    {model.is_default && ' [默认]'}
                  </Option>
                ))}
              </Select>
              <Button
                type="primary"
                onClick={handleSwitchModel}
                disabled={!selectedModel || selectedModel === currentModel?.id}
              >
                切换模型
              </Button>
            </Space>
          </Card>

          {config && (
            <Card title="配置信息" style={{ marginTop: 16 }}>
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="最大历史消息">{config.max_history}</Descriptions.Item>
                <Descriptions.Item label="会话超时">{config.session_timeout} 秒</Descriptions.Item>
                <Descriptions.Item label="最大 Token">{config.max_tokens}</Descriptions.Item>
                <Descriptions.Item label="温度">{config.temperature}</Descriptions.Item>
                <Descriptions.Item label="最大保存人格数">{config.max_saved_personas}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}
        </TabPane>

        <TabPane
          tab={<span><GlobalOutlined /> 全局人格</span>}
          key="global-persona"
        >
          {/* 显示当前全局人格 */}
          {personas?.global && (
            <Card 
              title="当前全局默认人格" 
              style={{ marginBottom: 16 }}
              extra={
                <Space>
                  <Button 
                    type="link" 
                    icon={<EyeOutlined />}
                    onClick={() => handleViewPersona({
                      name: '全局默认人格',
                      content: personas.global
                    })}
                  >
                    查看完整内容
                  </Button>
                  <Popconfirm
                    title="确定要清除全局人格吗？"
                    onConfirm={handleClearGlobalPersona}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button type="link" danger icon={<DeleteOutlined />}>
                      清除
                    </Button>
                  </Popconfirm>
                </Space>
              }
            >
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4, margin: 0 }}>
                {personas.global.length > 200 
                  ? personas.global.slice(0, 200) + '...' 
                  : personas.global}
              </pre>
            </Card>
          )}

          <Card title={personas?.global ? '修改全局默认人格' : '设置全局默认人格'}>
            <Alert
              message="全局默认人格"
              description="设置全局默认人格后，所有没有设置个人人格的用户都会使用这个人格。人格设置优先级：用户人格 > 群组人格 > 全局人格 > 配置默认"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Space direction="vertical" style={{ width: '100%' }}>
              <TextArea
                value={globalPersona}
                onChange={e => setGlobalPersona(e.target.value)}
                placeholder="请输入全局默认人格描述，例如：你是一个友好的AI助手..."
                rows={6}
              />
              <Space>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={handleSetGlobalPersona}
                  disabled={!globalPersona.trim()}
                >
                  {personas?.global ? '更新全局人格' : '保存全局人格'}
                </Button>
                {personas?.global && (
                  <Popconfirm
                    title="确定要清除全局人格吗？"
                    onConfirm={handleClearGlobalPersona}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button icon={<DeleteOutlined />} danger>
                      清除全局人格
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            </Space>
          </Card>

          {personas?.config && (
            <Card title="配置文件默认人格" style={{ marginTop: 16 }}>
              <Alert
                message="来自配置文件"
                description="这是 config/aichat.json 中配置的 default_persona"
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
              />
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>
                {personas.config}
              </pre>
            </Card>
          )}
        </TabPane>

        <TabPane
          tab={<span><TeamOutlined /> 群组人格</span>}
          key="group-persona"
        >
          <Card title="设置群组默认人格">
            <Alert
              message="群组人格"
              description="设置群组默认人格后，该群所有没有设置个人人格的用户都会使用这个人格。从下拉列表选择已加入的群组进行设置。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Space direction="vertical" style={{ width: '100%' }}>
              <Select
                style={{ width: 400 }}
                placeholder="选择群组"
                value={selectedGroupId}
                onChange={(value) => {
                  setSelectedGroupId(value)
                  setGroupPersonaInput({ ...groupPersonaInput, group_id: String(value) })
                }}
                showSearch
                optionFilterProp="children"
                filterOption={(input, option) =>
                  option?.children?.toLowerCase().includes(input.toLowerCase())
                }
              >
                {groups.map(group => (
                  <Option key={group.group_id} value={group.group_id}>
                    {group.group_name} ({group.group_id}) {group.has_persona && '[已设置人格]'}
                  </Option>
                ))}
              </Select>
              
              {selectedGroupId && (
                <div style={{ marginTop: 8 }}>
                  <Tag color="blue">
                    群成员数: {groups.find(g => g.group_id === selectedGroupId)?.member_count || 0}
                  </Tag>
                  {groups.find(g => g.group_id === selectedGroupId)?.has_persona && (
                    <Tag color="green">已设置人格</Tag>
                  )}
                </div>
              )}
              
              <TextArea
                placeholder="请输入群组默认人格描述..."
                value={groupPersonaInput.content}
                onChange={e => setGroupPersonaInput({ ...groupPersonaInput, content: e.target.value })}
                rows={6}
                style={{ marginTop: 8 }}
              />
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSetGroupPersona}
                disabled={!selectedGroupId}
              >
                保存群组人格
              </Button>
            </Space>
          </Card>

          {groups.filter(g => g.has_persona).length > 0 && (
            <Card title="已设置人格的群组" style={{ marginTop: 16 }}>
              <List
                size="small"
                bordered
                dataSource={groups.filter(g => g.has_persona)}
                renderItem={item => (
                  <List.Item
                    actions={[
                      <Button 
                        type="link" 
                        onClick={() => {
                          setSelectedGroupId(item.group_id)
                          setGroupPersonaInput({ ...groupPersonaInput, group_id: String(item.group_id) })
                        }}
                      >
                        编辑
                      </Button>,
                      <Popconfirm
                        title="确定要清除该群组的人格吗？"
                        onConfirm={async () => {
                          try {
                            await aichatApi.clearPersona('group', item.group_id)
                            message.success('群组人格已清除')
                            await fetchGroups()
                          } catch (error) {
                            message.error('清除失败: ' + error.message)
                          }
                        }}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="link" danger>清除</Button>
                      </Popconfirm>
                    ]}
                  >
                    <List.Item.Meta
                      title={`${item.group_name} (${item.group_id})`}
                      description={item.persona_preview}
                    />
                  </List.Item>
                )}
              />
            </Card>
          )}
        </TabPane>

        <TabPane
          tab={<span><UserOutlined /> 用户人格查询</span>}
          key="user-persona"
        >
          <Card title="查询用户人格">
            <Space style={{ marginBottom: 16 }}>
              <Input
                placeholder="请输入用户QQ号"
                value={userIdInput}
                onChange={e => setUserIdInput(e.target.value)}
                style={{ width: 200 }}
              />
              <Button type="primary" onClick={handleQueryUserPersona}>
                查询
              </Button>
            </Space>

            {userPersonaInfo && (
              <div>
                <Divider />
                <Title level={4}>查询结果</Title>
                <Descriptions bordered column={1}>
                  <Descriptions.Item label="当前上下文人格">
                    {userPersonaInfo.user || '未设置'}
                  </Descriptions.Item>
                  <Descriptions.Item label="当前上下文群组人格">
                    {userPersonaInfo.group || '未设置'}
                  </Descriptions.Item>
                  <Descriptions.Item label="全局人格">
                    {userPersonaInfo.global || '未设置'}
                  </Descriptions.Item>
                  <Descriptions.Item label="配置默认">
                    {userPersonaInfo.config || '未设置'}
                  </Descriptions.Item>
                  <Descriptions.Item label="当前生效">
                    <Tag color="green">{userPersonaInfo.effective || '无'}</Tag>
                  </Descriptions.Item>
                </Descriptions>

                {/* 显示该用户在所有群组中的人格设置 */}
                {userPersonaInfo.all_user_personas && userPersonaInfo.all_user_personas.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Title level={5}>该用户设置的所有人格</Title>
                    <List
                      size="small"
                      bordered
                      dataSource={userPersonaInfo.all_user_personas}
                      renderItem={item => (
                        <List.Item
                          actions={[
                            <Button 
                              type="link" 
                              icon={<EyeOutlined />}
                              onClick={() => handleViewPersona({
                                name: item.is_private ? '私聊人格' : `群组 ${item.group_id} 人格`,
                                content: item.full_persona || item.persona
                              })}
                            >
                              查看完整内容
                            </Button>
                          ]}
                        >
                          <List.Item.Meta
                            title={item.is_private ? '私聊人格' : `群组 ${item.group_id}`}
                            description={item.persona}
                          />
                        </List.Item>
                      )}
                    />
                  </div>
                )}
              </div>
            )}
          </Card>
        </TabPane>

        <TabPane
          tab={<span><SaveOutlined /> 已保存人格</span>}
          key="saved-personas"
        >
          <Card title="管理用户已保存的人格">
            <Space style={{ marginBottom: 16 }}>
              <Input
                placeholder="请输入用户QQ号"
                value={savedPersonaUserId}
                onChange={e => setSavedPersonaUserId(e.target.value)}
                style={{ width: 200 }}
              />
              <Button type="primary" onClick={handleFetchSavedPersonas}>
                查询
              </Button>
            </Space>

            {savedPersonas.length > 0 ? (
              <List
                bordered
                dataSource={savedPersonas}
                renderItem={item => (
                  <List.Item
                    actions={[
                      <Button 
                        type="link" 
                        icon={<EyeOutlined />}
                        onClick={() => handleViewPersona(item)}
                      >
                        查看完整内容
                      </Button>,
                      <Popconfirm
                        title="确定要删除这个人格吗？"
                        onConfirm={() => handleDeleteSavedPersona(item.name)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="link" danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    ]}
                  >
                    <List.Item.Meta
                      title={item.name}
                      description={item.content.length > 100 
                        ? item.content.slice(0, 100) + '...' 
                        : item.content}
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="该用户没有保存的人格" />
            )}

            <Divider />

            <Card title="添加新人格" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Input
                  placeholder="人格名称"
                  value={newPersonaName}
                  onChange={e => setNewPersonaName(e.target.value)}
                />
                <TextArea
                  placeholder="人格描述"
                  value={newPersonaContent}
                  onChange={e => setNewPersonaContent(e.target.value)}
                  rows={4}
                />
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={handleSavePersona}
                  disabled={!savedPersonaUserId}
                >
                  添加人格
                </Button>
              </Space>
            </Card>
          </Card>
        </TabPane>
      </Tabs>

      {/* 查看完整人格内容的弹窗 - 放在所有 TabPane 外部 */}
      <Modal
        title={viewingPersona?.name}
        open={viewPersonaModalVisible}
        onCancel={() => setViewPersonaModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setViewPersonaModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={700}
      >
        <TextArea
          value={viewingPersona?.content}
          readOnly
          rows={15}
          style={{ 
            fontFamily: 'monospace', 
            fontSize: 14,
            backgroundColor: '#f5f5f5'
          }}
        />
      </Modal>
    </div>
  )
}

export default Aichat
