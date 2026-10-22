<script setup>
import { computed } from 'vue'
const props = defineProps({ label: String, elapsed: Number, activity: Object, warning: String })
const batches = computed(() => props.activity?.batches || [])
const completed = computed(
  () => batches.value.filter((batch) => ['completed', 'failed'].includes(batch.status)).length
)
const labels = {
  queued: '排队',
  extracting: '提取中',
  reviewing: '复核中',
  repairing: '主控定向修正中',
  completed: '完成',
  failed: '失败，可重试',
}
const running = computed(() => Boolean(props.label) || props.activity?.status === 'running')
const harness = computed(() => props.activity?.harness)
const stepLabels = { running: '运行中', completed: '完成', failed: '失败', interrupted: '已中断' }
const actionLabels = {
  analyze_record: '分析记录',
  retrieve_templates: '检索模板',
  repair_fields: '定向修正',
  request_user: '请用户补充',
  handoff: '交回用户审核',
}
</script>

<template>
  <section class="operation-card" role="status" aria-live="polite" :aria-busy="running">
    <div class="inline-actions">
      <span v-if="running" class="loading-spinner" aria-hidden="true" />
      <strong>
        {{
          label ||
          (activity?.status === 'running'
            ? '服务器正在处理此任务'
            : activity?.status === 'partial'
              ? '部分处理完成，需要重试'
              : ['failed', 'interrupted'].includes(activity?.status)
                ? '处理未完成'
                : '最近一次处理已结束')
        }}
      </strong>
      <span>{{ label ? elapsed : activity?.elapsed_seconds || 0 }} 秒</span>
    </div>
    <p>{{ activity?.message || '正在等待服务器响应。无需重复点击；请保持此页面打开。' }}</p>
    <p v-if="activity?.requests_started" class="small-note">
      实际模型请求 {{ activity.requests_started }} 次 · 收到成功 HTTP 响应
      {{ activity.responses_received }} 次 · 请求失败 {{ activity.requests_failed }} 次 · {{ activity.model }}
      <br />
      收到响应不等于字段提取正确，仍需校验和人工审查。
    </p>
    <p v-else-if="activity && !label" class="small-note">
      此处理记录没有可核验的模型请求计数；不能据此断言模型已成功调用。
    </p>
    <template v-if="batches.length">
      <progress
        :value="completed"
        :max="batches.length"
        :aria-label="`已处理 ${completed} / ${batches.length} 批`"
      />
      <p>已处理 {{ completed }} / {{ batches.length }} 批（含失败批次），不是合同审核完成率。</p>
      <div class="batch-grid">
        <span
          v-for="batch in batches"
          :key="batch.index"
          :class="`batch-${batch.status}`"
          :title="batch.message"
        >
          第 {{ batch.index }} 批 · {{ labels[batch.status] }}
        </span>
      </div>
    </template>
    <div v-else-if="running" class="indeterminate-track"><span /></div>
    <details v-if="harness" class="harness-trace">
      <summary>查看 Agent 执行计划与决策摘要 · {{ harness.steps?.length || 0 }} 个步骤</summary>
      <p class="small-note">
        以下是实际执行轨迹和模型提供的简短结论说明，不是内部完整思维链，也不代表已获人工确认。
      </p>
      <p v-if="harness.plan_kind === 'capability_catalog'" class="small-note">
        可用能力清单（不是固定执行顺序）；下方轨迹记录主控实际选择的动作。
      </p>
      <ol>
        <li v-for="item in harness.plan" :key="item.name">{{ item.label }}</li>
      </ol>
      <p class="small-note">
        思考模式：{{ harness.thinking_mode }} · 推理强度：{{ harness.reasoning_effort }} · 请求预算：{{
          harness.model_requests
        }}
        / {{ harness.limits.requests }}
      </p>
      <p v-if="harness.token_usage?.total_tokens" class="small-note">
        服务商报告的累计 Token：{{ harness.token_usage.total_tokens }}（并非费用金额）
      </p>
      <p v-if="harness.steps?.length > 60" class="small-note">
        此处展示最近 60 步；完整记录可从任务 runs 接口读取。
      </p>
      <article v-for="step in (harness.steps || []).slice(-60)" :key="step.index">
        <strong>{{ step.index }}. {{ step.label }} · {{ stepLabels[step.status] || step.status }}</strong>
        <span v-if="step.elapsed_seconds !== undefined">· {{ step.elapsed_seconds }} 秒</span>
        <p v-if="step.chosen_action">
          主控选择：{{ actionLabels[step.chosen_action] || step.chosen_action }}
          <span v-if="step.target_count">· {{ step.target_count }} 个目标字段</span>
        </p>
        <p v-if="step.decision_summary">决策摘要：{{ step.decision_summary }}</p>
        <p v-else class="small-note">
          {{ step.status === 'running' ? '等待本步骤返回结果' : '此步骤未提供模型决策摘要' }}
        </p>
        <p v-if="step.error_type" class="review-issue">
          {{ step.error_type }}：此步骤未完成，请查看任务错误并重试或人工补充。
        </p>
      </article>
    </details>
    <p v-if="warning" class="review-issue">{{ warning }}</p>
  </section>
</template>
