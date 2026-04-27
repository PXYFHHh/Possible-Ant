import { ref, onUnmounted } from 'vue'

export function useTypewriter(speed = 30) {
  const displayText = ref('')
  const isTyping = ref(false)
  const fullText = ref('')
  let timer = null
  let index = 0

  function start(text) {
    stop()
    fullText.value = text
    displayText.value = ''
    index = 0
    isTyping.value = true

    return new Promise((resolve) => {
      function tick() {
        if (index < fullText.value.length) {
          displayText.value += fullText.value[index]
          index++
          timer = setTimeout(tick, speed)
        } else {
          isTyping.value = false
          resolve()
        }
      }
      timer = setTimeout(tick, speed)
    })
  }

  function stop() {
    if (timer) clearTimeout(timer)
    isTyping.value = false
  }

  function finish() {
    stop()
    displayText.value = fullText.value
  }

  onUnmounted(() => stop())

  return { displayText, isTyping, start, stop, finish }
}
