# Contributing to agy-flow

Thank you for considering contributing to agy-flow! 🎉

## Code of Conduct

This project adheres to the [Contributor Covenant](https://www.contributor-covenant.org/) code of conduct. By participating, you agree to abide by its terms.

## How to Contribute

### Reporting Bugs

1. Check existing issues for duplicates
2. Open a new issue with:
   - Environment details (OS, Python version, tool versions)
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs or screenshots

### Submitting PRs

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Commit changes: `git commit -m "feat: add my feature"`
4. Push to your fork: `git push origin feat/my-feature`
5. Submit a Pull Request

### Development Guidelines

**Code Style**:
- Python: `black` + `ruff` formatting
- Type annotations: use `str | None` instead of `Optional[str]`
- Prefer standard library over unnecessary dependencies

**Testing**:
- New features must include tests
- Run `python -m pytest` to verify all tests pass
- End-to-end: `python scripts/mcp_client_smoke.py`

**Commit Message Format**:
```
<type>: <short description>

<optional body>
```

Types: `feat` / `fix` / `docs` / `test` / `refactor` / `chore`

### PR Merge Criteria

- ✅ All tests passing
- ✅ Code style compliant
- ✅ Test coverage for new features
- ✅ Documentation updated (if applicable)

## Project Structure

```
agy-flow/
├── agy_flow/           # Core library
│   ├── mcp_server.py   # MCP Server
│   ├── handoff.py      # Handoff protocol
│   ├── router.py       # Routing
│   ├── tasks.py        # Task management
│   └── gateway.py      # Dashboard
├── test_*.py           # Test files
├── scripts/            # Utility scripts
└── .agents/            # Runtime state (generated)
```
