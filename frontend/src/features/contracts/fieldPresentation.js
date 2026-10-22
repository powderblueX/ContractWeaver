/** Internal field names stay in API payloads, never in the reading experience. */
export function fieldLabel(field) {
  if (field.display_name) return field.display_name
  const label = field.name
    .replace(/·位置.*$/, '')
    .replace(/^.*第[一二三四五六七八九十百]+条/, '')
    .replace(/[：:]+$/, '')
  if (label.startsWith('表格空白')) return '表格中的待填写单元格'
  return label.split(/[：:]/).filter(Boolean).at(-1) || '待核对空白'
}
export function readableText(text = '') {
  return text.replace(/\{[^{}]+\}/g, '________')
}
