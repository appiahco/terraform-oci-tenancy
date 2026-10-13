import test from 'node:test';
import assert from 'node:assert/strict';
import { remindersDue } from '../scripts/key-rotation.mjs';

test('each identity has an independent 90-day rotation deadline', () => {
  assert.deepEqual(remindersDue({apply: '2026-01-01', plan: '2026-01-02'}, new Date('2026-04-01T00:00:00Z')),
    [{role: 'apply', installed: '2026-01-01', due: '2026-04-01'}]);
  assert.deepEqual(remindersDue({}, new Date('2026-04-01T00:00:00Z')), []);
  assert.throws(() => remindersDue({apply: '2026-02-30'}));
});

const { createReminders } = await import('../scripts/key-rotation.mjs');
test('reminder issues are separate and deduplicated after closing', async () => {
  const issues = [];
  const github = {rest: {issues: {listForRepo: {}, create: async issue => issues.push(issue)}}, paginate: async () => issues};
  const options = {github, context: {repo: {owner: 'owner', repo: 'repo'}},
    dates: {apply: '2026-01-01', plan: '2026-01-02'}, now: new Date('2026-04-02T00:00:00Z')};
  await createReminders(options);
  assert.equal(issues.length, 2);
  assert.match(issues[0].title, /apply user/);
  assert.match(issues[1].title, /plan user/);
  issues.forEach(issue => issue.state = 'closed');
  await createReminders(options);
  assert.equal(issues.length, 2);
});
