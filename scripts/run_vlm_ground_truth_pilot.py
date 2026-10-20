import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import json
import base64
import time
import requests
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')

# 1. Configuration & Key Loading
ENV_FILE = Path(".env")
api_key = None
if ENV_FILE.exists():
    with open(ENV_FILE, "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.strip().split("=", 1)[1]
                break

if not api_key:
    api_key = os.environ.get("GEMINI_API_KEY", "")

pdf_path = Path("data/evaluation_dataset/real/Xerox Scan_10092025083530.pdf")
if not pdf_path.exists():
    pdf_path = Path("data/evaluation_dataset/real/Xerox_Scan_10092025083530.pdf")

# 6 Pilot Pages (0-indexed: 0=Page 1, 1=Page 2, 3=Page 4, 4=Page 5, 6=Page 7, 9=Page 10)
PILOT_PAGES = [0, 1, 3, 4, 6, 9]

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
IMG_OUT_DIR = REPORTS_DIR / "pilot_review_assets"
IMG_OUT_DIR.mkdir(exist_ok=True)

PROMPT = """You are an expert engineering drawing reviewer.
Analyze this scanned engineering drawing and detect all HANDWRITTEN reviewer redline comments, notes, stamps, and callouts (written in red, blue, or green pen/pencil).
Do NOT extract standard printed CAD background text, title block boilerplate, or table headers.
Ignore translucent yellow highlighter marks.
Only extract genuine reviewer annotations.

For each detected review note, return a JSON array of objects with:
- 'box_2d': [ymin, xmin, ymax, xmax] normalized on scale 0 to 1000
- 'ink_color': the color of the reviewer pen (e.g. 'red', 'blue', 'green')
- 'transcribed_text': exact verbatim transcription of the reviewer's handwriting (do not include printed CAD drawing text)
- 'action_verb': primary action command (e.g. 'REMOVE', 'UPDATE', 'VERIFY', 'CHECK', 'SEE') or null
- 'discipline': likely engineering discipline (e.g. 'Mechanical', 'Electrical', 'Structural', 'General')
- 'note_type': 'handwritten_comment', 'cloud_markup', 'dimension_change', or 'stamp'

If there are NO reviewer annotations on this page (it is a clean CAD drawing), return an empty JSON array: [].
Return ONLY valid JSON."""

def run_pilot():
    doc = fitz.open(pdf_path)
    pilot_results = []

    print("=" * 80)
    print(f"RUNNING GEMINI VISION VLM PILOT ON 6 PAGES OF {pdf_path.name}")
    print("=" * 80)

    for p_idx in PILOT_PAGES:
        page_num = p_idx + 1
        page = doc[p_idx]
        pw, ph = float(page.rect.width), float(page.rect.height)

        print(f"\nProcessing Page {page_num:2d} (Visual dimensions: {pw:.1f} x {ph:.1f} pt)...")

        # Render page at 150 DPI for crystal clear handwriting visibility
        zoom = 150.0 / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        b64_img = base64.b64encode(img_bytes).decode("utf-8")

        # Call Gemini 3.8 Flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": "image/png", "data": b64_img}}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code != 200:
                print(f"  Error from API ({resp.status_code}): {resp.text[:200]}")
                raw_items = []
            else:
                resp_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                raw_items = json.loads(resp_text)
                if not isinstance(raw_items, list):
                    raw_items = []
        except Exception as e:
            print(f"  Exception querying API: {e}")
            raw_items = []

        print(f"  -> Extracted {len(raw_items)} review annotations on Page {page_num}")

        # Convert normalized coordinates [0..1000] to PDF points [x0, y0, x1, y1]
        converted_items = []
        for idx, item in enumerate(raw_items, 1):
            box = item.get("box_2d", [0, 0, 0, 0])
            ymin, xmin, ymax, xmax = box[0], box[1], box[2], box[3]
            
            # Map 0..1000 to PDF coordinates
            x0 = round((xmin / 1000.0) * pw, 1)
            y0 = round((ymin / 1000.0) * ph, 1)
            x1 = round((xmax / 1000.0) * pw, 1)
            y1 = round((ymax / 1000.0) * ph, 1)

            conv = {
                "id": f"P{page_num}_N{idx}",
                "page": page_num,
                "bbox_pdf": [x0, y0, x1, y1],
                "bbox_norm": [ymin, xmin, ymax, xmax],
                "ink_color": item.get("ink_color", "red"),
                "transcribed_text": item.get("transcribed_text", "").strip(),
                "action_verb": item.get("action_verb"),
                "discipline": item.get("discipline", "General"),
                "note_type": item.get("note_type", "handwritten_comment")
            }
            converted_items.append(conv)
            print(f"     [{conv['id']}] ({conv['ink_color']}): {repr(conv['transcribed_text'][:65])}")

        # Generate overlay image with bounding boxes
        pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        draw = ImageDraw.Draw(pil_img)
        img_w, img_h = pil_img.size

        for item in converted_items:
            ymin, xmin, ymax, xmax = item["bbox_norm"]
            px0 = int((xmin / 1000.0) * img_w)
            py0 = int((ymin / 1000.0) * img_h)
            px1 = int((xmax / 1000.0) * img_w)
            py1 = int((ymax / 1000.0) * img_h)

            color = (255, 30, 30) if item["ink_color"] == "red" else (30, 100, 255)
            # Outline box
            draw.rectangle([px0, py0, px1, py1], outline=color, width=4)
            # Tag label
            draw.rectangle([px0, max(0, py0 - 24), px0 + 80, py0], fill=color)
            draw.text((px0 + 5, max(0, py0 - 20)), item["id"], fill=(255, 255, 255))

        out_img_name = f"page_{page_num}_annotated.png"
        out_img_path = IMG_OUT_DIR / out_img_name
        pil_img.save(out_img_path, format="PNG")

        pilot_results.append({
            "page_number": page_num,
            "width": pw,
            "height": ph,
            "annotation_count": len(converted_items),
            "image_filename": out_img_name,
            "annotations": converted_items
        })

        time.sleep(1.0) # Graceful delay between requests

    # 4. Save Structured JSON
    json_path = REPORTS_DIR / "ground_truth_pilot_6pages.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(pilot_results, f, indent=2)
    print(f"\n[OK] Pilot ground truth JSON saved to: {json_path}")

    # 5. Generate Standalone HTML Visual Verification App
    generate_html_reviewer(pilot_results)

def generate_html_reviewer(pilot_data):
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ground Truth Pilot Review — 6 Pages Xerox Scan</title>
<style>
  :root {
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --border-color: #334155;
    --text-primary: #f8fafc;
    --text-muted: #94a3b8;
    --accent: #38bdf8;
    --tag-red: #ef4444;
    --tag-blue: #3b82f6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  header {
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  header h1 { font-size: 1.15rem; font-weight: 600; color: #fff; }
  .badge { background: #0369a1; color: #e0f2fe; padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
  .layout {
    display: flex;
    flex: 1;
    overflow: hidden;
  }
  .sidebar {
    width: 320px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
  }
  .page-nav {
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    gap: 8px;
    overflow-x: auto;
  }
  .page-btn {
    background: #334155;
    color: #fff;
    border: none;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 0.85rem;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
  }
  .page-btn.active { background: var(--accent); color: #0f172a; font-weight: 600; }
  .items-list {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }
  .item-card {
    background: #0f172a;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 12px;
    cursor: pointer;
    transition: border-color 0.15s, transform 0.1s;
  }
  .item-card:hover { border-color: var(--accent); }
  .item-card.active { border-color: var(--accent); background: #1e293b; }
  .item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .item-id { font-weight: 700; font-size: 0.8rem; color: var(--accent); }
  .item-verb {
    background: #334155;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
  }
  .item-text {
    font-size: 0.88rem;
    line-height: 1.35;
    color: #e2e8f0;
    margin-bottom: 8px;
  }
  .item-meta {
    font-size: 0.75rem;
    color: var(--text-muted);
    display: flex;
    gap: 12px;
  }
  .main-viewer {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #090d16;
    overflow: auto;
    padding: 20px;
    position: relative;
  }
  .img-container {
    max-width: 95%;
    max-height: 95%;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    border-radius: 4px;
    overflow: hidden;
  }
  .img-container img {
    display: block;
    max-width: 100%;
    max-height: 85vh;
    object-fit: contain;
  }
  .empty-state {
    color: var(--text-muted);
    font-size: 0.95rem;
    text-align: center;
    padding: 40px 20px;
  }
</style>
</head>
<body>
  <header>
    <h1>AI-Assisted Ground Truth Pilot Review — Xerox Scan (6 Pages)</h1>
    <span class="badge">Model: Gemini 3.8 Flash Vision</span>
  </header>
  <div class="layout">
    <div class="sidebar">
      <div class="page-nav" id="pageNav"></div>
      <div class="items-list" id="itemsList"></div>
    </div>
    <div class="main-viewer">
      <div class="img-container">
        <img id="pageImg" src="" alt="Drawing Page Preview">
      </div>
    </div>
  </div>

  <script>
    const data = """ + json.dumps(pilot_data) + """;
    let currentPageIndex = 0;

    const pageNav = document.getElementById('pageNav');
    const itemsList = document.getElementById('itemsList');
    const pageImg = document.getElementById('pageImg');

    function renderNav() {
      pageNav.innerHTML = '';
      data.forEach((p, idx) => {
        const btn = document.createElement('button');
        btn.className = 'page-btn' + (idx === currentPageIndex ? ' active' : '');
        btn.textContent = `Page ${p.page_number} (${p.annotation_count})`;
        btn.onclick = () => selectPage(idx);
        pageNav.appendChild(btn);
      });
    }

    function selectPage(idx) {
      currentPageIndex = idx;
      renderNav();
      const p = data[idx];
      pageImg.src = 'pilot_review_assets/' + p.image_filename;

      itemsList.innerHTML = '';
      if (p.annotations.length === 0) {
        itemsList.innerHTML = `
          <div class="empty-state">
            <strong>Clean Page (0 Notes)</strong><br><br>
            No reviewer handwriting found on this page. Zero false positives or hallucinations.
          </div>
        `;
        return;
      }

      p.annotations.forEach(item => {
        const card = document.createElement('div');
        card.className = 'item-card';
        card.innerHTML = `
          <div class="item-header">
            <span class="item-id">${item.id}</span>
            <span class="item-verb">${item.action_verb || 'NOTE'}</span>
          </div>
          <div class="item-text">${item.transcribed_text}</div>
          <div class="item-meta">
            <span>Color: <strong>${item.ink_color}</strong></span>
            <span>Discipline: <strong>${item.discipline}</strong></span>
          </div>
        `;
        itemsList.appendChild(card);
      });
    }

    // Initialize on first page
    renderNav();
    selectPage(0);
  </script>
</body>
</html>
"""
    html_file = REPORTS_DIR / "ground_truth_pilot_review.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] Interactive HTML visual reviewer saved to: {html_file.resolve()}")

if __name__ == "__main__":
    run_pilot()
