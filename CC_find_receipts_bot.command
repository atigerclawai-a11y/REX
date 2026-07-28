#!/usr/bin/env bash
# CC_find_receipts_bot.command — locate @GOJReceipts_bot token and process
OUT="$HOME/Desktop/REX/logs/receipts_bot_search.txt"
mkdir -p "$HOME/Desktop/REX/logs"

{
echo "══════════════════════════════════════"
echo "  GOJReceipts Bot Locator"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════"

echo ""
echo "── LaunchAgents plists (all) ──"
ls -la "$HOME/Library/LaunchAgents/" 2>/dev/null || echo "(cannot list)"

echo ""
echo "── LaunchAgents: grep for receipt/goj/billing/8691 ──"
grep -rl "receipt\|GOJReceipt\|billing\|8691447" "$HOME/Library/LaunchAgents/" 2>/dev/null || echo "(no matches)"

echo ""
echo "── LaunchAgents: grep content for 8691447 ──"
grep -r "8691447" "$HOME/Library/LaunchAgents/" 2>/dev/null || echo "(no matches)"

echo ""
echo "── LaunchAgents: grep content for receipt ──"
grep -ri "receipt" "$HOME/Library/LaunchAgents/" 2>/dev/null || echo "(no matches)"

echo ""
echo "── ~/.zshrc token check ──"
grep -i "8691447\|GOJReceipt\|receipt.*token\|RECEIPT" "$HOME/.zshrc" 2>/dev/null || echo "(no matches)"

echo ""
echo "── ~/.zprofile token check ──"
grep -i "8691447\|GOJReceipt\|receipt.*token\|RECEIPT" "$HOME/.zprofile" 2>/dev/null || echo "(no matches)"

echo ""
echo "── Running processes with 8691447 ──"
pgrep -fla "8691447" 2>/dev/null || echo "(none)"

echo ""
echo "── Running python3 bot processes ──"
pgrep -fla "python.*bot\|bot.*python\|telegram" 2>/dev/null | grep -iv "pyc\|grep" || echo "(none)"

echo ""
echo "── Find any python file with 8691447 ──"
find "$HOME" -name "*.py" -o -name "*.json" -o -name "*.env" -o -name "*.txt" 2>/dev/null | xargs grep -l "8691447" 2>/dev/null || echo "(none found)"

echo ""
echo "══ DONE ══"
} | tee "$OUT"

echo ""
echo "Results saved to: $OUT"
sleep 8
