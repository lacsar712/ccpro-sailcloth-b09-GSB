<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')

const rolls = ref([])
const lofts = ref([])
const error = ref('')
const editing = ref(null)
const editingRow = ref(null)
const form = reactive({
  loftId: null,
  rollCode: '',
  status: 'raw',
  fabricWeightGsm: 380,
  notes: '',
})

const statusLabel = { raw: '原布', dipping: '浸渍中', cured: '已固化' }

// 编辑中的卷，克重输入是否允许改：
// 已固化全员锁定；工人只能在仍是出厂默认 380 时首写；管理员可改任意未固化卷。
const weightLocked = computed(() => {
  const row = editingRow.value
  if (!row) return false // 新建：可直接填实测克重（首写）
  if (row.status === 'cured') return true
  if (!isAdmin.value && row.fabricWeightGsm !== 380) return true
  return false
})
const weightLockHint = computed(() => {
  const row = editingRow.value
  if (!row) return ''
  if (row.status === 'cured') return '已固化卷克重已锁定，任何人不得修改'
  if (!isAdmin.value && row.fabricWeightGsm !== 380)
    return '操作工只能首写出厂默认 380；该卷克重已改写，如需更正请联系管理员'
  return ''
})

function firstError(data) {
  if (!data) return ''
  if (data.detail) return data.detail
  for (const key of ['fabricWeightGsm', 'expectedVersion', 'status', 'rollCode', 'non_field_errors']) {
    if (Array.isArray(data[key])) return data[key][0]
    if (typeof data[key] === 'string') return data[key]
  }
  return '保存失败'
}

async function load() {
  error.value = ''
  try {
    const [r, l] = await Promise.all([api.get('/rolls/'), api.get('/lofts/')])
    rolls.value = r.data.results || r.data
    lofts.value = l.data.results || l.data
    if (!form.loftId && lofts.value.length) form.loftId = lofts.value[0].id
  } catch {
    error.value = '加载失败'
  }
}

function startEdit(row) {
  editing.value = row.id
  editingRow.value = row
  form.loftId = row.loftId
  form.rollCode = row.rollCode
  form.status = row.status
  form.fabricWeightGsm = row.fabricWeightGsm
  form.notes = row.notes || ''
}

function resetForm() {
  editing.value = null
  editingRow.value = null
  form.rollCode = ''
  form.status = 'raw'
  form.fabricWeightGsm = 380
  form.notes = ''
  if (lofts.value.length) form.loftId = lofts.value[0].id
}

async function save() {
  error.value = ''
  try {
    if (editing.value) {
      const payload = { ...form, source: 'ledger' }
      // 乐观锁版本：克重实际变化时后端强制校验
      if (editingRow.value) payload.expectedVersion = editingRow.value.version
      await api.patch(`/rolls/${editing.value}/`, payload)
    } else {
      await api.post('/rolls/', { ...form, source: 'ledger' })
    }
    resetForm()
    await load()
  } catch (e) {
    error.value = firstError(e.response?.data)
    // 409 或越界后刷新，避免继续拿旧版本号提交
    if (e.response?.status === 409 || e.response?.status === 403) {
      resetForm()
      await load()
    }
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>布卷台账</h1>
    <p class="sub">次要列表入口。日常请在晾晒架点选布卷操作；此处用于新建/改卷号等台账维护。标「已固化」仍受固化时长 ≥ 12 小时约束。</p>
    <p v-if="error" class="error">{{ error }}</p>

    <form class="panel row" @submit.prevent="save">
      <label>帆布间
        <select v-model.number="form.loftId" required>
          <option v-for="l in lofts" :key="l.id" :value="l.id">{{ l.name }}</option>
        </select>
      </label>
      <label>卷号
        <input v-model="form.rollCode" required />
      </label>
      <label>状态
        <select v-model="form.status">
          <option value="raw">原布</option>
          <option value="dipping">浸渍中</option>
          <option value="cured">已固化</option>
        </select>
      </label>
      <label>克重 gsm
        <input v-model.number="form.fabricWeightGsm" type="number" :disabled="weightLocked" />
      </label>
      <label>备注
        <input v-model="form.notes" />
      </label>
      <button class="btn" type="submit">{{ editing ? '更新' : '新建' }}</button>
      <button v-if="editing" class="btn secondary" type="button" @click="resetForm">取消</button>
    </form>
    <p v-if="weightLockHint" class="hint weight-lock-note">🔒 {{ weightLockHint }}</p>

    <table>
      <thead>
        <tr>
          <th>帆布间</th>
          <th>卷号</th>
          <th>状态</th>
          <th>克重</th>
          <th>备注</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rolls" :key="row.id">
          <td>{{ row.loftName }}</td>
          <td>{{ row.rollCode }}</td>
          <td><span class="badge" :class="'badge-' + row.status">{{ statusLabel[row.status] || row.status }}</span></td>
          <td>
            {{ row.fabricWeightGsm }}
            <span v-if="row.status === 'cured'" title="已固化锁定">🔒</span>
          </td>
          <td>{{ row.notes }}</td>
          <td><button class="btn secondary" type="button" @click="startEdit(row)">编辑</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.weight-lock-note {
  margin: -8px 0 18px;
  padding: 8px 12px;
  border-left: 3px solid var(--accent);
  background: rgba(196, 163, 90, 0.12);
  border-radius: 0 8px 8px 0;
}
input:disabled {
  background: var(--canvas-deep);
  color: var(--muted);
  cursor: not-allowed;
}
</style>
