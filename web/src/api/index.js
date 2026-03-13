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
