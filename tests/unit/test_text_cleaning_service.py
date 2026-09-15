import pytest
from src.services.text_cleaning_service import TextCleaningService

def test_remove_ocr_noise():
    service = TextCleaningService()
    res = service.clean_text("Hello!!!")
    assert res.cleaned_text == "Hello!"

def test_normalize_whitespace():
    service = TextCleaningService()
    res = service.clean_text("Too   much    space")
    assert res.cleaned_text == "Too much space"

def test_engineering_abbreviation_expansion():
    service = TextCleaningService()
    res = service.clean_text("Check P&ID")
    assert "Piping and Instrumentation Diagram" in res.cleaned_text

def test_duplicate_detection():
    service = TextCleaningService()
    dups = service.detect_duplicates(["same text", "same text"])
    assert len(dups) == 1

def test_clean_batch_returns_stats():
    service = TextCleaningService()
    batch = [{"text": "A"}, {"text": "B"}, {"text": "C"}, {"text": "D"}, {"text": "E"}]
    res = service.clean_batch(batch)
    assert res.total_comments == 5

def test_similarity_score_range():
    service = TextCleaningService()
    res = service.clean_text("Text")
    assert 0.0 <= res.similarity_score <= 1.0

def test_domain_safe_spell_correction():
    service = TextCleaningService()
    
    # Typos in engineering review text
    res1 = service.clean_text("NUVA FEEDEER TAGS ARE CORRECT")
    assert "FEEDER" in res1.cleaned_text
    
    res2 = service.clean_text("RECIEVER B IS OPTIONAL")
    assert "RECEIVER" in res2.cleaned_text
    
    res3 = service.clean_text("THIS IS NOT THE NEST LOCATION")
    assert "BEST LOCATION" in res3.cleaned_text

def test_ocr_spelling_corrections():
    service = TextCleaningService()

    # OCR character misreads from real drawing reviews
    res1 = service.clean_text("AIN ACUEIVERN A IOULATIUN VALVE OULENVID")
    assert "AIR RECEIVER" in res1.cleaned_text
    assert "ISOLATION VALVE" in res1.cleaned_text
    assert "SOLENOID" in res1.cleaned_text

    res2 = service.clean_text("TEMPERATUR SENSOR SECHEMATICS")
    assert "TEMPERATURE" in res2.cleaned_text
    assert "SCHEMATICS" in res2.cleaned_text

    res3 = service.clean_text("TERMINAL  BLOCK ARANGEMENT")
    assert "TERMINAL BLOCK ARRANGEMENT" in res3.cleaned_text

def test_preserve_ground_bar_and_common_terms():
    service = TextCleaningService(expand_acronyms=True)
    
    # GROUND BAR should NOT be expanded to "Barometric Pressure"
    res = service.clean_text("Change to GROUND BAR MOUNTING.")
    assert "Barometric Pressure" not in res.cleaned_text
    assert "GROUND BAR MOUNTING" in res.cleaned_text.upper()

def test_preserve_dimensions_and_tags():
    service = TextCleaningService()
    
    # Protect fractions, schedules, and part tags
    raw = "CL EL 345'-11 3/4\" TYPICAL FOR 8\" SCH 40 PIPE (174005-S12-04-P08) -JDM"
    res = service.clean_text(raw)
    assert "345'-11 3/4\"" in res.cleaned_text
    assert "174005-S12-04-P08" in res.cleaned_text
    assert res.reviewer_initials == "JDM"

def test_preserve_complex_part_numbers():
    service = TextCleaningService()
    
    raw = "Change these to either Z-ISTPHCH1MTL, Z-ISTPHCH2MTL, or Z-ISTPHCH4MTL in AX."
    res = service.clean_text(raw)
    assert "Z-ISTPHCH1MTL" in res.cleaned_text
    assert "Z-ISTPHCH2MTL" in res.cleaned_text
    assert "Z-ISTPHCH4MTL" in res.cleaned_text

def test_multi_action_comment_segmentation():
    service = TextCleaningService()
    
    multi_action_text = "1. FOR GENERAL NOTES SEE C-54718-31-002 2. BILL OF MATERIALS REVISE QUANTITY 3. LASER SCANNING VERIFY DATES"
    res = service.clean_text(multi_action_text)
    assert len(res.sub_actions) >= 3
    assert any("GENERAL NOTES" in act for act in res.sub_actions)
    assert any("BILL OF MATERIALS" in act for act in res.sub_actions)

def test_reviewer_initials_and_priority_extraction():
    service = TextCleaningService()
    
    res_high = service.clean_text("INCORRECT TAGS! DO NOT PROCEED -JDM")
    assert res_high.reviewer_initials == "JDM"
    assert res_high.priority_level == "HIGH"
    
    res_med = service.clean_text("VERIFY GAS FLOW DIRECTION JCM")
    assert res_med.reviewer_initials == "JCM"
    assert res_med.priority_level == "MEDIUM"
    assert res_med.action_verb == "VERIFY"
    
    res_info = service.clean_text("FOR INFORMATION ONLY -BEK")
    assert res_info.reviewer_initials == "BEK"
    assert res_info.priority_level == "LOW"

def test_multi_discipline_terms_found():
    service = TextCleaningService()
    res = service.clean_text("VERIFY P&ID AND CHECK HSS WELDING IN BOM")
    assert "P&ID" in res.engineering_terms_found
    assert "HSS" in res.engineering_terms_found
    assert "BOM" in res.engineering_terms_found
