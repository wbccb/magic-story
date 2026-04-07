# 奇思妙画 (MagicStory) - POC Demo 运行与自测指南

本项目是“奇思妙画”的 POC (Proof of Concept) 演示环境，主要用于验证核心链路：**儿童涂鸦 + 语音 -> AI管线 -> 生成动画视频**。当前版本已经接入了四个真实可用的 AI / 媒体环节：**本地 ASR (`faster-whisper`)**、**可切换 Provider 的本地/兼容式 LLM**、**Edge-TTS 中文语音合成**、**FFmpeg MP4 合成**；图像生成和视频生成链路仍为 Mock 状态，用于验证前后端交互、任务队列和页面流转。

下面将引导您如何在本地启动服务并开展自测。

## 1. 环境准备

在开始之前，请确保您的电脑上已安装以下软件：

1. **Docker & Docker Compose** (用于运行后端 API、Redis 队列和 Celery Worker)
2. **Node.js (>= 18)** (用于运行前端 Vite 开发服务器)
3. **npm** (Node 包管理器)
4. **本地 LLM 服务** (推荐 Ollama 或任意 OpenAI 兼容接口)
5. **足够的模型空间** (首次运行 `faster-whisper` 会自动下载模型)

## 2. 后端 .env 配置

后端现在已经支持通过 `.env` 配置本地 LLM、ASR 和 TTS。

1. 进入 `server` 目录：
   ```bash
   cd server
   ```
2. 基于示例文件创建 `.env`：
   ```bash
   cp .env.example .env
   ```
3. 按需修改关键配置：

   ```env
   REDIS_URL=redis://redis:6379/0
   DATABASE_URL=sqlite:///./data/magic_story.db
   UPLOAD_DIR=./data/uploads
   OUTPUT_DIR=./data/outputs

   LLM_PROVIDER=ollama
   LLM_BASE_URL=http://host.docker.internal:11434/v1
   LLM_API_KEY=ollama
   LLM_MODEL=qwen3:latest
   LLM_TEMPERATURE=0.2
   LLM_TIMEOUT_SECONDS=60

   ASR_PROVIDER=faster_whisper
   ASR_MODEL_SIZE=small
   ASR_DEVICE=cpu
   ASR_COMPUTE_TYPE=int8

   EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural
   ```

常用配置说明：

- `LLM_PROVIDER`
  - `mock`: 保持原来的假数据
  - `ollama`: 连接本地 Ollama 的 OpenAI 兼容接口
  - `openai_compatible`: 连接任意兼容 OpenAI Chat Completions 的本地模型服务
- `LLM_BASE_URL`
  - Docker 环境下访问宿主机上的 Ollama，macOS 常用 `http://host.docker.internal:11434/v1`
- `ASR_MODEL_SIZE`
  - 可选如 `tiny`、`base`、`small`、`medium`
- `ASR_DEVICE`
  - 常见值：`cpu`、`cuda`

## 3. 启动服务

### 3.1 启动后端服务

后端服务包含 FastAPI 主服务、Redis 容器以及 Celery 异步任务处理器。

1. 打开终端，进入 `server` 目录：
   ```bash
   cd server
   ```
2. 使用 Docker Compose 一键启动：
   ```bash
   docker-compose up --build -d
   ```
   > 提示：`-d` 参数表示在后台运行。首次启动需要拉取基础镜像、安装 Python 依赖，并在首次执行 ASR 时下载 `faster-whisper` 模型，可能需要几分钟时间。

