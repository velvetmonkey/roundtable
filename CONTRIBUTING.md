# Contributing to Roundtable AI

Thank you for your interest in contributing to Roundtable AI! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.

## Getting Started

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/yourusername/roundtable.git
cd roundtable

# Install development dependencies
pip install -e ".[dev]"

# Or use the setup script
./scripts/setup-dev.sh
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov --cov-report=html

# Run specific test types
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
```

### Code Quality

Before submitting a PR, ensure your code passes all checks:

```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy roundtable_mcp_server
```

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/velvetmonkey/roundtable/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs or error messages

### Suggesting Features

1. Check if the feature has been suggested in [Issues](https://github.com/velvetmonkey/roundtable/issues)
2. If not, create a new issue with:
   - Clear description of the feature
   - Use cases and benefits
   - Possible implementation approach

### Submitting Pull Requests

1. **Fork the repository** and create a feature branch:
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. **Make your changes** following our coding standards:
   - Write clear, descriptive commit messages
   - Add tests for new functionality
   - Update documentation as needed
   - Follow existing code style

3. **Test your changes**:
   ```bash
   pytest
   black .
   ruff check .
   ```

4. **Commit your changes** using conventional commits:
   ```bash
   git commit -m "feat: add amazing feature"
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/amazing-feature
   ```

6. **Open a Pull Request** with:
   - Clear title and description
   - Reference to related issues
   - Screenshots/examples if applicable
   - Checklist of completed items

## Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```bash
feat(server): add Qwen agent support
fix(cli): resolve path validation issue
docs(readme): update installation instructions
test(unit): add tests for model mapping
```

## Adding a New Agent

To add a new AI agent to Roundtable:

1. **Create adapter** in `claudable_helper/cli/adapters/`:
   ```python
   class NewAgentCLI(BaseCLI):
       async def check_availability(self) -> Dict:
           # Implementation
       
       async def execute_with_streaming(self, ...) -> AsyncGenerator:
           # Implementation
   ```

2. **Add model mapping** in `claudable_helper/cli/base.py`:
   ```python
   MODEL_MAPPING = {
       "newagent": {
           "model-name": "actual-model-id"
       }
   }
   ```

3. **Register in server** (`roundtable_mcp_server/server.py`):
   - Import the adapter
   - Add to `valid_subagents`
   - Create `check_newagent_availability()` tool
   - Create `newagent_subagent()` tool

4. **Add tests** in `tests/unit/`:
   - Test availability checking
   - Test model mapping
   - Test execution flow

5. **Update documentation**:
   - Add to README.md
   - Update examples
   - Add to CLI help

## Code Style

- **Python**: Follow PEP 8
- **Line length**: 88 characters (Black default)
- **Imports**: Organized with isort
- **Type hints**: Use where appropriate
- **Docstrings**: Google style

## Testing Guidelines

- Write tests for all new functionality
- Maintain or improve code coverage
- Use descriptive test names
- Use fixtures for common setup
- Mock external dependencies

## Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions/classes
- Update examples if behavior changes
- Keep CHANGELOG.md updated

## Questions?

Feel free to open an issue for any questions or clarifications.

Thank you for contributing! 🎉
