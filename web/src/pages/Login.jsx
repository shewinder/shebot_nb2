import React, { useState } from 'react'
import { Card, Form, Input, Button, message, Typography } from 'antd'
import { LockOutlined, RobotOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { login as loginApi } from '../api'
import { useAuth } from '../hooks/useAuth'

const { Title } = Typography

function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { login } = useAuth()

  const handleSubmit = async (values) => {
    setLoading(true)
    try {
      const token = await loginApi(values.password)
      login(token, { username: 'admin' })
      message.success('登录成功')
      navigate('/')
    } catch (error) {
      message.error(error.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      height: '100vh',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card style={{ width: 400, borderRadius: 8, boxShadow: '0 4px 20px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <RobotOutlined style={{ fontSize: 64, color: '#1677ff' }} />
          <Title level={3} style={{ marginTop: 16, marginBottom: 0 }}>SheBot 控制台</Title>
          <Typography.Text type="secondary">QQ Bot 管理后台</Typography.Text>
        </div>
        
        <Form
          name="login"
          onFinish={handleSubmit}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入密码"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
            >
              登录
            </Button>
          </Form.Item>
        </Form>

        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', textAlign: 'center' }}>
          密码请在 .env.prod 中配置 web_password
        </Typography.Text>
      </Card>
    </div>
  )
}

export default Login
