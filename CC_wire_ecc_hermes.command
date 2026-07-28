#!/bin/bash
# CC_wire_ecc_hermes.command
# Wire ECC v2.0 to Hermes + Claude Code
#
# What this does:
#   1. Installs ECC developer profile into ~/.claude/ (Claude Code sessions)
#   2. Copies ECC skills into ~/.hermes/skills/ecc-imports/ (Hermes gateway)
#   3. Backs up existing ~/.claude/rules and ~/.claude/agents before touching them

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG=~/Desktop/REX/logs/cc_wire_ecc_hermes_${TIMESTAMP}.log
mkdir -p ~/Desktop/REX/logs
exec > >(tee "$LOG") 2>&1

ECC_DIR=~/Desktop/REX/ecc
CLAUDE_DIR=~/.claude
HERMES_SKILLS_DIR=~/.hermes/skills/ecc-imports

echo "══════════════════════════════════════════════════════"
echo "  CC_wire_ecc_hermes — $(date)"
echo "══════════════════════════════════════════════════════"
echo ""

# ── 0: Verify ECC exists ──────────────────────────────────
echo "── 0: Verify ECC source ─────────────────────────────"
if [ ! -f "$ECC_DIR/scripts/ecc.js" ]; then
  echo "  ❌ ECC not found at $ECC_DIR"
  echo "  Run CC_install_karpathy.command first? (ECC is at ~/Desktop/REX/ecc, not karpathy — just checking)"
  echo ""
  echo "  ECC should be at: ~/Desktop/REX/ecc/scripts/ecc.js"
  read -p "Press any key to close..."
  exit 1
fi
ECC_VERSION=$(node -e "const p=require('$ECC_DIR/package.json'); console.log(p.version)" 2>/dev/null || echo "unknown")
echo "  ✅ ECC found: v$ECC_VERSION at $ECC_DIR"
echo ""

# ── 1: Dry-run to show what will happen ──────────────────
echo "── 1: ECC install plan (developer profile → ~/.claude) ─"
node "$ECC_DIR/scripts/ecc.js" install --profile developer --target claude --dry-run 2>&1 | grep -E "^Mode:|^Target:|^Profile:|^Operations:|^Install root:" | sed 's/^/  /'
echo ""

# ── 2: Backup existing ~/.claude ECC dirs ────────────────
echo "── 2: Backup existing ~/.claude ECC content ─────────"
if [ -d "$CLAUDE_DIR/rules/ecc" ]; then
  cp -r "$CLAUDE_DIR/rules/ecc" "$CLAUDE_DIR/rules/ecc.bak_${TIMESTAMP}"
  echo "  Backed up: $CLAUDE_DIR/rules/ecc.bak_${TIMESTAMP}"
else
  echo "  (no existing rules/ecc to back up)"
fi
if [ -d "$CLAUDE_DIR/agents/ecc" ] || [ -d "$CLAUDE_DIR/agents" ]; then
  echo "  $CLAUDE_DIR/agents exists — noting for reference"
fi
echo ""

# ── 3: Install ECC into ~/.claude (Claude Code) ──────────
echo "── 3: Install ECC developer profile → ~/.claude ─────"
node "$ECC_DIR/scripts/ecc.js" install --profile developer --target claude 2>&1
if [ $? -eq 0 ]; then
  echo ""
  echo "  ✅ ECC installed into ~/.claude"
else
  echo "  ❌ ECC install failed — check output above"
  read -p "Press any key to close..."
  exit 1
fi
echo ""

# ── 4: Wire ECC skills into Hermes ───────────────────────
echo "── 4: Copy ECC skills → Hermes ──────────────────────"
if [ ! -d "$HERMES_SKILLS_DIR" ]; then
  mkdir -p "$HERMES_SKILLS_DIR"
  echo "  Created: $HERMES_SKILLS_DIR"
fi

