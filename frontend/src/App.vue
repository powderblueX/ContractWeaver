<!-- @file 应用路由视图与页面过渡入口。 -->
<template>
  <router-view v-slot="{ Component }">
    <Transition name="page" mode="out-in"><component :is="Component" /></Transition>
  </router-view>
</template>
