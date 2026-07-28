#!/usr/bin/env python3
"""
CC_menu_qr.py
──────────────────────────────────────────────────────────────────────────────
Menu QR Code Generator for GOJ

Given a client name + week, renders a PDF with the client name title and a QR code
pointing to the menu review surface (GOJ Live OCR endpoint).

Usage:
    python3 CC_menu_qr.py --client "Sunrise Manor" --week 25 --output /tmp/menu.pdf
    python3 CC_menu_qr.py --selftest

Environment variables:
    MENU_QR_BASE  — base URL for QR code target (default: http://127.0.0.1:8090/ocr)
"""

import argparse
import os
import sys
from pathlib import Path

import qrcode
try:
    import fitz  # pymupdf
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)


def generate_menu_qr(
    client_name: str,
    week: int,
    output_path: str | None = None,
    base_url: str | None = None,
) -> str:
    """
    Generate a PDF with client name title and a QR code.

    Args:
        client_name: Name of the client (e.g., "Sunrise Manor")
        week: Week number (e.g., 25)
        output_path: Output PDF path (default: /tmp/menu_qr_{client}_{week}.pdf)
        base_url: Base URL for QR code (default: env MENU_QR_BASE or http://127.0.0.1:8090/ocr)

    Returns:
        Path to generated PDF
    """
    if base_url is None:
        base_url = os.getenv("MENU_QR_BASE", "http://127.0.0.1:8090/ocr")

    if output_path is None:
        safe_name = client_name.replace(" ", "_").lower()
        output_path = f"/tmp/menu_qr_{safe_name}_{week}.pdf"

    # Generate QR code
    qr_text = f"{base_url}?client={client_name}&week={week}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    # Save QR code temporarily
    qr_temp = "/tmp/qr_temp.png"
    qr_img.save(qr_temp)

    # Create PDF with title and QR code
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter size

    # Add title
    title_text = f"Menu Review — {client_name}"
    title_rect = fitz.Rect(50, 50, 562, 120)
    page.insert_textbox(
        title_rect,
        title_text,
        fontsize=24,
        color=(0.0, 0.0, 0.0),
        align=fitz.TEXT_ALIGN_CENTER,
    )

    # Add subtitle with week info
    subtitle_text = f"Week {week}"
    subtitle_rect = fitz.Rect(50, 120, 562, 160)
    page.insert_textbox(
        subtitle_rect,
        subtitle_text,
        fontsize=14,
        color=(0.4, 0.4, 0.4),
        align=fitz.TEXT_ALIGN_CENTER,
    )

    # Insert QR code image (centered, roughly 300x300)
    qr_width, qr_height = qr_img.size
    scale = min(300 / qr_width, 300 / qr_height)
    scaled_w = int(qr_width * scale)
    scaled_h = int(qr_height * scale)
    x_offset = (612 - scaled_w) / 2
    y_offset = 250
    qr_rect = fitz.Rect(x_offset, y_offset, x_offset + scaled_w, y_offset + scaled_h)
    page.insert_image(qr_rect, filename=qr_temp)

    # Save PDF
    doc.save(output_path)
    doc.close()

    # Clean up temp QR image
    Path(qr_temp).unlink(missing_ok=True)

    print(f"Generated QR PDF: {output_path}")
    return output_path


def selftest():
    """Generate a test PDF and verify it."""
    test_output = "/tmp/menu_qr_test.pdf"
    try:
        output = generate_menu_qr(
            client_name="Test Client",
            week=1,
            output_path=test_output,
            base_url="http://127.0.0.1:8090/ocr",
        )

        # Verify PDF exists and has content
        if not Path(output).exists():
            print("ERROR: PDF was not created")
            return False

        file_size = Path(output).stat().st_size
        if file_size == 0:
            print("ERROR: PDF is empty")
            return False

        # Open and check for image
        doc = fitz.open(output)
        page_count = len(doc)
        if page_count == 0:
            doc.close()
            print("ERROR: PDF has no pages")
            return False

        page = doc[0]
        images = page.get_images()
        image_count = len(images)

        doc.close()

        if image_count == 0:
            print("WARNING: PDF has no embedded images (expected 1 QR code)")
            return False

        print(f"SELFTEST PASSED: {output} ({file_size} bytes, {page_count} page(s), {image_count} image(s))")
        return True

    except Exception as e:
        print(f"ERROR in selftest: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate QR code PDF for menu review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 CC_menu_qr.py --client "Sunrise Manor" --week 25
  python3 CC_menu_qr.py --selftest
  MENU_QR_BASE=http://hub.example.com/ocr python3 CC_menu_qr.py --client "Test" --week 1
        """,
    )
    parser.add_argument("--client", help="Client name")
    parser.add_argument("--week", type=int, help="Week number")
    parser.add_argument("--output", help="Output PDF path")
    parser.add_argument("--base-url", help="Base URL for QR code")
    parser.add_argument("--selftest", action="store_true", help="Run self-test")

    args = parser.parse_args()

    if args.selftest:
        success = selftest()
        sys.exit(0 if success else 1)

    if not args.client or args.week is None:
        parser.print_help()
        sys.exit(1)

    generate_menu_qr(
        client_name=args.client,
        week=args.week,
        output_path=args.output,
        base_url=args.base_url,
    )


if __name__ == "__main__":
    main()