3. **验证后端状态**：
   打开浏览器访问 [http://localhost:8000/health](http://localhost:8000/health)，如果返回 `{"status":"ok"}`，说明后端已成功启动。

4. **可选：确认媒体目录可访问**
   当前后端会把上传文件、TTS 输出文件和 FFmpeg 合成后的 MP4 都暴露在 `/media/*` 路径下。服务启动后，可以访问类似 [http://localhost:8000/media/](http://localhost:8000/media/) 的静态资源前缀来确认媒体目录已挂载。

5. **可选：确认运行时配置**
   访问 [http://localhost:8000/api/settings/runtime](http://localhost:8000/api/settings/runtime)，可以查看当前后端实际生效的 `LLM / ASR / TTS` 配置摘要。

### 3.2 启动前端服务

前端是一个基于 Vue 3 + Vite 的 H5 单页应用。

1. 打开一个新的终端窗口，进入 `client` 目录：
   ```bash
   cd client
   ```
2. 安装前端依赖：
   ```bash
   npm install
   ```
3. 启动开发服务器：
   ```bash
   npm run dev
   ```
4. **访问前端页面**：
   终端会输出一个本地访问地址，通常是 [http://localhost:5173/](http://localhost:5173/)。点击或在浏览器中打开该链接。

---

## 4. POC 端到端自测流程

打开前端页面后，您可以按照以下步骤模拟一个完整的用户体验流程：

### 步骤一：体验涂鸦画板 (Drawing Stage)
0. 在正式开始前，您可以先查看页面顶部新增的**图像服务配置**面板：
   - 支持切换为 **Comfy Cloud**。
   - 支持切换为 **本地 ComfyUI**。
   - 支持保存配置，并点击“测试连接”做基础校验。
   - 这套配置已经会持久化到后端，供后续真实接入图片生成工作流时直接复用。

1. 在白板上使用鼠标或触摸板进行绘画。
2. 尝试使用下方的工具栏：
   - 切换不同的**颜色**。
   - 切换画笔**粗细**（可以体验到 `perfect-freehand` 带来的平滑压感效果）。
   - 尝试使用**橡皮擦**、**撤销**和**清空**功能。
3. 画完后，点击下方的 **“画好了，去录音”** 按钮。

### 步骤二：体验语音录制 (Recording Stage)
1. 页面会提示您使用麦克风，请在浏览器弹窗中**允许麦克风权限**。
2. 点击 **“开始录音”**，对着麦克风描述您刚刚画的内容（例如：“这是一只正在奔跑的绿色恐龙”）。
3. 观察录音状态：
   - 会有红色的呼吸灯动画。
   - 会有 15 秒的倒计时显示。
4. 您可以提前点击 **“说完了 (点击停止)”**，或者等待 15 秒倒计时结束自动停止。

### 步骤三：体验魔法等待 (Waiting Stage)
1. 录音结束后，前端会自动将**涂鸦图片 (PNG)** 和 **录音文件 (WebM)** 打包上传至后端。
2. 页面进入“正在施展魔法...”的等待状态。
3. 您将看到一个**进度条**和**中文状态提示**，这些信息是前端每隔 2 秒通过 `/api/status` 接口向后端轮询获取的。
4. 观察提示文字的变化，它模拟了后端的 AI 管线流程：
   - 正在聆听你的故事... (真实 `faster-whisper` ASR)
   - 正在理解画面... (真实本地 / 兼容式 LLM)
   - 正在施展魔法... (ComfyUI)
   - 正在拍摄动画片... (I2V / 2.5D)
   - 正在请配音员准备... (真实 Edge-TTS)
   - 最后润色中... (真实 FFmpeg 合成)

### 步骤四：查看结果 (Result Stage)
1. 当进度达到 100% 后，页面会自动跳转到结果展示页。
2. 您会看到提示“你的动画片完成了！”。
3. 当前结果页会展示：
   - **真实生成的 MP4 视频播放器**
   - **真实生成的中文 TTS 音频播放器**
   - 本次任务生成的**旁白文本**
4. *注意：当前 POC 阶段，视频内容仍然是“静态涂鸦图 + 旁白音频”的合成成片，不是 AI 动画生成片段；但 ASR、LLM、TTS 与 FFmpeg 都已接入真实实现。*
4. 点击 **“再做一次”** 即可重置状态，开始新的测试。

---

## 5. 后台数据检查 (可选)

为了确认数据确实持久化到了后端，您可以检查 `server/data` 目录：

- **上传的文件**: 进入 `server/data/uploads` 目录，您会看到以 `UUID` 命名的 `.png` 和 `.webm` 文件，这些就是您刚才上传的原始涂鸦和录音。
- **TTS 输出文件**: 进入 `server/data/outputs` 目录，您会看到 `{story_id}_narration.mp3` 这样的文件名，这些是通过 `edge-tts` 真实生成的中文语音。
- **最终视频文件**: 进入 `server/data/outputs` 目录，您会看到 `{story_id}_story.mp4` 这样的文件名，这些是通过 FFmpeg 真实合成的最终成片。
- **数据库记录**: 后端使用 SQLite 数据库，文件位于 `server/data/magic_story.db`。您可以使用任何 SQLite 客户端（如 DB Browser for SQLite）打开它，查看 `stories` 表和 `render_costs` 表的生成记录和模拟花费。
- **图像服务配置**: 页面中保存的 Comfy Cloud / 本地 ComfyUI 配置会落到 `server/data/settings/comfy_config.json`，便于后续接入真实工作流时直接读取。

## 6. 当前真实接入与 Mock 边界

当前版本的链路状态如下：

- **已真实接入**
  - `ASR`: 使用 `faster-whisper`
  - `LLM 路由`: 使用可切换 Provider 的本地 / 兼容式模型接口
  - `TTS`: 使用 `edge-tts`
  - `FFmpeg 最终合成`: 使用本地 `ffmpeg` 将静态图与旁白音频合成为 MP4
  - 默认 LLM 模式：`.env` 中配置的 `ollama` 或 `openai_compatible`
  - 默认 ASR 模型：`.env` 中配置的 `ASR_MODEL_SIZE`
  - 默认中文音色：`zh-CN-XiaoxiaoNeural`
  - 输出格式：MP3 + MP4

- **仍为 Mock**
  - `ComfyUI / Comfy Cloud 图片生成`
  - `视频生成`

这意味着当前项目已经具备：

- 真实上传涂鸦与录音
- 真实异步任务流转
- 真实本地 ASR 转写
- 真实本地 / 兼容式 LLM 文本润色与路由决策
- 真实中文 TTS 生成与前端试听
- 真实 MP4 成片合成与前端播放
- 图像服务配置的前后端打通

但尚未真正调用 ComfyUI 或 Comfy Cloud 执行图片重绘工作流。

## 7. LLM 与 ASR 配置说明

后端当前支持以下 LLM 配置模式：

- `LLM_PROVIDER=mock`
  - 用于纯前后端流程联调
- `LLM_PROVIDER=ollama`
  - 适合本机已有 Ollama 的场景
  - 建议 `LLM_BASE_URL=http://host.docker.internal:11434/v1`
- `LLM_PROVIDER=openai_compatible`
  - 适合接入任意兼容 OpenAI Chat Completions 的本地模型网关

`ASR` 当前固定为真实本地方案：

- `ASR_PROVIDER=faster_whisper`
- 模型由 `ASR_MODEL_SIZE` 控制
- 设备由 `ASR_DEVICE` 控制
- 精度由 `ASR_COMPUTE_TYPE` 控制

注意事项：

- 如果使用 Docker 运行后端，而 LLM 跑在宿主机上，请确保容器能访问 `host.docker.internal`
- 首次转写时 `faster-whisper` 可能会下载模型，耗时取决于网络和模型大小
- 如果你的机器只有 CPU，建议从 `small + int8` 开始

## 8. Comfy Cloud / 本地 ComfyUI 配置说明

页面顶部的“图像服务配置”面板支持两种模式：

- **Comfy Cloud**
  - 适合后续接入官方云端工作流 API
  - 当前可填写：`Base URL`、`API Key`、`Workflow API 路径`、`Workflow ID`
  - 点击“测试连接”时会先做参数完整性校验

- **本地 ComfyUI**
  - 适合本机或局域网已有 ComfyUI 服务的场景
  - 当前可填写：`本地服务地址`、`Client ID`
  - 点击“测试连接”会请求 `<local_endpoint>/system_stats` 做基础连通性测试

当前这些配置已经通过后端接口持久化：

- `GET /api/settings/comfy`: 获取当前配置
- `PUT /api/settings/comfy`: 保存配置
- `POST /api/settings/comfy/test`: 测试配置
- `GET /api/settings/runtime`: 查看当前后端生效的 `.env` 模型配置摘要

## 9. 常见问题排查

- **Q: 前端提示“上传失败”？**
  A: 请检查 Docker 容器是否正常运行（`docker ps`），并确保后端服务运行在 `8000` 端口。Vite 默认将 `/api` 请求代理到 `http://127.0.0.1:8000`。
- **Q: 无法获取麦克风权限？**
  A: 如果您不是在 `localhost` 或 `127.0.0.1` 访问，浏览器可能会因为安全策略 (非 HTTPS 环境) 拒绝授予麦克风权限。请确保在本地测试时使用 `localhost` 访问。
- **Q: 进度条一直卡住不动？**
  A: 请检查 Celery Worker 是否正常启动。可以通过 `docker-compose logs -f celery_worker` 查看后台异步任务的执行日志。
- **Q: ASR 阶段失败了？**
  A: 请先确认容器里已安装 `faster-whisper`，并查看 Celery Worker 日志是否在首次运行时下载模型失败；如果是 CPU 环境，建议优先使用 `ASR_MODEL_SIZE=small` 和 `ASR_COMPUTE_TYPE=int8`。
- **Q: LLM 路由阶段失败了？**
  A: 请检查 `.env` 里的 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL` 是否正确；如果后端运行在 Docker 里而模型跑在宿主机上，通常应使用 `host.docker.internal` 而不是 `127.0.0.1`。
- **Q: 结果页没有出现 TTS 播放器？**
  A: 请检查 Celery Worker 日志里 `tts` 阶段是否报错，并确认容器内安装了 `edge-tts` 依赖。
- **Q: FFmpeg 阶段失败了？**
  A: 请先确认后端镜像中的 `ffmpeg` 可执行文件可用，并查看 Celery Worker 日志里是否提示输入图片、TTS 音频缺失或编码失败。
- **Q: 本地 ComfyUI 测试连接失败？**
  A: 请确认本地 ComfyUI 服务已经启动，并且 `system_stats` 接口可从当前浏览器访问的后端环境连通。

---
完成以上步骤后，即代表整个 POC Demo 的前后端基础骨架和交互流程验证通过。当前已经具备真实的本地 ASR、本地 / 兼容式 LLM、Edge-TTS 和 FFmpeg 合成能力；下一步即可继续在 `server/app/services` 中逐步接入真实的 ComfyUI / Comfy Cloud 和视频生成接口。
