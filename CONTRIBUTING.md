# Contributing to BPTAP Server

Thanks for your interest in contributing to the BPTAP backend. Please read this before submitting anything.

> All contributions are subject to [LICENSE.md](./LICENSE.md). By contributing, you agree your code will be governed by its terms.

---

## Issues

- Search existing issues before opening a new one
- Be specific — include steps to reproduce, expected vs actual behaviour, and relevant logs
- For security vulnerabilities, **do not open a public issue** — see [SECURITY.md](./SECURITY.md)

---

## Pull Requests

For any significant change (50+ lines or a new feature), **open an issue first** to align with maintainers before writing code.

### Before submitting

- Branch off `main`: `git checkout -b feat/your-feature`
- Follow existing Django/DRF patterns in the codebase
- Write clean Python — avoid unused imports, keep functions focused
- If adding new endpoints, include basic tests
- If changing models, include migrations

### PR checklist

- [ ] Linked to a related issue
- [ ] Migrations included if models changed
- [ ] No secrets or `.env` values committed
- [ ] Passes existing tests

---

## Commit Convention

| Prefix | Use for |
|--------|---------|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation |
| `refactor:` | Code restructuring |
| `chore:` | Dependencies, tooling |

---

