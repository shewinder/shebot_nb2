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
  Upload,
  Table
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
  FileImageOutlined,
  PictureOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  BugOutlined,
  CodeOutlined
} from '@ant-design/icons'
import * as aichatApi from '../api'

const { Title, Text } = Typography
const { TextArea } = Input
const { Option } = Select
const { TabPane } = Tabs

// HTML 转义函数，防止 XML/HTML 标签被浏览器解析
function escapeHtml(text) {
  if (typeof text !== 'string') return text
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

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

  // 模型选择相关
  const [availableModels, setAvailableModels] = useState([])
  const [selectedModelName, setSelectedModelName] = useState(null)
  const [switchingModel, setSwitchingModel] = useState(false)
  const [loadingModels, setLoadingModels] = useState(false)

  // 图像模型管理相关
  const [imageModels, setImageModels] = useState([])
  const [imageModelModalVisible, setImageModelModalVisible] = useState(false)
  const [imageModelModalMode, setImageModelModalMode] = useState('add') // 'add' 或 'edit'
  const [editingImageModelIndex, setEditingImageModelIndex] = useState(null)
  const [imageModelForm] = Form.useForm()

  // Session 调试相关
  const [sessions, setSessions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [sessionDetailVisible, setSessionDetailVisible] = useState(false)
  const [sessionDetail, setSessionDetail] = useState(null)
  const [sessionDetailLoading, setSessionDetailLoading] = useState(false)

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
        fetchGlobalPresets(),
        fetchImageModels()
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
      if (currentData?.api) {
        setSelectedModel(currentData.api)
      }
      // 同时获取可用模型列表，传入当前模型信息
      await fetchAvailableModels(currentData?.model)
    } catch (error) {
      message.error('加载模型列表失败: ' + error.message)
    }
  }

  const fetchAvailableModels = async (currentModelName = null) => {
    setLoadingModels(true)
    try {
      const res = await aichatApi.getAvailableModels()
      // 响应拦截器已解包，res 直接是模型数组
      const models = Array.isArray(res) ? res : (res.data || [])
      setAvailableModels(models)
      // 如果有当前模型，默认选中
      const modelToSelect = currentModelName || currentModel?.model
      if (modelToSelect && models.includes(modelToSelect)) {
        setSelectedModelName(modelToSelect)
      }
    } catch (error) {
      message.error('获取可用模型列表失败: ' + error.message)
      setAvailableModels([])
    } finally {
      setLoadingModels(false)
    }
  }

  const handleSwitchModelByName = async () => {
    if (!selectedModelName || selectedModelName === currentModel?.model) {
      message.info('请选择不同的模型')
      return
    }
    setSwitchingModel(true)
    try {
      const result = await aichatApi.switchModel(selectedModelName)
      message.success(result.data || '切换模型成功')
      await fetchModels()
    } catch (error) {
      message.error('切换模型失败: ' + error.message)
    } finally {
      setSwitchingModel(false)
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
    if (!selectedModel || selectedModel === currentModel?.api) {
      message.info('请选择不同的 API 厂商')
      return
    }
    try {
      const result = await aichatApi.switchApi(selectedModel)
      message.success(result.data || '切换成功')
      await fetchModels()
    } catch (error) {
      message.error('切换 API 厂商失败: ' + error.message)
    }
  }

  const handleSetGlobalPersona = async () => {
    try {
      const result = await aichatApi.setGlobalPersona(globalPersona)
      message.success(result)
      await fetchPersonas()
    } catch (error) {
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
      supports_multimodal: false,
      supports_tools: true,
      max_tokens: 8192,
      temperature: 0.7
    })
    setModelModalVisible(true)
  }

  // 打开编辑模型弹窗
  const openEditModelModal = (model) => {
    setModelModalMode('edit')
    setEditingModelId(model.api)
    // 先重置表单，避免上次状态干扰
    modelForm.resetFields()
    // 直接显示真实 api_key
    modelForm.setFieldsValue({
      api_base: model.api_base,
      api_key: model.api_key || '',
      model: model.model,
      max_tokens: model.max_tokens !== undefined && model.max_tokens !== null ? model.max_tokens : undefined,
      temperature: model.temperature !== undefined && model.temperature !== null ? model.temperature : undefined,
      supports_multimodal: model.supports_multimodal || false,
      supports_tools: model.supports_tools !== false
    })
    setModelModalVisible(true)
  }

  // 提交模型表单
  const handleModelSubmit = async (values) => {
    try {
      if (modelModalMode === 'add') {
        // 添加新 API 厂商
        const result = await aichatApi.addAichatApi(values)
        message.success(result.data || '添加成功')
      } else {
        // 编辑 API 厂商：直接提交所有值（已显示真实 api_key）
        const result = await aichatApi.updateAichatApi(editingModelId, values)
        message.success(result.data || '更新成功')
      }
      setModelModalVisible(false)
      await fetchModels()
    } catch (error) {
      message.error(modelModalMode === 'add' ? '添加 API 厂商失败: ' : '更新 API 厂商失败: ' + error.message)
    }
  }

  // 删除模型
  const handleDeleteModel = async (apiName) => {
    try {
      const result = await aichatApi.deleteAichatApi(apiName)
      message.success(result.data || '删除成功')
      await fetchModels()
    } catch (error) {
      message.error('删除 API 厂商失败: ' + error.message)
    }
  }

  // 设置默认模型（切换到该 API 厂商）
  const handleSetDefaultModel = async (apiName) => {
    try {
      const result = await aichatApi.switchApi(apiName)
      message.success(result.data || '切换成功')
      await fetchModels()
    } catch (error) {
      message.error('切换 API 厂商失败: ' + error.message)
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

  // ===== 图像模型管理相关函数 =====
  const fetchImageModels = async () => {
    try {
      const data = await aichatApi.getImageModels()
      setImageModels(data || [])
    } catch (error) {
      // 静默处理，不显示错误
    }
  }

  const openAddImageModelModal = () => {
    setImageModelModalMode('add')
    setEditingImageModelIndex(null)
    imageModelForm.resetFields()
    imageModelForm.setFieldsValue({
      api_format: 'openai',
      capabilities: ['generate']
    })
    setImageModelModalVisible(true)
  }

  const openEditImageModelModal = (record) => {
    setImageModelModalMode('edit')
    setEditingImageModelIndex(record.index)
    imageModelForm.resetFields()
    imageModelForm.setFieldsValue({
      model: record.model,
      api_format: record.api_format,
      capabilities: record.capabilities
    })
    setImageModelModalVisible(true)
  }

  const handleImageModelSubmit = async (values) => {
    try {
      if (imageModelModalMode === 'add') {
        const result = await aichatApi.addImageModel(values)
        message.success(result.data || '添加成功')
      } else {
        const result = await aichatApi.updateImageModel(editingImageModelIndex, values)
        message.success(result.data || '更新成功')
      }
      setImageModelModalVisible(false)
      await fetchImageModels()
    } catch (error) {
      message.error(imageModelModalMode === 'add' ? '添加失败: ' : '更新失败: ' + error.message)
    }
  }

  const handleDeleteImageModel = async (index) => {
    try {
      const result = await aichatApi.deleteImageModel(index)
      message.success(result.data || '删除成功')
      await fetchImageModels()
    } catch (error) {
      message.error('删除失败: ' + error.message)
    }
  }

  const handleMoveImageModel = async (index, direction) => {
    if (direction === 'up' && index === 0) return
    if (direction === 'down' && index === imageModels.length - 1) return

    const newModels = [...imageModels]
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    
    // 交换位置
    const temp = newModels[index]
    newModels[index] = newModels[targetIndex]
    newModels[targetIndex] = temp

    // 更新索引
    newModels.forEach((m, i) => m.index = i)

    try {
      // 构建提交数据（去掉index字段）
      const submitModels = newModels.map(({ model, api_format, capabilities }) => ({
        model, api_format, capabilities
      }))
      const result = await aichatApi.reorderImageModels(submitModels)
      message.success(result.data || '排序更新成功')
      await fetchImageModels()
    } catch (error) {
      message.error('排序更新失败: ' + error.message)
    }
  }

  // ===== Session 调试相关函数 =====
  const fetchSessions = async () => {
    setSessionsLoading(true)
    try {
      const res = await aichatApi.getSessions()
      setSessions(res?.sessions || [])
    } catch (error) {
      message.error('获取 Session 列表失败: ' + error.message)
    } finally {
      setSessionsLoading(false)
    }
  }

  const handleViewSessionDetail = async (sessionId) => {
    setSessionDetailLoading(true)
    setSessionDetailVisible(true)
    try {
      const res = await aichatApi.getSessionDetail(sessionId)
      setSessionDetail(res)
    } catch (error) {
      message.error('获取 Session 详情失败: ' + error.message)
      setSessionDetailVisible(false)
    } finally {
      setSessionDetailLoading(false)
    }
  }

  const handleDeleteSession = async (sessionId) => {
    try {
      await aichatApi.deleteSession(sessionId)
      message.success('Session 已删除')
      await fetchSessions()
    } catch (error) {
      message.error('删除失败: ' + error.message)
    }
  }

  const handleCleanupExpired = async () => {
    try {
      const res = await aichatApi.cleanupExpiredSessions()
      message.success(res)
      await fetchSessions()
    } catch (error) {
      message.error('清理失败: ' + error.message)
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
          tab={<span><RobotOutlined /> API 厂商管理</span>}
          key="models"
        >
          <Card
            title="当前 API 厂商"
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
            {currentModel?.api ? (
              <Descriptions bordered column={2}>
                <Descriptions.Item label="API 厂商">
                  <Tag color="blue">{currentModel.api}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="模型名称">
                  <code>{currentModel.model}</code>
                </Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color="green">当前使用</Tag>
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty description="未配置 API 厂商" />
            )}
          </Card>

          <Card title="切换 API 厂商" style={{ marginTop: 16 }}>
            <Space>
              <Text>选择 API 厂商:</Text>
              <Select
                style={{ width: 300 }}
                value={selectedModel}
                onChange={setSelectedModel}
                placeholder="请选择 API 厂商"
              >
                {models.map(model => (
                  <Option key={model.api} value={model.api}>
                    {model.api} ({model.model})
                    {model.is_current && ' [当前]'}
                  </Option>
                ))}
              </Select>
              <Button
                type="primary"
                onClick={handleSwitchModel}
                disabled={!selectedModel || selectedModel === currentModel?.api}
              >
                切换 API 厂商
              </Button>
            </Space>
          </Card>

          <Card 
            title="切换模型" 
            style={{ marginTop: 16 }}
            extra={
              <Button 
                icon={<ReloadOutlined />} 
                size="small" 
                onClick={() => fetchAvailableModels()}
                loading={loadingModels}
              >
                刷新模型列表
              </Button>
            }
          >
            {currentModel?.api ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Alert
                  message={`当前厂商: ${currentModel.api}，当前模型: ${currentModel.model}`}
                  type="info"
                  showIcon
                />
                <Space style={{ width: '100%' }}>
                  <Select
                    style={{ width: 400 }}
                    value={selectedModelName}
                    onChange={setSelectedModelName}
                    placeholder={availableModels.length > 0 ? `请选择模型 (共 ${availableModels.length} 个)` : '暂无可用模型'}
                    showSearch
                    optionFilterProp="value"
                    loading={loadingModels}
                    disabled={availableModels.length === 0}
                    virtual
                    listHeight={256}
                  >
                    {availableModels.map(model => (
                      <Option key={model} value={model}>
                        {model}
                        {model === currentModel?.model && ' [当前]'}
                      </Option>
                    ))}
                  </Select>
                  <Button
                    type="primary"
                    onClick={handleSwitchModelByName}
                    disabled={!selectedModelName || selectedModelName === currentModel?.model}
                    loading={switchingModel}
                  >
                    切换模型
                  </Button>
                </Space>
              </Space>
            ) : (
              <Empty description="请先配置 API 厂商" />
            )}
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
                      enable_markdown_render: config.enable_markdown_render,
                      markdown_min_length: config.markdown_min_length
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
                <Descriptions.Item label="Markdown渲染">{config.enable_markdown_render ? '开启' : '关闭'}</Descriptions.Item>
                <Descriptions.Item label="渲染最小长度">{config.markdown_min_length}</Descriptions.Item>
              </Descriptions>
            </Card>
          )}

          {/* API 厂商列表 */}
          <Card title="API 厂商列表" style={{ marginTop: 16 }}>
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
                    !item.is_current && (
                      <Popconfirm
                        title="确定要删除这个 API 厂商吗？"
                        onConfirm={() => handleDeleteModel(item.api)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="link" danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    ),
                    !item.is_current && (
                      <Button
                        type="link"
                        icon={<SettingOutlined />}
                        onClick={() => handleSetDefaultModel(item.api)}
                      >
                        切换到此厂商
                      </Button>
                    )
                  ].filter(Boolean)}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <span>{item.api}</span>
                        {item.is_current && <Tag color="green">当前使用</Tag>}
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0} style={{ fontSize: 12 }}>
                        <span>模型: {item.model}</span>
                        <span>API地址: {item.api_base}</span>
                        <span>密钥: <code style={{ color: '#f59e0b' }}>{item.api_key}</code></span>
                        <span>
                          温度: {item.temperature ?? '默认'} | 
                          MaxTokens: {item.max_tokens ?? '默认'} | 
                          多模态: {item.supports_multimodal ? '是' : '否'} |
                          Tools: {item.supports_tools !== false ? '是' : '否'}
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
          tab={<span><PictureOutlined /> 图像模型管理</span>}
          key="image-models"
        >
          <Card
            title="图像生成模型配置"
            extra={
              <Space>
                <Button icon={<PlusOutlined />} type="primary" onClick={openAddImageModelModal}>
                  添加模型
                </Button>
                <Button icon={<ReloadOutlined />} onClick={fetchImageModels}>
                  刷新
                </Button>
              </Space>
            }
          >
            <Alert
              message="模型选择优先级说明"
              description={
                <div>
                  <p>系统按列表顺序选择第一个满足需求的模型：</p>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    <li><strong>generate</strong>：根据文本描述生成新图片</li>
                    <li><strong>edit</strong>：编辑单张图片（如改变风格、添加元素）</li>
                    <li><strong>multi_edit</strong>：融合多张图片（如让人物穿衣服、替换背景）</li>
                  </ul>
                  <p style={{ marginTop: 8, marginBottom: 0 }}>列表越靠前的模型优先级越高。可通过上下箭头调整顺序。</p>
                </div>
              }
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            {imageModels.length > 0 ? (
              <List
                bordered
                dataSource={imageModels}
                renderItem={(item, index) => (
                  <List.Item
                    actions={[
                      <Button
                        type="text"
                        icon={<ArrowUpOutlined />}
                        disabled={index === 0}
                        onClick={() => handleMoveImageModel(index, 'up')}
                        title="上移"
                      />,
                      <Button
                        type="text"
                        icon={<ArrowDownOutlined />}
                        disabled={index === imageModels.length - 1}
                        onClick={() => handleMoveImageModel(index, 'down')}
                        title="下移"
                      />,
                      <Button
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => openEditImageModelModal(item)}
                      >
                        编辑
                      </Button>,
                      <Popconfirm
                        title="确定要删除这个图像模型吗？"
                        onConfirm={() => handleDeleteImageModel(item.index)}
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
                          <Tag color="blue">优先级 {index + 1}</Tag>
                          <span>{item.model}</span>
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={0} style={{ fontSize: 12 }}>
                          <span>API格式: <Tag>{item.api_format}</Tag></span>
                          <span>
                            支持能力: {item.capabilities?.map(cap => (
                              <Tag key={cap} color="green" size="small">
                                {cap === 'generate' ? '生成' : cap === 'edit' ? '编辑' : '多图融合'}
                              </Tag>
                            ))}
                          </span>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无图像模型配置，点击「添加模型」创建" />
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

        <TabPane
          tab={<span><BugOutlined /> Session 调试</span>}
          key="session-debug"
        >
          <Card
            title="活跃 Session 列表"
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={fetchSessions} loading={sessionsLoading}>
                  刷新
                </Button>
                <Popconfirm
                  title="确定要清理所有过期 Session 吗？"
                  onConfirm={handleCleanupExpired}
                  okText="确定"
                  cancelText="取消"
                >
                  <Button>清理过期</Button>
                </Popconfirm>
              </Space>
            }
          >
            <Alert
              message="Session 调试"
              description="查看当前所有活跃的对话 Session。过期的 Session 会自动清理，也可以手动删除。"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Table
              dataSource={sessions}
              rowKey="session_id"
              loading={sessionsLoading}
              pagination={{ pageSize: 10 }}
              columns={[
                {
                  title: 'Session ID',
                  dataIndex: 'session_id',
                  key: 'session_id',
                  width: 280,
                  render: (text) => <code style={{ fontSize: 12 }}>{text}</code>
                },
                {
                  title: '类型',
                  dataIndex: 'type',
                  key: 'type',
                  width: 80,
                  render: (type) => type === 'group' ? <Tag color="blue">群聊</Tag> : <Tag>私聊</Tag>
                },
                {
                  title: '消息数',
                  dataIndex: 'message_count',
                  key: 'message_count',
                  width: 80
                },
                {
                  title: '图片',
                  key: 'images',
                  width: 120,
                  render: (_, record) => (
                    <Space>
                      <Tag>用户:{record.user_images}</Tag>
                      <Tag>AI:{record.ai_images}</Tag>
                    </Space>
                  )
                },
                {
                  title: '连续对话',
                  dataIndex: 'continuous_mode',
                  key: 'continuous_mode',
                  width: 90,
                  render: (v) => v ? <Tag color="green">开启</Tag> : <Tag>关闭</Tag>
                },
                {
                  title: '选项模式',
                  dataIndex: 'choice_mode',
                  key: 'choice_mode',
                  width: 90,
                  render: (v) => v ? <Tag color="purple">开启</Tag> : <Tag>关闭</Tag>
                },
                {
                  title: '最后活跃',
                  dataIndex: 'last_active',
                  key: 'last_active',
                  width: 150
                },
                {
                  title: '状态',
                  dataIndex: 'is_expired',
                  key: 'is_expired',
                  width: 80,
                  render: (v) => v ? <Tag color="red">已过期</Tag> : <Tag color="green">活跃</Tag>
                },
                {
                  title: '操作',
                  key: 'action',
                  render: (_, record) => (
                    <Space>
                      <Button
                        type="link"
                        icon={<EyeOutlined />}
                        onClick={() => handleViewSessionDetail(record.session_id)}
                      >
                        详情
                      </Button>
                      <Popconfirm
                        title="确定要删除这个 Session 吗？"
                        onConfirm={() => handleDeleteSession(record.session_id)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button type="link" danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    </Space>
                  )
                }
              ]}
            />
          </Card>

          {/* Session 详情弹窗 */}
          <Modal
            title="Session 详情"
            open={sessionDetailVisible}
            onCancel={() => setSessionDetailVisible(false)}
            width={800}
            footer={[
              <Button key="close" onClick={() => setSessionDetailVisible(false)}>
                关闭
              </Button>
            ]}
          >
            {sessionDetailLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            ) : sessionDetail ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Descriptions bordered size="small" column={2}>
                  <Descriptions.Item label="Session ID" span={2}>
                    <code>{sessionDetail.session_id}</code>
                  </Descriptions.Item>
                  <Descriptions.Item label="用户ID">{sessionDetail.user_id}</Descriptions.Item>
                  <Descriptions.Item label="群组ID">{sessionDetail.group_id || '私聊'}</Descriptions.Item>
                  <Descriptions.Item label="连续对话">
                    {sessionDetail.continuous_mode ? '开启' : '关闭'}
                  </Descriptions.Item>
                  <Descriptions.Item label="选项模式">
                    {sessionDetail.choice_mode ? '开启' : '关闭'}
                  </Descriptions.Item>
                  <Descriptions.Item label="消息数">{sessionDetail.message_count}</Descriptions.Item>
                  <Descriptions.Item label="最后活跃">{sessionDetail.last_active}</Descriptions.Item>
                  <Descriptions.Item label="是否过期">
                    {sessionDetail.is_expired ? <Tag color="red">已过期</Tag> : <Tag color="green">活跃</Tag>}
                  </Descriptions.Item>
                </Descriptions>

                {sessionDetail.user_images?.length > 0 && (
                  <div>
                    <Text strong>用户图片:</Text>
                    <Space wrap>
                      {sessionDetail.user_images.map(img => (
                        <Tag key={img}>{img}</Tag>
                      ))}
                    </Space>
                  </div>
                )}

                {sessionDetail.ai_images?.length > 0 && (
                  <div>
                    <Text strong>AI 图片:</Text>
                    <Space wrap>
                      {sessionDetail.ai_images.map(img => (
                        <Tag key={img}>{img}</Tag>
                      ))}
                    </Space>
                  </div>
                )}

                <Divider orientation="left">消息历史 ({sessionDetail.messages?.length || 0} 条)</Divider>
                <List
                  size="small"
                  bordered
                  dataSource={sessionDetail.messages || []}
                  renderItem={(msg, idx) => (
                    <List.Item>
                      <div style={{ width: '100%' }}>
                        <Tag color={msg.role === 'user' ? 'blue' : msg.role === 'assistant' ? 'green' : 'default'}>
                          {msg.role}
                        </Tag>
                        <TextArea
                          value={typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2)}
                          readOnly
                          autoSize={{ minRows: 1, maxRows: 20 }}
                          style={{ 
                            marginTop: 8,
                            fontFamily: 'monospace',
                            fontSize: 12,
                            background: 'var(--ant-color-bg-elevated)'
                          }}
                        />
                      </div>
                    </List.Item>
                  )}
                />
              </Space>
            ) : null}
          </Modal>
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

      {/* 添加/编辑 API 厂商弹窗 */}
      <Modal
        title={modelModalMode === 'add' ? '添加新 API 厂商' : '编辑 API 厂商'}
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
              name="api"
              label="厂商标识"
              rules={[{ required: true, message: '请输入厂商标识' }]}
              extra="唯一标识，不可重复，建议使用英文和下划线，如：deepseek, kimi, gpt4"
            >
              <Input placeholder="例如：deepseek, gpt4, kimi" />
            </Form.Item>
          )}
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
            extra="具体的模型版本名称，如：deepseek-chat, gpt-4, kimi-latest"
          >
            <Input placeholder="例如：deepseek-chat, gpt-4, kimi-latest" />
          </Form.Item>
          <Form.Item
            name="max_tokens"
            label="最大 Tokens"
            extra="模型生成的最大 token 数"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={32768} />
          </Form.Item>
          <Form.Item
            name="temperature"
            label="温度 (Temperature)"
            extra="控制输出的随机性，范围 0-2，值越大输出越随机"
          >
            <InputNumber style={{ width: '100%' }} min={0} max={2} step={0.1} />
          </Form.Item>
          <Form.Item
            name="supports_multimodal"
            label="支持多模态"
            valuePropName="checked"
            extra="是否支持图片识别功能"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="supports_tools"
            label="支持 Tools/Function Calling"
            valuePropName="checked"
            extra="是否支持工具调用/函数调用功能（如生图等）"
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
            name="enable_markdown_render"
            label="启用 Markdown 渲染"
            valuePropName="checked"
            extra="是否开启 Markdown 渲染功能"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="markdown_min_length"
            label="渲染最小长度"
            rules={[{ required: true, message: '请输入渲染最小长度' }]}
            extra="超过此长度的消息才会进行 Markdown 渲染"
          >
            <InputNumber style={{ width: '100%' }} min={1} max={10000} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加/编辑图像模型弹窗 */}
      <Modal
        title={imageModelModalMode === 'add' ? '添加图像模型' : '编辑图像模型'}
        open={imageModelModalVisible}
        onCancel={() => setImageModelModalVisible(false)}
        onOk={() => imageModelForm.submit()}
        width={600}
      >
        <Form
          form={imageModelForm}
          layout="vertical"
          onFinish={handleImageModelSubmit}
        >
          <Form.Item
            name="model"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
            extra="具体的图像模型名称，如：gpt-image-1, gemini-3-pro-image-preview"
          >
            <Input placeholder="例如：gpt-image-1" />
          </Form.Item>
          <Form.Item
            name="api_format"
            label="API 格式"
            rules={[{ required: true, message: '请选择API格式' }]}
            extra="openai 格式兼容 OpenAI DALL-E API；gemini 格式兼容 Google Gemini API"
          >
            <Select placeholder="选择API格式">
              <Option value="openai">OpenAI (openai)</Option>
              <Option value="gemini">Gemini (gemini)</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="capabilities"
            label="支持能力"
            rules={[{ required: true, message: '请至少选择一项能力' }]}
            extra="选择该模型支持的功能，可多选"
          >
            <Select mode="multiple" placeholder="选择支持的能力">
              <Option value="generate">生成 (generate) - 根据文本描述生成新图片</Option>
              <Option value="edit">编辑 (edit) - 编辑单张图片</Option>
              <Option value="multi_edit">多图融合 (multi_edit) - 融合多张图片</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Aichat
