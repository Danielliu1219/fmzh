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
        :on-remove="onFileRemove"
        accept=".txt,.pdf,.docx"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到这里，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">
            MVP 支持 TXT / PDF / Word（.docx），单个文件不超过 20MB；上传时会校验格式与文件内容
          </div>
        </template>
      </el-upload>
      <div class="upload-form">
        <el-input v-model="uploadForm.title" placeholder="资料标题（默认取文件名）" />
        <el-select v-model="uploadForm.exam_id" placeholder="所属科目（选填）" clearable>
          <el-option v-for="e in exams" :key="e.id" :label="e.subject" :value="e.id" />
        </el-select>
        <el-select
          v-model="uploadForm.source_type"
          placeholder="来源类型"
          @change="sourceTouched = true"
        >
          <el-option v-for="s in sourceTypes" :key="s" :label="`${s}（${sourceLevelLabel(s)}）`" :value="s" />
        </el-select>
        <el-input v-model="uploadForm.description" placeholder="说明（选填）" />
        <el-button type="primary" :loading="uploading" :disabled="!file" @click="onUpload">
          上传并解析
        </el-button>
      </div>
      <div v-if="suggestingSource" class="source-suggest">正在识别资料来源…</div>
      <div v-else-if="sourceSuggestion" class="source-suggest">
        <span>
          系统建议来源：<b>{{ sourceSuggestion.source_type }}</b>
          <el-tag size="small" effect="plain" class="source-conf">
            {{ confidenceText(sourceSuggestion.confidence) }}置信度
          </el-tag>
          <span class="source-reason">{{ sourceSuggestion.reason }}</span>
        </span>
        <el-tag
          v-if="uploadForm.source_type === sourceSuggestion.source_type"
          size="small"
          type="success"
          effect="plain"
        >
          已采用
        </el-tag>
        <el-button v-else link type="primary" size="small" @click="applySuggestion">
          采用建议
        </el-button>
      </div>
      <div class="upload-weight-hint">
        资料权重将按来源「{{ uploadForm.source_type }}」默认
        {{ Math.round(sourceWeight(uploadForm.source_type) * 100) }}%（档位：{{
          sourceLevelLabel(uploadForm.source_type)
        }}），上传后可在编辑里手动调整
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
                  <el-tag size="small" type="warning" effect="plain">
                    权重 {{ Math.round((row.weight ?? 0.5) * 100) }}%（{{
                      row.weight_level ?? weightLevel(row.weight ?? 0.5)
                    }}）
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
                <el-button link type="primary" @click="openMistake(c)">答案与解析</el-button>
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
        <el-table-column label="资料权重" width="170">
          <template #default="{ row }">
            <div class="weight-cell">
              <el-progress
                :percentage="Math.round((row.weight ?? 0.5) * 100)"
                :stroke-width="8"
                :color="weightColor(row.weight ?? 0.5)"
              />
              <span class="weight-hint">{{ weightHint(row) }}</span>
            </div>
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

    <el-dialog v-model="mistakeVisible" :title="mistakeTitle" width="640px" style="max-width: calc(100vw - 32px)">
      <QuizFeedback v-if="mistakeDetail" :item="mistakeDetail" />
    </el-dialog>
    <el-dialog v-model="previewVisible" :title="previewTitle" width="min(760px, 94vw)">
      <div class="preview-box" v-loading="previewLoading">
        <el-alert v-if="previewError" :title="previewError" type="warning" :closable="false" />
        <SourceExcerpt v-else-if="linkedExcerpt" :reference="linkedExcerpt" />
        <pre v-else>{{ previewText || '（无解析文本，可能是解析失败或文件为扫描图片）' }}</pre>
      </div>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑资料" width="520px" :before-close="materialDraft.beforeClose">
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
        <el-form-item label="资料权重">
          <div class="weight-edit">
            <el-slider
              v-model="editForm.weightPercent"
              :min="0"
              :max="100"
              :step="1"
              show-input
              @change="editForm.weightTouched = true"
            />
            <div class="weight-edit-hint">
              <span>
                来源「{{ editForm.source_type }}」默认 {{ editDefaultPercent }}%（档位：{{
                  weightLevel(editForm.weightPercent / 100)
                }}）
              </span>
              <el-button
                link
                type="primary"
                :disabled="editForm.weightPercent === editDefaultPercent"
                @click="resetEditWeight"
              >
                恢复默认
              </el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="editForm.tags" placeholder="多个标签用逗号分隔（选填）" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="editSaving" @click="materialDraft.close">取消</el-button>
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
import { useDialogDraft, usePendingWork, useActionLock, confirmAction } from '../composables/usePendingWork'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { collectionApi, examApi, materialApi } from '../api'
import { USE_MOCK, mockStudySession } from '../mock/dashboard'
import { mockExams, mockMaterials } from '../mock/pages'
import SourceExcerpt from '../components/SourceExcerpt.vue'
import { mockNotebook as mockCollections } from '../mock/quizzes'
import { readMistake } from '../utils/quiz'
import QuizFeedback from '../components/QuizFeedback.vue'

