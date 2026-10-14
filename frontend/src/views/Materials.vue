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
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="library">资料库</el-radio-button>
          <el-radio-button value="list">列表</el-radio-button>
          <el-radio-button value="collection">收藏 · 错题本</el-radio-button>
        </el-radio-group>
        <el-select v-model="filter.exam_id" placeholder="按科目筛选" clearable @change="load">
          <el-option v-for="e in exams" :key="e.id" :label="e.subject" :value="e.id" />
        </el-select>
        <el-select v-model="filter.source_type" placeholder="按来源筛选" clearable @change="load">
          <el-option v-for="s in sourceTypes" :key="s" :label="s" :value="s" />
        </el-select>
        <el-input
          v-model="filter.tag"
          placeholder="按标签筛选"
          clearable
          style="width: 140px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-date-picker
          v-model="filter.dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="上传起始日"
          end-placeholder="截止日"
          style="width: 260px"
          @change="load"
        />
        <el-select v-model="filter.sort" style="width: 150px" @change="load">
          <el-option label="上传时间（新→旧）" value="date_desc" />
          <el-option label="上传时间（旧→新）" value="date_asc" />
          <el-option label="按标题" value="title" />
          <el-option label="按来源类型" value="source_type" />
          <el-option label="按科目" value="exam" />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="搜索标题 / 正文全文"
          clearable
          style="width: 220px"
          @keyup.enter="load"
          @clear="load"
        >
          <template #append>
            <el-button @click="load"><el-icon><Search /></el-icon></el-button>
          </template>
        </el-input>
        <el-button type="primary" plain :disabled="!selectedIds.length" @click="openMerge">
          合并导出{{ selectedIds.length ? `（${selectedIds.length}）` : '' }}
        </el-button>
      </div>

      <!-- 资料库视图：同科目的资料聚合归档（用例 3.3） -->
      <div v-if="viewMode === 'library'" v-loading="loading" class="library">
        <el-empty v-if="!groupedMaterials.length" :description="emptyText" />
        <el-collapse v-else>
          <el-collapse-item v-for="g in groupedMaterials" :key="g.key" :name="g.key">
            <template #title>
              <span class="group-title">{{ g.name }}</span>
              <el-tag size="small" effect="plain" class="group-count">{{ g.items.length }} 份</el-tag>
            </template>
            <div v-for="row in g.items" :key="row.id" class="lib-row">
              <el-checkbox
                :model-value="selectedIds.includes(row.id)"
                class="lib-check"
                @change="(v) => onSelectRow(row.id, v)"
              />
              <div class="lib-main">
                <div class="lib-line">
                  <b class="lib-title">{{ row.title }}</b>
                  <el-tag :type="sourceTagType(row.source_type)" effect="plain" size="small">
                    {{ row.source_type }}
                  </el-tag>
                  <el-tag size="small" type="info">{{ row.file_type.toUpperCase() }}</el-tag>
                  <el-tag size="small" :type="row.parse_status === 'done' ? 'success' : 'danger'">
                    {{ row.parse_status === 'done' ? '解析成功' : '解析失败' }}
                  </el-tag>
                  <span class="lib-desc">{{ row.description || '' }}</span>
                </div>
                <div v-if="row.snippet" class="snippet">{{ row.snippet }}</div>
              </div>
              <div class="lib-ops">
                <el-button link type="primary" @click="onPreview(row)">预览</el-button>
                <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
                <el-button
                  link
                  :type="favMaterialIds.has(row.id) ? 'warning' : 'info'"
                  title="收藏 / 取消收藏"
                  @click="onToggleFavorite(row)"
                >
                  <el-icon><StarFilled v-if="favMaterialIds.has(row.id)" /><Star v-else /></el-icon>
                </el-button>
                <el-button link type="danger" @click="onDelete(row)">删除</el-button>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- 收藏与错题本视图（用例 3.5） -->
      <div v-else-if="viewMode === 'collection'" v-loading="loading" class="library">
        <el-empty v-if="!collections.length" description="收藏和错题本还是空的" />
        <el-collapse v-else v-model="collectionOpen">
          <el-collapse-item name="fav">
            <template #title>
              <span class="group-title">收藏的资料</span>
              <el-tag size="small" effect="plain" class="group-count">{{ favMaterials.length }} 项</el-tag>
            </template>
            <el-empty
              v-if="!favMaterials.length"
              description="还没有收藏资料，可在列表里点星标"
              :image-size="60"
            />
            <div v-for="c in favMaterials" :key="c.id" class="lib-row">
              <div class="lib-main">
                <div class="lib-line">
                  <b class="lib-title">{{ c.title }}</b>
                  <el-tag size="small" type="warning" effect="plain">收藏</el-tag>
                </div>
              </div>
              <div class="lib-ops">
                <el-button link type="danger" @click="onRemoveCollection(c)">移除</el-button>
              </div>
            </div>
          </el-collapse-item>
          <el-collapse-item name="wrong">
            <template #title>
              <span class="group-title">错题本</span>
              <el-tag size="small" effect="plain" class="group-count">{{ wrongQuestions.length }} 题</el-tag>
            </template>
            <el-empty
              v-if="!wrongQuestions.length"
              description="还没有错题（自测答错的题会自动进来）"
              :image-size="60"
            />
            <div v-for="c in wrongQuestions" :key="c.id" class="lib-row">
              <div class="lib-main">
                <div class="lib-line">
                  <b class="lib-title">{{ c.title }}</b>
                  <el-tag size="small" :type="c.source === 'quiz' ? 'danger' : 'info'" effect="plain">
                    {{ c.source === 'quiz' ? '自测答错' : '手动收藏' }}
                  </el-tag>
                </div>
              </div>
              <div class="lib-ops">
                <el-button link type="danger" @click="onRemoveCollection(c)">移除</el-button>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- 列表视图 -->
      <el-table
        v-else
        :data="materials"
        v-loading="loading"
        :empty-text="emptyText"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column prop="title" label="标题" min-width="220">
          <template #default="{ row }">
            <b>{{ row.title }}</b>
            <div v-if="row.snippet" class="snippet">{{ row.snippet }}</div>
          </template>
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
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onPreview(row)">预览</el-button>
            <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
            <el-button
              link
              :type="favMaterialIds.has(row.id) ? 'warning' : 'info'"
              title="收藏 / 取消收藏"
              @click="onToggleFavorite(row)"
            >
              <el-icon><StarFilled v-if="favMaterialIds.has(row.id)" /><Star v-else /></el-icon>
            </el-button>
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

    <el-dialog v-model="editVisible" title="编辑资料" width="520px">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" placeholder="资料标题" />
        </el-form-item>
        <el-form-item label="所属科目">
          <el-select v-model="editForm.exam_id" placeholder="未归类" clearable style="width: 100%">
            <el-option v-for="e in exams" :key="e.id" :label="e.subject" :value="e.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源类型">
          <el-select v-model="editForm.source_type" style="width: 100%">
            <el-option v-for="s in sourceTypes" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="editForm.tags" placeholder="多个标签用逗号分隔（选填）" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="onEditSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="mergeVisible" title="合并导出复习笔记" width="680px">
      <el-form label-width="80px">
        <el-form-item label="笔记标题">
          <el-input v-model="mergeTitle" placeholder="复习笔记" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="mergeWarnings.length"
        type="warning"
        :closable="false"
        style="margin-bottom: 12px"
      >
        <div v-for="(w, i) in mergeWarnings" :key="i">{{ w }}</div>
      </el-alert>
      <div class="preview-box" v-loading="merging">
        <pre>{{ mergePreview || '（合并中…）' }}</pre>
      </div>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button :loading="merging" @click="exportAs('md')">下载 Markdown</el-button>
        <el-button type="primary" :loading="merging" @click="exportAs('pdf')">导出 PDF</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { collectionApi, examApi, materialApi } from '../api'
