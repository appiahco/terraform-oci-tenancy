const DAY = 86400000;

export function remindersDue(dates, now = new Date()) {
  return Object.entries(dates).flatMap(([role, installed]) => {
    if (!installed) return [];
    const start = new Date(`${installed}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(installed) || !Number.isFinite(+start) || start.toISOString().slice(0, 10) !== installed) {
      throw new Error(`Invalid ${role} rotation date; use YYYY-MM-DD`);
    }
    const due = new Date(+start + 90 * DAY);
    return +now >= +due ? [{role, installed, due: due.toISOString().slice(0, 10)}] : [];
  });
}

export async function createReminders({github, context, dates, now}) {
  const due = remindersDue(dates, now);
  if (!due.length) return;
  const issues = await github.paginate(github.rest.issues.listForRepo, {...context.repo, state: 'all', per_page: 100});
  for (const item of due) {
    const title = `chore(keys): rotate ${item.role} user API key installed ${item.installed}`;
    // A closed reminder is not a rotation: owner must advance the baseline after installing a new key.
    if (issues.some(issue => !issue.pull_request && issue.title === title)) continue;
    await github.rest.issues.create({...context.repo, title,
      body: `The ${item.role} user's key reached 90 days on ${item.due}. Follow [the manual rotation runbook](https://github.com/${context.repo.owner}/${context.repo.repo}/blob/main/bootstrap/README.md#key-rotation).\n\n- [ ] Generate a new local key pair.\n- [ ] Update the public key input and owner-apply Bootstrap against remote state.\n- [ ] Verify permissions and replace this identity's Environment secrets.\n- [ ] Advance OCI_${item.role.toUpperCase()}_ROTATED_ON only after successful installation.\n- [ ] Remove the old public key through an owner-reviewed Bootstrap apply and securely remove the old private key.`});
  }
}
