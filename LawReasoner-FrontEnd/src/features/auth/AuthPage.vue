<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { postJson } from '../../shared/httpClient'
import { saveSession } from '../../shared/authSession'

const router = useRouter()
const mode = ref('login')
const username = ref('')
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submitCredentials() {
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'register') await postJson('/auth/register', { username: username.value, email: email.value, password: password.value })
    const session = await postJson('/auth/login', { username: username.value, password: password.value })
    saveSession(session)
    router.replace('/')
  } catch (reason) {
    error.value = reason.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="auth-screen"><section class="auth-card">
    <span class="eyebrow">LAWREASONER / AGENT</span><h1>法理智推</h1>
    <p>让法律分析和合同起草从同一次对话开始。</p>
    <div class="segmented" role="tablist" aria-label="账户操作">
      <button :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
      <button :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
    </div>
    <form @submit.prevent="submitCredentials">
      <label>用户名或邮箱<input v-model="username" autocomplete="username" required /></label>
      <label v-if="mode === 'register'">邮箱<input v-model="email" type="email" autocomplete="email" required /></label>
      <label>密码<input v-model="password" type="password" :minlength="mode === 'register' ? 10 : undefined" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" required /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary" :disabled="busy">{{ busy ? '请稍候…' : mode === 'login' ? '进入工作台' : '创建账户并登录' }}</button>
    </form>
  </section></main>
</template>