import { USE_MOCK } from '../mock/dashboard'
import { mockExams, mockMaterials } from '../mock/pages'

const sourceTypes = ['历年题', '老师重点', '平时作业', '课堂笔记', '教材章节', '实验报告', '练习题', '其他']

const exams = ref([])
const materials = ref([])
const loading = ref(false)
const file = ref(null)
const uploading = ref(false)
const viewMode = ref('library') // library=按科目归档成资料库，list=平铺列表

const uploadForm = reactive({ title: '', exam_id: null, source_type: '其他', description: '' })
const filter = reactive({
  exam_id: null,
  source_type: '',
  tag: '',
  keyword: '',
  dateRange: [],
  sort: 'date_desc',
})

const editVisible = ref(false)
const editSaving = ref(false)
const editForm = reactive({ id: null, title: '', exam_id: null, source_type: '其他', description: '', tags: '' })

// 合并导出复习笔记（用例 3.6）
const selectedIds = ref([])
const mergeVisible = ref(false)
const mergeTitle = ref('复习笔记')
const mergePreview = ref('')
const mergeWarnings = ref([])
const merging = ref(false)
// 切视图时清空勾选，避免两种视图的选择状态对不上
watch(viewMode, () => {
  selectedIds.value = []
})

// 收藏与错题本（用例 3.5）
const collections = ref([])
const collectionOpen = ref(['fav', 'wrong'])
// 静态演示模式（无后端）下用本地数组假装收藏本，真实模式走后端
const mockCollections = ref([
  { id: 1, item_type: 'material', material_id: 2, title: '极限与连续 老师标注重点', content: '', source: 'manual', created_at: '2026-10-12T10:00:00' },
  { id: 2, item_type: 'question', material_id: null, title: '极限的四则运算与等价无穷小替换', content: '', source: 'quiz', created_at: '2026-10-13T20:00:00' },
])

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewTitle = ref('')
const previewText = ref('')

