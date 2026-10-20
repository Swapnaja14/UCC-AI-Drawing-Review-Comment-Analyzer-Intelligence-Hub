import os
import sys
import time
import json
from pathlib import Path
from PIL import Image
import numpy as np
import pymupdf as fitz

# Ensure offline mode and utf-8
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced

def load_florence2():
    print("[Florence-2] Loading model weights into memory (CPU, float32)...")
    t0 = time.time()
    device = "cpu"
    model = AutoModelForCausalLM.from_pretrained(
        "microsoft/Florence-2-base",
        dtype=torch.float32,
        trust_remote_code=True,
        local_files_only=True
    ).to(device)

    # CRITICAL FIX for transformers 5.x: tie embeddings and head to shared.weight
    lm = model.language_model
    lm.model.encoder.embed_tokens.weight = lm.model.shared.weight
    lm.model.decoder.embed_tokens.weight = lm.model.shared.weight
    lm.lm_head.weight = lm.model.shared.weight

    model.eval()

    processor = AutoProcessor.from_pretrained(
        "microsoft/Florence-2-base",
        trust_remote_code=True,
        local_files_only=True
    )
    print(f"[Florence-2] Model and Processor loaded & weights tied in {time.time()-t0:.2f}s")
    return model, processor, device

def run_florence_ocr(model, processor, device, pil_img, task="<OCR>"):
    try:
        rgb_img = pil_img.convert("RGB")
        inputs = processor(text=task, images=rgb_img, return_tensors="pt").to(device)
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.float32)

        t0 = time.time()
        with torch.no_grad():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=80,
                num_beams=1,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
                use_cache=False
            )
        latency = time.time() - t0

        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = processor.post_process_generation(
            generated_text,
            task=task,
            image_size=(rgb_img.width, rgb_img.height)
        )
        # Parse extracted text
        extracted_text = ""
        if isinstance(parsed_answer, dict):
            if task in parsed_answer:
                val = parsed_answer[task]
                if isinstance(val, str):
                    extracted_text = val.strip()
                elif isinstance(val, dict) and "labels" in val:
                    extracted_text = " ".join(val["labels"]).strip()
            elif "<OCR>" in parsed_answer:
                extracted_text = str(parsed_answer["<OCR>"]).strip()
            else:
                extracted_text = str(parsed_answer).strip()
        elif isinstance(parsed_answer, str):
            extracted_text = parsed_answer.strip()

        return extracted_text, latency
    except Exception as e:
        print(f"Error in Florence-2 inference: {e}")
        return "", 0.0

def compute_box_iou(boxA, boxB):
    # box: [x1, y1, x2, y2]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxBArea = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])
    unionArea = float(boxAArea + boxBArea - interArea)
    return interArea / unionArea if unionArea > 0 else 0.0