const sourceTypes = ['历年题', '老师重点', '平时作业', '课堂笔记', '教材章节', '实验报告', '练习题', '其他']

const route = useRoute()
// 资料权重默认层级（用例 4.2，与 backend/app/services/material_weight.py 保持一致）
const SOURCE_WEIGHTS = {
  老师重点: 1.0,
  历年题: 0.85,
  练习题: 0.85,
  平时作业: 0.7,
  课堂笔记: 0.7,
  教材章节: 0.55,
  实验报告: 0.55,
  其他: 0.5,
}
const sourceWeight = (sourceType) => SOURCE_WEIGHTS[sourceType] ?? 0.5
// 权重档位（用例 3.2，与 backend/app/services/material_weight.py 一致）
const weightLevel = (w) => (w >= 0.85 ? '高' : w >= 0.7 ? '中' : '低')
const sourceLevelLabel = (sourceType) => weightLevel(sourceWeight(sourceType))
const confidenceText = (c) => ({ high: '高', medium: '中', low: '低' })[c] || '低'
const weightColor = (w) => (w >= 0.85 ? '#e05d5d' : w >= 0.7 ? '#e6a23c' : '#3fa97a')
const weightHint = (row) => {
  const weight = row.weight ?? 0.5
  const isDefault = Math.abs(weight - (row.default_weight ?? sourceWeight(row.source_type))) < 1e-6
  const level = row.weight_level ?? weightLevel(weight)
  return `${isDefault ? '来源默认' : '已手动调整'} · ${level}`
}

// 静态演示模式下的来源建议（真实模式走后端解析正文，更准确）
const MOCK_SOURCE_RULES = [
  ['实验报告', ['实验报告', '实验', '报告']],
  ['老师重点', ['老师重点', '重点', '考点', '提纲', '讲义', '标注']],
  ['历年题', ['历年', '真题', '考题', '试卷', '试题', '期末考']],
  ['课堂笔记', ['课堂笔记', '笔记', '听课', '课堂记录']],
  ['平时作业', ['平时作业', '作业', '课后作业', 'homework']],
  ['教材章节', ['教材', '课本', '章节', '课件', 'ppt']],
  ['练习题', ['练习题', '练习', '习题', '题库', '刷题', 'exercise']],
]
const suggestSourceLocal = (filename) => {
  const name = (filename || '').toLowerCase()
  for (const [type, keywords] of MOCK_SOURCE_RULES) {
    const hit = keywords.find((k) => name.includes(k.toLowerCase()))
    if (hit) {
      return { source_type: type, confidence: 'medium', reason: `文件名含「${hit}」` }
    }
  }
  return {
    source_type: '其他',
    confidence: 'low',
    reason: '未识别到明显的来源特征，默认归为「其他」，可手动选择',
  }
}

