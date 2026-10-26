/** @file 将内部 Word 定位转换为面向用户的可读标签。 */
/**
 * 优先展示业务标签，避免把内部 Word 定位名直接暴露给用户。
 * @param {Object} field 字段元数据与审核状态。
 */
export function fieldLabel(field) {
  if (field.display_name) return field.display_name
  const label = field.name
    .replace(/·位置.*$/, '')
    .replace(/^.*第[一二三四五六七八九十百]+条/, '')
    .replace(/[：:]+$/, '')
  if (label.startsWith('表格空白')) return '表格中的待填写单元格'
  return label.split(/[：:]/).filter(Boolean).at(-1) || '待核对空白'
}
/**
 * 将内部字段标记转换为可读空白提示，不改变后端字段映射。
 * @param {string} text 待转换为可读内容的文字。
 */
export function readableText(text = '') {
  return text.replace(/\{[^{}]+\}/g, '________')
}
