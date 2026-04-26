# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Qwen agent support (5th agent available)
- Comprehensive test suite with 27 tests
- GitHub Actions CI/CD pipeline
- CodeQL security scanning
- Dependabot configuration
- CONTRIBUTING.md guide
- DEVELOPMENT.md guide
- Test coverage reporting with Codecov
- Development setup script

### Changed
- Updated README with CI/CD badges
- Improved documentation structure

### Fixed
- Code Scanning blocking issue resolved

## [0.5.1] - 2026-04-26

### Fixed
- Codex subagent now preserves successful `codex exec --json` responses even when Codex exits non-zero during post-turn rollout bookkeeping.
- Added regression coverage for completed-turn recovery and explicit `turn.failed` handling in the Codex adapter.

## [0.5.0] - 2024-12-09

### Added
- Initial release with 4 agents (Codex, Claude, Cursor, Gemini)
- FastMCP server implementation
- CLI adapter framework
- Model mapping system
- Streaming message support
- Progress reporting
- Availability checking
- Session management

### Features
- Context continuity across agents
- Parallel execution support
- Model specialization
- Zero markup pricing
- 26+ IDE support

## [0.4.0] - Previous releases

See [GitHub Releases](https://github.com/askbudi/roundtable/releases) for earlier versions.

---

## Release Types

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes
