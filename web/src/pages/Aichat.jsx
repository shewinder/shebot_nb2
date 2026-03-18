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
  Modal,
  Form,
  Switch,
  InputNumber,
  Upload
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
  EyeOutlined,
  EditOutlined,
  SettingOutlined,
  BookOutlined,
  TagOutlined,
  UploadOutlined,
  ImportOutlined,
  FileImageOutlined
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
  const [configModalVisible, setConfigModalVisible] = useState(false)
  const [configForm] = Form.useForm()

  // 模型编辑相关
  const [modelModalVisible, setModelModalVisible] = useState(false)
  const [modelModalMode, setModelModalMode] = useState('add') // 'add' 或 'edit'
  const [editingModelId, setEditingModelId] = useState(null)
  const [modelForm] = Form.useForm()

  // 全局预设人格相关
  const [globalPresets, setGlobalPresets] = useState([])
  const [newPresetName, setNewPresetName] = useState('')
  const [newPresetContent, setNewPresetContent] = useState('')
  const [editingPreset, setEditingPreset] = useState(null)
  const [presetModalVisible, setPresetModalVisible] = useState(false)
  const [presetForm] = Form.useForm()

  // 角色卡导入相关
  const [importUserId, setImportUserId] = useState('')
  const [importAsGlobal, setImportAsGlobal] = useState(false)
  const [importLoading, setImportLoading] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [uploadFileList, setUploadFileList] = useState([])

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
        fetchGroups(),
        fetchGlobalPresets()
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
        if (!importUserId) {
          setImportUserId(String(firstSu))
        }
      }
    } catch (error) {
      // 不显示错误，因为可能没有权限
    }
  }

  // 处理文件选择（阻止自动上传，仅保存文件列表，验证文件类型）
  const handleBeforeUpload = (file) => {
    // 验证文件类型
    const isValid = file.name.toLowerCase().endsWith('.png') || 
                    file.name.toLowerCase().endsWith('.json')
    if (!isValid) {
      message.error(`不支持的文件格式: ${file.name}，只支持 PNG 和 JSON 文件`)
    }
    // 阻止自动上传，返回 false
    return false
  }
  
  const handleFileChange = ({ fileList }) => {
    // 只更新文件列表，不触发上传
    setUploadFileList(fileList)
  }
  
  // 执行批量导入
  const handleImportBatch = async () => {
    if (!importUserId) {
      message.error('请输入用户ID')
      return
    }
    
    if (!uploadFileList || uploadFileList.length === 0) {
      message.error('请选择要导入的文件')
      return
    }
    
    setImportLoading(true)
    setImportResult(null)
    
    try {
      // 获取实际的 File 对象
      const files = uploadFileList.map(f => f.originFileObj).filter(Boolean)
      
      if (files.length === 0) {
        message.error('文件对象无效')
        setImportLoading(false)
        return
      }
      
      const result = await aichatApi.importCharacters(
        parseInt(importUserId),
        files,
        importAsGlobal
      )
      
      // 注意：request 拦截器已经解包了 response.data
      setImportResult(result)
      setUploadFileList([]) // 清空列表
      
      if (result?.summary?.success > 0) {
        message.success(`成功导入 ${result.summary.success} 个角色卡`)
        // 刷新列表
        if (importAsGlobal) {
          await fetchGlobalPresets()
        }
        if (parseInt(importUserId) === parseInt(savedPersonaUserId)) {
          await handleFetchSavedPersonas()
        }
      } else if (result?.summary?.skipped > 0) {
        message.warning('未找到有效的角色卡文件')
      } else {
        message.error('导入失败')
      }
    } catch (error) {
      message.error('导入失败: ' + error.message)
    } finally {
      setImportLoading(false)
    }
  }

  // 获取全局预设人格
  const fetchGlobalPresets = async () => {
    try {
      const data = await aichatApi.getGlobalPresets()
      setGlobalPresets(data || [])
    } catch (error) {
      message.error('加载全局预设人格失败: ' + error.message)
    }
  }

  // 处理添加/更新全局预设人格
  const handleAddGlobalPreset = async (values) => {
    try {
      // 如果是编辑模式且名称有变更，先重命名
      if (editingPreset && editingPreset.name !== values.name) {
        // 先重命名
        const renameResult = await aichatApi.updateGlobalPresetName(editingPreset.name, values.name)
        message.success(renameResult.data || '重命名成功')
      }
      
      // 添加/更新内容
      const result = await aichatApi.addGlobalPreset(values.name, values.content)
      message.success(result.data || '操作成功')
      setPresetModalVisible(false)
      presetForm.resetFields()
      setEditingPreset(null)
      await fetchGlobalPresets()
    } catch (error) {
      message.error('保存失败: ' + error.message)
    }
  }

  // 处理删除全局预设人格
  const handleDeleteGlobalPreset = async (name) => {
    try {
      const result = await aichatApi.deleteGlobalPreset(name)
      message.success(result.data || '删除成功')
      await fetchGlobalPresets()
    } catch (error) {
      message.error('删除失败: ' + error.message)
    }
  }

  // 打开添加预设人格弹窗
  const openAddPresetModal = () => {
    setEditingPreset(null)
    presetForm.resetFields()
    setPresetModalVisible(true)
  }

  // 打开编辑预设人格弹窗
  const openEditPresetModal = (preset) => {
    setEditingPreset(preset)
    presetForm.setFieldsValue({
      name: preset.name,
      content: preset.content
    })
    setPresetModalVisible(true)
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

  // 打开添加模型弹窗
  const openAddModelModal = () => {
    setModelModalMode('add')
    setEditingModelId(null)
    modelForm.resetFields()
    // 设置默认值
    modelForm.setFieldsValue({
      supports_multimodal: false
    })
    setModelModalVisible(true)
  }

  // 打开编辑模型弹窗
  const openEditModelModal = (model) => {
    setModelModalMode('edit')
    setEditingModelId(model.id)
    // 直接显示真实 api_key
    modelForm.setFieldsValue({
      name: model.name,
      api_base: model.api_base,
      api_key: model.api_key || '',
      model: model.model,
      max_tokens: model.max_tokens,
      temperature: model.temperature,
      supports_multimodal: model.supports_multimodal || false
    })
    setModelModalVisible(true)
  }

  // 提交模型表单
  const handleModelSubmit = async (values) => {
    try {
      if (modelModalMode === 'add') {
        // 添加新模型
        const result = await aichatApi.addAichatModel(values)
        message.success(result.data || '添加成功')
      } else {
        // 编辑模型：直接提交所有值（已显示真实 api_key）
        const result = await aichatApi.updateAichatModel(editingModelId, values)
        message.success(result.data || '更新成功')
      }
      setModelModalVisible(false)
      await fetchModels()
    } catch (error) {
      message.error(modelModalMode === 'add' ? '添加模型失败: ' : '更新模型失败: ' + error.message)
    }
  }

  // 删除模型
  const handleDeleteModel = async (modelId) => {
    try {
      const result = await aichatApi.deleteAichatModel(modelId)
      message.success(result.data || '删除成功')
      await fetchModels()
    } catch (error) {
      message.error('删除模型失败: ' + error.message)
    }
  }

  // 设置默认模型
  const handleSetDefaultModel = async (modelId) => {
    try {
      const result = await aichatApi.setDefaultAichatModel(modelId)
      message.success(result.data || '设置成功')
      await fetchModels()
    } catch (error) {
      message.error('设置默认模型失败: ' + error.message)
    }
  }

  // 更新全局配置
  const handleUpdateConfig = async (values) => {
    try {
      const result = await aichatApi.updateAichatConfig(values)
      message.success(result.data || '配置更新成功')
      setConfigModalVisible(false)
      await fetchConfig()
    } catch (error) {
      message.error('配置更新失败: ' + error.message)
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
              <Space>
                <Button icon={<PlusOutlined />} type="primary" onClick={openAddModelModal}>
                  新增模型
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchModels}>
                  刷新
                </Button>
              </Space>
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
            <Card 
              title="配置信息" 
              style={{ marginTop: 16 }}
              extra={
                <Button 
                  icon={<EditOutlined />} 
                  onClick={() => {
                    configForm.setFieldsValue({
                      max_history: config.max_history,
                      session_timeout: config.session_timeout,
                      max_tokens: config.max_tokens,
                      temperature: config.temperature,
                      max_saved_personas: config.max_saved_personas
                    })
                    setConfigModalVisible(true)
                  }}
                >
                  编辑配置
                </Button>
              }
            >
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="最大历史消息">{config.max_history}</Descriptions.Item>
                <Descriptions.Item label="会话超时">{config.session_timeout} 秒</Descriptions.Item>
                <Descriptions.Item label="最大 Token">{config.max_tokens}</Descriptions.Item>
                <Descriptions.Item label="温度">{config.temperature}</Descriptions.Item>
                <Descriptions.Item label="最大保存人格数">{config.max_saved_personas}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {/* 模型列表 */}
          <Card title="模型列表" style={{ marginTop: 16 }}>
            <List
              bordered
              dataSource={models}
              renderItem={item => (
                <List.Item
                  actions={[
                    <Button
                      type="link"
                      icon={<EditOutlined />}
                      onClick={() => openEditModelModal(item)}
                    >
                      编辑
                    </Button>,
                    !item.is_current && !item.is_default && (
                      <Popconfirm
                        title="确定要删除这个模型吗？"
                        onConfirm={() => handleDeleteModel(item.id)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="link" danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    ),
                    !item.is_default && (
                      <Button
                        type="link"
                        icon={<SettingOutlined />}
                        onClick={() => handleSetDefaultModel(item.id)}
                      >
                        设为默认
                      </Button>
                    )
                  ].filter(Boolean)}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <span>{item.name}</span>
                        {item.is_current && <Tag color="green">当前使用</Tag>}
                        {item.is_default && <Tag color="orange">默认</Tag>}
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0} style={{ fontSize: 12 }}>
                        <span>ID: <code>{item.id}</code></span>
                        <span>模型: {item.model}</span>
                        <span>API: {item.api_base}</span>
                        <span>密钥: <code style={{ color: '#f59e0b' }}>{item.api_key}</code></span>
                        <span>
                          温度: {item.temperature ?? '默认'} | 
                          MaxTokens: {item.max_tokens ?? '默认'} | 
                          多模态: {item.supports_multimodal ? '是' : '否'}
                        </span>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
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
              <pre style={{ 
                background: 'var(--ant-color-bg-elevated)', 
                color: 'var(--ant-color-text)',
                padding: 12, 
                borderRadius: 4, 
                margin: 0,
                border: '1px solid var(--ant-color-border)'
              }}>
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
              {/* 选择预设人格 */}
              {globalPresets.length > 0 && (
                <Select
                  style={{ width: '100%' }}
                  placeholder="快速选择：使用全局预设人格"
                  allowClear
                  onChange={(value) => {
                    if (value) {
                      setGlobalPersona(value)
                    }
                  }}
                >
                  {globalPresets.map(preset => (
                    <Option key={preset.name} value={preset.content}>
                      <Space>
                        <BookOutlined />
                        <span>{preset.name}</span>
                      </Space>
                    </Option>
                  ))}
                </Select>
              )}
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
              <pre style={{ 
                background: 'var(--ant-color-bg-elevated)', 
                color: 'var(--ant-color-text)',
                padding: 12, 
                borderRadius: 4,
                border: '1px solid var(--ant-color-border)'
              }}>
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

              {/* 选择预设人格 */}
              {selectedGroupId && globalPresets.length > 0 && (
                <Select
                  style={{ width: 400 }}
                  placeholder="快速选择：使用全局预设人格"
                  allowClear
                  onChange={(value) => {
                    if (value) {
                      setGroupPersonaInput({ ...groupPersonaInput, content: value })
                    }
                  }}
                >
                  {globalPresets.map(preset => (
                    <Option key={preset.name} value={preset.content}>
                      <Space>
                        <BookOutlined />
                        <span>{preset.name}</span>
                      </Space>
                    </Option>
                  ))}
                </Select>
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
                    <div style={{ maxWidth: '100%', wordBreak: 'break-all' }}>
                      {userPersonaInfo.user 
                        ? (userPersonaInfo.user.length > 100 
                            ? userPersonaInfo.user.slice(0, 100) + '...' 
                            : userPersonaInfo.user)
                        : '未设置'}
                    </div>
                  </Descriptions.Item>
                  <Descriptions.Item label="当前上下文群组人格">
                    <div style={{ maxWidth: '100%', wordBreak: 'break-all' }}>
                      {userPersonaInfo.group 
                        ? (userPersonaInfo.group.length > 100 
                            ? userPersonaInfo.group.slice(0, 100) + '...' 
                            : userPersonaInfo.group)
                        : '未设置'}
                    </div>
                  </Descriptions.Item>
                  <Descriptions.Item label="全局人格">
                    <div style={{ maxWidth: '100%', wordBreak: 'break-all' }}>
                      {userPersonaInfo.global 
                        ? (userPersonaInfo.global.length > 100 
                            ? userPersonaInfo.global.slice(0, 100) + '...' 
                            : userPersonaInfo.global)
                        : '未设置'}
                    </div>
                  </Descriptions.Item>
                  <Descriptions.Item label="配置默认">
                    <div style={{ maxWidth: '100%', wordBreak: 'break-all' }}>
                      {userPersonaInfo.config 
                        ? (userPersonaInfo.config.length > 100 
                            ? userPersonaInfo.config.slice(0, 100) + '...' 
                            : userPersonaInfo.config)
                        : '未设置'}
                    </div>
                  </Descriptions.Item>
                  <Descriptions.Item label="当前生效">
                    <Tag color="green" style={{ maxWidth: '100%', wordBreak: 'break-all', whiteSpace: 'normal', height: 'auto' }}>
                      {userPersonaInfo.effective || '无'}
                    </Tag>
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
                            description={
                              <span style={{ maxWidth: '100%', wordBreak: 'break-all' }}>
                                {item.persona && item.persona.length > 100 
                                  ? item.persona.slice(0, 100) + '...' 
                                  : (item.persona || '')}
                              </span>
                            }
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

        <TabPane
          tab={<span><BookOutlined /> 全局预设人格</span>}
          key="global-presets"
        >
          <Card
            title="全局预设人格管理"
            extra={
              <Space>
                <Button icon={<PlusOutlined />} type="primary" onClick={openAddPresetModal}>
                  添加预设人格
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchGlobalPresets}>
                  刷新
                </Button>
              </Space>
            }
          >
            <Alert
              message="全局预设人格"
              description="超级用户可以预设一些人格供所有用户使用。普通用户可以通过「切换人格 名称」或「使用人格 名称」命令直接使用这些预设人格。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            {globalPresets.length > 0 ? (
              <List
                bordered
                dataSource={globalPresets}
                renderItem={item => (
                  <List.Item
                    actions={[
                      <Button
                        type="link"
                        icon={<EyeOutlined />}
                        onClick={() => handleViewPersona(item)}
                      >
                        查看
                      </Button>,
                      <Button
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => openEditPresetModal(item)}
                      >
                        编辑
                      </Button>,
                      <Popconfirm
                        title={`确定要删除预设人格「${item.name}」吗？`}
                        onConfirm={() => handleDeleteGlobalPreset(item.name)}
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
                      title={
                        <Space>
                          <TagOutlined />
                          <span>{item.name}</span>
                        </Space>
                      }
                      description={
                        <span style={{ fontSize: 12 }}>
                          {item.content.length > 100
                            ? item.content.slice(0, 100) + '...'
                            : item.content}
                        </span>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无全局预设人格，点击「添加预设人格」创建" />
            )}
          </Card>
        </TabPane>

        <TabPane
          tab={<span><ImportOutlined /> 角色卡导入</span>}
          key="character-import"
        >
          <Card title="从 PNG 图片导入角色卡">
            <Alert
              message="角色卡导入"
              description="支持从 TavernAI / SillyTavern 格式的 PNG 角色卡图片或 JSON 文件导入人格。可同时上传多个文件批量导入。非角色卡文件会被自动跳过。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            <Space direction="vertical" style={{ width: '100%' }}>
              <Input
                placeholder="用户QQ号"
                value={importUserId}
                onChange={e => setImportUserId(e.target.value)}
                style={{ width: 200 }}
                prefix={<UserOutlined />}
              />
              
              <div>
                <span style={{ marginRight: 8 }}>导入为：</span>
                <Select
                  value={importAsGlobal}
                  onChange={setImportAsGlobal}
                  style={{ width: 200 }}
                >
                  <Option value={false}>个人人格</Option>
                  <Option value={true}>全局预设人格（需超级用户）</Option>
                </Select>
              </div>

              <Upload.Dragger
                multiple
                beforeUpload={handleBeforeUpload}
                onChange={handleFileChange}
                disabled={importLoading}
              >
                <p className="ant-upload-drag-icon">
                  <FileImageOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽角色卡文件到此区域</p>
                <p className="ant-upload-hint">
                  支持 PNG 图片和 JSON 文件批量上传，选择文件后点击导入按钮
                </p>
              </Upload.Dragger>
              
              {uploadFileList.length > 0 && (
                <Button
                  type="primary"
                  icon={<ImportOutlined />}
                  onClick={handleImportBatch}
                  loading={importLoading}
                  disabled={importLoading}
                  style={{ marginTop: 16 }}
                  block
                >
                  开始导入 ({uploadFileList.length} 个文件)
                </Button>
              )}

              {importLoading && (
                <div style={{ textAlign: 'center', padding: '20px' }}>
                  <Spin />
                  <p>正在导入...</p>
                </div>
              )}

              {importResult && (
                <Card title="导入结果" size="small">
                  <Space wrap>
                    <Tag color="success">成功: {importResult.summary?.success || 0}</Tag>
                    <Tag color="warning">跳过: {importResult.summary?.skipped || 0}</Tag>
                    <Tag color="error">失败: {importResult.summary?.failed || 0}</Tag>
                    <Tag>总计: {importResult.summary?.total || 0}</Tag>
                  </Space>
                  
                  {importResult.results && importResult.results.length > 0 && (
                    <List
                      size="small"
                      style={{ marginTop: 16, maxHeight: 300, overflow: 'auto' }}
                      dataSource={importResult.results}
                      renderItem={item => (
                        <List.Item>
                          <Space>
                            {item.success ? (
                              <Tag color="success">成功</Tag>
                            ) : item.message?.includes('不是有效的角色卡') ? (
                              <Tag color="default">跳过</Tag>
                            ) : (
                              <Tag color="error">失败</Tag>
                            )}
                            <Text strong>{item.name}</Text>
                            <Text type="secondary">{item.message}</Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              )}
            </Space>
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
            fontSize: 14
          }}
        />
      </Modal>

      {/* 添加/编辑模型弹窗 */}
      <Modal
        title={modelModalMode === 'add' ? '添加新模型' : '编辑模型'}
        open={modelModalVisible}
        onCancel={() => setModelModalVisible(false)}
        onOk={() => modelForm.submit()}
        width={600}
      >
        <Form
          form={modelForm}
          layout="vertical"
          onFinish={handleModelSubmit}
        >
          {modelModalMode === 'add' && (
            <Form.Item
              name="id"
              label="模型ID"
              rules={[{ required: true, message: '请输入模型ID' }]}
              extra="唯一标识，不可重复，建议使用英文和下划线"
            >
              <Input placeholder="例如：deepseek, gpt4, kimi" />
            </Form.Item>
          )}
          <Form.Item
            name="name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="例如：DeepSeek, GPT-4, Kimi" />
          </Form.Item>
          <Form.Item
            name="api_base"
            label="API 地址"
            rules={[{ required: true, message: '请输入API地址' }]}
          >
            <Input placeholder="例如：https://api.deepseek.com" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API 密钥"
            rules={[{ required: true, message: '请输入API密钥' }]}
          >
            <Input placeholder="输入API密钥" />
          </Form.Item>
          <Form.Item
            name="model"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
            extra="具体的模型版本名称"
          >
            <Input placeholder="例如：deepseek-chat, gpt-4, kimi-latest" />
          </Form.Item>
          <Form.Item
            name="max_tokens"
            label="最大 Tokens"
            extra="留空则使用全局默认设置"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={32768} placeholder="8192" />
          </Form.Item>
          <Form.Item
            name="temperature"
            label="温度 (Temperature)"
            extra="留空则使用全局默认设置，范围 0-2"
          >
            <InputNumber style={{ width: '100%' }} min={0} max={2} step={0.1} placeholder="0.7" />
          </Form.Item>
          <Form.Item
            name="supports_multimodal"
            label="支持多模态"
            valuePropName="checked"
            extra="是否支持图片识别功能"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加/编辑预设人格弹窗 */}
      <Modal
        title={editingPreset ? `编辑预设人格: ${editingPreset.name}` : '添加全局预设人格'}
        open={presetModalVisible}
        onCancel={() => {
          setPresetModalVisible(false)
          setEditingPreset(null)
          presetForm.resetFields()
        }}
        onOk={() => presetForm.submit()}
        width={600}
      >
        <Form
          form={presetForm}
          layout="vertical"
          onFinish={handleAddGlobalPreset}
        >
          <Form.Item
            name="name"
            label="人格名称"
            rules={[{ required: true, message: '请输入人格名称' }]}
            extra="建议使用简洁易记的名称，如：猫娘、温柔助手、霸道总裁"
          >
            <Input 
              placeholder="例如：猫娘" 
            />
          </Form.Item>
          <Form.Item
            name="content"
            label="人格描述"
            rules={[{ required: true, message: '请输入人格描述' }]}
            extra="详细描述AI应该扮演的角色、性格特点、说话方式等"
          >
            <TextArea
              placeholder="例如：你是一个温柔可爱的猫娘，说话轻声细语，喜欢用'喵~'结尾..."
              rows={8}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑全局配置弹窗 */}
      <Modal
        title="编辑全局配置"
        open={configModalVisible}
        onCancel={() => setConfigModalVisible(false)}
        onOk={() => configForm.submit()}
        width={600}
      >
        <Form
          form={configForm}
          layout="vertical"
          onFinish={handleUpdateConfig}
        >
          <Form.Item
            name="max_history"
            label="最大历史消息"
            rules={[{ required: true, message: '请输入最大历史消息数' }]}
            extra="保留的对话历史消息数量，超过此数量会清理旧消息"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={1000} />
          </Form.Item>
          <Form.Item
            name="session_timeout"
            label="会话超时时间（秒）"
            rules={[{ required: true, message: '请输入会话超时时间' }]}
            extra="超过此时间没有新消息，会话会被清理。0 表示永不过期"
          >
            <InputNumber style={{ width: '100%' }} min={0} max={86400} />
          </Form.Item>
          <Form.Item
            name="max_tokens"
            label="最大 Tokens"
            rules={[{ required: true, message: '请输入最大 Tokens' }]}
            extra="模型生成的最大 token 数"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={32768} />
          </Form.Item>
          <Form.Item
            name="temperature"
            label="温度 (Temperature)"
            rules={[{ required: true, message: '请输入温度值' }]}
            extra="控制输出的随机性，范围 0-2，值越大输出越随机"
          >
            <InputNumber style={{ width: '100%' }} min={0} max={2} step={0.1} />
          </Form.Item>
          <Form.Item
            name="max_saved_personas"
            label="最大保存人格数"
            rules={[{ required: true, message: '请输入最大保存人格数' }]}
            extra="每个用户最多可以保存的人格数量"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={50} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Aichat
