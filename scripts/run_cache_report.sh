#!/bin/bash
# Cache Performance Report Runner
#
# This script runs the cache performance report to demonstrate
# the AST caching improvements in the synthetic sensors package.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}Synthetic Sensors Cache Performance Report${NC}"
echo -e "${BLUE}===========================================${NC}"
echo

# Check if we're in a poetry environment
if ! command -v poetry &> /dev/null; then
    echo -e "${RED}Poetry not found. Please install poetry first.${NC}"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

echo -e "${YELLOW}Working directory: $PROJECT_ROOT${NC}"
echo -e "${YELLOW}Running cache performance report...${NC}"
echo

# Run the report
if poetry run python scripts/cache_performance_report.py; then
    echo
    echo -e "${GREEN}Cache performance report completed successfully!${NC}"
    echo -e "${GREEN}Results show the AST caching improvements are working.${NC}"
    echo
    echo -e "${BLUE}For more details, see:${NC}"
    echo -e "${BLUE}   docs/Cache_Behavior_and_Data_Lifecycle.md${NC}"
    echo
else
    echo
    echo -e "${RED}Cache performance report failed!${NC}"
    echo -e "${RED}Check the error output above for details.${NC}"
    exit 1
fi