# Dead Code Detection with Vulture

This project uses [Vulture](https://github.com/jendrikseipp/vulture) to detect unused (dead) code automatically.

## What is Vulture?

Vulture finds unused code in Python programs by using static analysis. It detects:

- Unused functions and methods
- Unused classes
- Unused variables
- Unused attributes
- Unused imports

## Configuration

### pyproject.toml Configuration

Vulture is configured in `pyproject.toml`:

```toml
[tool.vulture]
exclude = [
    "tests/",
    "scripts/",
    "examples/",
    "docs/",
    "*.pyc",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
]
min_confidence = 80
```

### Pre-commit Integration

Vulture runs automatically in pre-commit hooks with 80% confidence threshold. This catches high-confidence dead code before commits.

```yaml
# In .pre-commit-config.yaml
- repo: https://github.com/jendrikseipp/vulture
  rev: v2.14
  hooks:
    - id: vulture
      args: ['src/', 'vulture_whitelist.py', '--min-confidence=80']
```

## Whitelist File

The `vulture_whitelist.py` file contains code that appears unused to vulture but is actually legitimate:

- Exception classes used in tests
- Public API functions and constants
- Protocol methods for extensibility
- Data classes used in service calls
- Cache attributes for future features

## Usage

### Automatic (Recommended)

Vulture runs automatically via pre-commit hooks. Install hooks with:

```bash
poetry run pre-commit install
```

### Manual Checks

Run vulture manually with different confidence levels:

```bash
# High confidence (80%+) - same as pre-commit
poetry run vulture src/ vulture_whitelist.py --min-confidence=80

# Medium confidence (60%+) - may include false positives
poetry run vulture src/ vulture_whitelist.py --min-confidence=60

# Using the convenience script
python scripts/check_dead_code.py --confidence=60
```

### Developer Script

Use `scripts/check_dead_code.py` for flexible dead code checking:

```bash
# Check with default 60% confidence
python scripts/check_dead_code.py

# Check with custom confidence level
python scripts/check_dead_code.py --confidence=70
```

## Confidence Levels

- **80-100%**: High confidence dead code (caught by pre-commit)
  - Very likely to be truly unused
  - Safe to remove after verification

- **60-79%**: Medium confidence
  - May include false positives
  - Review carefully before removing

- **40-59%**: Low confidence
  - Many false positives expected
  - Use for exploration only

## False Positives

Some code may appear unused but is actually legitimate:

1. **Dynamic usage**: Code called via `getattr()` or reflection
2. **Public API**: Functions/classes intended for external use
3. **Extensibility**: Protocol methods and abstract base classes
4. **Future features**: Code prepared for upcoming functionality
5. **Test fixtures**: Code used indirectly by tests

Add such code to `vulture_whitelist.py` to suppress warnings.

## Best Practices

1. **Fix high-confidence issues immediately**: Don't let 80%+ confidence dead code accumulate
2. **Review medium-confidence issues periodically**: Check 60-79% confidence reports monthly
3. **Update whitelist judiciously**: Only whitelist truly legitimate code
4. **Document whitelist entries**: Include comments explaining why code is whitelisted
5. **Remove truly dead code**: Don't keep code "just in case" - use git history instead

## Integration with Development Workflow

Vulture integrates seamlessly with the development workflow:

1. **Development**: Write code normally
2. **Pre-commit**: Vulture automatically checks for high-confidence dead code
3. **CI/CD**: Pre-commit hooks ensure dead code doesn't reach the repository
4. **Periodic review**: Use the script to check lower confidence levels
5. **Cleanup**: Remove confirmed dead code to keep the codebase clean

## Troubleshooting

### False Positive in Pre-commit

If vulture incorrectly flags legitimate code:

1. Verify the code is actually used
2. Add the item to `vulture_whitelist.py`
3. Commit the whitelist update

### Script Not Working

Ensure you're in the project root and have dependencies installed:

```bash
cd /path/to/ha-synthetic-sensors
poetry install
python scripts/check_dead_code.py
```

### Understanding Output

Vulture output format:

```text
file:line: unused item 'name' (confidence% confidence)
```

Higher confidence percentages indicate vulture is more certain the code is unused.
