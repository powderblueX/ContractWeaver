/** @file 页面路由与登录守卫。 */
import { createRouter, createWebHistory } from 'vue-router'
import { hasSession } from '../shared/authSession'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      /** 加载合同工作区。 */
      component: () => import('../features/contracts/ContractWorkspacePage.vue'),
      meta: { auth: true },
    },
    { path: '/login', component: () => import('../features/auth/AuthPage.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  if (to.meta.auth && !hasSession()) return '/login'
  if (to.path === '/login' && hasSession()) return '/'
})

export default router
