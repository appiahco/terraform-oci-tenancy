import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderComment, updateComment } from '../scripts/plan-comment.mjs';

const plan = { resource_changes: [
  { mode: 'managed', change: { actions: ['create'] } },
  { mode: 'managed', change: { actions: ['update'] } },
  { mode: 'managed', change: { actions: ['delete'] } },
  { mode: 'managed', change: { actions: ['delete', 'create'] } },
  { mode: 'managed', change: { actions: ['create', 'delete'] } },
  { mode: 'data', change: { actions: ['read'] } },
] };
test('summarizes changes and both replacement orderings', () => {
  const body = renderComment('bootstrap', plan, 'plan text', 'https://example.test/log');
  assert.match(body, /\+3 ~1 -3/);
  assert.match(body, /2 replacements/);
  assert.match(body, /⚠️/);
  assert.match(body, /apply manually after merge/);
  assert.match(body, /<details>/);
  assert.match(body, /Always Free advisory/);
});
test('oversized and malicious-looking plan output stays within comment limit', () => {
  const body = renderComment('foundation', plan, '</pre>' + 'x'.repeat(61000), 'https://example.test/log');
  assert.ok(body.length < 60000);
  assert.match(body, /Full plan log/);
  const small = renderComment('workloads', {}, '</pre><script>oops</script>', 'url');
  assert.ok(!small.includes('<script>'));
  assert.ok(!small.includes('⚠️'));
});
test('creates then updates one sticky comment for the same Root', async () => {
  const comments = [{ id: 10, user: { type: 'User' }, body: '<!-- terraform-plan:foundation -->' }];
  const writes = [];
  const github = {
    paginate: async () => comments,
    rest: { issues: {
      listComments() {},
      createComment: async (args) => {
        writes.push(['create', args]);
        comments.push({ id: 11, user: { type: 'Bot' }, body: args.body });
      },
      updateComment: async (args) => writes.push(['update', args]),
    } },
  };
  const args = { github, root: 'foundation', plan, text: 'text', context: {
    repo: { owner: 'owner', repo: 'repo' }, payload: { pull_request: { number: 23 } },
    serverUrl: 'https://github.com', runId: 456,
  } };
  await updateComment(args);
  await updateComment(args);
  assert.deepEqual(writes.map(([kind]) => kind), ['create', 'update']);
  assert.equal(writes[1][1].comment_id, 11);
});
