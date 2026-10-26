<template>
  <div>
    <div class="page-head">
      <div>
        <p class="analysis-kicker">从零散资料，到有据可循的复习</p>
        <h2>AI 复习分析</h2>
      </div>
      <el-select
        v-model="examId"
        :disabled="courseLoading || profileLoading || analyzing || qaLoading || replanApplying"
        aria-label="选择要分析的科目"
        placeholder="选择课程，加载专属复习内容"
        class="subject-picker"
        @change="onExamChange"
      >
        <el-option
          v-for="e in exams"
          :key="e.id"
          :label="`${e.subject}（${e.exam_date}）`"
          :value="e.id"
        />
      </el-select>
    </div>

    <div v-if="!examId" class="course-context">
      <el-icon><InfoFilled /></el-icon>
      <p><strong>先说说你的情况，再选择课程。</strong>你可以先填写自然语言描述、目标区间和每日总时间；选择课程后，再补充该课基础与薄弱章节。</p>
      <router-link v-if="!exams.length && !courseLoading" to="/exams">去录入考试 ↗</router-link>
    </div>
    <div v-else class="course-context selected-course">
      <el-icon><Reading /></el-icon>
      <p><strong>{{ selectedExam?.subject }}</strong><span>考试日期 {{ selectedExam?.exam_date }} · 当前画像与方案仅对应这门课程</span></p>
    </div>

      <el-steps
        :active="step"
        align-center
        finish-status="success"
        class="steps"
      >
        <el-step title="描述学习情况" description="支持自然语言输入" />
        <el-step title="确认学习画像" description="核对并补全信息" />
        <el-step title="拿到复习方案" description="重点、计划与自测" />
      </el-steps>

      <!-- 第一步：自然语言描述 -->
      <el-card v-if="step === 0" v-loading="courseLoading" shadow="never" class="step-card">
        <div class="brief-intro">
          <span class="brief-index">01</span>
          <div>
            <h3>{{ selectedExam ? `说说你的${selectedExam.subject}复习情况` : '这一次，你想怎样准备期末？' }}</h3>
            <p>用自己的话描述学习情况，再确认目标区间与可用时间。</p>
          </div>
        </div>
        <section class="natural-input" aria-labelledby="natural-input-title">
          <div class="natural-input-head"><el-icon><ChatLineSquare /></el-icon><label id="natural-input-title" for="study-notes">用自然语言，说说你的情况</label><span>直接打字就可以</span></div>
          <p id="natural-input-help">像聊天一样写下学习基础、薄弱内容或特别要求，AI 会提取学习画像。目标区间以滑条选择为准，提取后还可以核对和补全。</p>
          <el-input id="study-notes" v-model="rawText" type="textarea" :rows="7" maxlength="2000" show-word-limit
            :disabled="profileLoading" aria-label="用自然语言描述你的复习情况" aria-describedby="natural-input-help"
            placeholder="例如：我这门课前半学期没跟上，公式记得不牢，做综合题容易卡住。希望先把基础补起来，再练常考题型；晚上复习比较方便，希望计划里多安排一些例题。" />
          <p class="natural-input-tip">不知道从哪说起？可以写「学到了哪里」「哪些内容不会」「希望怎样复习」。</p>
        </section>
        <el-form label-position="top" class="brief-form" :disabled="profileLoading">
          <el-form-item label="这门课想达到的目标区间" class="brief-wide goal-field">
            <ScoreGoalSlider v-model="brief.target_band" :disabled="profileLoading" />
          </el-form-item>
          <el-form-item v-if="examId" label="这门课的当前基础"
            ><el-select
              v-model="brief.learning_status"
              aria-label="当前学习基础"
              ><el-option
                label="基础薄弱，先补核心概念"
                value="weak" /><el-option
                label="基础一般，需要梳理重点"
                value="medium" /><el-option
                label="基础良好，想练综合难题"
                value="good" /></el-select
          ></el-form-item>
          <el-form-item v-if="examId" label="距离这门考试还有"
            ><el-input-number
              v-model="brief.available_days"
              :min="1"
              :max="60"
              aria-label="可用复习天数"
            /><span class="unit">天</span></el-form-item
          >
          <el-form-item label="每天可用总时间（所有科目合计）"
            ><el-input-number
              v-model="brief.daily_hours"
              :min="0.5"
              :max="16"
              :step="0.5"
              aria-label="每日可用小时数"
            /><span class="unit">小时</span></el-form-item
          >
          <el-form-item v-if="examId" label="这门课的薄弱章节（可选）"
            ><el-input
              v-model="brief.weak_chapters"
              placeholder="例如：极限、积分"
              maxlength="300"
          /></el-form-item>
        </el-form>
        <p class="choice-hint">
          各科保留各自的目标与基础，共享这份每日时间预算。生成后会统筹所有考试的未完成
          AI 任务，任务日期以首页与课程管理为准。
        </p>
        <div v-if="result" class="existing-analysis"><p>这门课已有复习方案。可以修改上方画像后重新生成，也可以继续查看已有方案。</p><el-button @click="step = 2">查看已有方案</el-button></div>
        <p v-if="!examId" class="select-before-submit">填写的内容会在当前页面保留；请在右上方选择课程后生成学习画像。</p>
        <div class="actions">
          <router-link to="/materials" class="material-link"
            >还没有资料？先去上传 ↗</router-link
          >
          <el-button
            type="primary"
            :loading="profileLoading"
            :disabled="!examId || courseLoading"
            @click="onExtractProfile"
          >
            {{ examId ? '生成学习画像 →' : '选择课程后生成学习画像' }}
          </el-button>
        </div>
      </el-card>

      <!-- 第二步：画像确认 / 补全 -->
      <el-card v-if="step === 1" shadow="never" class="step-card">
        <el-descriptions :column="2" border title="系统提取的学习画像">
          <el-descriptions-item label="备考目标">
            {{ scoreBandText(profile.target_band) || targetText(profile.target) || '（未提取到）' }}
          </el-descriptions-item>
          <el-descriptions-item label="基础水平">
            {{ statusText(profile.learning_status) || '（未提取到）' }}
          </el-descriptions-item>
          <el-descriptions-item label="剩余天数">
            {{ profile.available_days ?? '（未提取到）' }} 天
          </el-descriptions-item>
          <el-descriptions-item label="全科每日总预算">
            {{ brief.daily_hours }} 小时
          </el-descriptions-item>
          <el-descriptions-item label="薄弱章节" :span="2">
            {{
              profile.weak_chapters?.length
                ? profile.weak_chapters.join('、')
                : '（未提到）'
            }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 画像不完整：展示补全表单 -->
        <el-alert
          v-if="!profile.is_complete"
          type="warning"
          :closable="false"
          show-icon
          class="complete-alert"
          :title="`画像还缺少：${missingFieldLabels.join('、')}，请补全后继续`"
        />
        <div v-if="!profile.is_complete" class="complete-form">
          <el-form label-width="100px">
            <el-form-item v-if="missing.includes('target')" label="备考目标">
              <ScoreGoalSlider v-model="completeForm.target_band" :disabled="profileLoading" />
            </el-form-item>
            <el-form-item
              v-if="missing.includes('learning_status')"
              label="基础水平"
            >
              <el-radio-group v-model="completeForm.learning_status">
                <el-radio-button value="weak">基础薄弱</el-radio-button>
                <el-radio-button value="medium">基础一般</el-radio-button>
                <el-radio-button value="good">基础良好</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item
              v-if="missing.includes('available_days')"
              label="剩余天数"
            >
              <el-input-number
                v-model="completeForm.available_days"
                :min="1"
                :max="60"
              />
              <span class="unit">天</span>
            </el-form-item>
            <el-form-item
              v-if="missing.includes('daily_hours')"
              label="每天可投入"
            >
              <el-input-number
                v-model="completeForm.daily_hours"
                :min="0.5"
                :max="16"
                :step="0.5"
              />
              <span class="unit">小时</span>
            </el-form-item>
          </el-form>
          <div class="actions">
            <el-button @click="onBackToDescribe">重新描述</el-button>
            <el-button
              type="primary"
              :loading="profileLoading"
              :disabled="!completeFormValid"
              @click="onCompleteProfile"
            >
              提交补全
            </el-button>
          </div>
        </div>

        <!-- 画像完整：进入分析 -->
        <div v-else class="actions">
          <el-button @click="onBackToDescribe">重新描述</el-button>
          <el-button type="primary" :loading="analyzing" @click="onAnalyze">
            <el-icon><MagicStick /></el-icon>&nbsp;生成复习分析
          </el-button>
        </div>
      </el-card>

      <!-- 第三步：分析结果 -->
      <template v-if="step === 2 && result">
        <el-card shadow="never" class="result-card result-overview">
          <div class="result-head">
            <h3>{{ result.course }} · 复习分析</h3>
            <div class="result-controls"><el-button :disabled="analyzing" @click="onBackToDescribe">修改画像与目标</el-button><el-button :loading="analyzing" @click="onAnalyze">重新生成</el-button></div>
          </div>
          <el-alert type="info" :closable="false" :title="result.summary" />
          <div class="result-metrics">
            <div>
              <strong>{{ result.knowledge_points?.length || 0 }}</strong
              ><span>个知识点</span>
            </div>
            <div>
              <strong>{{ result.review_plan?.length || 0 }}</strong
              ><span>项复习安排</span>
            </div>
            <div>
              <strong>{{ result.quiz?.length || 0 }}</strong
              ><span>道自测题</span>
            </div>
            <router-link to="/#board"
              >去首页执行计划 <el-icon><Right /></el-icon
            ></router-link>
          </div>
          <p class="ai-reference">
            <el-icon><InfoFilled /></el-icon>AI
            生成内容仅供复习参考，请结合原始资料与课程要求核对。知识点权重表示复习优先级。
          </p>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header
            ><div class="knowledge-head">
              <div>
                <b>知识点优先级</b><span class="hint">先抓重点，再补薄弱</span>
              </div>
              <el-radio-group
                v-model="knowledgeView"
                size="small"
                aria-label="知识点展示方式"
                ><el-radio-button value="visual">重点视图</el-radio-button
                ><el-radio-button value="table"
                  >详细表格</el-radio-button
                ></el-radio-group
              >
            </div></template
          >
          <p class="mastery-note">按最近一次覆盖该知识点的自测计算，正确率 ≥80% 标记已掌握，无记录显示未测。
            <el-button link :loading="masteryLoading" @click="loadMastery">更新掌握状态</el-button>
          </p>
          <el-alert v-if="masteryError" :title="masteryError" type="warning" :closable="false" />
          <div v-if="knowledgeView === 'visual'" class="knowledge-list">
            <article v-for="(kp, i) in sortedKnowledge" :key="kp.name">
              <span class="knowledge-order">{{
                String(i + 1).padStart(2, '0')
              }}</span>
              <div class="knowledge-body">
                <div class="knowledge-title">
                  <b>{{ kp.name }}</b
                  ><span>{{
                    { high: '优先攻克', medium: '重点巩固', low: '有余力再看' }[
                      kp.importance
                    ] || '按计划复习'
                  }}</span>
                </div>
                <div class="weight-track">
                  <i
                    :style="{
                      width:
                        Math.round(Math.min(1, Math.max(0, kp.weight)) * 100) +
                        '%',
                    }"
                  ></i>
                </div>
                <p>{{ kp.recommend_reason }}</p>
                <div v-if="masteryFor(kp.name)" class="mastery-line">
                  <el-tag size="small" :type="masteryTypes[masteryFor(kp.name).status]">{{ masteryLabels[masteryFor(kp.name).status] }}</el-tag>
                  <span v-if="masteryFor(kp.name).total">最近自测 {{ masteryFor(kp.name).correct }}/{{ masteryFor(kp.name).total }} 题正确 · {{ masteryFor(kp.name).score }}%</span>
                  <span v-else>完成该知识点的自测后更新</span>
                </div>
                <details v-if="masteryFor(kp.name)?.total" class="mastery-evidence">
                  <summary>查看作答依据 · {{ masteryFor(kp.name).last_submitted_at?.replace('T', ' ').slice(0, 16) }}</summary>
                  <p v-for="(item, index) in masteryFor(kp.name).evidence" :key="index">{{ item.correct ? '答对' : item.unanswered ? '未答' : '答错' }} · {{ item.question }}</p>
                </details>
                <div class="knowledge-source">
                  <span v-if="kp.source">依据 · {{ kp.source }}</span
                  ><span v-if="kp.suggest_hours"
                    >建议 {{ kp.suggest_hours }} 小时</span
                  >
                  <el-button link type="primary" @click="openEvidence('knowledge', kp)">查看原文依据</el-button>
                </div>
              </div>
              <strong class="knowledge-weight"
                >{{ Math.round(kp.weight * 100) }}<small>%</small></strong
              >
            </article>
          </div>
          <el-table v-else :data="result.knowledge_points" size="large">
            <el-table-column prop="name" label="知识点" min-width="140">
              <template #default="{ row }"
                ><b>{{ row.name }}</b></template
              >
            </el-table-column>
            <el-table-column label="权重" min-width="180">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round(row.weight * 100)"
                  :stroke-width="12"
                  :color="weightColor(row.weight)"
                />
              </template>
            </el-table-column>
            <el-table-column label="重要程度" width="100">
              <template #default="{ row }">
                <el-tag
                  :type="
                    { high: 'danger', medium: 'warning', low: 'info' }[
                      row.importance
                    ]
                  "
                >
                  {{ { high: '高', medium: '中', low: '低' }[row.importance] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="掌握状态" min-width="140">
              <template #default="{ row }">
                <template v-if="masteryFor(row.name)">
                  <el-tag :type="masteryTypes[masteryFor(row.name).status]">{{ masteryLabels[masteryFor(row.name).status] }}</el-tag>
                  <small v-if="masteryFor(row.name).total"> {{ masteryFor(row.name).correct }}/{{ masteryFor(row.name).total }} 题</small>
                </template>
                <span v-else>{{ masteryLoading ? '更新中' : '暂未加载' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="suggest_hours" label="建议投入" width="90">
              <template #default="{ row }"
                >{{ row.suggest_hours }} 小时</template
              >
            </el-table-column>
            <el-table-column
              prop="recommend_reason"
              label="推荐理由"
              min-width="160"
            />
            <el-table-column prop="source" label="依据来源" min-width="150">
              <template #default="{ row }">
                <el-tag
                  v-if="row.source"
                  size="small"
                  type="success"
                  effect="plain"
                  >{{ row.source }}</el-tag
                >
                <el-button link type="primary" @click="openEvidence('knowledge', row)">查看原文</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 思维导图与记忆卡片（用例 4.4） -->
        <el-card v-if="study" shadow="never" class="result-card">
          <template #header>
            <b>思维导图与记忆卡片</b>
            <span class="hint">提纲可视化 · 点击卡片翻面背诵</span>
          </template>
          <div ref="mindmapRef" class="mindmap-chart"></div>
          <el-divider />
          <div v-if="cards.length" class="flash-area">
            <div
              class="flash-card"
              :class="{ flipped: cardFlipped }"
              @click="cardFlipped = !cardFlipped"
            >
              <div class="flash-inner">
                <div class="flash-face flash-front">
                  <span class="flash-label">正面 · 背诵要点</span>
                  <p class="flash-text">{{ currentCard?.front }}</p>
                  <span class="flash-hint">{{ currentCard?.hint }}</span>
                </div>
                <div class="flash-face flash-back">
                  <span class="flash-label">背面 · 资料依据</span>
                  <p class="flash-text">{{ currentCard?.back }}</p>
                </div>
              </div>
            </div>
            <div class="flash-controls">
              <el-button size="small" @click="prevCard">上一张</el-button>
              <span class="flash-count">{{ cardIndex + 1 }} / {{ cards.length }}</span>
              <el-button size="small" @click="nextCard">下一张</el-button>
              <el-button size="small" @click="shuffleCards">打乱顺序</el-button>
              <el-button link type="primary" @click="cardFlipped = !cardFlipped">
                翻面
              </el-button>
            </div>
          </div>
          <el-empty v-else description="暂无可背诵的卡片" :image-size="60" />
        </el-card>

        <!-- 资料问答（用例 4.5） -->
        <el-card shadow="never" class="result-card">
          <template #header>
            <b>资料问答</b>
            <span class="hint">就当前科目的复习资料提问，支持多轮追问与历史保存</span>
          </template>
          <div ref="qaListRef" class="qa-list">
            <el-empty
              v-if="!qaMessages.length"
              description="试着问：这份资料的重点是什么？"
              :image-size="60"
            />
            <div v-for="m in qaMessages" :key="m.id" class="qa-row" :class="m.role">
              <div class="qa-bubble">
                <div class="qa-role">{{ m.role === 'user' ? '我' : 'AI 助手' }}</div>
                <div class="qa-content">{{ m.content }}</div>
              </div>
            </div>
          </div>
          <div class="qa-input-row">
            <div class="qa-input-box">
              <el-input
                v-model="qaInput"
                type="textarea"
                :rows="2"
                maxlength="2000"
                show-word-limit
                placeholder="针对资料提问，例如：极限这一章有哪些必考内容？"
                @keydown.enter.exact.prevent="onAsk"
              />
            </div>
            <el-button
              type="primary"
              :loading="qaLoading"
              :disabled="!qaInput.trim()"
              @click="onAsk"
            >
              发送
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header>
            <b>常考题型与高频考点</b>
            <span class="hint">基于历年题与多来源资料统计</span>
          </template>
          <div v-if="result.question_types?.length" class="type-block">
            <div ref="typeChartRef" class="type-chart"></div>
            <el-table :data="result.question_types" size="small" class="type-table">
              <el-table-column prop="type" label="题型" width="100" />
              <el-table-column prop="count" label="出现次数" width="90" />
              <el-table-column label="占比" width="90">
                <template #default="{ row }">{{ Math.round(row.frequency * 100) }}%</template>
              </el-table-column>
              <el-table-column prop="basis" label="统计依据" min-width="180" />
              <el-table-column prop="source" label="来源" min-width="150">
                <template #default="{ row }">{{ row.source }} <el-button link type="primary" @click="openEvidence('question_type', row)">查看原文</el-button></template>
              </el-table-column>
            </el-table>
          </div>
          <el-divider v-if="result.question_types?.length" />
          <el-timeline>
            <el-timeline-item
              v-for="(f, i) in sortedFocus"
              :key="i"
              :type="f.level === 'must' ? 'danger' : 'primary'"
              :hollow="f.level !== 'must'"
            >
              <el-tag
                size="small"
                :type="f.level === 'must' ? 'danger' : 'primary'"
                class="focus-tag"
              >
                {{ f.level === 'must' ? '必考' : '常考' }}
              </el-tag>
              <el-tag v-if="f.frequency" size="small" type="info" effect="plain" class="focus-tag">
                出现 {{ f.frequency }} 次
              </el-tag>
              {{ f.content }}
              <div class="focus-basis">
                依据：{{ f.basis }}（{{ f.source }}）
                <el-button link type="primary" @click="openEvidence('focus', f)">查看原文依据</el-button>
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <el-card shadow="never" class="result-card">
          <template #header
            ><b>复习计划</b
            ><span class="hint">{{
              USE_MOCK
                ? '以下为示例计划，演示操作不保存'
                : '本科内容建议；全科统筹后的实际日期见首页与课程管理'
            }}</span></template
          >
          <el-alert
            v-if="schedulingNote"
            :title="schedulingNote"
            type="warning"
            :closable="false"
            show-icon
          />
          <el-table :data="result.review_plan">
            <el-table-column prop="day" label="第几天" width="80">
              <template #default="{ row }">第 {{ row.day }} 天</template>
            </el-table-column>
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="title" label="复习主题" min-width="180" />
            <el-table-column
              prop="estimated_minutes"
              label="预计时长"
              width="100"
            >
              <template #default="{ row }"
                >{{ row.estimated_minutes }} 分钟</template
              >
            </el-table-column>
            <el-table-column label="优先级" width="90">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="['', 'danger', 'warning', 'info'][row.priority]"
                >
                  {{ ['', '高', '中', '低'][row.priority] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="具体内容" min-width="200" />
          </el-table>
        </el-card>

        <QuizPanel v-if="analysisId && result.quiz?.length" :key="analysisId" :analysis-id="analysisId" :questions="result.quiz" :subject="result.course" @submitted="loadMastery" />

        <!-- 动态调整计划与权重（用例 4.12） -->
        <el-card shadow="never" class="result-card">
          <template #header>
            <b>动态调整计划与权重</b>
            <span class="hint">根据打卡、自测错题与剩余天数重新排序</span>
          </template>
          <div class="replan-actions">
            <el-button type="primary" plain :loading="replanLoading" @click="onReplanPreview">
              预览调整
            </el-button>
            <span class="replan-tip">
              已完成的打卡记录会保留；按反馈追加针对性练习，并在全科预算内重排未完成的 AI 任务。
            </span>
          </div>
        </el-card>

      </template>

      <!-- 动态调整预览 -->
      <el-dialog v-model="replanVisible" title="动态调整预览" width="760px">
        <el-alert
          v-if="replanPreview"
          :title="replanPreview.note"
          type="info"
          :closable="false"
          class="replan-note"
        />
        <h4 class="replan-title">知识点权重调整</h4>
        <el-table :data="replanPreview?.weights || []" size="small" max-height="260">
          <el-table-column prop="name" label="知识点" min-width="140" />
          <el-table-column label="权重变化" width="150">
            <template #default="{ row }">
              <span
                :class="{
                  'weight-up': row.new_weight > row.old_weight,
                  'weight-down': row.new_weight < row.old_weight,
                }"
              >
                {{ Math.round(row.old_weight * 100) }}% → {{ Math.round(row.new_weight * 100) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="调整依据" min-width="240" />
        </el-table>
        <el-divider />
        <el-alert v-for="(conflict, i) in replanPreview?.scheduling?.conflicts || []" :key="i" type="warning" :closable="false" :title="`${conflict.title || conflict.date || '排程冲突'}：${conflict.reason}，超出 ${conflict.minutes} 分钟`" />
        <h4 class="replan-title">调整后的全科复习计划</h4>
        <el-table :data="replanPreview?.scheduling?.assignments || []" size="small" max-height="240">
          <el-table-column label="科目" min-width="100">
            <template #default="{ row }">{{ exams.find(e => e.id === row.exam_id)?.subject || '当前科目' }}</template>
          </el-table-column>
          <el-table-column prop="date" label="日期" width="110" />
          <el-table-column prop="title" label="任务" min-width="180" />
          <el-table-column prop="minutes" label="时长" width="90">
            <template #default="{ row }">{{ row.minutes }} 分钟</template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button @click="replanVisible = false">取消</el-button>
          <el-button type="primary" :loading="replanApplying" :disabled="!replanPreview || !!replanPreview.scheduling?.conflicts?.length" @click="onReplanApply">
            应用调整
          </el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="evidenceVisible" :title="evidenceData?.item_title ? `${evidenceData.item_title} · 原文依据` : '原文依据'" width="min(760px, 94vw)">
        <div v-loading="evidenceLoading" class="evidence-content">
          <el-alert v-if="evidenceError" :title="evidenceError" type="warning" :closable="false" />
          <template v-if="evidenceData">
            <p class="mastery-note">{{ evidenceData.note }}</p>
            <SourceExcerpt v-for="(reference, index) in evidenceData.items" :key="index" :reference="reference">
              <router-link v-if="sourceRoute(reference, evidenceData.exam_id)" :to="sourceRoute(reference, evidenceData.exam_id)">在资料库中查看 →</router-link>
            </SourceExcerpt>
          </template>
        </div>
        <template #footer><el-button @click="evidenceVisible = false">关闭</el-button></template>
      </el-dialog>

      <!-- 分析中提示 -->
      <el-card v-if="step === 2 && analyzing" shadow="never" class="step-card">
        <el-result
          icon="info"
          title="AI 正在分析你的资料…"
          sub-title="通常需要几十秒，请稍候"
        >
          <template #extra
            ><el-progress :percentage="100" :indeterminate="true" :duration="2"
          /></template>
        </el-result>
      </el-card>

      <!-- 分析失败：给出原因与出口，不留空白页 -->
      <el-card
        v-if="step === 2 && analyzeError"
        shadow="never"
        class="step-card"
      >
        <el-result icon="error" title="分析没有成功" :sub-title="analyzeError">
          <template #extra>
            <el-button
              v-if="analyzeError.includes('资料')"
              type="primary"
              @click="$router.push('/materials')"
            >
              去上传资料
            </el-button>
            <el-button @click="backToProfile">返回上一步</el-button>
            <el-button type="primary" @click="onAnalyze">重试</el-button>
          </template>
        </el-result>
      </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { aiApi, examApi, studyApi } from '../api'
import { USE_MOCK, getToday, mockStudySession } from '../mock/dashboard'
import { buildStudyPlan, applyStudyPlan } from '../utils/studyPlan'
import { daysUntil } from '../utils/studyProgress'
import { mockProfile, mockAnalysis, mockMaterials } from '../mock/pages'
import SourceExcerpt from '../components/SourceExcerpt.vue'
import { mockEvidence, sourceRoute } from '../utils/sourceEvidence.js'
import QuizPanel from '../components/QuizPanel.vue'
import { mockAnalysisSessions, mockQuizHistory, mockQuizDetail, mockMastery } from '../mock/quizzes'
import { masteryLabels, masteryTypes } from '../utils/mastery'
import { feedbackReplan } from '../utils/replan'
import ScoreGoalSlider from '../components/ScoreGoalSlider.vue'
import { scoreBand, scoreBandText } from '../utils/scoreTargets'
import * as echarts from 'echarts'

const FIELD_LABELS = {
  target: '备考目标',
  learning_status: '基础水平',
  available_days: '剩余天数',
  daily_hours: '每天可投入时间',
}

const exams = ref([])
const route = useRoute()
const knowledgeView = ref('visual')
const brief = reactive({
  target_band: 'D',
  learning_status: 'weak',
  available_days: 5,
  daily_hours: 3,
  weak_chapters: '',
})
const sortedKnowledge = computed(() =>
  [...(result.value?.knowledge_points || [])].sort(
    (a, b) => b.weight - a.weight,
  ),
)
const examId = ref(null)
const selectedExam = computed(() => exams.value.find((exam) => exam.id === examId.value))
const courseLoading = ref(false)
const courseDrafts = new Map()
let activeExamId = null
const step = ref(0)
const rawText = ref('')
const profile = ref(null)
const result = ref(null)
const analysisId = ref(null)
const profileLoading = ref(false)
const analyzing = ref(false)
const analyzeError = ref('')
const schedulingNote = ref('')
const evidenceVisible = ref(false)
const evidenceData = ref(null)
const evidenceLoading = ref(false)
const evidenceError = ref('')
let evidenceRequest = 0
const openEvidence = async (kind, item) => {
  const requestId = ++evidenceRequest
  const collection = { knowledge: result.value.knowledge_points, focus: result.value.exam_focus, question_type: result.value.question_types }[kind]
  const itemIndex = collection.indexOf(item)
  evidenceVisible.value = true
  evidenceData.value = null
  evidenceError.value = ''
  evidenceLoading.value = true
  try {
    const data = USE_MOCK ? mockEvidence(item, examId.value, mockMaterials)
      : await aiApi.evidence(examId.value, { analysis_id: analysisId.value, kind, item_index: itemIndex })
    if (requestId === evidenceRequest) evidenceData.value = data
  } catch {
    if (requestId === evidenceRequest) evidenceError.value = '原文依据暂时无法获取，请关闭后重试；资料可能已变化。'
  } finally { if (requestId === evidenceRequest) evidenceLoading.value = false }
}
watch(evidenceVisible, value => { if (!value) { evidenceRequest++; evidenceLoading.value = false } })
const mastery = ref([])
const masteryLoading = ref(false)
const masteryError = ref('')
const masteryFor = (name) => mastery.value.find(point => point.name === name)
let masteryRequest = 0
const loadMastery = async () => {
  const requestId = ++masteryRequest
  mastery.value = []
  masteryError.value = ''
  if (!examId.value || !analysisId.value || !result.value) { masteryLoading.value = false; return }
  masteryLoading.value = true
  try {
    const points = USE_MOCK
      ? mockMastery(result.value.course, result.value.knowledge_points.map(point => point.name))
      : (await aiApi.mastery(examId.value)).points
    if (requestId === masteryRequest) mastery.value = points
  } catch {
    if (requestId === masteryRequest) masteryError.value = '掌握状态暂未获取，请点击更新重试；自测和复习计划仍可使用。'
  } finally { if (requestId === masteryRequest) masteryLoading.value = false }
}

const completeForm = reactive({
  target_band: 'D',
  learning_status: 'weak',
  available_days: 5,
  daily_hours: 3,
})

// 思维导图与记忆卡片（用例 4.4）
const study = ref(null)
const cardIndex = ref(0)
const cardFlipped = ref(false)
const mindmapRef = ref(null)
let mindmapChart = null
const cards = computed(() => study.value?.cards || [])
const currentCard = computed(() => cards.value[cardIndex.value] || null)

// 常考题型与高频考点（用例 4.7）
const typeChartRef = ref(null)
let typeChart = null
const sortedFocus = computed(() =>
  [...(result.value?.exam_focus || [])].sort(
    (a, b) => (b.frequency || 0) - (a.frequency || 0),
  ),
)

// 资料问答（用例 4.5）
const qaConversationId = ref(null)
const qaMessages = ref([])
const qaInput = ref('')
const qaLoading = ref(false)
const qaListRef = ref(null)

// 动态调整计划与权重（用例 4.12）
const replanVisible = ref(false)
const replanLoading = ref(false)
const replanApplying = ref(false)
const replanPreview = ref(null)


const missing = computed(() => profile.value?.missing_fields || [])
const missingFieldLabels = computed(() =>
  missing.value.map((f) => FIELD_LABELS[f] || f),
)
const completeFormValid = computed(() =>
  missing.value.every((f) => {
    if (f === 'target')
      return !!scoreBand(completeForm.target_band)
    if (f === 'learning_status')
      return ['weak', 'medium', 'good'].includes(completeForm.learning_status)
    if (f === 'available_days') return completeForm.available_days > 0
    if (f === 'daily_hours') return completeForm.daily_hours > 0
    return true
  }),
)

const targetText = (t) =>
  ({ pass: '保及格', medium: '稳中等', high: '冲高分' })[t]
const statusText = (s) =>
  ({ weak: '基础薄弱', medium: '基础一般', good: '基础良好' })[s]
const weightColor = (w) =>
  w >= 0.8 ? '#c2472f' : w >= 0.6 ? '#a06a22' : '#35554c'

const buildSupplement = () => {
  const parts = []
  if (missing.value.includes('target'))
    parts.push(`我的目标区间是${scoreBandText(completeForm.target_band)}`)
  if (missing.value.includes('learning_status'))
    parts.push(`我基础${statusText(completeForm.learning_status)}`)
  if (missing.value.includes('available_days'))
    parts.push(`还有${completeForm.available_days}天考试`)
  if (missing.value.includes('daily_hours'))
    parts.push(`每天能学${completeForm.daily_hours}小时`)
  return parts.join('，')
}

const onExtractProfile = async () => {
  if (!examId.value || courseLoading.value) return
  profileLoading.value = true
  try {
    if (USE_MOCK) {
      mockStudySession.daily_minutes = Math.round(brief.daily_hours * 60)
      mockStudySession.focus.goal_minutes = mockStudySession.daily_minutes
      // mock 模式下返回本地演示画像
      await new Promise((r) => setTimeout(r, 600))
      profile.value = {
        ...structuredClone(mockProfile),
        exam_id: examId.value,
        raw_text: rawText.value,
        target: scoreBand(brief.target_band).strategy,
        target_band: brief.target_band,
        learning_status: brief.learning_status,
        available_days: brief.available_days,
        daily_hours: brief.daily_hours,
        weak_chapters: brief.weak_chapters
          .split(/[、，,]/)
          .map((s) => s.trim())
          .filter(Boolean),
      }
    } else {
      await studyApi.saveSettings({
        daily_minutes: Math.round(brief.daily_hours * 60),
      })
      const basis = {
        weak: '我基础差',
        medium: '我的基础一般',
        good: '我的基础很好',
      }[brief.learning_status]
      const description = `${basis}，还有${brief.available_days}天考试，每天能学${brief.daily_hours}小时。${brief.weak_chapters.trim() ? '薄弱的是' + brief.weak_chapters + '。' : ''}${rawText.value}\n明确选择的目标区间：${scoreBandText(brief.target_band)}，目标以此区间为准。`
      profile.value = await aiApi.profile({
        exam_id: examId.value,
        raw_text: description,
        target_band: brief.target_band,
      })
    }
    completeForm.target_band = brief.target_band
    step.value = 1
    if (profile.value.is_complete) ElMessage.success('画像提取完成')
    else ElMessage.warning('画像缺少部分信息，请补全')
  } catch {
    /* 错误提示已由拦截器弹出，留在当前步骤 */
  } finally {
    profileLoading.value = false
  }
}

const onCompleteProfile = async () => {
  profileLoading.value = true
  try {
    profile.value = await aiApi.profile({
      exam_id: examId.value,
      raw_text: '',
      supplement: buildSupplement(),
      target_band: missing.value.includes('target') ? completeForm.target_band : profile.value.target_band,
    })
    if (profile.value.is_complete) ElMessage.success('画像已补全')
  } catch {
    /* 错误提示已由拦截器弹出，留在补全表单 */
  } finally {
    profileLoading.value = false
  }
}

const previewAnalysis = () => {
  const subject =
    exams.value.find((e) => e.id === examId.value)?.subject || '当前科目'
  const names = subject.includes('英语')
    ? ['核心词汇', '长难句与语法', '阅读理解', '听力与精听', '写作与翻译']
    : subject.includes('数据')
      ? ['线性表', '树与二叉树', '图的遍历', '查找与排序', '算法复杂度']
      : subject.includes('数学')
        ? mockAnalysis.knowledge_points.map((p) => p.name)
        : ['核心概念', '重点原理', '典型题型', '综合练习', '错题复盘']
  const copy = structuredClone(mockAnalysis)
  copy.course = subject
  const band = scoreBand(profile.value?.target_band || brief.target_band)
  copy.summary = `${subject}的示例复习方案，目标为${scoreBandText(band.id)}。全科每日共享 ${brief.daily_hours} 小时，实际日期与各科分配统一在首页确认；以下考点权重用于演示。`
  copy.knowledge_points = copy.knowledge_points.map((p, i) => ({
    ...p,
    name: names[i],
    source: '示例资料',
    recommend_reason: '演示建议：结合本课程资料与当前基础安排优先级',
  }))
  copy.exam_focus = copy.exam_focus.map((p, i) => ({
    ...p,
    content: `${names[i]}的基础题与常见考法`,
    basis: '演示内容，请以实际课程要求为准',
    source: '示例资料',
  }))
  copy.review_plan = copy.review_plan.map((p, i) => ({
    ...p,
    title: names[i],
    detail: `按${band.range}目标复习${names[i]}，${band.min >= 85 ? '增加综合应用与限时训练' : band.min >= 70 ? '巩固常见题型并练习综合应用' : '优先基础题与高频考点'}，整理易错点`,
    estimated_minutes: Math.max(
      15,
      Math.round(
        (brief.daily_hours * 60) / Math.max(1, exams.value.length) / 5,
      ) * 5,
    ),
  }))
  if (subject.includes('英语'))
    copy.quiz = [
      {
        question: '请选择正确的词形：She ___ to the library every day.',
        options: ['go', 'goes', 'going', 'gone'],
        answer: 'B',
        analysis: '一般现在时的主语为第三人称单数，动词用 goes。',
        knowledge_point: '长难句与语法',
      },
    ]
  else if (subject.includes('数据'))
    copy.quiz = [
      {
        question: '采用先进先出规则的数据结构是？',
        options: ['栈', '队列', '二叉搜索树', '堆'],
        answer: 'B',
        analysis: '队列遵循先进先出，栈遵循后进先出。',
        knowledge_point: '线性表',
      },
    ]
  else if (!subject.includes('数学'))
    copy.quiz = [
      {
        question: '复习后发现某类题反复出错，下一步更合适的做法是？',
        options: [
          '跳过这个知识点',
          '整理错因并补充针对性练习',
          '只增加背诵时间',
          '等到考前再看',
        ],
        answer: 'B',
        analysis: '先识别错因，再通过针对性练习检查是否掌握。',
        knowledge_point: '错题复盘',
      },
    ]
  return copy
}

// 静态演示模式：从 mockAnalysis 直接构建导图与卡片
const buildMockStudy = () => {
  const course = result.value.course
  const kpNodes = result.value.knowledge_points.map((kp) => ({
    name: `${kp.name}（${Math.round(kp.weight * 100)}%）`,
    value: kp.weight,
    level: kp.importance,
    source: kp.source,
    children: [
      { name: `依据：${kp.recommend_reason}` },
      { name: `建议投入：${kp.suggest_hours} 小时` },
    ],
  }))
  const focusNodes = result.value.exam_focus.map((f) => ({
    name: `${f.level === 'must' ? '必考' : '常考'}：${f.content}`,
    level: f.level,
    source: f.source,
    children: [{ name: `依据：${f.basis}` }],
  }))
  return {
    exam_id: examId.value,
    course,
    mindmap: {
      name: course,
      children: [
        { name: '知识点', children: kpNodes },
        { name: '考点', children: focusNodes },
      ],
    },
    cards: [
      ...result.value.knowledge_points.map((kp, i) => ({
        id: i + 1,
        front: kp.name,
        back: kp.recommend_reason,
        hint: `依据来源：${kp.source} · 建议投入 ${kp.suggest_hours} 小时`,
        knowledge_point: kp.name,
        source: kp.source,
      })),
      ...result.value.exam_focus.map((f, i) => ({
        id: 100 + i,
        front: f.content,
        back: f.basis,
        hint: `来源：${f.source} · ${f.level === 'must' ? '必考' : '常考'}`,
        knowledge_point: '',
        source: f.source,
      })),
    ],
  }
}

const renderMindmap = async () => {
  await nextTick()
  if (!mindmapRef.value || !study.value) return
  if (!mindmapChart) mindmapChart = echarts.init(mindmapRef.value)
  mindmapChart.setOption(
    {
      tooltip: { trigger: 'item', triggerOn: 'mousemove' },
      series: [
        {
          type: 'tree',
          orient: 'LR',
          data: [study.value.mindmap],
          top: '3%',
          left: '8%',
          bottom: '3%',
          right: '18%',
          symbol: 'circle',
          symbolSize: 9,
          initialTreeDepth: 3,
          expandAndCollapse: true,
          label: {
            position: 'left',
            verticalAlign: 'middle',
            align: 'right',
            fontSize: 12,
            color: '#0c1614',
            width: 200,
            overflow: 'break',
          },
          leaves: {
            label: { position: 'right', align: 'left', width: 220, overflow: 'break' },
          },
          lineStyle: { color: '#d9d4c3', width: 1.2, curveness: 0.5 },
          itemStyle: { color: '#e66348', borderColor: '#e66348' },
          emphasis: { focus: 'descendant' },
          animationDuration: 400,
        },
      ],
    },
    true,
  )
  mindmapChart.resize()
}

const loadStudy = async () => {
  // 重建图表，避免 v-if 切换后复用已脱离 DOM 的旧实例
  if (mindmapChart) {
    mindmapChart.dispose()
    mindmapChart = null
  }
  if (!examId.value) {
    study.value = null
    return
  }
  if (USE_MOCK) {
    study.value = buildMockStudy()
  } else {
    try {
      study.value = await aiApi.mindmap(examId.value)
    } catch {
      study.value = null // 没有分析结果或接口失败时不展示该卡片
    }
  }
  cardIndex.value = 0
  cardFlipped.value = false
  await renderMindmap()
}

const prevCard = () => {
  if (!cards.value.length) return
  cardIndex.value = (cardIndex.value - 1 + cards.value.length) % cards.value.length
  cardFlipped.value = false
}

const nextCard = () => {
  if (!cards.value.length) return
  cardIndex.value = (cardIndex.value + 1) % cards.value.length
  cardFlipped.value = false
}

const shuffleCards = () => {
  if (!study.value?.cards?.length) return
  const shuffled = [...study.value.cards]
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  study.value.cards = shuffled
  cardIndex.value = 0
  cardFlipped.value = false
}

const renderTypeChart = async () => {
  if (typeChart) {
    typeChart.dispose()
    typeChart = null
  }
  await nextTick()
  const types = result.value?.question_types || []
  if (!typeChartRef.value || !types.length) return
  typeChart = echarts.init(typeChartRef.value)
  typeChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => `${params[0].name}<br/>占比 ${params[0].value}%`,
    },
    grid: { left: 48, right: 20, top: 30, bottom: 36 },
    xAxis: {
      type: 'category',
      data: types.map((item) => item.type),
      axisLabel: { color: '#454e48' },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { formatter: '{value}%', color: '#8b9084' },
      splitLine: { lineStyle: { color: '#e9e5d7' } },
    },
    series: [
      {
        type: 'bar',
        data: types.map((item) => Math.round(item.frequency * 100)),
        barWidth: '46%',
        itemStyle: { color: '#e66348', borderRadius: [6, 6, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c}%', color: '#0c1614' },
      },
    ],
  })
  typeChart.resize()
}

const resizeMindmap = () => {
  mindmapChart?.resize()
  typeChart?.resize()
}

// 静态演示模式的本地问答：优先匹配知识点/考点
const mockQaAnswer = (question) => {
  const kp = result.value.knowledge_points.find((item) => question.includes(item.name))
  if (kp) {
    return (
      `（Mock）「${kp.name}」权重 ${Math.round(kp.weight * 100)}%，` +
      `推荐依据：${kp.recommend_reason}（${kp.source}），建议投入 ${kp.suggest_hours} 小时。`
    )
  }
  const focus = result.value.exam_focus.find((item) => question.includes(item.content.slice(0, 4)))
  if (focus) {
    return `（Mock）${focus.content}：${focus.basis}（${focus.source}）。`
  }
  const top = result.value.knowledge_points.slice(0, 3).map((item) => item.name).join('、')
  return `（Mock）根据当前资料，建议优先复习：${top}。以上内容仅供复习参考，请结合教材与老师要求判断。`
}

const scrollQaToBottom = async () => {
  await nextTick()
  if (qaListRef.value) qaListRef.value.scrollTop = qaListRef.value.scrollHeight
}

const loadQa = async () => {
  qaConversationId.value = null
  qaMessages.value = []
  if (!examId.value || USE_MOCK) return
  try {
    const conversations = await aiApi.qaConversations(examId.value)
    if (!conversations.length) return
    const detail = await aiApi.qaConversation(conversations[0].id)
    qaConversationId.value = detail.id
    qaMessages.value = detail.messages || []
    await scrollQaToBottom()
  } catch {
    /* 没有历史会话时保持空状态 */
  }
}

const onAsk = async () => {
  const content = qaInput.value.trim()
  if (!content || qaLoading.value) return
  qaLoading.value = true
  qaInput.value = ''
  const optimistic = {
    id: `tmp-${Date.now()}`,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
  }
  qaMessages.value = [...qaMessages.value, optimistic]
  await scrollQaToBottom()
  try {
    if (USE_MOCK) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      qaMessages.value = [
        ...qaMessages.value,
        {
          id: `tmp-a-${Date.now()}`,
          role: 'assistant',
          content: mockQaAnswer(content),
          created_at: new Date().toISOString(),
        },
      ]
    } else {
      if (!qaConversationId.value) {
        const conversation = await aiApi.createQaConversation(examId.value)
        qaConversationId.value = conversation.id
      }
      const conversation = await aiApi.askQa(qaConversationId.value, content)
      qaConversationId.value = conversation.id
      qaMessages.value = conversation.messages || []
    }
  } catch (e) {
    // 失败时撤回乐观展示的提问
    qaMessages.value = qaMessages.value.filter((item) => item.id !== optimistic.id)
    ElMessage.error(e?.response?.data?.detail || '提问失败，请稍后重试')
  } finally {
    qaLoading.value = false
    await scrollQaToBottom()
  }
}

const mockFeedback = () => {
  const latest = mockQuizHistory(analysisId.value).find(a => a.status === 'submitted')
  return latest ? mockQuizDetail(latest.id).result.items.map(item => ({ ...item, subject: result.value.course })) : []
}
const buildMockReplan = () => feedbackReplan(
  result.value, examId.value, mockStudySession.tasks, mockStudySession.exams,
  mockStudySession.daily_minutes, getToday(), mockFeedback(),
)
const applyMockReplan = () => {
  const preview = replanPreview.value
  if (preview.fingerprint !== buildMockReplan().fingerprint) throw new Error('任务、预算或自测结果已变化，请重新预览')
  if (preview.scheduling.conflicts.length) throw new Error('请先处理排程冲突')
  mockStudySession.tasks = applyStudyPlan(preview.candidate, preview.scheduling)
  const weightMap = Object.fromEntries(preview.weights.map(item => [item.name, item.new_weight]))
  result.value.knowledge_points = result.value.knowledge_points.map(kp => ({ ...kp, weight: weightMap[kp.name] ?? kp.weight })).sort((a, b) => b.weight-a.weight)
  result.value.review_plan = preview.plan
  result.value.replan_base_weights = preview.base
  result.value.replan_feedback_key = preview.feedbackKey
  const saved = mockAnalysisSessions.get(examId.value)
  if (saved) saved.result = JSON.parse(JSON.stringify(result.value))
}

const onReplanPreview = async () => {
  if (!examId.value) return
  replanLoading.value = true
  try {
    replanPreview.value = USE_MOCK
      ? buildMockReplan()
      : await aiApi.replan(examId.value, false)
    replanVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '预览失败，请稍后重试')
  } finally {
    replanLoading.value = false
  }
}

const onReplanApply = async () => {
  if (!replanPreview.value) return
  replanApplying.value = true
  try {
    if (USE_MOCK) {
      applyMockReplan()
    } else {
      replanPreview.value = await aiApi.replan(examId.value, true, replanPreview.value.fingerprint)
      try {
        const latest = await aiApi.latestAnalysis(examId.value)
        result.value = latest.result
      } catch {
        /* 保留当前展示 */
      }
      await loadStudy()
      await renderTypeChart()
    }
    await loadStudy()
    await renderTypeChart()
    replanVisible.value = false
    ElMessage.success('已按当前进度调整计划与权重')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '应用失败，请稍后重试')
  } finally {
    replanApplying.value = false
  }
}

const onAnalyze = async () => {
  if (!examId.value) return
  analyzing.value = true
  analyzeError.value = ''
  schedulingNote.value = ''
  result.value = null
  step.value = 2
  try {
    if (USE_MOCK) {
      // mock 模式下返回本地演示分析结果（模拟分析耗时）
      await new Promise((r) => setTimeout(r, 1500))
      result.value = previewAnalysis()
      analysisId.value = `mock-${examId.value}-${Date.now()}`
      mockAnalysisSessions.set(examId.value, {
        id: analysisId.value, result: JSON.parse(JSON.stringify(result.value)),
        profile: profile.value ? JSON.parse(JSON.stringify(profile.value)) : null,
        brief: { ...brief }, rawText: rawText.value,
      })
      const retained = mockStudySession.tasks.filter(
        (t) => t.exam_id !== examId.value || t.is_done || t.source !== 'ai',
      )
      const completed = new Map()
      retained
        .filter(
          (t) => t.exam_id === examId.value && t.is_done && t.source === 'ai',
        )
        .forEach((t) => {
          const name = t.title.replace(/（分段 \d+\/\d+）$/, '')
          completed.set(name, (completed.get(name) || 0) + t.estimated_minutes)
        })
      let nextId = Math.max(0, ...mockStudySession.tasks.map((t) => t.id)) + 1
      const generated = result.value.review_plan
        .map((p) => ({
          id: nextId++,
          exam_id: examId.value,
          exam: result.value.course,
          title: `${result.value.course} · ${p.title}`,
          plan_date: p.date,
          estimated_minutes: p.estimated_minutes,
          priority: p.priority,
          is_done: false,
          done_at: null,
          source: 'ai',
        }))
        .map((t) => ({
          ...t,
          estimated_minutes: Math.max(
            0,
            t.estimated_minutes - (completed.get(t.title) || 0),
          ),
        }))
        .filter((t) => t.estimated_minutes > 0)
      const candidate = [...retained, ...generated]
      const plan = buildStudyPlan(
        candidate,
        mockStudySession.exams,
        mockStudySession.daily_minutes,
        getToday(),
      )
      if (plan.conflicts.length)
        schedulingNote.value =
          '示例分析已完成，但全科容量不足，新任务未覆盖原计划。请先调整时间或任务。'
      else mockStudySession.tasks = applyStudyPlan(candidate, plan)
    } else {
      const resp = await aiApi.analyze(examId.value)
      result.value = resp.result
      analysisId.value = resp.id
      if (resp.scheduling && !resp.scheduling.applied)
        schedulingNote.value =
          '分析已完成，但新任务无法在全科预算内排完，因此没有写入或覆盖现有任务。请调整预算、复习范围或目标后重新生成。'
    }
    await loadStudy()
    await renderTypeChart()
    await loadQa()
    if (schedulingNote.value) ElMessage.warning(schedulingNote.value)
    else
      ElMessage.success(
        USE_MOCK
          ? '示例分析与全科计划已更新，本次演示内有效'
          : '分析完成，复习计划已生成每日任务',
      )
  } catch (e) {
    // 失败时展示原因和出口，避免页面空白
    analyzeError.value =
      e?.response?.data?.detail || e?.message || '网络异常，请稍后重试'
  } finally {
    analyzing.value = false
  }
}

const onBackToDescribe = () => {
  step.value = 0
  analyzeError.value = ''
}

const backToProfile = () => {
  analyzeError.value = ''
  step.value = profile.value ? 1 : 0
}

const onExamChange = async () => {
  // 未选课时的公共草稿带入第一门课；之后按课程保留草稿，避免串课。
  if (activeExamId) courseDrafts.set(activeExamId, { brief: { ...brief }, rawText: rawText.value, profile: profile.value })
  const firstSelection = !activeExamId
  const hasPublicDraft = firstSelection && (rawText.value.trim() || brief.target_band !== 'D')
  activeExamId = examId.value
  study.value = null
  qaConversationId.value = null
  qaMessages.value = []
  qaInput.value = ''
  replanPreview.value = null
  replanVisible.value = false
  step.value = 0
  analyzeError.value = ''
  profile.value = null
  result.value = null
  analysisId.value = null
  schedulingNote.value = ''
  const selected = exams.value.find((e) => e.id === examId.value)
  if (!firstSelection) {
    rawText.value = ''
    Object.assign(brief, { target_band: 'D', learning_status: 'weak', weak_chapters: '' })
  }
  brief.available_days = Math.max(
    1,
    Math.min(60, selected ? daysUntil(selected.exam_date, getToday()) : 5),
  )
  const draft = courseDrafts.get(examId.value)
  if (draft) {
    const hours = brief.daily_hours
    Object.assign(brief, draft.brief, { daily_hours: hours })
    rawText.value = draft.rawText
    profile.value = draft.profile
  }
  courseLoading.value = true
  try {
    if (USE_MOCK) {
      const saved = mockAnalysisSessions.get(examId.value)
      if (saved) {
        result.value = structuredClone(saved.result)
        analysisId.value = saved.id
        if (!draft && !hasPublicDraft && saved.brief) {
          const hours = brief.daily_hours
          Object.assign(brief, saved.brief, { daily_hours: hours })
          rawText.value = saved.rawText || ''
          profile.value = saved.profile
        }
      }
    } else {
      const [savedProfile, savedAnalysis] = await Promise.allSettled([
        aiApi.savedProfile(examId.value), aiApi.latestAnalysis(examId.value),
      ])
      if (!draft && !hasPublicDraft && savedProfile.status === 'fulfilled') {
        const saved = savedProfile.value
        profile.value = saved
        rawText.value = saved.raw_text
        Object.assign(brief, {
          target_band: saved.target_band || ({ pass: 'D', medium: 'B', high: 'A' }[saved.target] || 'D'),
          learning_status: saved.learning_status || 'weak',
          weak_chapters: (saved.weak_chapters || []).join('、'),
        })
      }
      if (savedAnalysis.status === 'fulfilled') {
        result.value = savedAnalysis.value.result
        analysisId.value = savedAnalysis.value.id
      }
    }
    await loadQa()
  } finally { courseLoading.value = false }
}

watch([examId, analysisId], loadMastery)
watch([examId, analysisId], () => { evidenceVisible.value = false; evidenceData.value = null })

onMounted(async () => {
  window.addEventListener('resize', resizeMindmap)
  if (USE_MOCK) {
    exams.value = structuredClone(mockStudySession.exams)
    brief.daily_hours = mockStudySession.daily_minutes / 60
  } else {
    exams.value = await examApi.list()
    brief.daily_hours = (await studyApi.settings()).daily_minutes / 60
  }
  const requested = Number(route.query.exam)
  if (exams.value.some((e) => e.id === requested)) {
    examId.value = requested
    await onExamChange()
  }
})

watch([step, analysisId], async () => {
  if (step.value === 2 && result.value && !analyzing.value) {
    await loadStudy()
    await renderTypeChart()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeMindmap)
  mindmapChart?.dispose()
  mindmapChart = null
  typeChart?.dispose()
  typeChart = null
})
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 20px;
  flex-wrap: wrap;
}
.page-head h2 {
  color: var(--text-hi);
  margin: 0;
  font-size: 28px;
}
.analysis-kicker {
  margin: 0 0 10px;
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.06em;
}
.subject-picker {
  width: 300px;
}
.course-context { display: flex; align-items: flex-start; gap: 12px; padding: 16px 20px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--bg-card); }
.course-context > .el-icon { color: var(--coral-deep); margin-top: 4px; flex-shrink: 0; }
.course-context p { margin: 0; color: var(--ink-2); font-size: 12px; line-height: 1.9; }
.course-context strong { color: var(--ink-1); }
.course-context a { margin-left: auto; color: var(--coral-deep); font-size: 12px; white-space: nowrap; }
.selected-course p { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; }
.selected-course strong { font-size: 15px; }
.natural-input { padding: 24px; margin-bottom: 32px; border: 1px solid var(--coral); border-left: 4px solid var(--coral); border-radius: var(--radius-md); background: var(--coral-soft); }
.natural-input-head { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.natural-input-head .el-icon { font-size: 22px; color: var(--coral-deep); }
.natural-input-head label { font-size: 19px; font-weight: 700; color: var(--ink-1); }
.natural-input-head > span { margin-left: auto; color: var(--coral-deep); font-size: 11px; }
.natural-input > p { font-size: 12px; color: var(--ink-2); line-height: 1.9; margin: 12px 0 16px; }
.natural-input :deep(.el-textarea__inner) { min-height: 190px; padding: 16px 18px 30px; font-size: 14px; line-height: 1.9; background: var(--bg-card); resize: vertical; }
.natural-input :deep(.el-input__count) { background: var(--bg-card); padding: 3px; }
.natural-input .natural-input-tip { margin: 12px 0 0; font-size: 11px; color: var(--ink-2); }
.goal-field { padding-bottom: 26px; margin-bottom: 20px; border-bottom: 1px solid var(--line); }
.existing-analysis { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 16px; margin-top: 20px; background: var(--bg-soft); border-radius: var(--radius-sm); }
.existing-analysis p { flex: 1; min-width: 180px; font-size: 12px; line-height: 1.8; margin: 0; color: var(--ink-2); }
.select-before-submit { color: var(--coral-deep); font-size: 12px; line-height: 1.8; margin: 18px 0 0; }
.result-controls { display: flex; flex-wrap: wrap; gap: 10px; }
.result-controls .el-button + .el-button { margin-left: 0; }
.brief-intro {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  margin: 8px 0 28px;
}
.brief-index {
  font: 500 36px/1 var(--font-num);
  color: var(--coral-deep);
}
.brief-intro h3 {
  font-size: 19px;
  margin: 0 0 10px;
}
.brief-intro p {
  font-size: 12px;
  line-height: 1.8;
  color: var(--ink-3);
  margin: 0;
}
.brief-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.brief-wide {
  grid-column: 1 / -1;
}
.choice-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.8;
}
.material-link {
  align-self: center;
  margin-right: auto;
  color: var(--ink-3);
  font-size: 12px;
  text-decoration: none;
}
.result-overview {
  border-color: var(--ink-1);
}
.result-head h3 {
  font-size: 23px;
  margin: 6px 0 20px;
}
.result-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 30px;
  margin-top: 24px;
}
.result-metrics > div {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.result-metrics strong {
  font: 500 32px var(--font-num);
}
.result-metrics span {
  font-size: 12px;
  color: var(--ink-3);
}
.result-metrics a {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  color: var(--coral-deep);
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}
.ai-reference {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--ink-3);
  font-size: 11px;
  line-height: 1.8;
  margin: 22px 0 0;
  padding-top: 15px;
  border-top: 1px solid var(--line);
}
.ai-reference .el-icon {
  flex-shrink: 0;
  margin-top: 4px;
}
.knowledge-head {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  align-items: center;
  justify-content: space-between;
}
.knowledge-list article {
  display: flex;
  gap: 24px;
  padding: 24px 0;
  border-bottom: 1px solid var(--line);
}
.knowledge-list article:first-child {
  padding-top: 5px;
}
.knowledge-list article:last-child {
  border: 0;
  padding-bottom: 5px;
}
.knowledge-order {
  font: 500 17px var(--font-num);
  color: var(--ink-3);
}
.knowledge-body {
  flex: 1;
  min-width: 0;
}
.knowledge-title {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.knowledge-title b {
  font-size: 15px;
}
.knowledge-title span {
  color: var(--coral-deep);
  font-size: 11px;
  background: var(--coral-soft);
  padding: 3px 6px;
  border-radius: 3px;
}
.weight-track {
  height: 6px;
  background: var(--bg-soft);
  border-radius: 3px;
  overflow: hidden;
  margin: 15px 0 10px;
}
.weight-track i {
  display: block;
  height: 100%;
  background: var(--coral);
  border-radius: 3px;
}
.knowledge-body p {
  color: var(--ink-2);
  font-size: 12px;
  line-height: 1.9;
  margin: 0;
}
.knowledge-source {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 10px;
  color: var(--ink-3);
  font-size: 11px;
}
.knowledge-weight {
  font: 500 30px var(--font-num);
}
.knowledge-weight small {
  font-size: 12px;
  margin-left: 3px;
}
@media (max-width: 680px) {
  .course-context { padding: 14px; flex-wrap: wrap; }
  .course-context p { flex: 1; min-width: 0; }
  .course-context a { width: 100%; margin-left: 26px; }
  .selected-course p { display: block; }
  .selected-course p > span { display: block; margin-top: 4px; }
  .natural-input { padding: 18px 14px; margin-bottom: 26px; }
  .natural-input-head { gap: 8px; }
  .natural-input-head label { font-size: 16px; }
  .natural-input-head > span { margin-left: 30px; width: 100%; }
  .natural-input :deep(.el-textarea__inner) { min-height: 210px; font-size: 14px; padding: 13px 13px 30px; }
  .result-controls { width: 100%; }
  .subject-picker {
    width: 100%;
  }
  .brief-form {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .brief-wide {
    grid-column: auto;
  }
  .brief-intro {
    gap: 12px;
  }
  .brief-intro h3 {
    font-size: 16px;
  }
  .brief-index {
    font-size: 28px;
  }
  .steps :deep(.el-step__description) {
    display: none;
  }
  .steps :deep(.el-step__title) {
    font-size: 12px;
  }
  .actions {
    flex-wrap: wrap;
    gap: 12px;
  }
  .material-link {
    width: 100%;
  }
  .result-head {
    flex-wrap: wrap;
    gap: 12px;
  }
  .result-head h3 {
    font-size: 19px;
  }
  .result-metrics {
    gap: 16px;
  }
  .result-metrics strong {
    font-size: 26px;
  }
  .result-metrics span {
    font-size: 10px;
  }
  .result-metrics a {
    width: 100%;
    margin-left: 0;
  }
  .knowledge-list article {
    gap: 12px;
    padding: 20px 0;
  }
  .knowledge-order {
    font-size: 13px;
  }
  .knowledge-title b {
    font-size: 13px;
  }
  .knowledge-title span {
    font-size: 10px;
  }
  .knowledge-weight {
    font-size: 24px;
  }
  .knowledge-source {
    font-size: 10px;
  }
  .hint {
    display: block;
    margin: 6px 0 0 !important;
  }
}
.steps {
  margin: 24px 0;
}
.step-card {
  max-width: 960px;
  margin: 0 auto;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}
.complete-alert {
  margin: 16px 0;
}
.complete-form {
  margin-top: 8px;
}
.unit {
  margin-left: 8px;
  color: var(--text-low);
}
.result-card {
  margin-bottom: 16px;
}
.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.result-head h3 {
  color: var(--text-hi);
}
.hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--text-low);
  font-weight: normal;
}
.focus-tag {
  margin-right: 8px;
}
.focus-basis {
  margin-top: 4px;
  color: var(--text-low);
  font-size: 13px;
}
.quiz-options {
  color: var(--text-mid);
  font-size: 14px;
  line-height: 2;
}
.quiz-answer {
  display: flex;
  align-items: center;
  gap: 12px;
}
.kp {
  color: var(--text-low);
  font-size: 13px;
}
.quiz-analysis {
  margin-top: 8px;
  color: var(--text-mid);
  font-size: 13px;
}
.mindmap-chart {
  width: 100%;
  height: 460px;
}
.type-block {
  margin-bottom: 8px;
}
.type-chart {
  width: 100%;
  height: 260px;
}
.type-table {
  margin-top: 4px;
}
.flash-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 8px 0 4px;
}
.flash-card {
  width: min(580px, 100%);
  height: 230px;
  perspective: 1200px;
  cursor: pointer;
}
.flash-inner {
  position: relative;
  width: 100%;
  height: 100%;
  transition: transform 0.5s;
  transform-style: preserve-3d;
}
.flash-card.flipped .flash-inner {
  transform: rotateY(180deg);
}
.flash-face {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
  backface-visibility: hidden;
  background: var(--bg-card);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}
