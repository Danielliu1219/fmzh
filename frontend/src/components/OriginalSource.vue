<template>
  <section class="original-source">
    <p v-if="USE_MOCK" class="original-note">演示模式不包含私人原文件；本地应用支持查看原页与下载。</p>
    <div v-else class="original-actions">
      <el-button v-if="canPreview" :loading="busy" @click="loadImage">{{ imageUrl ? '重新加载原页' : '查看原页图片' }}</el-button>
      <el-select v-if="pages.length > 1" v-model="page" aria-label="选择原文页码" @change="loadImage">
        <el-option v-for="number in pages" :key="number" :value="number" :label="`第 ${number} 页`" />
      </el-select>
      <el-button :loading="downloading" @click="download">下载原文件</el-button>
    </div>
    <p class="original-note">{{ note }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <a v-if="imageUrl" :href="imageUrl" target="_blank" rel="noopener" title="在新标签页放大原页"><img :src="imageUrl" :alt="`${title} ${page ? '第 '+page+' 页' : '原图'}`" /></a>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { sourceApi } from '../api/studySources'
import { USE_MOCK } from '../mock/dashboard'
const props=defineProps({materialId:Number,fileType:String,title:String,pages:{type:Array,default:()=>[]},unitId:String,revision:String,autoPreview:Boolean})
const page=ref(null), imageUrl=ref(''),busy=ref(false),downloading=ref(false),error=ref('')
let revision=0
const canPreview=computed(()=>['png','jpg','jpeg'].includes(props.fileType) || (props.fileType==='pdf' && props.pages.length))
const note=computed(()=>props.fileType==='pdf' ? '原页保留排版与公式，查看不消耗 Token。整页可能包含相邻题目，可点击图片放大。' : ['png','jpg','jpeg'].includes(props.fileType) ? '显示上传的原始图片，查看不消耗 Token，识别文字仅供检索。' : '课件按幻灯片号定位，Word 按段落定位；请下载原文件核对排版与公式。')
function clear(){ if(imageUrl.value) URL.revokeObjectURL(imageUrl.value); imageUrl.value='' }
function params(download=false){return {unit_id:props.unitId || undefined,revision:props.revision || undefined,page:props.fileType==='pdf' ? page.value : undefined,download}}
async function loadImage(){
  if(USE_MOCK)return
  const current=revision;busy.value=true;error.value=''
  try {
    const blob=await sourceApi.original(props.materialId,params())
    if(current!==revision)return
    if(!blob.type.startsWith('image/')) throw new Error('该资料无法直接预览，请下载原文件。')
    clear(); imageUrl.value=URL.createObjectURL(blob)
  } catch(e){if(current===revision)error.value=e.message || '原页加载失败，请下载原文件。'}
  finally{if(current===revision)busy.value=false}
}
async function download(){
  if(USE_MOCK)return
  downloading.value=true
  try {
    const blob=await sourceApi.original(props.materialId,params(true))
    const url=URL.createObjectURL(blob),link=document.createElement('a')
    link.href=url;link.download=`${props.title || '原文件'}.${props.fileType}`;link.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  } finally{downloading.value=false}
}
watch(()=>[props.materialId,props.unitId,props.revision,props.pages.join(',')],()=>{revision++;clear();page.value=props.pages[0]||null;error.value='';busy.value=false;if(props.autoPreview && canPreview.value)loadImage()},{immediate:true})
onBeforeUnmount(()=>{revision++;clear()})
</script>

<style scoped>
.original-source { margin: 16px 0; }
.original-actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.original-actions .el-select { width:140px; }
.original-note { font-size:12px; line-height:1.8; color:var(--ink-3); }
img { display:block; width:100%; height:auto; background:#fff; border:1px solid var(--line); }
</style>