const examName = (id) => exams.value.find((e) => e.id === id)?.subject || '未归类'
const sourceTagType = (s) =>
  ({ 历年题: 'danger', 老师重点: 'warning', 平时作业: 'info', 课堂笔记: 'success', 教材章节: 'info', 实验报告: 'info', 练习题: 'info', 其他: 'info' }[s] || 'info')

// 综合资料库：把资料按科目聚合（用例 3.3），未归类的排在最后
const groupedMaterials = computed(() => {
  const byExam = new Map()
  const ungrouped = []
  for (const m of materials.value) {
    const exam = exams.value.find((e) => e.id === m.exam_id)
    if (!exam) {
      ungrouped.push(m)
      continue
    }
    if (!byExam.has(exam.id)) byExam.set(exam.id, { key: String(exam.id), name: exam.subject, items: [] })
    byExam.get(exam.id).items.push(m)
  }
  const groups = exams.value.map((e) => byExam.get(e.id)).filter(Boolean)
  if (ungrouped.length) groups.push({ key: 'none', name: '未归类', items: ungrouped })
  return groups
})

// 有没有加筛选条件：决定空列表的提示文案（用例 3.4 备选流 A1）
const hasFilter = computed(() =>
  Boolean(
    filter.exam_id ||
      filter.source_type ||
      filter.tag ||
      filter.keyword ||
      (filter.dateRange && filter.dateRange.length),
  ),
)
const emptyText = computed(() => (hasFilter.value ? '没有匹配的资料' : '还没有上传资料'))

// 已收藏的资料 id 集合：给列表/资料库里的星标显示状态
const favMaterialIds = computed(() => {
  const ids = new Set()
  for (const item of collections.value) {
    if (item.item_type === 'material' && item.material_id) ids.add(item.material_id)
  }
  return ids
})
const favMaterials = computed(() => collections.value.filter((c) => c.item_type === 'material'))
const wrongQuestions = computed(() => collections.value.filter((c) => c.item_type === 'question'))

const loadExams = async () => {
  if (USE_MOCK) {
    exams.value = mockExams
    return
  }
  exams.value = await examApi.list()
}
// mock 模式下本地筛选/排序演示数据（演示数据没有解析正文，故全文命中只在真实后端生效）
const mockFiltered = () => {
  const [from, to] = filter.dateRange || []
  const list = mockMaterials.filter((m) => {
    if (filter.exam_id && m.exam_id !== filter.exam_id) return false
    if (filter.source_type && m.source_type !== filter.source_type) return false
    if (filter.tag && !(m.tags || '').includes(filter.tag)) return false
    if (filter.keyword) {
      const k = filter.keyword
      const hit =
        m.title.includes(k) || (m.description || '').includes(k) || (m.tags || '').includes(k)
      if (!hit) return false
    }
    if (from && to) {
      const d = (m.created_at || '').slice(0, 10)
      if (d && (d < from || d > to)) return false
    }
    return true
  })
  const byKey = { title: 'title', source_type: 'source_type', exam: 'exam_id' }
  const key = byKey[filter.sort]
  if (key) list.sort((a, b) => String(a[key] ?? '').localeCompare(String(b[key] ?? ''), 'zh'))
  else if (filter.sort === 'date_asc') list.reverse()
  return list
}

const load = async () => {
  loading.value = true
  try {
    if (USE_MOCK) {
      materials.value = mockFiltered()
    } else {
      const [from, to] = filter.dateRange || []
      materials.value = await materialApi.list({
        exam_id: filter.exam_id || undefined,
        source_type: filter.source_type || undefined,
        tag: filter.tag || undefined,
        keyword: filter.keyword || undefined,
        date_from: from || undefined,
        date_to: to || undefined,
        sort: filter.sort,
      })
    }
  } finally {
    loading.value = false
  }
}