const exams = ref([])
const materials = ref([])
const loading = ref(false)
const file = ref(null)
const uploading = ref(false)
const viewMode = ref(route.query.view === 'collection' ? 'collection' : 'library')
// 系统辅助识别来源建议（用例 3.2）
const sourceSuggestion = ref(null)
const suggestingSource = ref(false)
const sourceTouched = ref(false) // 学生是否手动改过来源类型

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
const editForm = reactive({
  id: null,
  title: '',
  exam_id: null,
  source_type: '其他',
  description: '',
  tags: '',
  weightPercent: 50, // 资料权重（用例 4.2），界面用百分比
  weightTouched: false, // 学生是否手动拖动过滑块
})
const editDefaultPercent = computed(() => Math.round(sourceWeight(editForm.source_type) * 100))
const resetEditWeight = () => {
  editForm.weightPercent = editDefaultPercent.value
  editForm.weightTouched = false
}

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
const mistakeVisible = ref(false)
const mistakeTitle = ref('')
const mistakeDetail = ref(null)
const openMistake = item => {
  mistakeTitle.value = item.title
  mistakeDetail.value = readMistake(item.content)
  mistakeVisible.value = true
}
watch(() => route.query.view, value => { if(value === 'collection') viewMode.value = 'collection' })

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewTitle = ref('')
const previewText = ref('')
const previewError = ref('')
const linkedExcerpt = ref(null)
let previewRequest = 0

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
    exams.value = structuredClone(mockStudySession.exams)
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

// 选文件后请求来源建议；失败不影响正常上传
const requestSourceSuggestion = async (rawFile) => {
  sourceSuggestion.value = null
  if (!rawFile) return
  suggestingSource.value = true
  try {
    let suggestion
    if (USE_MOCK) {
      suggestion = suggestSourceLocal(rawFile.name)
    } else {
      const formData = new FormData()
      formData.append('file', rawFile)
      suggestion = await materialApi.suggestSource(formData)
    }
    sourceSuggestion.value = suggestion
    // 学生还没手动选过来源时，自动采用系统建议
    if (suggestion && !sourceTouched.value) {
      uploadForm.source_type = suggestion.source_type
    }
  } catch (e) {
    sourceSuggestion.value = null
  } finally {
    suggestingSource.value = false
  }
}

const onFileChange = (uploadFile) => {
  file.value = uploadFile.raw
  if (!uploadForm.title) uploadForm.title = uploadFile.name.replace(/\.[^.]+$/, '')
  requestSourceSuggestion(uploadFile.raw)
}

const onFileRemove = () => {
  file.value = null
  sourceSuggestion.value = null
}

const applySuggestion = () => {
  if (!sourceSuggestion.value) return
  uploadForm.source_type = sourceSuggestion.value.source_type
  sourceTouched.value = false
}

const onUpload = async () => {
  if(uploading.value || !file.value) return
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
        weight: sourceWeight(uploadForm.source_type),
        default_weight: sourceWeight(uploadForm.source_type),
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
    sourceSuggestion.value = null
    sourceTouched.value = false
    load()
  } finally {
    uploading.value = false
  }
}

const onPreview = async (row) => {
  const requestId = ++previewRequest
  previewVisible.value = true
  previewTitle.value = row.title
  previewText.value = ''
  previewError.value = ''
  linkedExcerpt.value = null
  if (USE_MOCK) {
    previewText.value = row.text_preview || ''
    return
  }
  previewLoading.value = true
  try {
    const detail = await materialApi.detail(row.id)
    if (requestId === previewRequest) previewText.value = detail.text_preview || ''
  } finally {
    if (requestId === previewRequest) previewLoading.value = false
  }
}

const openLinkedExcerpt = async () => {
  const id = Number(route.query.material)
  if (!Number.isInteger(id) || id < 1) return
  const requestId = ++previewRequest
  previewVisible.value = true
  previewTitle.value = '引用原文'
  previewText.value = ''
  previewError.value = ''
  linkedExcerpt.value = null
  previewLoading.value = true
  try {
    const start = Number(route.query.start), end = Number(route.query.end)
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) throw new Error('无效位置')
    let reference
    if (USE_MOCK) {
      const row = mockMaterials.find(material => material.id === id && material.exam_id === Number(route.query.exam))
      if (!row || end > (row.text_preview || '').length) throw new Error('演示资料未找到')
      reference = { material_id: row.id, material_title: row.title, source_type: row.source_type, file_type: row.file_type,
        status: 'available', location: '演示解析文本片段', context: row.text_preview, highlight_start: start,
        highlight_end: end, note: '演示原文定位，真实模式会核对资料内容是否变化。' }
    } else {
      reference = await materialApi.excerpt(id, { start, end, content_hash: String(route.query.hash || ''), material_created_at: String(route.query.created_at || '') })
    }
    if (requestId === previewRequest) { linkedExcerpt.value = reference; previewTitle.value = reference.material_title }
  } catch {
    if (requestId === previewRequest) previewError.value = '无法打开这条引用，资料可能已删除或内容变化。请返回分析页重新定位。'
  } finally { if (requestId === previewRequest) previewLoading.value = false }
}
watch(previewVisible, value => { if (!value) { previewRequest++; previewLoading.value = false } })

