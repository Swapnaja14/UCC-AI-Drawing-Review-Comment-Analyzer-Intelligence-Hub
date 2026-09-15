"""
src/services/text_cleaning_service.py
Advanced Text Cleaning, Multi-Discipline Engineering Dictionary, Domain-Safe Spell Correction,
Comment Action Segmentation, Reviewer Attribution, and Semantic Duplicate Detection Engine.
"""

import re
import difflib
import time
from typing import List, Dict, Any, Tuple, Optional, Set
from src.core.dtos.comment_processing_dtos import (
    CleanedCommentDTO,
    CorrectionDTO,
    TextCleaningResultDTO
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class TextCleaningService:
    """
    NLP & Text Intelligence Engine for engineering reviewer markup text.
    Provides multi-discipline acronym expansion, domain-safe spell correction,
    OCR noise suppression, multi-action segmentation, reviewer attribution,
    priority scoring, and cross-drawing semantic duplicate detection.
    """

    def __init__(self, expand_acronyms: bool = True):
        self.expand_acronyms = expand_acronyms
        self.engineering_dict = self._build_engineering_dictionary()
        self.discipline_taxonomies = self._build_discipline_taxonomies()
        self.known_typos = self._build_known_typos_map()
        self._standard_vocab = self._build_standard_vocab()
        self.action_verbs = self._build_action_verbs_set()
        self.high_priority_keywords = {
            "DO NOT", "INCORRECT", "WRONG", "CRITICAL", "SAFETY", 
            "CONFLICTING", "MUST", "ERROR", "HOLD", "STOP", "FAIL", "REJECT"
        }
        self.medium_priority_keywords = {
            "VERIFY", "CONFIRM", "UPDATE", "REVISE", "CHECK", "ROTATE", 
            "ADD", "INDICATE", "CLARIFY", "MATCH", "SWITCH", "LOCATE", "REFERENCE"
        }
        self.low_priority_keywords = {
            "FOR INFORMATION ONLY", "NOTE:", "NOTE", "SIMILAR TO", "FYI", "TYPICAL", "AS-BUILT"
        }

    # =========================================================================
    # 1. DICTIONARIES & TAXONOMIES
    # =========================================================================

    def _build_engineering_dictionary(self) -> Dict[str, str]:
        """Comprehensive multi-discipline engineering acronym and terminology dictionary."""
        return {
            # Drawing & General Documentation
            'DWG': 'Drawing',
            'REV': 'Revision',
            'REQD': 'Required',
            "REQ'D": 'Required',
            'QTY': 'Quantity',
            'DIA': 'Diameter',
            'THK': 'Thickness',
            'MIN': 'Minimum',
            'MAX': 'Maximum',
            'ELEV': 'Elevation',
            'COORD': 'Coordinate',
            'SPECS': 'Specifications',
            'DTL': 'Detail',
            'SECT': 'Section',
            'CTR': 'Center',
            'REF': 'Reference',

            # Piping & Process
            'P&ID': 'Piping and Instrumentation Diagram',
            'P&I': 'Piping and Instrumentation',
            'PFD': 'Process Flow Diagram',
            'BOM': 'Bill of Materials',
            'MTO': 'Material Take-Off',
            'NPS': 'Nominal Pipe Size',
            'DN': 'Diameter Nominal',
            'PN': 'Pressure Nominal',
            'SCH': 'Schedule',
            'SS316L': 'Stainless Steel 316L',
            'SS304': 'Stainless Steel 304',
            'CS': 'Carbon Steel',
            'PSV': 'Pressure Safety Valve',
            'PRV': 'Pressure Relief Valve',
            'ESD': 'Emergency Shutdown',
            'HAZOP': 'Hazard and Operability Study',
            'SIL': 'Safety Integrity Level',
            'FLG': 'Flange',
            'EXP': 'Expansion',
            'BW': 'Butt Weld',
            'SW': 'Socket Weld',
            'THD': 'Threaded',
            'NPT': 'National Pipe Taper',
            'RF': 'Raised Face',
            'FF': 'Flat Face',
            'RTJ': 'Ring Type Joint',
            'SO': 'Slip On',
            'WN': 'Weld Neck',
            'BL': 'Blind Flange',
            'SPEC': 'Specification',
            'FEED': 'Front End Engineering Design',
            'EPC': 'Engineering Procurement Construction',
            'MOC': 'Management of Change',

            # Mechanical & HVAC
            'GA': 'General Arrangement',
            'ISO': 'Isometric',
            'DIM': 'Dimension',
            'TOL': 'Tolerance',
            'HVAC': 'Heating Ventilation and Air Conditioning',
            'CFM': 'Cubic Feet per Minute',
            'BHP': 'Brake Horsepower',
            'RPM': 'Revolutions Per Minute',
            'GPM': 'Gallons Per Minute',
            'AHU': 'Air Handling Unit',
            'FCU': 'Fan Coil Unit',
            'VAV': 'Variable Air Volume',
            'CW': 'Cold Water',
            'HW': 'Hot Water',
            'CHW': 'Chilled Water',
            'HP': 'Horsepower',
            'KW': 'Kilowatt',
            'PSI': 'Pounds per Square Inch',
            'PSIG': 'Pounds per Square Inch Gauge',
            'BAR': 'Barometric Pressure',
            'FPM': 'Feet Per Minute',
            'REF': 'Reference',
            'TYP': 'Typical',
            'SHT': 'Sheet',

            # Civil & Structural
            'HSS': 'Hollow Structural Section',
            'CL': 'Centerline',
            'EL': 'Elevation',
            'TOC': 'Top of Concrete',
            'BOS': 'Bottom of Steel',
            'TOS': 'Top of Steel',
            'PL': 'Plate',
            'COL': 'Column',
            'FTG': 'Footing',
            'BM': 'Beam',
            'WF': 'Wide Flange',
            'FND': 'Foundation',
            'AB': 'Anchor Bolt',
            'CJ': 'Construction Joint',
            'EJ': 'Expansion Joint',
            'REBAR': 'Reinforcing Bar',
            'FFL': 'Finished Floor Level',
            'SSL': 'Structural Slab Level',
            'GL': 'Ground Level',

            # Electrical & Instrumentation
            'I/O': 'Input Output',
            'PLC': 'Programmable Logic Controller',
            'DCS': 'Distributed Control System',
            'SCADA': 'Supervisory Control and Data Acquisition',
            'VFD': 'Variable Frequency Drive',
            'RTD': 'Resistance Temperature Detector',
            'JB': 'Junction Box',
            'NEMA': 'National Electrical Manufacturers Association',
            'PE': 'Protective Earth',
            'GND': 'Ground',
            'MCC': 'Motor Control Center',
            'UPS': 'Uninterruptible Power Supply',
            'CT': 'Current Transformer',
            'PT': 'Potential Transformer',
            'DP': 'Differential Pressure',
            'FIT': 'Flow Indicating Transmitter',
            'LIT': 'Level Indicating Transmitter',
            'PIT': 'Pressure Indicating Transmitter',
            'TIT': 'Temperature Indicating Transmitter',
            'FCV': 'Flow Control Valve',
            'LCV': 'Level Control Valve',
            'PCV': 'Pressure Control Valve',
            'TCV': 'Temperature Control Valve',
            'SOV': 'Solenoid Operated Valve',

            # Quality, Codes & Standards
            'ASME': 'American Society of Mechanical Engineers',
            'AWS': 'American Welding Society',
            'API': 'American Petroleum Institute',
            'ASTM': 'American Society for Testing and Materials',
            'NFPA': 'National Fire Protection Association',
            'OSHA': 'Occupational Safety and Health Administration',
            'PPE': 'Personal Protective Equipment',
            'SOP': 'Standard Operating Procedure',
            'QA': 'Quality Assurance',
            'QC': 'Quality Control',
            'NDE': 'Non-Destructive Examination',
            'NDT': 'Non-Destructive Testing',
            'WPS': 'Welding Procedure Specification',
            'PQR': 'Procedure Qualification Record',
            'NACE': 'National Association of Corrosion Engineers',
            'MSS': 'Manufacturers Standardization Society',
            'ISA': 'International Society of Automation',
            'IEEE': 'Institute of Electrical and Electronics Engineers',
            'NEC': 'National Electrical Code',
            'IEC': 'International Electrotechnical Commission',
        }

    def _build_discipline_taxonomies(self) -> Dict[str, Set[str]]:
        """Categorized keywords mapped to technical engineering disciplines."""
        return {
            "Piping/Process": {
                "P&ID", "PFD", "PIPE", "PIPING", "VALVE", "FLANGE", "FITTING", "FLG", "EXP",
                "NPS", "DN", "SCH", "SS316L", "CS", "PSV", "PRV", "ESD", "HAZOP", "MTO",
                "NUVALOY", "AIRLINE", "FEEDER", "FLOW", "GAS", "HOPPER", "BOM", "NOZZLE"
            },
            "Mechanical/HVAC": {
                "HVAC", "DUCT", "AIR", "CFM", "AHU", "VAV", "PUMP", "COMPRESSOR", "MOTOR",
                "BEARING", "COUPLING", "FAN", "BLOWER", "COOLING", "HEATER", "EXHAUST", "DAMPER"
            },
            "Structural/Civil": {
                "STEEL", "BEAM", "COLUMN", "CONCRETE", "FOUNDATION", "HSS", "BRACKET",
                "WELD", "WELDING", "FLANGE", "GIRDER", "TRUSS", "BASEPLATE", "ANCHOR", "REBAR",
                "GRID", "FOOTING", "TOC", "BOS", "TOS", "PLATE"
            },
            "Electrical/Instrument": {
                "PLC", "DCS", "SCADA", "VFD", "TRANSMITTER", "SENSOR", "CONDUIT", "CABLE",
                "VOLT", "AMPERE", "WATT", "CIRCUIT", "PANEL", "JB", "MCC", "WIRE", "JUNCTION",
                "INSTRUMENT", "TAG", "CONTROL", "LOOP", "I/O", "RTD", "GND", "PE"
            },
            "General/Administrative": {
                "NOTE", "GENERAL", "SPECIFICATION", "REVISION", "REV", "DRAWING", "DWG", "BORDER",
                "APPROVED", "REVIEW", "STATUS", "INFORMATION", "DATE", "SIGNATURE", "SCALE", "TITLE"
            }
        }

    def _build_known_typos_map(self) -> Dict[str, str]:
        """Known OCR character confusions and reviewer typos mapped to clean words."""
        return {
            'FEEDEER': 'FEEDER',
            'RECIEVER': 'RECEIVER',
            'DIMENSIO': 'DIMENSION',
            'DIMENSIOS': 'DIMENSIONS',
            'DIMENION': 'DIMENSION',
            'FLNAGE': 'FLANGE',
            'VAVLE': 'VALVE',
            'PIPNG': 'PIPING',
            'ISOMETRC': 'ISOMETRIC',
            'SPECFICATION': 'SPECIFICATION',
            'SPECIFCATION': 'SPECIFICATION',
            'SCHEDUL': 'SCHEDULE',
            'CONECT': 'CONNECT',
            'PRESSUR': 'PRESSURE',
            'TEMPATURE': 'TEMPERATURE',
            'ELEVATON': 'ELEVATION',
            'FOUNDATON': 'FOUNDATION',
            'STRUCTUR': 'STRUCTURE',
            'ELECTIC': 'ELECTRIC',
            'TOLERENCE': 'TOLERANCE',
            'DIAMETR': 'DIAMETER',
            'THICKNES': 'THICKNESS',
            'CLEARNCE': 'CLEARANCE',
            'INSTALATION': 'INSTALLATION',
            'CORRECTON': 'CORRECTION',
            'MODIFCATION': 'MODIFICATION',
            'ALIGNMNT': 'ALIGNMENT',
            'NEST LOCATION': 'BEST LOCATION',
            'SPETTER': 'SPLITTER',
            'APROVED': 'APPROVED',
            'REQUIRS': 'REQUIRES',
            'REFERANCE': 'REFERENCE',
            'CALCULATONS': 'CALCULATIONS',
            'SPECFYING': 'SPECIFYING',
            'ARANGEMENT': 'ARRANGEMENT',
            'LOCATON': 'LOCATION',
            'DISCRIPTION': 'DESCRIPTION',
            'CONFIM': 'CONFIRM',
            'REQURED': 'REQUIRED',
            'SECTON': 'SECTION',
            'INCLUES': 'INCLUDES',
            'EXISTIN': 'EXISTING',
            'APPROXIMAT': 'APPROXIMATE',
            'EASIER TO FOLL': 'EASIER TO FOLLOW',
            'BREAKNG': 'BREAKING',
            'MOUNTNG': 'MOUNTING',
            'DRAWNG': 'DRAWING',
            'MATERIA': 'MATERIAL',
            'REQUIRMENT': 'REQUIREMENT',
        }

    def _build_standard_vocab(self) -> Set[str]:
        """Core engineering terms for fuzzy spell correction."""
        return {
            "FLANGE", "FLANGES", "DIMENSION", "DIMENSIONS", "VALVE", "VALVES", "PIPING", "PIPE", "PIPES",
            "ISOMETRIC", "SPECIFICATION", "SPECIFICATIONS", "SCHEDULE", "SCHEDULES", "PRESSURE", "TEMPERATURE",
            "ELEVATION", "ELEVATIONS", "FOUNDATION", "FOUNDATIONS", "STRUCTURE", "STRUCTURES",
            "TOLERANCE", "TOLERANCES", "CLEARANCE", "CLEARANCES", "INSTALLATION", "ALIGNMENT",
            "MATERIAL", "MATERIALS", "CALCULATION", "CALCULATIONS", "REQUIREMENT", "REQUIREMENTS",
            "ARRANGEMENT", "LOCATION", "LOCATIONS", "DESCRIPTION", "DESCRIPTIONS", "EXISTING", "APPROXIMATE",
            "DRAWING", "DRAWINGS", "SECTION", "SECTIONS", "RECEIVER", "FEEDER", "SPLITTER", "APPROVED",
            "VERIFY", "UPDATE", "CONFIRM", "REMOVE", "CHECK", "ROTATE", "REVISE",
            "CORRECTION", "CORRECTIONS", "MODIFICATION", "MODIFICATIONS",
            "EQUIPMENT", "INSTRUMENT", "INSTRUMENTS", "TRANSMITTER", "TRANSMITTERS"
        }

    def _build_action_verbs_set(self) -> Set[str]:
        """Core engineering review action verbs."""
        return {
            "VERIFY", "UPDATE", "CONFIRM", "REMOVE", "CHECK", "ROTATE", 
            "REVISE", "ADD", "SHOW", "INDICATE", "REFERENCE", "LOCATE",
            "SPECIFY", "MATCH", "SWITCH", "CORRECT", "PROVIDE", "INCLUDE",
            "CHANGE", "DELETE", "ALIGN", "EXTEND", "CONNECT", "INSTALL"
        }

    # =========================================================================
    # 2. CORE TEXT CLEANING PIPELINE
    # =========================================================================

    def clean_text(self, raw_text: str) -> CleanedCommentDTO:
        """
        Clean, normalize, correct, and enrich a single reviewer comment string.
        """
        if not raw_text:
            return CleanedCommentDTO(
                original_text="",
                cleaned_text="",
                corrections=[],
                similarity_score=1.0,
                sub_actions=[],
                reviewer_initials=None,
                action_verb=None,
                priority_level="MEDIUM",
                engineering_terms_found=[],
                is_duplicate_of=None
            )

        corrections: List[CorrectionDTO] = []
        text = raw_text

        # Step 1: Strip OCR Noise & Scan Artifacts (protecting fractions, tags, and dimensions)
        text, noise_corrections = self._strip_ocr_noise(text)
        corrections.extend(noise_corrections)

        # Step 2: Normalize Whitespace & Punctuation
        text, ws_corrections = self._normalize_whitespace(text)
        corrections.extend(ws_corrections)

        # Step 3: Extract Reviewer Initials & Sign-offs
        reviewer_initials, text_after_init = self._extract_reviewer_initials(text)

        # Step 4: Known Typos & OCR Domain Corrections
        text, typo_corrections = self._apply_domain_spell_correction(text)
        corrections.extend(typo_corrections)

        # Step 5: Expand Engineering Abbreviations (if enabled)
        if self.expand_acronyms:
            text, abbr_corrections = self._expand_abbreviations(text)
            corrections.extend(abbr_corrections)

        # Step 6: Identify Multi-Action Sub-Clauses
        sub_actions = self._segment_actions(text)

        # Step 7: Detect Action Verbs & Priority Level
        action_verb = self._detect_action_verb(text)
        priority_level = self._detect_priority(text)
        engineering_terms = self._detect_engineering_terms(raw_text)

        similarity = difflib.SequenceMatcher(None, raw_text, text).ratio()

        return CleanedCommentDTO(
            original_text=raw_text,
            cleaned_text=text,
            corrections=corrections,
            similarity_score=round(similarity, 3),
            sub_actions=sub_actions,
            reviewer_initials=reviewer_initials,
            action_verb=action_verb,
            priority_level=priority_level,
            engineering_terms_found=engineering_terms,
            is_duplicate_of=None
        )

    # =========================================================================
    # 3. HELPER CLEANING STAGES
    # =========================================================================

    def _strip_ocr_noise(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Removes scan artifacts while preserving technical tags, dimensions, and fractions."""
        corrections = []
        original = text

        # Strip repeated non-alphanumeric noise symbols (e.g. !!!! -> !, ??? -> ?, ///// -> /)
        noise_pattern = re.compile(r'([!@#$%\^&*()_+={}\[\]:;"\'<>,.?/\\|`~])\1+')
        if noise_pattern.search(text):
            text = noise_pattern.sub(r'\1', text)

        # Remove stray leading backslash-colon noise (e.g. "\\ : Cy Vy" -> "Cy Vy")
        text = re.sub(r'^[\\/|:;\s~_]+', '', text)
        
        # Remove weird OCR artifacts like "_~"
        text = text.replace('_~', ' ')
        
        # Clean double spaces caused by noise removal
        text = re.sub(r'\s+', ' ', text).strip()

        if text != original:
            corrections.append(CorrectionDTO(original=original, corrected=text, correction_type='noise_removal'))

        return text, corrections

    def _normalize_whitespace(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Normalizes spaces around parentheses, hyphens, and quotes."""
        corrections = []
        original = text

        # Standardize multiple spaces and newlines
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # Fix spacing around parentheses: "( text )" -> "(text)"
        text = re.sub(r'\(\s+', '(', text)
        text = re.sub(r'\s+\)', ')', text)

        if text != original:
            corrections.append(CorrectionDTO(original=original, corrected=text, correction_type='whitespace'))

        return text, corrections

    def _extract_reviewer_initials(self, text: str) -> Tuple[Optional[str], str]:
        """Extracts reviewer attribution like '-JDM', '-JCM', '-BEK', '-MWR', '-JJD', 'By: BreKol'."""
        initials = None
        
        # Pattern 1: Suffix initials like "-JDM", "-JCM", "-BEK", "-JJD", "-MWR"
        suffix_match = re.search(r'(?:^|\s)[-–—]\s*([A-Z]{2,4})(?:\s*|\.?)$', text)
        if suffix_match:
            initials = suffix_match.group(1).upper()
            return initials, text

        # Pattern 2: Suffix without hyphen e.g. "BELONGS JCM" or "TYPICAL FOR ALL JCM"
        trailing_match = re.search(r'\b([A-Z]{2,3})$', text.strip())
        if trailing_match and trailing_match.group(1) in {"JCM", "JDM", "MWR", "BEK", "JJD", "UCC", "UCCI"}:
            initials = trailing_match.group(1)
            return initials, text

        # Pattern 3: Explicit signature "By: BreKol" or "BY DATE BreKol"
        by_match = re.search(r'(?:BY|By|BY DATE|By:)\s+([A-Za-z0-9_-]+)', text)
        if by_match:
            initials = by_match.group(1)
            return initials, text

        return None, text

    def _apply_domain_spell_correction(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Applies domain-safe spelling and phrase corrections."""
        corrections = []
        original = text

        # 1. Multi-word phrase corrections first
        phrase_fixes = [
            (r'\bNEST LOCATION\b', 'BEST LOCATION'),
            (r'\bEASIER TO FOLL\b', 'EASIER TO FOLLOW'),
            (r'\bBILL OF MATERIA\b', 'BILL OF MATERIALS'),
            (r'\bGENERAL NO\b', 'GENERAL NOTES'),
            (r'\bDIMENSIONS OF EXISTIN\b', 'DIMENSIONS OF EXISTING'),
            (r'\bCL EL\b', 'CENTERLINE ELEVATION'),
        ]
        for pattern, replacement in phrase_fixes:
            if re.search(pattern, text, re.IGNORECASE):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # 2. Word-level known typos and fuzzy domain spelling
        words = text.split()
        cleaned_words = []
        for w in words:
            clean_token = w.strip('.,!?;:()"\'')
            upper_token = clean_token.upper()
            
            if upper_token in self.known_typos:
                corrected_w = self.known_typos[upper_token]
                # Match original casing
                if clean_token.isupper():
                    target_replace = corrected_w
                elif clean_token.istitle():
                    target_replace = corrected_w.title()
                else:
                    target_replace = corrected_w.lower()
                replaced = w.replace(clean_token, target_replace)
                cleaned_words.append(replaced)
                corrections.append(CorrectionDTO(original=clean_token, corrected=target_replace, correction_type='spelling'))
            elif len(upper_token) >= 5 and upper_token.isalpha() and upper_token not in self.engineering_dict and upper_token not in self._standard_vocab:
                matches = difflib.get_close_matches(upper_token, self._standard_vocab, n=1, cutoff=0.82)
                if matches and matches[0] != upper_token:
                    matched = matches[0]
                    target_replace = matched if clean_token.isupper() else (matched.title() if clean_token.istitle() else matched.lower())
                    replaced = w.replace(clean_token, target_replace)
                    cleaned_words.append(replaced)
                    corrections.append(CorrectionDTO(original=clean_token, corrected=target_replace, correction_type='spelling'))
                else:
                    cleaned_words.append(w)
            else:
                cleaned_words.append(w)

        text = ' '.join(cleaned_words)
        if text != original and not corrections:
            corrections.append(CorrectionDTO(original=original, corrected=text, correction_type='spelling'))

        return text, corrections

    def _expand_abbreviations(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Expands engineering acronyms into full standard terminology."""
        corrections = []
        original = text

        words = text.split()
        expanded_words = []
        for word in words:
            clean_word = word.strip('.,!?;:()"\'')
            upper_word = clean_word.upper()
            if upper_word in self.engineering_dict:
                expanded = self.engineering_dict[upper_word]
                expanded_words.append(word.replace(clean_word, expanded))
                corrections.append(CorrectionDTO(original=clean_word, corrected=expanded, correction_type='abbreviation'))
            elif "-" in clean_word and any(c.isalpha() for c in clean_word) and any(c.isdigit() for c in clean_word):
                # Handle hyphenated tags like PSV-101, SCH-40, P&ID-01
                parts = clean_word.split("-", 1)
                prefix_upper = parts[0].upper()
                if prefix_upper in self.engineering_dict and len(prefix_upper) >= 2:
                    expanded_prefix = self.engineering_dict[prefix_upper]
                    expanded_tag = f"{expanded_prefix}-{parts[1]}"
                    expanded_words.append(word.replace(clean_word, expanded_tag))
                    corrections.append(CorrectionDTO(original=parts[0], corrected=expanded_prefix, correction_type='abbreviation'))
                else:
                    expanded_words.append(word)
            else:
                expanded_words.append(word)

        text = ' '.join(expanded_words)
        return text, corrections

    def _segment_actions(self, text: str) -> List[str]:
        """Detects multi-action punch list items (e.g. '1. ... 2. ... 3. ...' or '(A) ... (B) ...')."""
        # Numbered list pattern: "1. ... 2. ... 3. ..." or "(1) ... (2) ..."
        numbered_pattern = re.split(r'(?:\d+[\.\)]|\([A-Za-z\d]+\))\s+', text)
        if len(numbered_pattern) > 1:
            actions = [act.strip() for act in numbered_pattern if len(act.strip()) > 3]
            if len(actions) > 1:
                return actions

        # Clause transition split (e.g. "THIS SHOULD SHOW ... AND ALSO VERIFY ...")
        clause_pattern = re.split(r';|\b(?:ALSO VERIFY|AND REVISE|PLEASE ALSO)\b', text, flags=re.IGNORECASE)
        if len(clause_pattern) > 1:
            actions = [act.strip() for act in clause_pattern if len(act.strip()) > 5]
            if len(actions) > 1:
                return actions

        return [text] if text else []

    def _detect_action_verb(self, text: str) -> Optional[str]:
        """Finds primary action verb in comment."""
        upper_text = text.upper()
        words = re.findall(r'\b[A-Z]+\b', upper_text)
        for w in words:
            if w in self.action_verbs:
                return w
        return None

    def _detect_priority(self, text: str) -> str:
        """Determines action priority level based on sentiment and urgency."""
        upper = text.upper()
        for kw in self.high_priority_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', upper):
                return "HIGH"
        for kw in self.medium_priority_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', upper):
                return "MEDIUM"
        for kw in self.low_priority_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', upper):
                return "LOW"
        return "MEDIUM"

    def _detect_engineering_terms(self, text: str) -> List[str]:
        """Extracts all domain terms present in text."""
        upper = text.upper()
        found = []
        for term in self.engineering_dict.keys():
            if re.search(r'\b' + re.escape(term) + r'\b', upper):
                found.append(term)
        return found

    # =========================================================================
    # 4. BATCH CLEANING & SEMANTIC DUPLICATE DETECTION
    # =========================================================================

    def clean_batch(self, comments: List[Dict[str, Any]], drawing_id: str = '') -> TextCleaningResultDTO:
        """Processes a list of raw comments and performs duplicate detection."""
        start_time = time.time()
        cleaned = []
        texts = []

        for comment in comments:
            raw = comment.get('text', '') or comment.get('raw_text', '')
            res = self.clean_text(raw)
            cleaned.append(res)
            texts.append(res.cleaned_text)

        dups = self.detect_duplicates(texts)

        # Mark duplicates
        for orig_idx, dup_idx in dups:
            if dup_idx < len(cleaned):
                cleaned[dup_idx].is_duplicate_of = f"CMT-{orig_idx}"

        elapsed = (time.time() - start_time) * 1000
        return TextCleaningResultDTO(
            drawing_id=drawing_id,
            total_comments=len(comments),
            cleaned_comments=cleaned,
            duplicates_removed=len(dups),
            processing_time_ms=elapsed
        )

    def detect_duplicates(self, texts: List[str], threshold: float = 0.85) -> List[Tuple[int, int]]:
        """
        Detects duplicate or highly similar comments using SequenceMatcher.
        Returns list of (canonical_index, duplicate_index).
        """
        duplicates = []
        for i in range(len(texts)):
            if not texts[i].strip():
                continue
            for j in range(i + 1, len(texts)):
                if not texts[j].strip():
                    continue
                ratio = difflib.SequenceMatcher(None, texts[i].upper(), texts[j].upper()).ratio()
                if ratio >= threshold:
                    duplicates.append((i, j))
        return duplicates
