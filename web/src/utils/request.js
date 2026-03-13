import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.token = token
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    const { data } = response
    if (data.status === 200) {
      return data.data
    }
    if (data.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(new Error(data.data || '登录已过期'))
    }
    return Promise.reject(new Error(data.data || '请求失败'))
  },
  (error) => {
    const msg = error.response?.data?.message || error.message || '网络错误'
    return Promise.reject(new Error(msg))
  }
)

export default request
