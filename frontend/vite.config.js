/** @file 开发服务器与 API 代理配置；这里只读取公开 VITE_ 配置，不加载模型密钥。 */
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, process.cwd(), 'VITE_')
  // 本地开发服务器将业务 API 请求转发到后端。

  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/api': {
          target: environment.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
