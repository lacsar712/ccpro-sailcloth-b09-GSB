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
const form = reactive({
  loftId: null,
  rollCode: '',
  status: 'raw',
  fabricWeightGsm: 380,
  expectedVersion: 0,
  notes: '',
})

const statusLabel = { raw: '原布', dipping: '浸渍中', cured: '已固化' }

// 编辑态下克重输入是否可写：
// 管理员可改任意未固化卷；操作工只能把仍是 380 的克重首写为非 380；已固化全员锁定。
const weightLocked = computed(() => {
  if (!editing.value) return true
  const row = rolls.value.find((r) => r.id === editing.value)
  if (!row) return true
  if (row.status === 'cured') return true
  if (isAdmin.value) return false
  return row.fabricWeightGsm !== 380
})

const weightLockHint = computed(() => {
  const row = rolls.value.find((r) => r.id === editing.value)
  if (!row) return '新建布卷的克重恒为出厂默认 380，创建后再首写'
  if (row.status === 'cured') return '该布卷已固化，克重全员不可修改'
  if (!isAdmin.value && row.fabricWeightGsm !== 380)
    return '操作工只能写入首个非出厂克重；再改须由管理员进行'
  return ''
})

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
  form.loftId = row.loftId
  form.rollCode = row.rollCode
  form.status = row.status
  form.fabricWeightGsm = row.fabricWeightGsm
  form.expectedVersion = row.version ?? 0
  form.notes = row.notes || ''
}

function resetForm() {
  editing.value = null
  form.rollCode = ''
  form.status = 'raw'
  form.fabricWeightGsm = 380
  form.expectedVersion = 0
  form.notes = ''
  if (lofts.value.length) form.loftId = lofts.value[0].id
}

function extractError(data) {
  return (
    data?.detail ||
    data?.fabricWeightGsm?.[0] ||
    data?.expectedVersion?.[0] ||
    data?.status?.[0] ||
    data?.rollCode?.[0] ||
    '保存失败（若标为已固化，请确认最近浸渍固化时长 ≥ 12 小时）'
  )
}

async function save() {
  error.value = ''
  try {
    if (editing.value) {
      await api.patch(`/rolls/${editing.value}/`, {
        loftId: form.loftId,
        rollCode: form.rollCode,
        status: form.status,
        fabricWeightGsm: form.fabricWeightGsm,
        expectedVersion: form.expectedVersion,
        notes: form.notes,
      })
    } else {
      await api.post('/rolls/', { ...form })
    }
    resetForm()
    await load()
  } catch (e) {
    const data = e.response?.data
    error.value = extractError(data)
    // 409：克重刚被他人改写；403：无权限。都以服务器现状为准刷新列表。
    if (e.response?.status === 409 || e.response?.status === 403) {
      const row = rolls.value.find((r) => r.id === editing.value)
      await load()
      if (row && e.response?.status === 409) {
        const fresh = rolls.value.find((r) => r.id === row.id)
        if (fresh) startEdit(fresh)
      }
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
        <input
          v-model.number="form.fabricWeightGsm"
          type="number"
          :disabled="weightLocked"
          :title="weightLockHint"
        />
        <small v-if="weightLockHint" class="field-hint">{{ weightLockHint }}</small>
      </label>
      <label>备注
        <input v-model="form.notes" />
      </label>
      <button class="btn" type="submit">{{ editing ? '更新' : '新建' }}</button>
      <button v-if="editing" class="btn secondary" type="button" @click="resetForm">取消</button>
    </form>

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
          <td>{{ row.fabricWeightGsm }}</td>
          <td>{{ row.notes }}</td>
          <td><button class="btn secondary" type="button" @click="startEdit(row)">编辑</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
