/** @file 只读检查模块说明与具名 JavaScript 函数的 JSDoc；匿名回调由所属操作说明覆盖。 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse } from '@babel/parser'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const failures = []
let filesChecked = 0
let functionsChecked = 0

/** 递归枚举受控源码目录，不读取依赖缓存或用户文件。 */
function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(directory, entry.name)
    return entry.isDirectory() ? sourceFiles(filename) : [filename]
  })
}

/** 检查紧邻声明前是否存在 JSDoc，普通行注释不能替代函数说明。 */
function hasFunctionDoc(script, position) {
  const lineStart = script.lastIndexOf('\n', position - 1) + 1
  const preceding = script.slice(0, lineStart).trimEnd()
  const start = preceding.lastIndexOf('/**')
  return start >= 0 && preceding.indexOf('*/', start) === preceding.length - 2
}

/** 检查声明、赋值函数及单独成行的 API 方法，不强迫给每个 map 回调重复写注释。 */
function inspectNode(node, script, filename) {
  if (!node || typeof node !== 'object') return
  let name = null
  if (node.type === 'FunctionDeclaration') name = node.id.name
  if (
    node.type === 'VariableDeclarator' &&
    ['ArrowFunctionExpression', 'FunctionExpression'].includes(node.init?.type)
  )
    name = node.id.name
  if (
    node.type === 'ObjectProperty' &&
    ['ArrowFunctionExpression', 'FunctionExpression'].includes(node.value?.type)
  ) {
    const prefix = script.slice(script.lastIndexOf('\n', node.start - 1) + 1, node.start)
    if (!prefix.trim()) name = node.key.name || node.key.value
  }
  if (name) {
    functionsChecked++
    if (!hasFunctionDoc(script, node.start)) failures.push(`${filename}:${node.loc.start.line} ${name}`)
  }
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'comments', 'leadingComments', 'trailingComments', 'innerComments', 'extra'].includes(key))
      continue
    if (Array.isArray(value)) value.forEach((child) => inspectNode(child, script, filename))
    else if (value && typeof value === 'object') inspectNode(value, script, filename)
  }
}

for (const filename of [
  ...sourceFiles(path.join(frontendRoot, 'src')),
  ...sourceFiles(path.join(frontendRoot, 'scripts')),
]) {
  if (!['.vue', '.js', '.mjs', '.css'].includes(path.extname(filename))) continue
  filesChecked++
  const source = fs.readFileSync(filename, 'utf8')
  if (!source.includes('@file')) failures.push(`${filename}:1 @file`)
  if (filename.endsWith('.css')) continue
  const script = filename.endsWith('.vue')
    ? /<script\b[^>]*>([\s\S]*?)<\/script>/.exec(source)?.[1] || ''
    : source
  inspectNode(parse(script, { sourceType: 'module' }), script, filename)
}
console.log(JSON.stringify({ filesChecked, functionsChecked, missing: failures }, null, 2))
if (failures.length) process.exitCode = 1
