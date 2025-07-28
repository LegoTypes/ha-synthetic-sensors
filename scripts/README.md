# Shared Scripts

This directory contains shared scripts that can be used across multiple projects.

## Available Scripts

### `validate_examples.sh`

A validation script for YAML examples and test fixtures in the synthetic sensors project.

**Usage:**

```bash
./scripts/validate_examples.sh [options]
```

**Options:**

- `--examples`: Validate all YAML files in the examples directory
- `--fixtures`: Validate test fixtures for expected sensors
- `--all`: Validate everything (default behavior)
- `--file FILE`: Validate a specific YAML file
- `--verbose, -v`: Enable verbose output
- `--help`: Show help message

**Examples:**

```bash
# Validate everything (default)
./scripts/validate_examples.sh

# Validate only examples
./scripts/validate_examples.sh --examples

# Validate only test fixtures
./scripts/validate_examples.sh --fixtures

# Validate a specific file
./scripts/validate_examples.sh --file examples/idiom_1_backing_entity.yaml

# Verbose output
./scripts/validate_examples.sh --verbose
```

**What it does:**

1. **YAML Validation**: Uses the actual implementation's validation logic to check YAML files
2. **Test Fixture Validation**: Ensures test fixtures contain expected sensors for tests
3. **Enhanced Reporting**: Provides detailed error and warning messages with context
4. **Poetry Integration**: Automatically uses Poetry environment if available

**Coverage:**

- `examples/*.yaml` - All example YAML files
- Test fixtures with expected sensor validation
- Individual file validation with detailed reporting

**VS Code Integration:** Add this task to your `.vscode/tasks.json`:

```json
{
  "label": "Validate examples",
  "type": "shell",
  "command": "./scripts/validate_examples.sh",
  "args": ["--all"],
  "group": "test",
  "detail": "Validate YAML examples and test fixtures"
}
```

### `fix-markdown.sh`

A markdown formatting script that combines Prettier and markdownlint-cli2.

**Usage:**

```bash
./scripts/fix-markdown.sh <workspace_root>
```

**Example:**

```bash
./scripts/fix-markdown.sh /path/to/your/project
```

**What it does:**

1. **Prettier**: Handles line wrapping and general formatting
   - Breaks lines at 125 characters
   - Wraps prose content intelligently
   - Uses workspace `.prettierrc` if available, otherwise defaults

2. **markdownlint-cli2**: Handles markdown-specific rules
   - Heading spacing
   - Code block spacing
   - List formatting
   - Uses workspace `.markdownlint-cli2.jsonc` if available

**Coverage:**

- `*.md` (root level)
- `docs/**/*.md`
- `tests/**/*.md`
- `.github/**/*.md`

**VS Code Integration:** Add this single task to your `.vscode/tasks.json`:

```json
{
  "label": "Fix markdown formatting",
  "type": "shell",
  "command": "/Users/bflood/projects/scripts/fix-markdown.sh",
  "args": ["${workspaceFolder}"],
  "group": "test",
  "detail": "Comprehensive markdown formatting using shared script (Prettier + markdownlint)"
}
```

**Note:** This single task replaces the need for separate check-only or markdownlint-only tasks since it handles both line
wrapping and markdown-specific fixes comprehensively.

## Requirements

- Node.js and npm (for npx)
- Prettier (installed via npx)
- markdownlint-cli2 (installed via npx)

## Adding New Scripts

When adding new shared scripts:

1. Create the script in this directory
2. Make it executable: `chmod +x scripts/script-name.sh`
3. Update this README with usage instructions
4. Consider adding VS Code task examples