const loadCollections = async () => {
  if (USE_MOCK) {
    collections.value = mockCollections.value
    return
  }
  collections.value = await collectionApi.list()
}

const onFileChange = (uploadFile) => {
  file.value = uploadFile.raw
  if (!uploadForm.title) uploadForm.title = uploadFile.name.replace(/\.[^.]+$/, '')
}

const onUpload = async () => {
  uploading.value = true
  try {
    if (USE_MOCK) {
      // mock 模式下模拟解析成功并加入本地列表
      await new Promise((r) => setTimeout(r, 800))
      mockMaterials.unshift({
        id: Date.now(),
        title: uploadForm.title || file.value.name,
        exam_id: uploadForm.exam_id,
        source_type: uploadForm.source_type,
        file_type: (file.value.name.split('.').pop() || 'txt').toLowerCase(),
        parse_status: 'done',
        description: uploadForm.description,
        text_preview: '（静态演示文本）上传文件在真实后端下会解析出文本，此处为预览占位。',
      })
    } else {
      const formData = new FormData()
      formData.append('file', file.value)
      formData.append('title', uploadForm.title || file.value.name)
      if (uploadForm.exam_id) formData.append('exam_id', uploadForm.exam_id)
      formData.append('source_type', uploadForm.source_type)
      formData.append('description', uploadForm.description)
      await materialApi.upload(formData)
    }
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
  if (USE_MOCK) {
    previewText.value = row.text_preview || ''
    return
  }
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
  if (USE_MOCK) {
    const i = mockMaterials.findIndex((m) => m.id === row.id)
    if (i >= 0) mockMaterials.splice(i, 1)
    ElMessage.success('已删除')
    load()
    return
  }
  await materialApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

const onEdit = (row) => {
  editForm.id = row.id
  editForm.title = row.title
  editForm.exam_id = row.exam_id ?? null
  editForm.source_type = row.source_type
  editForm.description = row.description || ''
  editForm.tags = row.tags || ''
  editVisible.value = true
}

// 保存编辑：改标题/说明/标签，改科目即为「移动分类」（用例 3.3）
const onEditSave = async () => {
  const title = editForm.title.trim()
  if (!title) {
    ElMessage.warning('标题不能为空')
    return
  }
  editSaving.value = true
  try {
    const payload = {
      title,
      exam_id: editForm.exam_id ?? null,
      source_type: editForm.source_type,
      description: editForm.description,
      tags: editForm.tags,
    }
    if (USE_MOCK) {
      const target = mockMaterials.find((m) => m.id === editForm.id)
      if (target) Object.assign(target, payload)
    } else {
      await materialApi.update(editForm.id, payload)
    }
    ElMessage.success('已保存')
    editVisible.value = false
    load()
  } finally {
    editSaving.value = false
  }
}

// 星标：收藏 / 取消收藏一份资料（用例 3.5）
const onToggleFavorite = async (row) => {
  const existing = collections.value.find(
    (c) => c.item_type === 'material' && c.material_id === row.id,
  )
  if (USE_MOCK) {
    if (existing) {
      mockCollections.value = mockCollections.value.filter((c) => c.id !== existing.id)
      ElMessage.success('已取消收藏')
    } else {
      mockCollections.value = [
        {
          id: Date.now(),
          item_type: 'material',
          material_id: row.id,
          title: row.title,
          content: '',
          source: 'manual',
          created_at: new Date().toISOString(),
        },
        ...mockCollections.value,
      ]
      ElMessage.success('已加入收藏')
    }
  } else if (existing) {
    await collectionApi.remove(existing.id)
    ElMessage.success('已取消收藏')
  } else {
    await collectionApi.add({ item_type: 'material', material_id: row.id })
    ElMessage.success('已加入收藏')
  }
  loadCollections()
}

// 从收藏本里移除（收藏的资料或错题）
const onRemoveCollection = async (item) => {
  if (USE_MOCK) {
    mockCollections.value = mockCollections.value.filter((c) => c.id !== item.id)
  } else {
    await collectionApi.remove(item.id)
  }
  ElMessage.success('已移除')
  loadCollections()
}

// ---------------- 合并导出复习笔记（用例 3.6） ----------------

const onSelectRow = (id, checked) => {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id]
  } else {
    selectedIds.value = selectedIds.value.filter((x) => x !== id)
  }
}
const onSelectionChange = (rows) => {
  selectedIds.value = rows.map((r) => r.id)
}

