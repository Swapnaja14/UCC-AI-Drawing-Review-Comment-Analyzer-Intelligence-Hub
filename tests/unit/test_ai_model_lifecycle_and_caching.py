"""
Unit tests verifying AI Model Lifecycle, Single-Load Caching, Concurrency, and Memory Stability:
1. Verify model is loaded once and cached in memory across multiple ClassificationService instances.
2. Measure model initialization time separately from per-comment inference latency.
3. Verify concurrent threads share the same model instance without duplicating weights.
4. Verify memory stability during long-running batch inference (no tensor/memory leaks).
"""

import os
import sys
import time
import gc
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
import pytest

from src.services.classification_service import ClassificationService


def test_1_singleton_model_reuse_across_instances():
    """Verify that creating multiple ClassificationService instances reuses the exact same in-memory model."""
    svc1 = ClassificationService()
    svc2 = ClassificationService()
    svc3 = ClassificationService()

    # Ensure model is loaded in svc1
    svc1.ensure_loaded()

    # Verify svc2 and svc3 share the exact same model & tokenizer memory object IDs
    assert svc1._ai_model is not None
    assert svc2._ai_model is not None
    assert svc3._ai_model is not None

    assert id(svc1._ai_model) == id(svc2._ai_model)
    assert id(svc2._ai_model) == id(svc3._ai_model)

    assert id(svc1._ai_tokenizer) == id(svc2._ai_tokenizer)
    assert id(svc2._ai_tokenizer) == id(svc3._ai_tokenizer)

    # Check cache dict length is exactly 1
    assert len(ClassificationService._models_cache) == 1


def test_2_initialization_vs_inference_time():
    """Verify that cold model loading time is separated from warm inference time."""
    # Temporarily clear cache to measure cold initialization time
    with ClassificationService._cache_lock:
        ClassificationService._models_cache.clear()

    svc = ClassificationService()

    # 1. Measure Cold Load Time
    t_load_start = time.perf_counter()
    loaded = svc.ensure_loaded()
    t_load_ms = (time.perf_counter() - t_load_start) * 1000.0

    assert loaded is True
    print(f"\n[Model Initialization Time]: {t_load_ms:.2f} ms")

    # 2. Measure Warm Inference Time (Single comment)
    sample_text = "REVISE BEAM SIZE TO W24X68 AND CHECK MOMENT CONNECTION AT COLUMN FLANGE"
    
    t_inf_start = time.perf_counter()
    res1 = svc.classify_comment(sample_text)
    t_inf_ms_1 = (time.perf_counter() - t_inf_start) * 1000.0

    t_inf_start2 = time.perf_counter()
    res2 = svc.classify_comment(sample_text)
    t_inf_ms_2 = (time.perf_counter() - t_inf_start2) * 1000.0

    print(f"[Inference 1 Latency]: {t_inf_ms_1:.2f} ms")
    print(f"[Inference 2 Latency]: {t_inf_ms_2:.2f} ms")

    assert res1.classification_method == "ai_model"
    assert res2.classification_method == "ai_model"
    assert res1.primary_category.category_name == res2.primary_category.category_name

    # Subsequent warm inference should be fast and consistent
    assert t_inf_ms_2 < 500.0



def test_3_concurrent_inference_shares_single_model():
    """Verify that multi-threaded concurrent inference accesses the shared model without duplicating instances."""
    svc = ClassificationService()
    svc.ensure_loaded()

    model_obj_id = id(svc._ai_model)
    cache_len_before = len(ClassificationService._models_cache)

    comments = [
        "REVISE PIPE SCHEDULE TO SCH 80 FOR HIGH PRESSURE STEAM",
        "ALIGN TEXT WITH CENTERLINE ELEVATION EL 104.5M",
        "WELD CALLOUT MISSING 1/4 INCH FILLET ON SHEAR TAB",
        "UPDATE DRAWING TITLE BLOCK TO REVISION B",
        "CHECK MINIMUM CLEARANCE AT CABLE TRAY CROSSING",
        "CORRECT SPELLING OF STRUCTURAL STIFFENER IN NOTE 4",
        "NOZZLE FLANGE RATING MUST BE ANSI 300#",
        "MISSING HIDDEN LINES ON ISOMETRIC PROJECTION",
    ] * 5  # 40 items

    def _classify_worker(text):
        local_svc = ClassificationService()
        assert id(local_svc._ai_model) == model_obj_id
        return local_svc.classify_comment(text)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_classify_worker, comments))

    assert len(results) == 40
    assert all(r.classification_method == "ai_model" for r in results)
    # Ensure no extra model copies were created in cache during multi-threaded execution
    assert len(ClassificationService._models_cache) == cache_len_before


def test_4_memory_consumption_stability_long_batch():
    """Verify memory remains constant and does not leak over 200 consecutive inferences."""
    svc = ClassificationService()
    svc.ensure_loaded()

    gc.collect()
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    sample_texts = [
        "REVISE BEAM SIZE TO W24X68",
        "CHECK FLANGE RATING 300#",
        "CORRECT TYPO IN TITLE BLOCK",
        "ADD EXPANSION JOINT JB-101",
    ] * 50  # 200 inferences

    for t in sample_texts:
        _ = svc.classify_comment(t)

    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, 'lineno')
    total_leak_kb = sum(stat.size_diff for stat in stats) / 1024.0
    print(f"\n[Memory Diff across 200 inferences]: {total_leak_kb:.2f} KB")

    # Memory growth should be negligible (< 10 MB total allocation growth for 200 inferences)
    assert total_leak_kb < 10240.0
