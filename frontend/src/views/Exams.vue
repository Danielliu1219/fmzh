<template>
  <div>
    <div class="page-head">
      <h2>课程管理</h2>
      <span class="head-sub">录入要复习的课程和考试时间，考表和倒计时从这里生成</span>
      <el-button type="primary" @click="openDialog()">
        <el-icon><Plus /></el-icon>&nbsp;添加课程
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="exams" v-loading="loading" empty-text="还没有课程，点右上角添加">
        <el-table-column prop="subject" label="科目" min-width="120">
          <template #default="{ row }">
            <b>{{ row.subject }}</b>
          </template>
        </el-table-column>
        <el-table-column prop="exam_date" label="考试日期" width="120" />
        <el-table-column prop="location" label="地点" min-width="120">
          <template #default="{ row }">{{ row.location || '-' }}</template>
        </el-table-column>
        <el-table-column prop="duration_minutes" label="时长" width="100">
          <template #default="{ row }">{{ row.duration_minutes }} 分钟</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="140">
          <template #default="{ row }">{{ row.note || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑课程' : '添加课程'" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="科目" prop="subject">
          <el-input v-model="form.subject" placeholder="如：高等数学" />
        </el-form-item>
        <el-form-item label="考试日期" prop="exam_date">
          <el-date-picker v-model="form.exam_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="地点" prop="location">
          <el-input v-model="form.location" placeholder="如：教三 101（选填）" />
        </el-form-item>
        <el-form-item label="时长" prop="duration_minutes">
          <el-input-number v-model="form.duration_minutes" :min="10" :max="480" :step="10" />
          <span class="unit">分钟</span>
        </el-form-item>
        <el-form-item label="备注" prop="note">
          <el-input v-model="form.note" placeholder="开卷/闭卷等（选填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { examApi } from '../api'

const exams = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref()

const emptyForm = () => ({
  id: null,
  subject: '',
  exam_date: '',
  location: '',
  duration_minutes: 120,
  note: '',
})
const form = reactive(emptyForm())
const rules = {
  subject: [{ required: true, message: '请输入科目', trigger: 'blur' }],
  exam_date: [{ required: true, message: '请选择考试日期', trigger: 'change' }],
}

const load = async () => {
  loading.value = true
  try {
    exams.value = await examApi.list()
  } finally {
    loading.value = false
  }
}

const openDialog = (row) => {
  Object.assign(form, emptyForm(), row ? { ...row } : {})
  dialogVisible.value = true
}

const onSave = async () => {
  await formRef.value.validate()
  saving.value = true
  try {
    if (form.id) {
      await examApi.update(form.id, form)
      ElMessage.success('修改成功')
    } else {
      await examApi.create(form)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

const onDelete = async (row) => {
  await ElMessageBox.confirm(
    `确定删除「${row.subject}」吗？该考试下的资料、分析和任务也会随之失效。`,
    '删除确认',
    { type: 'warning' },
  )
  await examApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page-head h2 {
  color: var(--text-hi);
}
.head-sub {
  flex: 1;
  font-size: 13px;
  color: var(--text-low);
}
.unit {
  margin-left: 8px;
  color: var(--text-low);
  font-size: 13px;
}
</style>
