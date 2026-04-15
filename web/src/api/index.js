import request from '../utils/request'

// 登录
export const login = (password) => request.post('/login', { password })

// 获取群列表
export const getGroupList = () => request.get('/get_group_list')

// 获取服务列表
export const getLoadedServices = () => request.get('/get_loaded_services')

// 获取服务在群的启用状态
export const getServiceGroups = (svName) => request.get(`/get_service_groups/${svName}`)

// 获取群的服务配置
export const getGroupServices = (groupId) => request.get(`/get_group_services/${groupId}`)

// 设置服务配置
export const setService = (data) => request.post('/set_service', { data })

// 获取插件配置
export const getPluginConfig = () => request.get('/get_plugin_config')

// 设置插件配置
export const setPluginConfig = (name, config) => request.post('/set_plugin', { name, config })

// 获取已加载插件
export const getLoadedPlugins = () => request.get('/get_loaded_plugins')

// 获取项目信息
export const getProjectInfo = () => request.get('/get_project_info')

// 获取 Bot 配置
export const getConfig = () => request.get('/get_config')

// ===== AI Chat API =====
// 获取所有 API 厂商（模型列表）
export const getAichatApis = () => request.get('/aichat/apis')

// 获取所有模型列表（兼容命名，实际返回 API 列表）
export const getAichatModels = () => request.get('/aichat/apis')

// 添加新模型（API 厂商）
export const addAichatModel = (data) => request.post('/aichat/add-api', data)

// 更新模型（API 厂商）
export const updateAichatModel = (modelId, data) => request.post(`/aichat/update-api/${modelId}`, data)

// 删除模型（API 厂商）
export const deleteAichatModel = (modelId) => request.post(`/aichat/delete-api/${modelId}`)

// 设置默认模型（切换到该 API 厂商）
export const setDefaultAichatModel = (modelId) => request.post('/aichat/switch-api', { api: modelId })

// 获取当前 API 厂商
export const getCurrentApi = () => request.get('/aichat/current-api')

// 切换 API 厂商
export const switchApi = (api) => request.post('/aichat/switch-api', { api })

// 获取当前模型
export const getCurrentModel = () => request.get('/aichat/current-model')

// 获取当前厂商的可用模型列表
export const getAvailableModels = () => request.get('/aichat/available-models')

// 切换模型（在当前 API 下）
export const switchModel = (model) => request.post('/aichat/switch-model', { model })

// 获取人格设置
export const getAichatPersonas = (group_id, user_id) => {
  let url = '/aichat/personas'
  const params = []
  if (group_id) params.push(`group_id=${group_id}`)
  if (user_id) params.push(`user_id=${user_id}`)
  if (params.length > 0) url += '?' + params.join('&')
  return request.get(url)
}

// 设置全局人格
export const setGlobalPersona = (content) => request.post('/aichat/set-global-persona', {
  type: 'global',
  content
})

// 设置群组人格
export const setGroupPersona = (group_id, content) => request.post('/aichat/set-group-persona', {
  type: 'group',
  group_id,
  content
})

// 清除人格
export const clearPersona = (type, group_id, user_id) => {
  let url = `/aichat/clear-persona?type=${type}`
  if (group_id) url += `&group_id=${group_id}`
  if (user_id) url += `&user_id=${user_id}`
  return request.post(url)
}

// 获取用户已保存的人格
export const getSavedPersonas = (user_id) => request.get(`/aichat/saved-personas?user_id=${user_id}`)

// 保存人格
export const savePersona = (user_id, name, content) => request.post('/aichat/save-persona', {
  user_id,
  name,
  content
})

// 删除保存的人格
export const deleteSavedPersona = (user_id, name) => request.post('/aichat/delete-saved-persona', {
  user_id,
  name
})

// 获取 AI Chat 配置
export const getAichatConfig = () => request.get('/aichat/config')

// 获取群组列表（带人格信息）
export const getAichatGroups = () => request.get('/aichat/groups')

// 更新 AI Chat 配置
export const updateAichatConfig = (config) => request.post('/aichat/update-config', config)

// 获取超级用户列表
export const getSuperusers = () => request.get('/aichat/superusers')

// 添加新 API 厂商
export const addAichatApi = (data) => request.post('/aichat/add-api', data)

// 更新 API 厂商
export const updateAichatApi = (apiName, data) => request.post(`/aichat/update-api/${apiName}`, data)

// 删除 API 厂商
export const deleteAichatApi = (apiName) => request.post(`/aichat/delete-api/${apiName}`)

// ===== 全局预设人格 API =====
// 获取全局预设人格列表
export const getGlobalPresets = () => request.get('/aichat/global-presets')

// 添加/更新全局预设人格
export const addGlobalPreset = (name, content) => request.post('/aichat/add-global-preset', {
  name,
  content
})

// 删除全局预设人格
export const deleteGlobalPreset = (name) => request.post('/aichat/delete-global-preset', {
  name
})

// 修改全局预设人格名称
export const updateGlobalPresetName = (oldName, newName) => request.post('/aichat/update-global-preset-name', {
  old_name: oldName,
  new_name: newName
})

// ===== 角色卡导入 API =====
// 批量导入角色卡
export const importCharacters = (user_id, files, as_global = false) => {
  const formData = new FormData()
  formData.append('user_id', user_id)
  formData.append('as_global', as_global)
  files.forEach(file => formData.append('files', file))
  
  return request.post('/aichat/import-character', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// 导入单个角色卡
export const importCharacterSingle = (user_id, file, as_global = false) => {
  const formData = new FormData()
  formData.append('user_id', user_id)
  formData.append('as_global', as_global)
  formData.append('file', file)
  
  return request.post('/aichat/import-character-single', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// ===== 图像模型管理 API =====
// 获取图像 API 配置
export const getImageApis = () => request.get('/aichat/image-apis')

// 更新图像 API 配置
export const updateImageApis = (data) => request.post('/aichat/image-apis', data)


// ===== Session 调试 API =====
// 获取所有 Session 列表
export const getSessions = () => request.get('/aichat/sessions')

// 获取指定 Session 详情
export const getSessionDetail = (sessionId) => request.get(`/aichat/sessions/${sessionId}`)

// 删除指定 Session
export const deleteSession = (sessionId) => request.delete(`/aichat/sessions/${sessionId}`)

// 清理过期 Session
export const cleanupExpiredSessions = () => request.post('/aichat/sessions/cleanup-expired')


// ===== SKILL 管理 API =====
// 获取所有可用 SKILL 列表
export const getSkills = () => request.get('/aichat/skills')

// 获取 SKILL 系统配置
export const getSkillsConfig = () => request.get('/aichat/config/skills')

// 更新 SKILL 系统配置
export const updateSkillsConfig = (config) => request.post('/aichat/config/skills', config)
