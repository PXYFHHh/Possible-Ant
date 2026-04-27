<template>
  <nav class="floating-nav" :class="{ open: isOpen }">
    <button class="nav-toggle" @click="isOpen = !isOpen" :aria-label="isOpen ? '关闭菜单' : '打开菜单'">
      <Menu :size="18" />
    </button>

    <Transition name="nav-drop">
      <div v-if="isOpen" class="nav-drop">
        <div class="nav-drop-inner glass">
          <button
            v-for="item in items"
            :key="item.path"
            class="nav-item"
            :class="{ active: $route.path === item.path }"
            @click="navigate(item.path)"
          >
            <component :is="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </button>
        </div>
      </div>
    </Transition>
  </nav>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Menu, MessageCircle, BookOpen } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const isOpen = ref(false)

const items = [
  { path: '/', label: '聊天', icon: MessageCircle },
  { path: '/knowledge', label: '知识库', icon: BookOpen },
]

function navigate(path) {
  isOpen.value = false
  router.push(path)
}
</script>

<style scoped>
.floating-nav {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.nav-toggle {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--bg-surface);
  backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  display: grid;
  place-items: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  box-shadow: var(--glass-shadow);
}

.nav-toggle:hover {
  border-color: var(--glass-border-hover);
  color: var(--text-primary);
}

.nav-drop {
  min-width: 160px;
}

.nav-drop-inner {
  padding: 6px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
}

.nav-item:hover {
  background: rgba(99, 102, 241, 0.08);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(99, 102, 241, 0.12);
  color: var(--accent-light);
}

.nav-item svg {
  flex-shrink: 0;
}

.nav-drop-enter-active { transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1); }
.nav-drop-leave-active { transition: all 0.15s ease-in; }
.nav-drop-enter-from { opacity: 0; transform: translateY(-8px) scale(0.95); }
.nav-drop-leave-to { opacity: 0; transform: translateY(-4px) scale(0.97); }
</style>
