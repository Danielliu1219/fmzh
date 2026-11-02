export const MATERIAL_EXTENSIONS = new Set(['txt', 'pdf', 'docx', 'ppt', 'pptx', 'png', 'jpg', 'jpeg'])
export const MAX_MATERIAL_BYTES = 20 * 1024 * 1024
export const uploadPath = file => file.webkitRelativePath || file.name
export const uploadKey = file => `${uploadPath(file)}:${file.size}:${file.lastModified || 0}`
export const uploadBytes = queue => queue.reduce((sum, item) => sum + item.raw.size, 0)
export const uploadTitle = file => file.name.replace(/\.[^.]+$/, '').slice(0, 128) || file.name.slice(0, 128)

// 目录仅作本地选择；上传始终使用独立文件，不把本机目录写进服务端路径。
export function addUploadFiles(queue, files, remainingBytes = Infinity) {
  const accepted = [...queue], rejected = [], known = new Set(queue.map(item => uploadKey(item.raw)))
  let bytes = uploadBytes(queue)
  for (const raw of files) {
    const key = uploadKey(raw)
    if (known.has(key)) continue
    let reason = ''
    if (!MATERIAL_EXTENSIONS.has(raw.name.split('.').pop().toLowerCase())) reason = '格式不支持'
    else if (!raw.size) reason = '文件为空'
    else if (raw.size > MAX_MATERIAL_BYTES) reason = '单个文件超过20MB'
    else if (bytes + raw.size > remainingBytes) reason = '超出剩余资料容量'
    if (reason) { rejected.push({ name: uploadPath(raw), reason }); continue }
    accepted.push({ id: key, raw, path: uploadPath(raw), error: '' })
    known.add(key); bytes += raw.size
  }
  return { accepted, rejected }
}

// 成功项立即移出暂存区；失败项保留，重试不会再次上传已经成功的文件。
export async function runUploadBatch(queue, uploadOne, onSettled = () => {}) {
  const succeeded = [], failed = []
  for (const item of [...queue]) {
    try {
      const material = await uploadOne(item.raw)
      succeeded.push(material)
      onSettled(item, null, material)
    } catch (error) {
      failed.push(item)
      onSettled(item, error)
      if (error?.response?.status === 401) break
    }
  }
  return { succeeded, failed }
}
