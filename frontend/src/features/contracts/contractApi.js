/** HTTP operations mirror explicit server-side contract workflow transitions. */
import { requestJson, postJson, downloadContract } from '../../shared/httpClient'

const workspacePath = (id) => `/workspaces/${encodeURIComponent(id)}`

export const contractApi = {
  health: () => requestJson('/health'),
  download: (id) => downloadContract(id),
  list: () => requestJson('/workspaces'),
  get: (id) => requestJson(workspacePath(id)),
  activity: (id, signal) => requestJson(`${workspacePath(id)}/activity`, { signal }),
  create: (source) => postJson('/workspaces', source),
  analyze: (workspace) =>
    postJson(`${workspacePath(workspace.id)}/analyze`, { revision: workspace.revision }),
  selectTemplate: (workspace, templateId) =>
    postJson(`${workspacePath(workspace.id)}/template`, {
      revision: workspace.revision,
      template_id: templateId,
    }),
  extract: (workspace, replaceReviewed, retryFailed) =>
    postJson(`${workspacePath(workspace.id)}/extract`, {
      revision: workspace.revision,
      replace_reviewed: replaceReviewed,
      retry_failed: retryFailed,
    }),
  review: (workspace, decisions) =>
    requestJson(`${workspacePath(workspace.id)}/fields`, {
      method: 'PATCH',
      body: JSON.stringify({ revision: workspace.revision, decisions }),
    }),
  preview: (workspace) => requestJson(`${workspacePath(workspace.id)}/preview`),
  generate: (workspace, visualReviewAcknowledged = false) =>
    postJson(`${workspacePath(workspace.id)}/generate`, {
      revision: workspace.revision,
      preview_acknowledged: true,
      visual_review_acknowledged: visualReviewAcknowledged,
    }),
  rename: (workspace, title) =>
    requestJson(workspacePath(workspace.id), {
      method: 'PATCH',
      body: JSON.stringify({ revision: workspace.revision, title }),
    }),
  remove: (id) => requestJson(workspacePath(id), { method: 'DELETE' }),
  browseTemplates: (filters) => requestJson(`/contracts/templates?${new URLSearchParams(filters)}`),
  templateDetails: (id) => requestJson(`/contracts/templates/${encodeURIComponent(id)}`),
  parseSource: (file) => {
    const body = new FormData()
    body.append('file', file)
    return requestJson('/sources/parse', { method: 'POST', body })
  },
}
