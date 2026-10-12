## Agent skills

### Issue tracker

Issues live in GitHub Issues (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Conventions

- **Atomic**: every issue, commit and PR covers one concern. Never bundle unrelated changes.
- **Conventional Commits**: every issue title, commit message and PR title follows the [Conventional Commits](https://www.conventionalcommits.org) spec (`type(scope)!: description`).
