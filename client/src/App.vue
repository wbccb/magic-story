<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import DrawingCanvas from './components/DrawingCanvas.vue'
import AudioRecorder from './components/AudioRecorder.vue'
import axios from 'axios'

// 状态管理
// 用途: 控制当前页面处于哪个阶段
const currentStage = ref<'draw' | 'record' | 'wait' | 'result'>('draw')

const canvasRef = ref<InstanceType<typeof DrawingCanvas> | null>(null)
const audioBlob = ref<Blob | null>(null)
const imageBlob = ref<Blob | null>(null)
const storyId = ref<string>('')

// 等待页状态
const progressPct = ref(0)
const stepMessage = ref('')
const finalVideoUrl = ref('')
const redrawnImageUrl = ref('')
const ttsAudioUrl = ref('')
const narrationText = ref('')
const recorderRef = ref<InstanceType<typeof AudioRecorder> | null>(null)
let pollTimer: number | null = null
const workflowUploading = ref(false)

type ComfyProvider = 'cloud' | 'local'

interface ComfySettings {
  provider: ComfyProvider
  label: string
  base_url: string
  api_key: string
  workflow_api: string
  workflow_id: string
  local_endpoint: string
  client_id: string
  positive_prompt: string
  negative_prompt: string
  template_ready?: boolean
  template_path?: string | null
  placeholders?: string[]
}

const comfySettings = ref<ComfySettings>({
  provider: 'local',
  label: '本地 ComfyUI',
  base_url: '',
  api_key: '',
  workflow_api: '/api/prompt',
  workflow_id: '',
  local_endpoint: 'http://127.0.0.1:8188',
  client_id: 'magic-story-poc',
  positive_prompt: "children's picture book illustration, clay art, soft lighting, colorful scene, {narration}",
  negative_prompt: 'blurry, low quality, distorted, extra limbs, text, watermark'
})
const configSaving = ref(false)
const configTesting = ref(false)
const configStatus = ref('')
const activeProviderLabel = computed(() => comfySettings.value.provider === 'cloud' ? 'Comfy Cloud' : '本地 ComfyUI')

// 加载图像服务配置
// 用途: 页面初始化时回显已保存的 Comfy Cloud 或本地 ComfyUI 配置
const loadComfySettings = async () => {
  try {
    const res = await axios.get('/api/settings/comfy')
    comfySettings.value = res.data
  } catch (err) {
    console.error(err)
    configStatus.value = '图像服务配置读取失败，已使用默认值。'
  }
}

// 保存图像服务配置
// 用途: 让前端页面支持切换和持久化图片生成服务接入方式
const saveComfySettings = async () => {
  configSaving.value = true
  configStatus.value = ''
  try {
    const res = await axios.put('/api/settings/comfy', comfySettings.value)
    comfySettings.value = res.data
    configStatus.value = '图像服务配置已保存。'
  } catch (err: any) {
    console.error(err)
    configStatus.value = err?.response?.data?.detail || '保存失败，请检查配置。'
  } finally {
    configSaving.value = false
  }
}

// 测试图像服务连接
// 用途: 在真正接入图片生成工作流前，帮助用户先确认配置是否有效
const testComfySettings = async () => {
  configTesting.value = true
  configStatus.value = ''
  try {
    const res = await axios.post('/api/settings/comfy/test', comfySettings.value)
    configStatus.value = res.data.message || '连接测试成功。'
  } catch (err: any) {
    console.error(err)
    configStatus.value = err?.response?.data?.detail || '连接测试失败。'
  } finally {
    configTesting.value = false
  }
}

// 上传工作流模板
// 用途: 保存从 ComfyUI 导出的 API workflow JSON，让后端在重绘阶段注入占位符后直接执行
const uploadWorkflowTemplate = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  workflowUploading.value = true
  configStatus.value = ''
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await axios.post('/api/settings/comfy/workflow', formData)
    comfySettings.value.template_ready = res.data.template_ready
    comfySettings.value.template_path = res.data.template_path
    comfySettings.value.placeholders = res.data.placeholders
    configStatus.value = 'Workflow 模板上传成功，后端会在重绘时自动注入占位符。'
  } catch (err: any) {
    console.error(err)
    configStatus.value = err?.response?.data?.detail || 'Workflow 上传失败。'
  } finally {
    workflowUploading.value = false
    input.value = ''
  }
}

// 步骤 1: 完成画图，进入录音
const handleDrawComplete = async () => {
  if (canvasRef.value) {
    const blob = await canvasRef.value.getCanvasBlob()
    if (blob) {
      imageBlob.value = blob
      currentStage.value = 'record'
    } else {
      alert('请先画点什么吧！')
    }
  }
}

