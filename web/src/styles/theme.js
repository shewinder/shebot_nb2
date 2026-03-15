// Ant Design 主题配置

export const lightTheme = {
  token: {
    colorPrimary: '#6366f1',
    colorInfo: '#6366f1',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    borderRadius: 8,
    wireframe: false,
  },
  components: {
    Card: {
      borderRadiusLG: 12,
      boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
    },
    Menu: {
      borderRadius: 8,
    },
    Button: {
      borderRadius: 8,
    },
  },
}

export const darkTheme = {
  token: {
    colorPrimary: '#818cf8',
    colorInfo: '#818cf8',
    colorSuccess: '#34d399',
    colorWarning: '#fbbf24',
    colorError: '#f87171',
    borderRadius: 8,
    wireframe: false,
  },
  components: {
    Card: {
      borderRadiusLG: 12,
    },
    Menu: {
      borderRadius: 8,
    },
    Button: {
      borderRadius: 8,
    },
  },
}