def main():
    pdf_path = Path("data/evaluation_dataset/real/Xerox Scan_10092025083530.pdf")
    if not pdf_path.exists():
        pdf_path = Path("data/evaluation_dataset/real/Xerox_Scan_10092025083530.pdf")

    crops_dir = Path("reports/florence2_crops")
    crops_dir.mkdir(parents=True, exist_ok=True)

    # Load Gemini ground truth
    gt_file = Path("reports/ground_truth_pilot_6pages.json")
    ground_truth_by_page = {}
    if gt_file.exists():
        with open(gt_file, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
            for page_entry in gt_data:
                ground_truth_by_page[page_entry["page_number"]] = page_entry.get("annotations", [])

    # Load baseline Tesseract results
    baseline_file = Path("reports/all_pages_color_isolated_scan_results.json")
    tesseract_by_page = {}
    if baseline_file.exists():
        with open(baseline_file, "r", encoding="utf-8") as f:
            base_data = json.load(f)
            for page_entry in base_data:
                tesseract_by_page[page_entry["page"]] = page_entry.get("comments", [])

    # Initialize detection service and Florence-2
    detector = AnnotationDetectionServiceEnhanced(detect_markers_as_items=True)
    model, processor, device = load_florence2()

    doc = fitz.open(pdf_path)
    pilot_page_indices = [0, 1, 3, 4, 6, 9]  # Pages 1, 2, 4, 5, 7, 10

    results = []
    total_crops_processed = 0
    total_inference_time = 0.0

    print(f"\n=================================================================")
    print(f"RUNNING FLORENCE-2 OCR ON 6 PILOT PAGES ({len(pilot_page_indices)} pages)")
    print(f"=================================================================\n")

    for p_idx in pilot_page_indices:
        page_num = p_idx + 1
        page = doc[p_idx]
        pw, ph = page.rect.width, page.rect.height

        # Render page to high-res pixmap (150 DPI)
        scale = 150.0 / 72.0
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_full = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Detect candidate bounding boxes using hybrid method
        detection_res = detector.detect_annotations_on_page(pdf_path, p_idx, method="hybrid")
        raw_annotations = detection_res.regions if detection_res else []

        page_gt = ground_truth_by_page.get(page_num, [])
        page_tess = tesseract_by_page.get(page_num, [])

        print(f"--- PAGE {page_num}: Detected {len(raw_annotations)} Candidate Markup Regions ---")

        page_record = {
            "page_number": page_num,
            "page_width": pw,
            "page_height": ph,
            "detected_regions_count": len(raw_annotations),
            "regions": []
        }

        for idx, ann in enumerate(raw_annotations, 1):
            x1_pdf, y1_pdf, x2_pdf, y2_pdf = ann.x0, ann.y0, ann.x1, ann.y1

            # Scale to pixmap pixel coordinates with margin
            margin_pdf = 6.0
            x1_pix = max(0, int((x1_pdf - margin_pdf) * scale))
            y1_pix = max(0, int((y1_pdf - margin_pdf) * scale))
            x2_pix = min(pix.width, int((x2_pdf + margin_pdf) * scale))
            y2_pix = min(pix.height, int((y2_pdf + margin_pdf) * scale))

            if (x2_pix - x1_pix) < 10 or (y2_pix - y1_pix) < 10:
                continue

            raw_crop = img_full.crop((x1_pix, y1_pix, x2_pix, y2_pix))

            # Create color-isolated crop (red/blue/green reviewer ink vs white background)
            np_crop = np.array(raw_crop)
            nr = np_crop[:, :, 0].astype(int)
            ng = np_crop[:, :, 1].astype(int)
            nb = np_crop[:, :, 2].astype(int)

            mask_red = (nr >= 120) & ((nr - np.maximum(ng, nb)) >= 24)
            mask_blue = (nb >= 110) & ((nb - np.maximum(nr, ng)) >= 24)
            mask_green = (ng >= 100) & ((ng - np.maximum(nr, nb)) >= 24)
            colored_mask = mask_red | mask_blue | mask_green

            iso_arr = np.full((np_crop.shape[0], np_crop.shape[1], 3), 255, dtype=np.uint8)
            # Retain original colored ink on white background
            iso_arr[colored_mask] = np_crop[colored_mask]
            iso_crop = Image.fromarray(iso_arr)

            # Save crop files
            raw_crop_filename = f"p{page_num}_box{idx}_raw.png"
            iso_crop_filename = f"p{page_num}_box{idx}_isolated.png"
            raw_crop_path = crops_dir / raw_crop_filename
            iso_crop_path = crops_dir / iso_crop_filename

            raw_crop.save(raw_crop_path)
            iso_crop.save(iso_crop_path)

            # Run Florence-2 OCR on raw crop
            florence_raw_text, lat_raw = run_florence_ocr(model, processor, device, raw_crop, task="<OCR>")
            # Run Florence-2 OCR on isolated crop
            florence_iso_text, lat_iso = run_florence_ocr(model, processor, device, iso_crop, task="<OCR>")

            total_crops_processed += 2
            total_inference_time += (lat_raw + lat_iso)

            # Find matching Gemini Ground Truth annotation by IoU
            matched_gt = None
            best_iou = 0.0
            candidate_box = [x1_pdf, y1_pdf, x2_pdf, y2_pdf]
            for gt_ann in page_gt:
                gt_box = gt_ann.get("bbox_pdf", [])
                if len(gt_box) == 4:
                    iou = compute_box_iou(candidate_box, gt_box)
                    if iou > best_iou:
                        best_iou = iou
                        matched_gt = gt_ann

            # Find matching Tesseract comment
            matched_tess_text = ""
            for tess_item in page_tess:
                t_box = tess_item.get("bbox", [])
                if len(t_box) == 4 and compute_box_iou(candidate_box, t_box) > 0.3:
                    matched_tess_text = tess_item.get("extracted_comment_text", "")
                    break

            region_data = {
                "box_id": f"P{page_num}_B{idx}",
                "page": page_num,
                "bbox_pdf": [round(x1_pdf, 1), round(y1_pdf, 1), round(x2_pdf, 1), round(y2_pdf, 1)],
                "confidence": round(float(ann.confidence), 3),
                "detected_color": getattr(ann, "label", "red"),
                "raw_crop_rel": f"florence2_crops/{raw_crop_filename}",
                "isolated_crop_rel": f"florence2_crops/{iso_crop_filename}",
                "florence_raw_text": florence_raw_text,
                "florence_iso_text": florence_iso_text,
                "florence_latency_sec": round(lat_raw + lat_iso, 2),
                "tesseract_text": matched_tess_text,
                "matched_gt_id": matched_gt.get("id") if matched_gt else None,
                "matched_gt_text": matched_gt.get("transcribed_text") if matched_gt else None,
                "matched_gt_type": matched_gt.get("note_type") if matched_gt else None,
                "gt_iou": round(best_iou, 3)
            }
            page_record["regions"].append(region_data)

            print(f"  [Box {idx}] GT: '{matched_gt.get('transcribed_text') if matched_gt else 'None'}'")
            print(f"          Florence (Raw): '{florence_raw_text}'")
            print(f"          Florence (Iso): '{florence_iso_text}'")

        results.append(page_record)

    # Save JSON report
    out_json = Path("reports/florence2_scan_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[Output] Saved Florence-2 scan results to: {out_json}")

    # Generate HTML review page
    generate_html_review(results, total_crops_processed, total_inference_time)

def generate_html_review(results, total_crops, total_time):
    html_path = Path("reports/florence2_review.html")

    all_regions = []
    for p in results:
        for r in p["regions"]:
            all_regions.append(r)

    avg_time = (total_time / total_crops) if total_crops > 0 else 0.0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Florence-2 Local VLM Scanned Markup Benchmark</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-secondary: #131b2e;
            --bg-card: #1a233a;
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: rgba(255, 255, 255, 0.08);
            --card-radius: 12px;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 24px;
        }}
        .header {{
            max-width: 1400px;
            margin: 0 auto 24px auto;
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
            border: 1px solid var(--border-color);
            border-radius: var(--card-radius);
            padding: 24px 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        }}
        .title-area h1 {{
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(90deg, #00f2fe, #4facfe);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        .title-area p {{
            color: var(--text-secondary);
            font-size: 14px;
        }}
        .stats-grid {{
            display: flex;
            gap: 20px;
        }}
        .stat-card {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 18px;
            text-align: center;
        }}
        .stat-val {{
            font-size: 20px;
            font-weight: 700;
            color: var(--accent-cyan);
        }}
        .stat-lbl {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .filter-bar {{
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            align-items: center;
        }}
        .filter-btn {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .filter-btn.active, .filter-btn:hover {{
            background: rgba(79, 172, 254, 0.15);
            border-color: var(--accent-blue);
            color: #fff;
        }}
        .comparison-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0 12px;
        }}
        .comparison-table th {{
            padding: 12px 16px;
            text-align: left;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }}
        .comparison-row {{
            background: var(--bg-card);
            border-radius: var(--card-radius);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .comparison-row:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.35);
        }}
        .comparison-row td {{
            padding: 16px;
            vertical-align: top;
            border-top: 1px solid var(--border-color);
            border-bottom: 1px solid var(--border-color);
        }}
        .comparison-row td:first-child {{
            border-left: 1px solid var(--border-color);
            border-top-left-radius: var(--card-radius);
            border-bottom-left-radius: var(--card-radius);
        }}
        .comparison-row td:last-child {{
            border-right: 1px solid var(--border-color);
            border-top-right-radius: var(--card-radius);
            border-bottom-right-radius: var(--card-radius);
        }}
        .meta-col {{
            width: 110px;
        }}
        .badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 4px;
            margin-bottom: 6px;
            text-transform: uppercase;
        }}
        .badge-red {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .badge-blue {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
        .box-title {{
            font-size: 13px;
            font-weight: 600;
            color: #fff;
        }}
        .box-coords {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        .crops-col {{
            width: 280px;
        }}
        .crop-wrapper {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .crop-item {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .crop-lbl {{
            font-size: 10px;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        .crop-img {{
            max-width: 260px;
            max-height: 100px;
            object-fit: contain;
            border-radius: 6px;
            background: #fff;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .text-box {{
            padding: 10px 12px;
            border-radius: 6px;
            font-size: 13px;
            line-height: 1.4;
            min-height: 50px;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .text-florence {{
            background: rgba(139, 92, 246, 0.1);
            border: 1px solid rgba(139, 92, 246, 0.3);
            color: #ddd6fe;
            font-family: 'JetBrains Mono', monospace;
        }}
        .text-gt {{
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #6ee7b7;
            font-weight: 500;
        }}
        .text-tess {{
            background: rgba(100, 116, 139, 0.1);
            border: 1px solid rgba(100, 116, 139, 0.3);
            color: #94a3b8;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
        }}
        .empty-text {{
            color: var(--text-muted);
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title-area">
            <h1>Microsoft Florence-2 Local VLM Scanned Markup Benchmark</h1>
            <p>Evaluation of compact local VLM (Florence-2-base, CPU) on Xerox scanned engineering drawings</p>
        </div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-val">{len(results)}</div>
                <div class="stat-lbl">Pilot Pages</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{len(all_regions)}</div>
                <div class="stat-lbl">Candidate Regions</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{avg_time:.2f}s</div>
                <div class="stat-lbl">Avg Inference / Crop</div>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="filter-bar">
            <span style="font-size: 12px; color: var(--text-muted); margin-right: 8px;">FILTER PAGE:</span>
            <button class="filter-btn active" onclick="filterPage('all')">All Pages ({len(all_regions)})</button>
"""
    for p in results:
        p_num = p["page_number"]
        cnt = len(p["regions"])
        html += f'            <button class="filter-btn" onclick="filterPage({p_num})">Page {p_num} ({cnt})</button>\n'

    html += """        </div>

        <table class="comparison-table">
            <thead>
                <tr>
                    <th style="width: 120px;">Markup Box</th>
                    <th style="width: 280px;">Visual Crops</th>
                    <th style="width: 320px;">Florence-2 (Local VLM)</th>
                    <th style="width: 300px;">Gemini Ground Truth</th>
                    <th>Tesseract Baseline</th>
                </tr>
            </thead>
            <tbody>
"""

    for r in all_regions:
        p_num = r["page"]
        b_id = r["box_id"]
        color = r.get("detected_color", "red")
        raw_crop = r.get("raw_crop_rel", "")
        iso_crop = r.get("isolated_crop_rel", "")
        f_raw = r.get("florence_raw_text", "")
        f_iso = r.get("florence_iso_text", "")
        gt_text = r.get("matched_gt_text", "")
        gt_type = r.get("matched_gt_type", "markup")
        tess_text = r.get("tesseract_text", "")
        coords = r.get("bbox_pdf", [])

        f_raw_disp = f_raw if f_raw else '<span class="empty-text">[No text detected]</span>'
        f_iso_disp = f_iso if f_iso else '<span class="empty-text">[No text detected]</span>'
        gt_disp = gt_text if gt_text else '<span class="empty-text">[Graphic markup / No text]</span>'
        tess_disp = tess_text if tess_text else '<span class="empty-text">[No text]</span>'

        badge_cls = "badge-blue" if color == "blue" else "badge-red"

        html += f"""                <tr class="comparison-row" data-page="{p_num}">
                    <td class="meta-col">
                        <span class="badge {badge_cls}">{color}</span>
                        <div class="box-title">{b_id}</div>
                        <div class="box-coords">[{coords[0]}, {coords[1]}]<br>[{coords[2]}, {coords[3]}]</div>
                    </td>
                    <td class="crops-col">
                        <div class="crop-wrapper">
                            <div class="crop-item">
                                <span class="crop-lbl">Raw Page Crop:</span>
                                <img src="{raw_crop}" class="crop-img" alt="Raw Crop">
                            </div>
                            <div class="crop-item">
                                <span class="crop-lbl">Color Isolated (Mask):</span>
                                <img src="{iso_crop}" class="crop-img" alt="Isolated Crop">
                            </div>
                        </div>
                    </td>
                    <td>
                        <div style="display: flex; flex-direction: column; gap: 8px;">
                            <div>
                                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">From Raw Crop:</span>
                                <div class="text-box text-florence">{f_raw_disp}</div>
                            </div>
                            <div>
                                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">From Color-Isolated Crop:</span>
                                <div class="text-box text-florence">{f_iso_disp}</div>
                            </div>
                            <div style="font-size: 10px; color: var(--text-muted);">Latency: {r.get('florence_latency_sec', 0)}s</div>
                        </div>
                    </td>
                    <td>
                        <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Type: {gt_type}</span>
                        <div class="text-box text-gt">{gt_disp}</div>
                    </td>
                    <td>
                        <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Tesseract:</span>
                        <div class="text-box text-tess">{tess_disp}</div>
                    </td>
                </tr>
"""

    html += """            </tbody>
        </table>
    </div>

    <script>
        function filterPage(pageNum) {
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            const rows = document.querySelectorAll('.comparison-row');
            rows.forEach(row => {
                if (pageNum === 'all' || row.getAttribute('data-page') == pageNum) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Output] Generated Florence-2 HTML Review page: {html_path}")

if __name__ == "__main__":
    main()
