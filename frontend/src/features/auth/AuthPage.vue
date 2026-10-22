<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { postJson } from '../../shared/httpClient'
import { saveSession } from '../../shared/authSession'

const router = useRouter()
const mode = ref('login')
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submitCredentials() {
  if (busy.value) return
  const credentials = { email: email.value.trim(), password: password.value }
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'register') await postJson('/auth/register', credentials)
    const session = await postJson('/auth/login', credentials)
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
  <main class="auth-screen">
    <section class="auth-card">
      <span class="eyebrow">CONTRACTWEAVER / MULTI-AGENT</span>
      <h1>ContractWeaver</h1>
      <p>从协商记录中提取约定，由你核对，完成合同填写。</p>
      <div class="segmented" role="tablist" aria-label="账户操作">
        <button :disabled="busy" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button :disabled="busy" :class="{ active: mode === 'register' }" @click="mode = 'register'">
          注册
        </button>
      </div>
      <form @submit.prevent="submitCredentials">
        <label>
          邮箱
          <input v-model="email" type="email" autocomplete="email" :disabled="busy" required />
        </label>
        <label>
          密码
          <input
            v-model="password"
            :disabled="busy"
            type="password"
            :minlength="mode === 'register' ? 10 : undefined"
            :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
            required
          />
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="primary" :disabled="busy">
          <span v-if="busy" class="loading-spinner" aria-hidden="true" />
          {{ busy ? '请稍候…' : mode === 'login' ? '进入工作台' : '创建账户并登录' }}
        </button>
      </form>
    </section>
  </main>
</template>
