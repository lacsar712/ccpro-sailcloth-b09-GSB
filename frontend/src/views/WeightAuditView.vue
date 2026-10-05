<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'

const audits = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/weight-audits/')
    audits.value = data.results || data
  } catch {
    error.value = '克重审计加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <header class="rack-head" style="margin-bottom: 16px">
      <div>
        <h1>克重审计</h1>
        <p class="sub">记录每一次克重改写：谁、在何时、把哪一卷的克重从旧值改到新值。只读，任何人不得在此修改。</p>
      </div>
      <button class="btn secondary" type="button" :disabled="loading" @click="load">刷新</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <table>
      <thead>
        <tr>
          <th>时间</th>
          <th>帆布间</th>
          <th>卷号</th>
          <th>修改人</th>
          <th>旧克重</th>
          <th>新克重</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in audits" :key="row.id">
          <td>{{ new Date(row.changedAt).toLocaleString() }}</td>
          <td>{{ row.loftName }}</td>
          <td>{{ row.rollCode }}</td>
          <td>{{ row.changedBy }}</td>
          <td>{{ row.oldValue }}</td>
          <td><strong>{{ row.newValue }}</strong></td>
        </tr>
      </tbody>
    </table>
    <p v-if="!audits.length && !error" class="hint">
      {{ loading ? '加载中…' : '暂无克重修改记录' }}
    </p>
  </div>
</template>
