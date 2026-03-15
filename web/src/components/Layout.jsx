import React, { useState } from 'react'
import { Layout as AntLayout, Menu, Avatar, Dropdown, Space, Typography, Button } from 'antd'
import {
  DashboardOutlined,
  AppstoreOutlined,
  SettingOutlined,
  FileTextOutlined,
  LogoutOutlined,
  UserOutlined,
  DownOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import ThemeToggle from './ThemeToggle'

const { Header, Sider, Content } = AntLayout
const { Title, Text } = Typography

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/services', icon: <AppstoreOutlined />, label: '服务管理' },
  { key: '/configs', icon: <SettingOutlined />, label: '配置管理' },
  { key: '/logs', icon: <FileTextOutlined />, label: '日志监控' },
]

function Layout({ isDark, toggleTheme }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const handleMenuClick = ({ key }) => {
    navigate(key)
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
      danger: true,
    },
  ]

  const siderStyle = {
    background: isDark 
      ? 'linear-gradient(180deg, #1e293b 0%, #0f172a 100%)'
      : 'linear-gradient(180deg, #4f46e5 0%, #7c3aed 100%)',
    boxShadow: '2px 0 8px rgba(0,0,0,0.15)',
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider 
        trigger={null} 
        collapsible 
        collapsed={collapsed}
        width={220}
        style={siderStyle}
      >
        <div style={{ 
          padding: collapsed ? '16px 8px' : '24px 16px',
          textAlign: 'center',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
        }}>
          <div style={{
            width: collapsed ? 40 : 50,
            height: collapsed ? 40 : 50,
            margin: '0 auto',
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: collapsed ? 20 : 28,
            color: '#fff',
            marginBottom: collapsed ? 0 : 12,
          }}>
            🤖
          </div>
          {!collapsed && (
            <Title level={5} style={{ color: '#fff', margin: 0, fontWeight: 600 }}>
              SheBot
            </Title>
          )}
        </div>
        
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems.map(item => ({
            ...item,
            style: {
              margin: '4px 8px',
              borderRadius: 'var(--radius-md)',
            }
          }))}
          onClick={handleMenuClick}
          style={{ 
            background: 'transparent',
            border: 'none',
            padding: '8px 0',
          }}
        />
      </Sider>
      
      <AntLayout>
        <Header style={{ 
          background: 'var(--bg-elevated)',
          padding: '0 24px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          zIndex: 10,
        }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{ fontSize: 16 }}
          />
          
          <Space size={24}>
            <ThemeToggle isDark={isDark} onToggle={toggleTheme} />
            
            <Button
              type="text"
              icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={toggleFullscreen}
            />
            
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Space style={{ cursor: 'pointer', padding: '4px 8px', borderRadius: 'var(--radius-md)' }}>
                <Avatar 
                  icon={<UserOutlined />} 
                  style={{ background: 'var(--primary)' }}
                />
                <Text strong style={{ color: 'var(--text-primary)' }}>
                  {user?.username || '管理员'}
                </Text>
                <DownOutlined style={{ fontSize: 12, color: 'var(--text-tertiary)' }} />
              </Space>
            </Dropdown>
          </Space>
        </Header>
        
        <Content style={{ 
          margin: 24,
          padding: 24,
          background: 'var(--bg-elevated)',
          borderRadius: 'var(--radius-lg)',
          minHeight: 280,
          boxShadow: 'var(--shadow-sm)',
        }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
