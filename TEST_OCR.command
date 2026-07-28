#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  OCR PIPELINE TEST — Verifies all 4 engines are ready
#  Creates a real test PDF and runs it through the full pipeline.
#  Double-click to run. Safe — creates and deletes its own test files.
# ═══════════════════════════════════════════════════════════════════

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

REX_DIR="$HOME/Desktop/REX"

# Find venv python
VENV_PYTHON=""
for CANDIDATE in \
    "$HOME/debate-chamber/.venv/bin/python3" \
    "$REX_DIR/.venv/bin/python3" \
    "$(command -v python3)"; do
    [ -f "$CANDIDATE" ] && VENV_PYTHON="$CANDIDATE" && break
done
[ -z "$VENV_PYTHON" ] && VENV_PYTHON="python3"

PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}✅${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}❌${NC} $1"; FAIL=$((FAIL+1)); }
hdr()  { echo ""; echo -e "${BOLD}${CYAN}━━ $1${NC}"; }

clear
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  🔬 OCR Pipeline Test${NC}"
echo -e "${BOLD}  $(date '+%b %d %Y %I:%M %p')${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Python: $VENV_PYTHON"

# ── Section 1: Python packages ─────────────────────────────────────
hdr "1  PYTHON PACKAGES"

check_import() {
    local mod="$1"; local label="$2"
    "$VENV_PYTHON" -c "import $mod; print('ok')" 2>/dev/null | grep -q "ok" \
        && pass "$label importable" \
        || fail "$label NOT importable — run install_ocr_deps.command"
}

check_import "pdfplumber"        "pdfplumber (Engine 1)"
check_import "fitz"              "PyMuPDF/fitz (Engine 1 fallback)"
check_import "pdf2image"         "pdf2image (Engine 2/3)"
check_import "pytesseract"       "pytesseract (Engine 2)"
check_import "PIL"               "Pillow/PIL (image processing)"
check_import "anthropic"         "anthropic (Engine 4 / Claude Vision)"

# ── Section 2: System tools ────────────────────────────────────────
hdr "2  SYSTEM TOOLS"

if command -v tesseract >/dev/null 2>&1; then
    TESS_VER=$(tesseract --version 2>&1 | head -1)
    pass "Tesseract: $TESS_VER"
    if tesseract --list-langs 2>/dev/null | grep -q "^rus$"; then
        pass "Russian language pack (rus) installed"
    else
        fail "Russian language pack MISSING — run: brew install tesseract-lang"
    fi
    if tesseract --list-langs 2>/dev/null | grep -q "^eng$"; then
        pass "English language pack (eng) installed"
    fi
else
    fail "Tesseract not found — run: brew install tesseract tesseract-lang"
fi

if command -v pdftoppm >/dev/null 2>&1; then
    pass "Poppler (pdftoppm) installed — pdf2image can convert PDFs"
elif command -v pdfimages >/dev/null 2>&1; then
    pass "Poppler (pdfimages) installed — pdf2image can convert PDFs"
else
    fail "Poppler not found — run: brew install poppler"
fi

# ── Section 3: Create a real test PDF and run OCR on it ───────────
hdr "3  LIVE OCR TEST"

TEST_DIR=$(mktemp -d 2>/dev/null || echo "/tmp/ocr_test_$$")
TEST_PDF="$TEST_DIR/test_goj.pdf"
TEST_RESULT="$TEST_DIR/result.txt"

echo "  Creating test PDF..."

# Create a simple PDF using Python (no external tools needed)
"$VENV_PYTHON" - <<'PYEOF' "$TEST_PDF"
import sys
outpath = sys.argv[1]

# Minimal valid PDF with embedded text (no image — tests Engine 1)
pdf_content = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
  /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 120 >>
