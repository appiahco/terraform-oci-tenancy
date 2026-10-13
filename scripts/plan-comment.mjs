const marker = (root) => `<!-- terraform-plan:${root} -->`;
const escape = (text) => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

export function renderComment(root, plan, text, logUrl) {
  let creates = 0, updates = 0, deletes = 0, replacements = 0;
  for (const resource of plan.resource_changes ?? []) {
    if (resource.mode === 'data') continue;
    const actions = resource.change.actions;
    if (actions.includes('create')) creates++;
    if (actions.includes('update')) updates++;
    if (actions.includes('delete')) deletes++;
    if (actions.includes('create') && actions.includes('delete')) replacements++;
  }
  const header = `${marker(root)}\n### ${root} plan\n\n+${creates} ~${updates} -${deletes} (${replacements} replacements)\n\n` +
    (deletes ? '⚠️ This plan destroys or replaces resources. Review before merging.\n\n' : '') +
    (root === 'bootstrap' ? '**Bootstrap: apply manually after merge.**\n\n' : '');
  // Integration point for the Always Free advisory ticket: accept advisory content here when implemented.
  const advisory = '\n\n### Always Free advisory\n\nReserved for the Always Free advisory ticket; no cost assessment has run.\n';
  const details = `<details><summary>Plan text</summary>\n\n<pre>${escape(text)}</pre>\n</details>`;
  const body = header + details + advisory;
  return body.length <= 60000 ? body : header + `[Full plan log](${logUrl})` + advisory;
}

export async function updateComment({ github, context, root, plan, text }) {
  const issue_number = context.payload.pull_request.number;
  const logUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const body = renderComment(root, plan, text, logUrl);
  const comments = await github.paginate(github.rest.issues.listComments, { ...context.repo, issue_number });
  const existing = comments.find(c => c.user?.type === 'Bot' && c.body?.startsWith(marker(root)));
  if (existing) {
    await github.rest.issues.updateComment({ ...context.repo, comment_id: existing.id, body });
  } else {
    await github.rest.issues.createComment({ ...context.repo, issue_number, body });
  }
}