const onDelete = async (row) => {
  return materialAction.run(async () => {
  await ElMessageBox.confirm(`确定删除「${row.title}」吗？解析文本也会被删除。`, '删除确认', { type: 'warning' })
  if (USE_MOCK) {
    const i = mockMaterials.findIndex((m) => m.id === row.id)
    if (i >= 0) mockMaterials.splice(i, 1)
    ElMessage.success('已删除')
    load()
    return
  }
  const result = await materialApi.remove(row.id)
  if (result.cleanup_pending) ElMessage.warning('资料已删除，文件清理待重试，可由管理员重试清理')
  else ElMessage.success('已删除')
  load()
  })
}

const onEdit = (row) => {
  editForm.id = row.id
  editForm.title = row.title
  editForm.exam_id = row.exam_id ?? null
  editForm.source_type = row.source_type
  editForm.description = row.description || ''
  editForm.tags = row.tags || ''
  const weight = row.weight ?? sourceWeight(row.source_type)
  const defaultWeight = row.default_weight ?? sourceWeight(row.source_type)
  editForm.weightPercent = Math.round(weight * 100)
  editForm.weightTouched = Math.abs(weight - defaultWeight) > 1e-6
  editVisible.value = true
}

// 保存编辑：改标题/说明/标签，改科目即为「移动分类」（用例 3.3）
const onEditSave = async () => {
  if(editSaving.value) return
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
    // 只有学生手动调过权重才传 weight；没动过时后端会按（可能已改的）来源类型恢复默认
    if (editForm.weightTouched) payload.weight = editForm.weightPercent / 100
    if (USE_MOCK) {
      const target = mockMaterials.find((m) => m.id === editForm.id)
      if (target) {
        Object.assign(target, payload)
        if (payload.weight == null) target.weight = sourceWeight(target.source_type)
        target.default_weight = sourceWeight(target.source_type)
      }
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
  return materialAction.run(async () => {
  if(item.item_type === 'question' && !await confirmAction(`确认从错题本移除「${item.title}」？自测历史与成绩保留。`,'移除错题',{confirmButtonText:'移除错题',cancelButtonText:'保留'})) return
  if (USE_MOCK) {
    mockCollections.value = mockCollections.value.filter((c) => c.id !== item.id)
  } else {
    await collectionApi.remove(item.id)
  }
  ElMessage.success('已移除')
  loadCollections()
  })
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

const materialAction = useActionLock('资料或错题操作')
const materialDraft = useDialogDraft(editForm,editVisible,editSaving,'资料信息')
usePendingWork(() => ({busy:[uploading.value && '资料上传',merging.value && '笔记导出'].filter(Boolean),warning:file.value ? '有尚未上传的文件，离开会清除当前文件选择和上传表单。' : ''}))

onMounted(() => {
  const requested = Number(route.query.exam)
  if (requested > 0) { filter.exam_id = requested; uploadForm.exam_id = requested }
  loadExams()
  load()
  loadCollections()
  openLinkedExcerpt()
})
watch(() => [route.query.material, route.query.start, route.query.end, route.query.hash, route.query.created_at], openLinkedExcerpt)
watch(() => route.query.exam, value => {
  filter.exam_id = Number(value) || null
  uploadForm.exam_id = filter.exam_id
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
.weight-cell {
  display: flex;
  flex-direction: column;
}
.weight-hint {
  font-size: 12px;
  color: var(--text-mid);
}
.weight-edit {
  width: 100%;
}
.weight-edit-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-mid);
}
.upload-weight-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-mid);
}
.source-suggest {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--text-hi);
  background: var(--bg-soft, #f7f4ee);
  border-radius: 6px;
}
.source-conf {
  margin: 0 8px;
}
.source-reason {
  color: var(--text-mid);
  font-size: 12px;
}
</style>
