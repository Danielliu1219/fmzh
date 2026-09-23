<template>
  <div>
    <div class="page-head">
      <h2>复习资料</h2>
    </div>

    <el-card shadow="never" class="upload-card">
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        :on-change="onFileChange"
        :on-remove="() => (file = null)"
        accept=".txt,.pdf,.docx"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到这里，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">MVP 支持 TXT / PDF / Word（.docx），单个文件不超过 20MB</div>
        </template>
      </el-upload>
      <div class="upload-form">
        <el-input v-model="uploadForm.title" placeholder="资料标题（默认取文件名）" />
        <el-select v-model="uploadForm.exam_id" placeholder="所属科目（选填）" clearable>
          <el-option v-for="e in exams" :key="e.id" :label="e.subject" :value="e.id" />
        </el-select>
        <el-select v-model="uploadForm.source_type" placeholder="来源类型">
          <el-option v-for="s in sourceTypes" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input v-model="uploadForm.description" placeholder="说明（选填）" />
        <el-button type="primary" :loading="uploading" :disabled="!file" @click="onUpload">
          上传并解析
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="list-card">
      <div class="filters">
        <el-select v-model="filter.exam_id" placeholder="按科目筛选" clearable @change="load">
          <el-option v-for="e in exams" :key="e.id" :label="e.subject" :value="e.id" />
        </el-select>
        <el-select v-model="filter.source_type" placeholder="按来源筛选" clearable @change="load">
          <el-option v-for="s in sourceTypes" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="搜索标题/说明"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        >
          <template #append>
            <el-button @click="load"><el-icon><Search /></el-icon></el-button>
          </template>
        </el-input>
      </div>

      <el-table :data="materials" v-loading="loading" empty-text="还没有上传资料">
        <el-table-column prop="title" label="标题" min-width="180">
          <template #default="{ row }"><b>{{ row.title }}</b></template>
        </el-table-column>
        <el-table-column label="科目" width="120">
          <template #default="{ row }">{{ examName(row.exam_id) }}</template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">
            <el-tag :type="sourceTagType(row.source_type)" effect="plain">{{ row.source_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_type" label="格式" width="80">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.file_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="解析状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.parse_status === 'done' ? 'success' : 'danger'">
              {{ row.parse_status === 'done' ? '解析成功' : '解析失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="140">
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onPreview(row)">预览</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="previewVisible" :title="previewTitle" width="680px">
      <div class="preview-box" v-loading="previewLoading">
        <pre>{{ previewText || '（无解析文本，可能是解析失败或文件为扫描图片）' }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { examApi, materialApi } from '../api'

const sourceTypes = ['历年题', '老师重点', '课堂笔记', '作业', '练习题', '其他']

const exams = ref([])
const materials = ref([])
const loading = ref(false)
const file = ref(null)
const uploading = ref(false)

const uploadForm = reactive({ title: '', exam_id: null, source_type: '其他', description: '' })
const filter = reactive({ exam_id: null, source_type: '', keyword: '' })

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewTitle = ref('')
const previewText = ref('')

const examName = (id) => exams.value.find((e) => e.id === id)?.subject || '未归类'
const sourceTagType = (s) =>
  ({ 历年题: 'danger', 老师重点: 'warning', 课堂笔记: 'success', 作业: 'info', 练习题: 'info', 其他: 'info' }[s] || 'info')

const loadExams = async () => {
  exams.value = await examApi.list()
}
const load = async () => {
  loading.value = true
  try {
    materials.value = await materialApi.list({
      exam_id: filter.exam_id || undefined,
      source_type: filter.source_type || undefined,
      keyword: filter.keyword || undefined,
    })
  } finally {
    loading.value = false
  }
}

const onFileChange = (uploadFile) => {
  file.value = uploadFile.raw
  if (!uploadForm.title) uploadForm.title = uploadFile.name.replace(/\.[^.]+$/, '')
}

const onUpload = async () => {
  const formData = new FormData()
  formData.append('file', file.value)
  formData.append('title', uploadForm.title || file.value.name)
  if (uploadForm.exam_id) formData.append('exam_id', uploadForm.exam_id)
  formData.append('source_type', uploadForm.source_type)
  formData.append('description', uploadForm.description)
  uploading.value = true
  try {
    await materialApi.upload(formData)
    ElMessage.success('上传成功，解析完成')
    file.value = null
    uploadForm.title = ''
    uploadForm.description = ''
    load()
  } finally {
    uploading.value = false
  }
}

const onPreview = async (row) => {
  previewVisible.value = true
  previewTitle.value = row.title
  previewLoading.value = true
  try {
    const detail = await materialApi.detail(row.id)
    previewText.value = detail.text_preview || ''
  } finally {
    previewLoading.value = false
  }
}

const onDelete = async (row) => {
  await ElMessageBox.confirm(`确定删除「${row.title}」吗？解析文本也会被删除。`, '删除确认', { type: 'warning' })
  await materialApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(() => {
  loadExams()
  load()
})
</script>

<style scoped>
.page-head {
  margin-bottom: 16px;
}
.page-head h2 {
  color: var(--text-hi);
}
.upload-card {
  margin-bottom: 16px;
}
.upload-form {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr 1.2fr auto;
  gap: 12px;
  margin-top: 16px;
}
.list-card {
  min-height: 200px;
}
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.filters .el-select {
  width: 160px;
}
.preview-box {
  max-height: 480px;
  overflow: auto;
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px;
}
.preview-box pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  color: var(--text-mid);
}
</style>
