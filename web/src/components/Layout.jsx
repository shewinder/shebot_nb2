import React from 'react'
import { Layout as AntLayout, Menu, Avatar, Dropdown, Space, Typography } from 'antd'
import {
  DashboardOutlined,
  AppstoreOutlined,
  SettingOutlined,
  FileTextOutlined,
  LogoutOutlined,
  UserOutlined,
  DownOutlined
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const { Header, Sider, Content } = AntLayout
const { Title } = Typography

const menuItems = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '仪表盘'
  },
  {
    key: '/services',
    icon: <AppstoreOutlined />,
    label: '服务管理'
  },
  {
    key: '/configs',
    icon: <SettingOutlined />,
    label: '配置管理'
  },
  {
    key: '/logs',
    icon: <FileTextOutlined />,
    label: '日志监控'
  }
]

function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  const handleMenuClick = ({ key }) => {
    navigate(key)
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout
    }
  ]

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={200}>
        <div style={{ padding: '16px', textAlign: 'center' }}>
          <Title level={4} style={{ color: '#fff', margin: 0 }}>
            SheBot
          </Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>
      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.username || '管理员'}</span>
              <DownOutlined />
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: '24px', padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
