# Shared Scripts

This directory contains shared scripts that can be used across multiple projects.

## Available Scripts

### `fix-markdown.sh`

A comprehensive markdown formatting script that combines Prettier and markdownlint-cli2.

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
