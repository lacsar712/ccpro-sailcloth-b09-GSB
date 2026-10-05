<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api'

const logs = ref([])
const rolls = ref([])
const loading = ref(false)
const error = ref('')
const filterRollId = ref('')

const sourceLabel = { panel: '晾晒架面板', ledger: '布卷台账' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [r, l] = await Promise.all([api.get('/rolls/'), api.get('/weight-logs/')])
    rolls.value = r.data.results || r.data
    logs.value = l.data.results || l.data
  } catch {
    error.value = '克重审计加载失败'
  } finally {
    loading.value = false
  }
}

const shownLogs = computed(() =>
  filterRollId.value
    ? logs.value.filter((row) => row.rollId === Number(filterRollId.value))
    : logs.value
)

onMounted(load)
</script>

<template>
  <div>
    <h1>克重审计</h1>
    <p class="sub">
      记录每次克重改写：谁、何时、把哪一卷的克重从旧值改到新值，以及写入入口（晾晒架面板 / 布卷台账）。
      本页只读，所有记录均由布卷接口在校验通过后自动产生。
    </p>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="panel row audit-toolbar">
      <label>按布卷筛选
        <select v-model="filterRollId">
          <option value="">全部布卷</option>
          <option v-for="r in rolls" :key="r.id" :value="r.id">
            {{ r.loftName }} / {{ r.rollCode }}
          </option>
        </select>
      </label>
      <button class="btn secondary" type="button" :disabled="loading" @click="load">刷新</button>
      <span class="hint">共 {{ shownLogs.length }} 条改写记录</span>
    </div>

    <table>
      <thead>
        <tr>
          <th>时间</th>
          <th>帆布间</th>
          <th>卷号</th>
          <th>旧克重</th>
          <th>新克重</th>
          <th>操作人</th>
          <th>写入入口</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in shownLogs" :key="row.id">
          <td>{{ new Date(row.changedAt).toLocaleString() }}</td>
          <td>{{ row.loftName }}</td>
          <td>{{ row.rollCode }}</td>
          <td class="num old-weight">{{ row.oldValue }}</td>
          <td class="num new-weight">{{ row.newValue }}</td>
          <td>{{ row.changedBy }}</td>
          <td>
            <span class="badge" :class="row.source === 'panel' ? 'badge-dipping' : 'badge-raw'">
              {{ sourceLabel[row.source] || row.sourceLabel || row.source }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!shownLogs.length && !loading" class="hint empty-audit">尚无克重改写记录</p>
  </div>
</template>

<style scoped>
.audit-toolbar {
  gap: 16px;
}
.num {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.old-weight {
  color: var(--muted);
}
.old-weight::after {
  content: ' →';
}
.new-weight {
  color: var(--navy);
}
.empty-audit {
  margin-top: 16px;
}
</style>