const buildMockMarkdown = (chosen, title) => {
  const lines = [`# ${title}`, '', `> 由「期末周别慌」合并生成 · 共 ${chosen.length} 份资料`, '']
  chosen.forEach((m, i) => {
    lines.push(`## ${i + 1}. ${m.title}`, '', `- 来源类型：${m.source_type}`, '')
    lines.push((m.text_preview || '（静态演示文本，真实后端下为解析出的正文）').trim())
    lines.push('', '---')
  })
  return {
    title,
    markdown: lines.join('\n') + '\n',
    material_count: chosen.length,
    total_chars: 0,
    warnings: [],
  }
}

const requestMerge = async () => {
  if (USE_MOCK) {
    const chosen = selectedIds.value
      .map((id) => materials.value.find((m) => m.id === id))
      .filter(Boolean)
    return buildMockMarkdown(chosen, mergeTitle.value.trim() || '复习笔记')
  }
  return await materialApi.merge({
    material_ids: selectedIds.value,
    title: mergeTitle.value.trim(),
  })
}

const openMerge = async () => {
  mergeTitle.value = '复习笔记'
  mergePreview.value = ''
  mergeWarnings.value = []
  mergeVisible.value = true
  merging.value = true
  try {
    const res = await requestMerge()
    mergePreview.value = res.markdown
    mergeWarnings.value = res.warnings || []
  } finally {
    merging.value = false
  }
}

// 把生成的 Markdown 转成 HTML（只覆盖本项目自己生成的那几个语法：# / ## / - / > / --- / 空行）
const mdToHtml = (md) => {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return md
    .split('\n')
    .map((line) => {
      if (line.startsWith('# ')) return `<h1>${esc(line.slice(2))}</h1>`
      if (line.startsWith('## ')) return `<h2>${esc(line.slice(3))}</h2>`
      if (line.startsWith('- ')) return `<li>${esc(line.slice(2))}</li>`
      if (line.startsWith('> ')) return `<p class="quote">${esc(line.slice(2))}</p>`
      if (line.trim() === '---') return '<hr />'
      if (!line.trim()) return ''
      return `<p>${esc(line)}</p>`
    })
    .join('\n')
}

const downloadMarkdown = (title, markdown) => {
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${title}.md`
  link.click()
  URL.revokeObjectURL(url)
}

// 导出 PDF：借浏览器「另存为 PDF」打印，避免在后端引入 PDF 依赖和字体问题
const printPdf = (title, markdown) => {
  const win = window.open('', '_blank')
  if (!win) {
    ElMessage.warning('浏览器拦截了新窗口，允许弹出窗口后重试')
    return
  }
  const style =
    'body{font-family:"Noto Serif SC","Songti SC",serif;line-height:1.9;color:#0c1614;' +
    'max-width:720px;margin:40px auto;padding:0 24px}' +
    'h1{font-size:26px;border-bottom:2px solid #0c1614;padding-bottom:12px}' +
    'h2{font-size:19px;margin-top:32px}' +
    '.quote{color:#5b6b66;border-left:3px solid #e66348;padding-left:10px}' +
    'li{margin:4px 0}p{white-space:pre-wrap;word-break:break-word}' +
    'hr{border:none;border-top:1px dashed #c9c3b4;margin:24px 0}'
  win.document.write(
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" />' +
      `<title>${title}</title><style>${style}</style></head><body>` +
      mdToHtml(markdown) +
      '</body></html>',
  )
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 300)
}

const exportAs = async (format) => {
  if (!selectedIds.value.length) return
  merging.value = true
  try {
    const res = await requestMerge()
    if (format === 'md') {
      downloadMarkdown(res.title, res.markdown)
      ElMessage.success('已下载 Markdown 复习笔记')
    } else {
      printPdf(res.title, res.markdown)
      ElMessage.success('已打开打印窗口，选「另存为 PDF」即可')
    }
    mergeVisible.value = false
  } finally {
    merging.value = false
  }
}

onMounted(() => {
  loadExams()
  load()
  loadCollections()
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
  flex-wrap: wrap;
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
.library {
  min-height: 120px;
}
.group-title {
  font-weight: 600;
  color: var(--text-hi);
}
.group-count {
  margin-left: 8px;
}
.lib-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--line);
}
.lib-row:last-child {
  border-bottom: none;
}
.lib-check {
  flex: none;
}
.lib-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.lib-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.snippet {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-mid);
}
.lib-title {
  color: var(--text-hi);
}
.lib-desc {
  color: var(--text-mid);
  font-size: 13px;
}
.lib-ops {
  flex: none;
}
</style>