// 步骤 2: 完成录音，提交数据
const handleRecordComplete = async (blob: Blob) => {
  audioBlob.value = blob
  await submitData()
}

// 步骤 3: 提交数据到后端
const submitData = async () => {
  if (!imageBlob.value || !audioBlob.value) return

  currentStage.value = 'wait'
  const formData = new FormData()
  formData.append('image', imageBlob.value, 'drawing.png')
  formData.append('audio', audioBlob.value, 'recording.webm')

  try {
    // 1. 上传文件
    const uploadRes = await axios.post('/api/upload', formData)
    storyId.value = uploadRes.data.story_id

    // 2. 触发渲染
    await axios.post(`/api/render/${storyId.value}`)

    // 3. 开始轮询
    pollStatus()
  } catch (err) {
    console.error(err)
    alert('上传失败，请重试')
    currentStage.value = 'draw'
  }
}

// 步骤 4: 轮询后端状态
const pollStatus = () => {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const res = await axios.get(`/api/status/${storyId.value}`)
      progressPct.value = res.data.progress_pct
      stepMessage.value = res.data.step_message

      if (res.data.status === 'completed') {
        stopPolling()
        fetchResult()
      } else if (res.data.status === 'failed') {
        stopPolling()
        alert('生成失败: ' + (res.data.error_message || '未知错误'))
        currentStage.value = 'draw'
      }
    } catch (err) {
      console.error(err)
    }
  }, 2000)
}