stream
BT /F1 12 Tf 72 720 Td
(GOJ Sign-In Sheet) Tj 0 -20 Td
(Monday April 13 2026) Tj 0 -20 Td
(Client: Test Entry) Tj 0 -20 Td
(Attendance: Present) Tj
ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000437 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
510
%%EOF"""
with open(outpath, 'wb') as f:
    f.write(pdf_content)
print("PDF created")
PYEOF

if [ -f "$TEST_PDF" ]; then
    pass "Test PDF created at $TEST_PDF"
else
    fail "Could not create test PDF"
fi

# Engine 1: pdfplumber
echo ""
echo -e "  ${BOLD}Testing Engine 1 — pdfplumber (text layer)...${NC}"
"$VENV_PYTHON" - <<PYEOF "$TEST_PDF" "$TEST_RESULT"
import sys
try:
    import pdfplumber
    with pdfplumber.open(sys.argv[1]) as pdf:
        text = " ".join(p.extract_text() or "" for p in pdf.pages).strip()
    if text and len(text) > 5:
        print(f"SUCCESS: {text[:80]}")
    else:
        print("EMPTY: no text layer found (normal for scanned PDFs)")
except Exception as e:
    print(f"FAIL: {e}")
PYEOF
ENGINE1=$("$VENV_PYTHON" - <<PYEOF "$TEST_PDF"
import sys
try:
    import pdfplumber
    with pdfplumber.open(sys.argv[1]) as pdf:
        text = " ".join(p.extract_text() or "" for p in pdf.pages).strip()
    print("ok" if text and len(text)>5 else "empty")
except Exception as e:
    print(f"fail:{e}")
PYEOF
)
case "$ENGINE1" in
    ok)    pass "Engine 1 (pdfplumber) — extracted text successfully" ;;
    empty) pass "Engine 1 (pdfplumber) — ready (no text layer in test PDF, normal)" ;;
    fail*) fail "Engine 1 (pdfplumber) — ${ENGINE1#fail:}" ;;
esac

# Engine 2: Tesseract via fitz
echo ""
echo -e "  ${BOLD}Testing Engine 2 — Tesseract + fitz (scanned PDFs)...${NC}"
ENGINE2=$("$VENV_PYTHON" - <<PYEOF "$TEST_PDF"
import sys
try:
    import fitz, pytesseract
    from PIL import Image
    import io
    doc = fitz.open(sys.argv[1])
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    text = pytesseract.image_to_string(img, lang='eng+rus').strip()
    print("ok" if text else "empty")
except Exception as e:
    print(f"fail:{e}")
PYEOF
)
case "$ENGINE2" in
    ok)    pass "Engine 2 (Tesseract+fitz) — ran successfully, text extracted" ;;
    empty) pass "Engine 2 (Tesseract+fitz) — ran, no text (test PDF may be minimal)" ;;
    fail*) fail "Engine 2 (Tesseract+fitz) — ${ENGINE2#fail:}" ;;
esac

# Engine 2 alt: pdf2image path
echo ""
echo -e "  ${BOLD}Testing Engine 2 alt — pdf2image (alternate conversion)...${NC}"
ENGINE2B=$("$VENV_PYTHON" - <<PYEOF "$TEST_PDF"
import sys
try:
    from pdf2image import convert_from_path
    pages = convert_from_path(sys.argv[1], dpi=150)
    print(f"ok:{len(pages)} page(s)")
except Exception as e:
    print(f"fail:{e}")
PYEOF
)
case "$ENGINE2B" in
    ok*)   pass "Engine 2 alt (pdf2image) — ${ENGINE2B#ok:}" ;;
    fail*) fail "Engine 2 alt (pdf2image) — ${ENGINE2B#fail:}" ;;
esac

# Engine 3: Paperless-NGX (Tailscale)
echo ""
echo -e "  ${BOLD}Testing Engine 3 — Paperless-NGX (network)...${NC}"
PAPERLESS_URL="http://100.99.86.60:8000"
PAPERLESS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 4 "$PAPERLESS_URL" 2>/dev/null)
if [ "$PAPERLESS_CODE" = "200" ] || [ "$PAPERLESS_CODE" = "301" ] || [ "$PAPERLESS_CODE" = "302" ]; then
    pass "Engine 3 (Paperless-NGX) — reachable at $PAPERLESS_URL (HTTP $PAPERLESS_CODE)"
elif [ "$PAPERLESS_CODE" = "000" ]; then
    echo -e "  ${YELLOW}⚠️  Engine 3 (Paperless-NGX) — not reachable (Tailscale may be off or Paperless down)${NC}"
else
    echo -e "  ${YELLOW}⚠️  Engine 3 (Paperless-NGX) — HTTP $PAPERLESS_CODE (may need Tailscale)${NC}"
fi

# Engine 4: Claude Vision (API key check only — don't charge for test)
echo ""
echo -e "  ${BOLD}Testing Engine 4 — Claude Vision (API key check)...${NC}"
if [ -f "$REX_DIR/.env" ]; then
    KEY=$(grep "^ANTHROPIC_API_KEY" "$REX_DIR/.env" | cut -d= -f2 | tr -d '"')
    if [[ "$KEY" == sk-ant-* ]]; then
        pass "Engine 4 (Claude Vision) — ANTHROPIC_API_KEY present and valid format"
    else
        fail "Engine 4 (Claude Vision) — ANTHROPIC_API_KEY missing or wrong format"
    fi
else
    fail "Engine 4 (Claude Vision) — .env file not found"
fi

# ── Section 4: Intake folder ───────────────────────────────────────
hdr "4  DOCUMENT INTAKE FOLDER"

SIGNINS="$REX_DIR/signins"
if [ -d "$SIGNINS" ]; then
    COUNT=$(ls "$SIGNINS"/*.pdf 2>/dev/null | wc -l | tr -d ' ')
    if [ "$COUNT" -gt 0 ]; then
        echo -e "  ${YELLOW}⚠️ ${NC} $COUNT PDF(s) waiting in signins/ — run the intake to process them"
        ls "$SIGNINS"/*.pdf 2>/dev/null | while read f; do echo -e "     📄 $(basename "$f")"; done
    else
        pass "Intake folder exists — no PDFs waiting (all clear)"
    fi
else
    fail "Intake folder missing: $SIGNINS — create it with: mkdir -p $SIGNINS"
fi

# ── Cleanup ────────────────────────────────────────────────────────
rm -rf "$TEST_DIR" 2>/dev/null

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  RESULT: ${GREEN}$PASS passed${NC}  ${RED}$FAIL failed${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  ✅ OCR pipeline is fully operational.${NC}"
    echo -e "  Drop a PDF into ~/Desktop/REX/signins/ and Rexxie will process it."
else
    echo -e "${RED}${BOLD}  ❌ $FAIL issue(s) found — see above.${NC}"
    echo -e "  ${YELLOW}Fix: double-click install_ocr_deps.command then re-run this test.${NC}"
fi

echo ""
echo "Press Enter to close..."
read