.flash-back {
  transform: rotateY(180deg);
  background: var(--coral-soft);
}
.flash-label {
  font-size: 12px;
  color: var(--text-low);
}
.flash-text {
  margin: 0;
  font-size: 16px;
  line-height: 1.75;
  color: var(--text-hi);
  white-space: pre-wrap;
}
.flash-hint {
  font-size: 12px;
  color: var(--text-low);
}
.flash-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.flash-count {
  font-size: 13px;
  color: var(--text-mid);
  min-width: 64px;
  text-align: center;
}
.qa-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 340px;
  overflow-y: auto;
  padding: 4px 2px 8px;
}
.qa-row {
  display: flex;
  justify-content: flex-start;
}
.qa-row.user {
  justify-content: flex-end;
}
.qa-bubble {
  max-width: 78%;
  padding: 10px 12px;
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
}
.qa-row.user .qa-bubble {
  background: var(--coral-soft);
  border-color: var(--coral);
}
.qa-role {
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--text-low);
}
.qa-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-hi);
  white-space: pre-wrap;
}
.qa-input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 12px;
}
.qa-input-box {
  flex: 1;
}
.replan-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}
.replan-tip {
  font-size: 12px;
  color: var(--text-low);
}
.replan-note {
  margin-bottom: 14px;
}
.replan-title {
  margin: 4px 0 10px;
  font-size: 14px;
  color: var(--text-hi);
}
.weight-up {
  color: var(--red);
  font-weight: 600;
}
.mastery-note { font-size: 12px; line-height: 1.8; color: var(--ink-3); }
.mastery-line { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; font-size: 12px; color: var(--ink-2); }
.mastery-evidence { margin-top: 10px; font-size: 12px; line-height: 1.8; color: var(--ink-2); }
.mastery-evidence summary { cursor: pointer; }
.mastery-evidence p { overflow-wrap: anywhere; }
.weight-down {
  color: var(--green);
  font-weight: 600;
}
</style>
