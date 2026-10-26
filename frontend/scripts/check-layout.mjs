/** @file 使用真实浏览器与模拟 API 检查控件间距；不访问业务后端、用户数据库或真实 LLM。 */
import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const modulePath = process.env.CONTRACTWEAVER_PUPPETEER_MODULE
const browserPath = process.env.CONTRACTWEAVER_BROWSER
assert(
  modulePath && browserPath,
  'Set CONTRACTWEAVER_PUPPETEER_MODULE and CONTRACTWEAVER_BROWSER to existing local tools.'
)
const { default: puppeteer } = await import(pathToFileURL(modulePath).href)
const browser = await puppeteer.launch({ executablePath: browserPath, headless: true })
const baseUrl = process.env.CONTRACTWEAVER_LAYOUT_URL || 'http://127.0.0.1:5198'
const report = []

/** 为每次视口检查创建新夹具，不能复用生产任务或真实密钥。 */
function fixture(ready) {
  /** 创建一个字段快照，审核态只由当前虚构场景决定。 */
  const field = (name, value) => ({
    name,
    display_name: name,
    value,
    extracted_value: value,
    status: ready ? (value ? 'confirmed' : 'omitted') : value ? 'extracted' : 'missing',
    context: `合同填写：{${name}}`,
    evidence: [],
    alternatives: [],
    review_issues: [],
    note: '',
    user_note: '',
  })
  return {
    id: 'layout-fixture',
    title: '布局验证保管合同',
    source_name: '虚构会议纪要',
    source_text: '双方确认保管费3000元，账号尚未提供。',
    revision: ready ? 3 : 2,
    stage: ready ? 'ready_to_generate' : 'field_review',
    fields: [field('保管人', '示例保管公司'), field('费用', '3000元'), field('账号', ''), field('签字', '')],
    selected_template: {
      id: 'template-fixture',
      name: '保管合同（布局夹具）',
      requires_visual_review: true,
      warnings: [],
    },
    analysis: null,
    recommendations: [],
    extraction_failures: [],
    coverage_gaps: [],
    coverage_status: 'completed',
    artifacts: [],
    events: [],
    agent_questions: [],
    coordination_warnings: [],
    last_run: {},
  }
}

/** 按可见名称点击组件按钮，避免依赖含义不清的元素索引。 */
async function clickText(page, text) {
  await page.evaluate((label) => {
    const button = [...document.querySelectorAll('button')].find((item) => item.textContent.trim() === label)
    if (!button) throw new Error(`Missing button: ${label}`)
    button.click()
  }, text)
}

try {
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    const page = await browser.newPage()
    await page.setViewport(viewport)
    let ready = false
    await page.evaluateOnNewDocument(() =>
      sessionStorage.setItem(
        'contractweaver.session',
        JSON.stringify({
          access_token: 'layout-test-only',
          expires_at: '2099-01-01T00:00:00Z',
          user: { email: 'layout@example.org' },
        })
      )
    )
    await page.setRequestInterception(true)
    page.on('request', async (request) => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/v1/')) return request.continue()
      let body
      if (url.pathname.endsWith('/health'))
        body = { model_configured: true, max_source_chars: 60000, max_upload_bytes: 5242880 }
      else if (url.pathname.endsWith('/activity')) body = { status: 'idle' }
      else if (url.pathname.endsWith('/preview'))
        body = {
          revision: 3,
          pending_count: 0,
          omitted_fields: ['账号', '签字'],
          blocks: [{ type: 'paragraph', text: '虚构保管合同：费用3000元。未确定事项暂留空。' }],
        }
      else if (url.pathname.endsWith('/contracts/templates')) body = { items: [], total: 0, limit: 24 }
      else if (url.pathname.endsWith('/workspaces'))
        body = [
          {
            id: 'layout-fixture',
            title: '布局验证保管合同',
            stage: ready ? 'ready_to_generate' : 'field_review',
          },
        ]
      else if (url.pathname.endsWith('/workspaces/layout-fixture')) body = fixture(ready)
      else throw new Error(`Unexpected API in fixture: ${url.pathname}`)
      await request.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    })
    await page.goto(baseUrl, { waitUntil: 'networkidle0' })
    await page.waitForSelector('.task-row button')
    await page.click('.task-row button')
    await page.waitForSelector('.review-toolbar')
    await page.waitForFunction(
      () => document.querySelector('.review-toolbar').getBoundingClientRect().height > 0
    )
    const gaps = await page.evaluate(() => {
      /** 读取实际 CSS 布局盒，不能以样式字符串代替浏览器几何结果。 */
      const box = (selector) => document.querySelector(selector).getBoundingClientRect()
      return {
        ignoreToShortcuts: box('.review-shortcuts').top - box('.ignore-unknown-tools').bottom,
        bulkToActions:
          box('.review-toolbar > .inline-actions:last-child').top - box('.bulk-blank-tools').bottom,
        horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth,
      }
    })
    assert(gaps.ignoreToShortcuts >= 12, JSON.stringify(gaps))
    assert(gaps.bulkToActions >= 12, JSON.stringify(gaps))
    assert(gaps.horizontalOverflow <= 1, JSON.stringify(gaps))
    await (
      await page.$('.review-toolbar')
    ).screenshot({ path: path.join(root, `figures/review-spacing-${viewport.width}.png`) })

    ready = true
    await page.reload({ waitUntil: 'networkidle0' })
    await page.click('.task-row button')
    await page.waitForSelector('.preview-panel')
    await clickText(page, '载入预览')
    await page.waitForSelector('.contract-paper')
    const previewGaps = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('.preview-panel > .checkbox-label')].map((item) =>
        item.getBoundingClientRect()
      )
      const button = document.querySelector('.generate-button').getBoundingClientRect()
      return {
        checkboxGroups: labels[1].top - labels[0].bottom,
        approvalToGenerate: button.top - labels[1].bottom,
      }
    })
    assert(previewGaps.checkboxGroups >= 12, JSON.stringify(previewGaps))
    assert(previewGaps.approvalToGenerate >= 16, JSON.stringify(previewGaps))
    await (
      await page.$('.preview-panel')
    ).screenshot({ path: path.join(root, `figures/preview-spacing-${viewport.width}.png`) })
    report.push({ viewport, review: gaps, preview: previewGaps })
    await page.close()
  }
  console.log(JSON.stringify(report, null, 2))
} finally {
  await browser.close()
}
