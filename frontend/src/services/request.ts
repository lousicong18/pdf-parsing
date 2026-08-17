import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    const data = error.response?.data
    const msg = data?.detail || error.message || '请求失败'
    const code = data?.code
    ElMessage.error(code ? `[${code}] ${msg}` : msg)
    return Promise.reject(error)
  }
)

export default request
