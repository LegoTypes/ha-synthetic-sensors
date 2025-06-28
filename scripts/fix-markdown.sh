#!/bin/bash
# Fix markdown files locally
# Run this script to automatically fix markdown linting issues

echo "🔧 Fixing markdown files..."

# Run markdownlint with --fix to automatically fix issues
if poetry run markdownlint-cli2 --fix --config .markdownlint-cli2.jsonc "**/*.md"; then
    echo "✅ Markdown files fixed successfully!"
    echo "📝 Please review the changes and commit them."
else
    echo "❌ Some markdown issues could not be automatically fixed."
    echo "📖 Please review the errors above and fix them manually."
    exit 1
fi