# Copy the highest-value skills for GHS operations
HIGH_VALUE_SKILLS=(
  "deep-research"
  "automation-audit-ops"
  "enterprise-agent-ops"
  "agentic-engineering"
  "agentic-os"
  "autonomous-agent-harness"
  "continuous-agent-loop"
  "data-scraper-agent"
  "email-ops"
  "finance-billing-ops"
  "agent-architecture-audit"
  "orchestration-ops"
  "security-hardening"
  "agent-eval"
  "business-analyst"
)

COPIED=0
SKIPPED=0
for SKILL in "${HIGH_VALUE_SKILLS[@]}"; do
  SRC="$ECC_DIR/skills/$SKILL"
  if [ -d "$SRC" ]; then
    cp -r "$SRC" "$HERMES_SKILLS_DIR/$SKILL"
    echo "  ✅ $SKILL"
    COPIED=$((COPIED + 1))
  else
    echo "  ⚠️  not found: $SKILL (skipped)"
    SKIPPED=$((SKIPPED + 1))
  fi
done

echo ""
echo "  Copied: $COPIED skills to $HERMES_SKILLS_DIR"
echo "  Skipped: $SKIPPED (not in this ECC build)"
echo ""

# ── 5: Copy ECC agents into Hermes ───────────────────────
echo "── 5: Copy ECC agents → Hermes ─────────────────────"
HERMES_AGENTS_DIR=~/.hermes/agents/ecc-imports
if [ ! -d "$HERMES_AGENTS_DIR" ]; then
  mkdir -p "$HERMES_AGENTS_DIR"
  echo "  Created: $HERMES_AGENTS_DIR"
fi

# Copy high-value agents
HIGH_VALUE_AGENTS=(
  "chief-of-staff.md"
  "architect.md"
  "code-reviewer.md"
  "docs-lookup.md"
  "security-auditor.md"
  "data-analyst.md"
  "devops-engineer.md"
)

for AGENT in "${HIGH_VALUE_AGENTS[@]}"; do
  SRC="$ECC_DIR/agents/$AGENT"
  if [ -f "$SRC" ]; then
    cp "$SRC" "$HERMES_AGENTS_DIR/$AGENT"
    echo "  ✅ $AGENT"
  else
    echo "  ⚠️  not found: $AGENT (skipped)"
  fi
done
echo ""

# ── 6: Verify installation ───────────────────────────────
echo "── 6: Verify installation ───────────────────────────"
echo ""
echo "  ~/.claude rules installed:"
ls "$CLAUDE_DIR/rules/ecc/" 2>/dev/null | head -10 | sed 's/^/    /' || echo "    (none)"
echo ""
echo "  Hermes skills imported:"
ls "$HERMES_SKILLS_DIR/" 2>/dev/null | sed 's/^/    /' || echo "    (none)"
echo ""
echo "  Hermes agents imported:"
ls "$HERMES_AGENTS_DIR/" 2>/dev/null | sed 's/^/    /' || echo "    (none)"
echo ""

# ── 7: List total ECC install state ──────────────────────
echo "── 7: ECC install state ─────────────────────────────"
node "$ECC_DIR/scripts/ecc.js" list-installed --json 2>/dev/null | python3 -c "
import sys, json
try:
  data = json.load(sys.stdin)
  print(f'  Total managed files: {len(data) if isinstance(data, list) else \"see JSON\"}')
except:
  print('  (install state logged to ecc/ecc-install-state.json)')
" 2>/dev/null || echo "  (state check skipped)"
echo ""

echo "══════════════════════════════════════════════════════"
echo "  Done — $(date)"
echo ""
echo "  ECC v$ECC_VERSION wired:"
echo "  • Claude Code: ~/.claude/rules/ecc/ + agents + hooks"
echo "  • Hermes skills: ~/.hermes/skills/ecc-imports/"
echo "  • Hermes agents: ~/.hermes/agents/ecc-imports/"
echo ""
echo "  Next: restart Hermes gateway to pick up new agents"
echo "  Log: $LOG"
echo "══════════════════════════════════════════════════════"
echo ""
read -p "Press any key to close..."
