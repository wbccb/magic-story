<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getStroke } from 'perfect-freehand'

// 颜色和粗细选项
const colors = ['#000000', '#FF0000', '#00FF00', '#0000FF', '#FFA500']
const sizes = [4, 8, 16]

const currentColor = ref(colors[0])
const currentSize = ref(sizes[1])
const isEraser = ref(false)

const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null

// 笔画数据
// 用途: 存储用户的触控点数据，供 perfect-freehand 渲染平滑曲线
let points: number[][] = []
let strokes: { color: string; size: number; points: number[][] }[] = []
let isDrawing = false

onMounted(() => {
  if (canvasRef.value) {
    // 设置画布分辨率
    canvasRef.value.width = 600
    canvasRef.value.height = 400
    ctx = canvasRef.value.getContext('2d')
    if (ctx) {
      ctx.fillStyle = '#FFFFFF'
      ctx.fillRect(0, 0, 600, 400)
    }
  }
})

// 开始画线
const handlePointerDown = (e: PointerEvent) => {
  isDrawing = true
  const rect = canvasRef.value!.getBoundingClientRect()
  points = [[e.clientX - rect.left, e.clientY - rect.top, e.pressure || 0.5]]
  canvasRef.value?.setPointerCapture(e.pointerId)
}

// 移动画线
const handlePointerMove = (e: PointerEvent) => {
  if (!isDrawing) return
  const rect = canvasRef.value!.getBoundingClientRect()
  points.push([e.clientX - rect.left, e.clientY - rect.top, e.pressure || 0.5])
  render()
}

// 结束画线
const handlePointerUp = () => {
  isDrawing = false
  if (points.length > 0) {
    strokes.push({
      color: isEraser.value ? '#FFFFFF' : currentColor.value,
      size: currentSize.value,
      points: [...points]
    })
  }
  points = []
}

// 绘制 svg path
function getSvgPathFromStroke(stroke: number[][]) {
  if (!stroke.length) return ''
  const d = stroke.reduce(
    (acc, [x0, y0], i, arr) => {
      const [x1, y1] = arr[(i + 1) % arr.length]
      acc.push(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2)
      return acc
    },
    ['M', ...stroke[0], 'Q']
  )
  d.push('Z')
  return d.join(' ')
}

// 渲染到 Canvas
// 用途: 使用 perfect-freehand 将触控点转化为平滑多边形并绘制
const render = () => {
  if (!ctx || !canvasRef.value) return
  ctx.fillStyle = '#FFFFFF'
  ctx.fillRect(0, 0, 600, 400)

  // 绘制已保存的笔画
  for (const stroke of strokes) {
    const outline = getStroke(stroke.points, { size: stroke.size, thinning: 0.5, smoothing: 0.5, streamline: 0.5 })
    const pathData = getSvgPathFromStroke(outline)
    const p = new Path2D(pathData)
    ctx.fillStyle = stroke.color
    ctx.fill(p)
  }

  // 绘制当前的笔画
  if (points.length > 0) {
    const outline = getStroke(points, { size: currentSize.value, thinning: 0.5, smoothing: 0.5, streamline: 0.5 })
    const pathData = getSvgPathFromStroke(outline)
    const p = new Path2D(pathData)
    ctx.fillStyle = isEraser.value ? '#FFFFFF' : currentColor.value
    ctx.fill(p)
  }
}

// 清空画布
// 用途: 重置所有笔画并恢复空白画布
const clearCanvas = () => {
  strokes = []
  points = []
  isDrawing = false
  render()
}

// 撤销一步
const undo = () => {
  strokes.pop()
  render()
}

// 暴露给父组件的方法
// 用途: 将Canvas内容导出为Blob以便上传
defineExpose({
  getCanvasBlob: (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (canvasRef.value && strokes.length > 0) {
        canvasRef.value.toBlob((blob) => resolve(blob), 'image/png')
      } else {
        resolve(null)
      }
    })
  },
  clearCanvas
})
</script>

<template>
  <div class="drawing-container">
    <div class="toolbar">
      <div class="colors">
        <button 
          v-for="c in colors" :key="c" 
          :style="{ backgroundColor: c }" 
          :class="{ active: currentColor === c && !isEraser }"
          @click="currentColor = c; isEraser = false"
        ></button>
      </div>
      <div class="sizes">
        <button 
          v-for="s in sizes" :key="s" 
          :class="{ active: currentSize === s }"
          @click="currentSize = s"
        >{{ s }}px</button>
      </div>
      <button :class="{ active: isEraser }" @click="isEraser = true">橡皮擦</button>
      <button @click="undo">撤销</button>
      <button @click="clearCanvas">清空</button>
    </div>
    <canvas 
      ref="canvasRef" 
      class="canvas"
      @pointerdown="handlePointerDown"
      @pointermove="handlePointerMove"
      @pointerup="handlePointerUp"
      @pointerleave="handlePointerUp"
    ></canvas>
  </div>
</template>

<style scoped>
.drawing-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.toolbar {
  display: flex;
  gap: 15px;
  align-items: center;
  background: #f5f5f5;
  padding: 10px;
  border-radius: 8px;
}
.colors button {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
}
.colors button.active { border-color: #000; transform: scale(1.1); }
.sizes button, .toolbar > button {
  padding: 4px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}
.sizes button.active, .toolbar > button.active { background: #e0e0e0; font-weight: bold; }
.canvas {
  border: 2px solid #ccc;
  border-radius: 8px;
  touch-action: none; /* 防止移动端滚动 */
  cursor: crosshair;
}
</style>
