# SheBot Web 控制台

基于 React + Ant Design 的 QQ Bot 管理后台。

## 功能特性

- 📊 **仪表盘** - 查看 Bot 运行状态、群数量、服务数量、插件列表
- 🎛️ **服务管理** - 按服务或按群查看和修改服务启用状态
- ⚙️ **配置管理** - 可视化编辑插件配置（JSON 格式）
- 📜 **日志监控** - 实时查看 Bot 运行日志（支持 WebSocket）

## 技术栈

- React 18
- Ant Design 5
- React Router 6
- Axios
- Vite

## 开发

```bash
# 进入 web 目录
cd web

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

开发服务器默认运行在 http://localhost:3000，会自动代理 API 请求到 http://localhost:9002。

## 构建

```bash
# 构建生产版本
npm run build
```

构建后的文件会输出到 `static/` 目录，直接访问 http://localhost:9002 即可使用。

## 项目结构

```
web/
├── src/
│   ├── api/           # API 接口
│   ├── components/    # 公共组件
│   ├── hooks/         # 自定义 hooks
│   ├── pages/         # 页面组件
│   ├── utils/         # 工具函数
│   ├── App.jsx        # 路由配置
│   └── main.jsx       # 入口文件
├── index.html
├── package.json
└── vite.config.js
```

## 后端 API

Web 控制台依赖以下后端 API：

- `POST /login` - 登录
- `GET /get_group_list` - 获取群列表
- `GET /get_loaded_services` - 获取服务列表
- `GET /get_service_groups/{sv_name}` - 获取服务在群的启用状态
- `GET /get_group_services/{group_id}` - 获取群的服务配置
- `POST /set_service` - 设置服务配置
- `GET /get_plugin_config` - 获取插件配置
- `POST /set_plugin` - 设置插件配置
- `GET /get_loaded_plugins` - 获取已加载插件
- `GET /get_project_info` - 获取项目信息
- `WS /ws/logs` - 日志 WebSocket（可选）

## 注意事项

1. 首次使用前需要先构建：`npm run build`
2. 登录账号为 QQ 号，默认密码为 QQ 号
3. 生产环境建议启用 token 验证（取消 app.py 中的注释）
