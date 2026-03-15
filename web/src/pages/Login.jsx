import React, { useState, useEffect } from 'react'
import { Card, Form, Input, Button, message, Typography } from 'antd'
import { LockOutlined, SafetyOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { login as loginApi } from '../api'
import { useAuth } from '../hooks/useAuth'

const { Title, Text } = Typography

// 浮动粒子背景
function ParticleBackground() {
  const [particles, setParticles] = useState([])

  useEffect(() => {
    const newParticles = Array.from({ length: 20 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      top: Math.random() * 100,
      size: Math.random() * 6 + 2,
      delay: Math.random() * 5,
      duration: Math.random() * 10 + 10,
    }))
    setParticles(newParticles)
  }, [])

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        overflow: 'hidden',
        zIndex: 0,
        background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%)',
      }}
    >
      {/* 渐变光晕 */}
      <div
        style={{
          position: 'absolute',
          top: '20%',
          left: '10%',
          width: '40%',
          height: '40%',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.3) 0%, transparent 70%)',
          borderRadius: '50%',
          animation: 'float 20s ease-in-out infinite',
        }}
      />
      <div
        style={{
          position: 'absolute',
          bottom: '10%',
          right: '10%',
          width: '50%',
          height: '50%',
          background: 'radial-gradient(circle, rgba(139, 92, 246, 0.2) 0%, transparent 70%)',
          borderRadius: '50%',
          animation: 'float 25s ease-in-out infinite reverse',
        }}
      />

      {/* 浮动粒子 */}
      {particles.map((p) => (
        <div
          key={p.id}
          style={{
            position: 'absolute',
            left: `${p.left}%`,
            top: `${p.top}%`,
            width: p.size,
            height: p.size,
            background: 'rgba(255, 255, 255, 0.6)',
            borderRadius: '50%',
            animation: `float ${p.duration}s ease-in-out infinite`,
            animationDelay: `${p.delay}s`,
            boxShadow: '0 0 10px rgba(255, 255, 255, 0.5)',
          }}
        />
      ))}

      {/* 网格背景 */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: `
            linear-gradient(rgba(99, 102, 241, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(99, 102, 241, 0.03) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }}
      />
    </div>
  )
}

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
    <>
      <ParticleBackground />
      <div
        style={{
          height: '100vh',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          position: 'relative',
          zIndex: 1,
        }}
      >
        <Card
          className="glass"
          style={{
            width: 420,
            borderRadius: '24px',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            background: 'rgba(30, 41, 59, 0.7)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          }}
          bodyStyle={{ padding: '40px' }}
        >
          <div style={{ textAlign: 'center', marginBottom: 40 }}>
            <div
              style={{
                width: 80,
                height: 80,
                margin: '0 auto 20px',
                borderRadius: '20px',
                background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 40,
                boxShadow: '0 0 30px rgba(99, 102, 241, 0.5)',
                animation: 'glow 2s ease-in-out infinite',
              }}
            >
              🤖
            </div>
            <Title
              level={3}
              style={{
                margin: 0,
                marginBottom: 8,
                color: '#fff',
                fontWeight: 700,
              }}
            >
              SheBot 控制台
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.6)' }}>
              QQ Bot 管理后台
            </Text>
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
                prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.5)' }} />}
                placeholder="请输入密码"
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '12px',
                  color: '#fff',
                }}
                placeholderStyle={{ color: 'rgba(255,255,255,0.4)' }}
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0, marginTop: 24 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                size="large"
                style={{
                  height: 48,
                  borderRadius: '12px',
                  fontSize: 16,
                  fontWeight: 600,
                  background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                  border: 'none',
                  boxShadow: '0 4px 15px rgba(99, 102, 241, 0.4)',
                }}
              >
                登录
              </Button>
            </Form.Item>
          </Form>

          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <SafetyOutlined style={{ color: 'rgba(255,255,255,0.3)', marginRight: 8 }} />
            <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
              安全加密连接
            </Text>
          </div>
        </Card>
      </div>

      <style>{`
        @keyframes glow {
          0%, 100% {
            box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
          }
          50% {
            box-shadow: 0 0 40px rgba(99, 102, 241, 0.8);
          }
        }
      `}</style>
    </>
  )
}

export default Login
