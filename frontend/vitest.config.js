/** @file 前端单元测试配置。 */
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: { environment: 'jsdom', include: ['src/**/*.test.js'], clearMocks: true },
})
