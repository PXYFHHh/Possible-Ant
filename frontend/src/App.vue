<template>
  <div class="app-shell">
    <canvas ref="gridCanvas" class="bg-grid" />
    <div class="glow-orb glow-orb-1" />
    <div class="glow-orb glow-orb-2" />

    <Transition name="page" mode="out-in">
      <router-view :key="$route.path" />
    </Transition>

    <FloatingNav />
    <ToastContainer ref="toastRef" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import FloatingNav from '@/components/shared/FloatingNav.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import { useChatStore } from '@/stores/chat'
import { useKbStore } from '@/stores/knowledge'

const route = useRoute()
const chatStore = useChatStore()
const kbStore = useKbStore()

const gridCanvas = ref(null)
let animFrame = null

function drawGrid() {
  const canvas = gridCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  canvas.style.width = window.innerWidth + 'px'
  canvas.style.height = window.innerHeight + 'px'
  ctx.scale(dpr, dpr)

  const w = window.innerWidth
  const h = window.innerHeight
  const size = 48

  ctx.clearRect(0, 0, w, h)

  ctx.strokeStyle = 'rgba(99, 102, 241, 0.04)'
  ctx.lineWidth = 1
  for (let x = 0; x <= w; x += size) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let y = 0; y <= h; y += size) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }

  const dotSize = 1.5
  ctx.fillStyle = 'rgba(99, 102, 241, 0.08)'
  for (let x = size / 2; x <= w; x += size) {
    for (let y = size / 2; y <= h; y += size) {
      ctx.beginPath(); ctx.arc(x, y, dotSize, 0, Math.PI * 2); ctx.fill()
    }
  }
}

function handleResize() {
  if (animFrame) cancelAnimationFrame(animFrame)
  animFrame = requestAnimationFrame(drawGrid)
}

let pollTimer = null

onMounted(() => {
  drawGrid()
  window.addEventListener('resize', handleResize)

  pollTimer = setInterval(() => {
    kbStore.loadActiveJobs()
  }, 5000)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (animFrame) cancelAnimationFrame(animFrame)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.app-shell {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
}

.bg-grid {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.glow-orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(120px);
  pointer-events: none;
  z-index: 0;
  opacity: 0.15;
}
.glow-orb-1 {
  width: 600px;
  height: 600px;
  top: -200px;
  right: -150px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.5), transparent);
  animation: pulse-breath 8s ease-in-out infinite;
}
.glow-orb-2 {
  width: 400px;
  height: 400px;
  bottom: -100px;
  left: -100px;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.4), transparent);
  animation: pulse-breath 10s ease-in-out infinite reverse;
}

.page-enter-active,
.page-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
