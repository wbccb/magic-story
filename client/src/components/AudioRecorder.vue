<script setup lang="ts">
import { ref, onUnmounted } from 'vue'

const emit = defineEmits<{
  (e: 'complete', blob: Blob): void
}>()

const isRecording = ref(false)
const timeRemaining = ref(15)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const shouldEmitOnStop = ref(false)
let timer: number | null = null

// 开始录音
// 用途: 请求麦克风权限并使用 MediaRecorder 录制音频
const startRecording = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder.value = new MediaRecorder(stream)
    
    mediaRecorder.value.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.value.push(e.data)
      }
    }

    mediaRecorder.value.onstop = () => {
      if (shouldEmitOnStop.value) {
        const blob = new Blob(audioChunks.value, { type: 'audio/webm' })
        emit('complete', blob)
      }
      // 清理资源
      stream.getTracks().forEach(track => track.stop())
      mediaRecorder.value = null
      shouldEmitOnStop.value = false
      audioChunks.value = []
    }

    audioChunks.value = []
    shouldEmitOnStop.value = true
    mediaRecorder.value.start()
    isRecording.value = true
    timeRemaining.value = 15

    // 倒计时逻辑
    timer = setInterval(() => {
      timeRemaining.value--
      if (timeRemaining.value <= 0) {
        stopRecording()
      }
    }, 1000)

  } catch (err) {
    console.error('获取麦克风失败', err)
    alert('需要麦克风权限才能讲故事哦！')
  }
}

// 停止录音
// 用途: 正常结束录音并将结果回传给父组件
const stopRecording = () => {
  if (mediaRecorder.value && isRecording.value) {
    mediaRecorder.value.stop()
    isRecording.value = false
    if (timer) clearInterval(timer)
    timer = null
  }
}

// 取消录音
// 用途: 用户返回重画或组件卸载时中止录音，但不提交结果
const cancelRecording = () => {
  if (mediaRecorder.value && isRecording.value) {
    shouldEmitOnStop.value = false
    mediaRecorder.value.stop()
    isRecording.value = false
  }
  if (timer) clearInterval(timer)
  timer = null
}

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (isRecording.value) cancelRecording()
})

// 暴露给父组件的方法
// 用途: 在返回重画时安全取消录音，避免误触发上传
defineExpose({
  cancelRecording
})
</script>

<template>
  <div class="recorder-container">
    <h2>讲讲你的故事吧</h2>
    <p class="instruction">用麦克风描述一下你画了什么，限时15秒</p>
    
    <div class="record-area">
      <div v-if="isRecording" class="recording-indicator">
        <div class="pulse-ring"></div>
        <span>录音中... {{ timeRemaining }}s</span>
      </div>
      
      <button 
        class="record-btn" 
        :class="{ recording: isRecording }"
        @click="isRecording ? stopRecording() : startRecording()"
      >
        {{ isRecording ? '说完了 (点击停止)' : '开始录音' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.recorder-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
}
.instruction { color: #666; }
.record-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  min-height: 150px;
}
.record-btn {
  width: 150px;
  height: 150px;
  border-radius: 50%;
  border: none;
  background: #f44336;
  color: white;
  font-size: 18px;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(244, 67, 54, 0.3);
  transition: all 0.3s;
}
.record-btn:hover { transform: scale(1.05); }
.record-btn.recording { background: #d32f2f; }
.recording-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #f44336;
  font-weight: bold;
}
.pulse-ring {
  width: 12px;
  height: 12px;
  background: #f44336;
  border-radius: 50%;
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(244, 67, 54, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(244, 67, 54, 0); }
}
</style>