// 停止轮询
// 用途: 在流程结束或重置时清理定时器，避免重复请求
const stopPolling = () => {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 步骤 5: 获取最终结果
const fetchResult = async () => {
  try {
    const res = await axios.get(`/api/result/${storyId.value}`)
    finalVideoUrl.value = res.data.final_video_url
    redrawnImageUrl.value = res.data.redrawn_image_url || ''
    ttsAudioUrl.value = res.data.tts_audio_url || ''
    narrationText.value = res.data.narration || ''
    currentStage.value = 'result'
  } catch (err) {
    console.error(err)
  }
}

// 返回重画
// 用途: 取消当前录音并回到绘画阶段，不触发上传
const goBackToDraw = () => {
  recorderRef.value?.cancelRecording()
  currentStage.value = 'draw'
}

// 重置流程
// 用途: 清空页面级状态并重置画板，开始下一次完整测试
const reset = () => {
  stopPolling()
  currentStage.value = 'draw'
  progressPct.value = 0
  stepMessage.value = ''
  storyId.value = ''
  imageBlob.value = null
  audioBlob.value = null
  finalVideoUrl.value = ''
  redrawnImageUrl.value = ''
  ttsAudioUrl.value = ''
  narrationText.value = ''
  recorderRef.value?.cancelRecording()
  canvasRef.value?.clearCanvas()
}

onMounted(() => {
  loadComfySettings()
})
</script>

<template>
  <div class="app-container">
    <header class="header">
      <h1>奇思妙画 POC Demo</h1>
      <p class="subhead">当前图像服务：{{ activeProviderLabel }}</p>
    </header>

    <main class="main-content">
      <section class="config-panel">
        <div class="config-header">
          <div>
            <h2>图像服务配置</h2>
            <p>支持填写 Comfy Cloud 官方 API，或切换到自定义本地 ComfyUI。</p>
          </div>
          <span class="provider-badge">{{ activeProviderLabel }}</span>
        </div>

        <div class="provider-switch">
          <button
            class="toggle-btn"
            :class="{ active: comfySettings.provider === 'cloud' }"
            @click="comfySettings.provider = 'cloud'"
          >
            Comfy Cloud
          </button>
          <button
            class="toggle-btn"
            :class="{ active: comfySettings.provider === 'local' }"
            @click="comfySettings.provider = 'local'"
          >
            本地 ComfyUI
          </button>
        </div>

        <div class="config-grid">
          <label class="field">
            <span>配置名称</span>
            <input v-model="comfySettings.label" type="text" placeholder="例如：Comfy Cloud 生产环境" />
          </label>

          <label v-if="comfySettings.provider === 'cloud'" class="field">
            <span>Base URL</span>
            <input v-model="comfySettings.base_url" type="url" placeholder="https://..." />
          </label>

          <label v-if="comfySettings.provider === 'cloud'" class="field">
            <span>API Key</span>
            <input v-model="comfySettings.api_key" type="password" placeholder="可选，按你的 Comfy Cloud 配置填写" />
          </label>

          <label v-if="comfySettings.provider === 'cloud'" class="field">
            <span>提交接口路径</span>
            <input v-model="comfySettings.workflow_api" type="text" placeholder="/api/prompt" />
          </label>

          <label v-if="comfySettings.provider === 'cloud'" class="field">
            <span>Workflow ID</span>
            <input v-model="comfySettings.workflow_id" type="text" placeholder="可选，预留给后续工作流调用" />
          </label>

          <label v-if="comfySettings.provider === 'local'" class="field">
            <span>本地服务地址</span>
            <input v-model="comfySettings.local_endpoint" type="url" placeholder="http://127.0.0.1:8188" />
          </label>

          <label v-if="comfySettings.provider === 'local'" class="field">
            <span>Client ID</span>
            <input v-model="comfySettings.client_id" type="text" placeholder="magic-story-poc" />
          </label>

          <label class="field field-wide">
            <span>正向提示词模板</span>
            <textarea v-model="comfySettings.positive_prompt" rows="3" placeholder="支持 {narration} 占位符"></textarea>
          </label>

          <label class="field field-wide">
            <span>负向提示词模板</span>
            <textarea v-model="comfySettings.negative_prompt" rows="3" placeholder="blurry, low quality, distorted"></textarea>
          </label>
        </div>

        <div class="workflow-panel">
          <div>
            <p class="workflow-title">Workflow 模板</p>
            <p class="workflow-desc">上传从 ComfyUI 导出的 API 格式 JSON，并在模板里使用占位符：{{ comfySettings.placeholders?.join(' / ') }}</p>
            <p class="workflow-state" :class="{ ready: comfySettings.template_ready }">
              {{ comfySettings.template_ready ? `已就绪：${comfySettings.template_path}` : '尚未上传 workflow 模板，ComfyUI 重绘会自动跳过。' }}
            </p>
          </div>
          <label class="upload-btn">
            {{ workflowUploading ? '上传中...' : '上传 Workflow JSON' }}
            <input type="file" accept=".json,application/json" :disabled="workflowUploading" @change="uploadWorkflowTemplate" />
          </label>
        </div>

        <div class="config-actions">
          <button class="secondary-btn" :disabled="configSaving" @click="saveComfySettings">
            {{ configSaving ? '保存中...' : '保存配置' }}
          </button>
          <button class="primary-btn slim" :disabled="configTesting" @click="testComfySettings">
            {{ configTesting ? '测试中...' : '测试连接' }}
          </button>
        </div>

        <p v-if="configStatus" class="config-status">{{ configStatus }}</p>
      </section>

      <!-- 绘画阶段 -->
      <div v-show="currentStage === 'draw'" class="stage">
        <DrawingCanvas ref="canvasRef" />
        <button class="primary-btn" @click="handleDrawComplete">画好了，去录音</button>
      </div>

      <!-- 录音阶段 -->
      <div v-if="currentStage === 'record'" class="stage">
        <AudioRecorder ref="recorderRef" @complete="handleRecordComplete" />
        <button class="secondary-btn" @click="goBackToDraw">返回重画</button>
      </div>

      <!-- 等待阶段 -->
      <div v-if="currentStage === 'wait'" class="stage wait-stage">
        <h2>正在施展魔法...</h2>
        <div class="progress-bar-container">
          <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
        </div>
        <p class="step-message">{{ stepMessage }} ({{ progressPct }}%)</p>
      </div>

      <!-- 结果阶段 -->
      <div v-if="currentStage === 'result'" class="stage result-stage">
        <h2>你的动画片完成了！</h2>
        <div v-if="finalVideoUrl" class="video-card">
          <video class="result-video" :src="finalVideoUrl" controls preload="metadata"></video>
          <p class="video-hint">当前成片由上传涂鸦和 TTS 音频通过 FFmpeg 真实合成。</p>
        </div>
        <div v-else class="video-placeholder">
          <p>视频已生成，但当前未拿到可播放地址。</p>
        </div>
        <div v-if="redrawnImageUrl" class="image-card">
          <h3>ComfyUI 重绘结果</h3>
          <img class="redrawn-image" :src="redrawnImageUrl" alt="ComfyUI redrawn result" />
        </div>
        <div v-if="ttsAudioUrl" class="tts-card">
          <h3>真实 TTS 试听</h3>
          <p class="tts-text">{{ narrationText }}</p>
          <audio :src="ttsAudioUrl" controls preload="metadata"></audio>
        </div>
        <button class="primary-btn" @click="reset">再做一次</button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.app-container {
  max-width: 980px;
  margin: 0 auto;
  padding: 24px;
  text-align: center;
}
.header { margin-bottom: 20px; }
.subhead {
  color: #5b6475;
  margin-top: 8px;
}
.main-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.config-panel {
  background: linear-gradient(135deg, #f9f4ea, #eef6ff);
  border: 1px solid #d7dfeb;
  border-radius: 18px;
  padding: 22px;
  text-align: left;
  box-shadow: 0 14px 32px rgba(36, 57, 89, 0.08);
}
.config-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}
.config-header h2 {
  margin: 0;
}
.config-header p {
  margin: 8px 0 0;
  color: #5e6576;
}
.provider-badge {
  padding: 8px 12px;
  border-radius: 999px;
  background: #17324d;
  color: #fff;
  font-size: 13px;
}
.provider-switch {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.toggle-btn {
  border: 1px solid #b8c4d5;
  background: rgba(255, 255, 255, 0.82);
  color: #17324d;
  border-radius: 999px;
  padding: 10px 16px;
  cursor: pointer;
  font-size: 14px;
}
.toggle-btn.active {
  background: #17324d;
  color: #fff;
  border-color: #17324d;
}
.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  color: #304056;
}
.field-wide {
  grid-column: 1 / -1;
}
.field input {
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.92);
}
.field textarea {
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.92);
  resize: vertical;
  font-family: inherit;
}
.workflow-panel {
  margin-top: 18px;
  border: 1px dashed #b8c4d5;
  border-radius: 14px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.workflow-title {
  margin: 0;
  font-weight: 700;
  color: #17324d;
}
.workflow-desc {
  margin: 6px 0 0;
  color: #5e6576;
  font-size: 13px;
}
.workflow-state {
  margin: 10px 0 0;
  color: #8a4b13;
  font-size: 13px;
  word-break: break-all;
}
.workflow-state.ready {
  color: #1b4d37;
}
.upload-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #17324d;
  background: #17324d;
  color: #fff;
  border-radius: 999px;
  padding: 10px 16px;
  cursor: pointer;
  font-size: 14px;
}
.upload-btn input {
  display: none;
}
.config-actions {
  display: flex;
  gap: 12px;
  margin-top: 18px;
  flex-wrap: wrap;
}
.config-status {
  margin: 14px 0 0;
  color: #1b4d37;
  font-size: 14px;
}
.stage {
  background: #fff;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.primary-btn {
  background: #4caf50;
  color: white;
  border: none;
  padding: 12px 24px;
  font-size: 16px;
  border-radius: 8px;
  cursor: pointer;
  margin-top: 10px;
}
.secondary-btn {
  background: #9e9e9e;
  color: white;
  border: none;
  padding: 10px 20px;
  font-size: 14px;
  border-radius: 8px;
  cursor: pointer;
}
.wait-stage .progress-bar-container {
  width: 100%;
  max-width: 400px;
  height: 20px;
  background: #e0e0e0;
  border-radius: 10px;
  overflow: hidden;
}
.wait-stage .progress-bar {
  height: 100%;
  background: #4caf50;
  transition: width 0.3s ease;
}
.slim {
  margin-top: 0;
}
.video-placeholder {
  width: 100%;
  max-width: 600px;
  aspect-ratio: 16/9;
  background: #000;
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
}
.video-card {
  width: 100%;
  max-width: 720px;
  background: #111827;
  border-radius: 14px;
  padding: 14px;
}
.result-video {
  width: 100%;
  display: block;
  border-radius: 10px;
  background: #000;
}
.video-hint {
  color: #d7deeb;
  margin: 12px 0 0;
  font-size: 14px;
}
.image-card {
  width: 100%;
  max-width: 600px;
  background: #f6f8fb;
  border: 1px solid #dbe4f0;
  border-radius: 12px;
  padding: 16px;
}
.image-card h3 {
  margin: 0 0 12px;
}
.redrawn-image {
  width: 100%;
  display: block;
  border-radius: 10px;
  background: #fff;
}
.tts-card {
  width: 100%;
  max-width: 600px;
  background: #f6f8fb;
  border: 1px solid #dbe4f0;
  border-radius: 12px;
  padding: 16px;
}
.tts-card h3 {
  margin: 0 0 10px;
}
.tts-text {
  color: #495468;
  margin: 0 0 12px;
}
.tts-card audio {
  width: 100%;
}
.note { font-size: 12px; color: #ccc; }
@media (max-width: 720px) {
  .app-container {
    padding: 16px;
  }
  .config-header {
    flex-direction: column;
  }
  .provider-switch,
  .config-actions {
    flex-direction: column;
  }
}
</style>
