import threading
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    TRANSFORMERS_AVAILABLE = True
except (ImportError, OSError, Exception):
    torch = None
    AutoTokenizer = None
    AutoModelForSequenceClassification = None
    TRANSFORMERS_AVAILABLE = False

from src.core.dtos.classification_dtos import (
    CategoryPredictionDTO,
    ClassificationResultDTO,
    BatchClassificationDTO
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

class ClassificationService:
    def __init__(self, model_dir: Optional[Path] = None):
        self.keywords = self._build_category_keywords()
        self.HIGH_CONFIDENCE = 0.80
        self.LOW_CONFIDENCE = 0.60
        self.model_dir = model_dir or (Path(__file__).resolve().parent.parent.parent / "models" / "distilbert_engineering_classifier")
        self._ai_model = None
        self._ai_tokenizer = None
        self._ai_device = None
        self._model_load_failed = False
        self._model_lock = threading.Lock()
        # Asynchronously pre-warm the PyTorch model in the background
        threading.Thread(target=self._ensure_model_loaded, daemon=True).start()
        
    def _build_category_keywords(self) -> Dict[str, List[str]]:
        return {
            'Technical': [
                'member size', 'beam size', 'column size', 'missing connection', 'moment connection', 
                'shear tab', 'connection detail', 'wrong weld', 'fillet weld', 'weld callout', 
                'part number wrong', 'part number mismatch', 'ECN no', 'ECN number', 'machining symbol', 
                'machining finish', 'surface finish', 'incorrect tolerance', 'tolerance', 'stiffener plate', 
                'gusset plate', 'flange rating', 'pipe schedule', 'pressure rating', 'bolt grade', 
                'A325', 'nozzle flange', 'undersized', 'shear connection'
            ],
            'Drafting': [
                'line overlap', 'missing hidden line', 'hidden line', 'incorrect drawing scale', 
                'drawing scale', 'wrong views', 'projection', 'section cut', 'view orientation', 
                'leader line', 'detail bubble', 'dashed line', 'hatch pattern', 'line weight', 
                'isometric view', 'match line', 'centerline', 'arrowhead', 'break line', 
                'overlapping text', 'view mismatch'
            ],
            'Dimension': [
                'incorrect dimension', 'missing dimension', 'dimension', 'dim', 'CL EL', 
                'centerline elevation', 'center-to-center', 'elevation callout', 'TOC', 
                'dimension string', 'radial clearance', 'coordinate dimensions', 'nozzle projection', 
                'anchor bolt centers', 'vertical clearance', 'cut length', 'setback', 'discrepancy in diameter', 
                'radius dimension', 'overall height', 'projection dimension'
            ],
            'Cosmetic': [
                'text alignment', 'font size', 'spelling', 'typo', 'typo error', 
                'font style', 'Romans', 'text overlapping', 'text rotated', 'justification', 
                'font height', 'cosmetic cleanup', 'stray CAD', 'capitalization', 'font thickness', 
                'misaligned column'
            ],
            'Standards': [
                'incorrect symbol', 'codal issue', 'symbol', 'standard', 'ISA-5.1', 
                'OSHA', 'IBC', 'AWS A2.4', 'STD-001', 'IEEE', 'IEC', 
                'hazardous area', 'NFPA 497', 'ASME B16.5', 'API 526', 'AISC', 
                'MSS SP-58', 'GD&T', 'ASME Y14.5', 'ISO 7010', 'NFPA 101', 'ANSI Z358.1', 
                'ASME B36.10M', 'non-standard abbreviation', 'code stamp'
            ],
            'Coordination': [
                'clash', 'conflict', 'inter-discipline', 'coordinate', 'interference', 
                'clash with piping', 'clash with civil', 'clash with electrical', 'cable tray clash', 
                'HVAC duct clash', 'penetrates', 'junction box clash', 'footprint', 
                'sprinkler clash', 'hook travel', 'tie-in', 'battery limit', 'diagonal bracing blocks', 
                'motor removal path'
            ],
            'Documentation': [
                'title block', 'title block incomplete', 'project number missing', 'client drawing reference', 
                'approval signatures', 'checker', 'sign-off block', 'master document register', 
                'sheet reference', 'scale box', 'project code', 'CAD drawing file', 'specification number', 
                'drawing status stamp', 'ISSUED FOR CONSTRUCTION', 'IFC', 'IFD', 'sheet number', 
                'client logo', 'vendor certified', 'cross-reference index', 'professional seal', 
                'transmittal number', 'work order'
            ],
            'Revision': [
                'revision cloud', 'revision table', 'revision symbol', 'delta', 'triangle tag', 
                'Rev A', 'Rev B', 'Rev C', 'Rev 1', 'Rev 2', 'Rev 0', 
                'revision cloud missing', 'revision table not updated', 'revision description', 
                'revision note', 'ECN', 'revision history', 'cloud boundary'
            ],
            'Calculation': [
                'calculation', 'design inconsistency', 'pressure drop calculation', 'calculation sheet', 
                'pump head calculation', 'thermal expansion', 'allowable stress', 'pile load capacity', 
                'soil report', 'voltage drop calculation', 'wall thickness calculation', 
                'relief valve sizing', 'overturning moment', 'flow rate calculation', 
                'short circuit current', 'deflection calculation', 'hydraulic gradient', 
                'seismic load', 'thermal relief', 'heat loss calculation', 'buckling calculation', 
                'bearing pressure'
            ],
            'Feasibility': [
                'erection feasibility', 'fabrication feasibility', 'feasibility', 'accessibility', 
                'maintenance accessibility', 'tube bundle pull', 'erection sequence', 'bend radius', 
                'handwheel unreachable', 'chain wheel', 'bolting accessibility', 'torque wrench clearance', 
                'lifting lug', 'shipping clearance', 'roadway clearance', 'bolted splice', 
                'field assembly', 'constructability', 'rebar congestion', 'hand lever hits', 
                'filter basket', 'field weld accessibility'
            ],
            'Material': [
                'incorrect material', 'material specified', 'material grade', 'ASTM A36', 
                'A992', 'gasket material', 'PTFE', 'spiral wound', 'fastener material', 
                'ASTM A193', '316L', '304SS', 'carbon steel', 'anchor bolt material', 
                'insulation material', 'ASTM A572', 'O-ring elastomer', 'Viton', 'rebar grade', 
                'A615', 'grout material', 'non-shrink cementitious', 'ASTM A105', 
                'corrosion allowance'
            ],
            'Notes': [
                'incorrect notes', 'update notes', 'general note', 'note', 'mandatory note', 
                'PWHT requirement', 'obsolete specification', 'contradicts note', 'safety note', 
                'coating note', 'paint note', 'environmental note', 'torque requirements', 
                'hydrotest pressure note', 'NDT requirement', 'slope requirement', 'compressive strength'
            ],
            'BOM': [
                'BOM', 'bill of materials', 'incorrect part number', 'part number in BOM', 
                'BOM quantity', 'quantity mismatch', 'BOM description', 'MTO line item', 
                'material take-off', 'unit weight', 'flange rating in BOM', 'spare parts list', 
                'item count', 'component schedule', 'vendor cut sheet', 'SAP catalog'
            ]
        }

    def _rule_based_classify(self, text: str) -> List[CategoryPredictionDTO]:
        """
        Rule-based classification using keyword matching.
        
        Improved algorithm:
        - Exact word matches get full weight (1.0)
        - Partial matches get half weight (0.5)
        - Confidence scales logarithmically (more realistic)
        """
        predictions = []
        text_lower = text.lower()
        words = text_lower.split()
        
        for category, kws in self.keywords.items():
            # Find keyword matches with quality scoring
            matches = []
            match_score = 0.0
            
            for kw in kws:
                kw_lower = kw.lower()
                # Exact word match (higher weight)
                if kw_lower in words:
                    if kw not in matches:
                        matches.append(kw)
                    match_score += 1.0
                # Partial match in text (lower weight)
                elif kw_lower in text_lower:
                    if kw not in matches:
                        matches.append(kw)
                    match_score += 0.5
            
            if matches:
                # Calculate confidence with logarithmic scaling
                # This gives more realistic confidence growth
                # 1 match ≈ 47%, 2 matches ≈ 57%, 3 matches ≈ 65%, 4+ matches ≈ 70%+
                conf = min(1.0, 0.3 + (0.25 * math.log(match_score + 1)))
                predictions.append(CategoryPredictionDTO(category, conf, matches))
            else:
                predictions.append(CategoryPredictionDTO(category, 0.0, []))
                
        return sorted(predictions, key=lambda x: x.confidence, reverse=True)

    def _ensure_model_loaded(self) -> bool:
        """Helper to ensure DistilBERT is loaded once on target device in a thread-safe manner."""
        if self._ai_model is not None:
            return True
        if self._model_load_failed or not TRANSFORMERS_AVAILABLE:
            return False
        if not self.model_dir.exists() or not (self.model_dir / "model.safetensors").exists():
            return False
            
        with self._model_lock:
            if self._ai_model is not None:
                return True
            try:
                self._ai_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                self._ai_tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
                self._ai_model = AutoModelForSequenceClassification.from_pretrained(str(self.model_dir))
                self._ai_model.to(self._ai_device)
                self._ai_model.eval()
                logger.info(f"Loaded fine-tuned DistilBERT classifier from: {self.model_dir}")
                return True
            except Exception as e:
                logger.warning(f"Could not load DistilBERT model: {e}")
                self._model_load_failed = True
                return False

    def _try_ai_classify(self, text: str) -> Optional[List[CategoryPredictionDTO]]:
        """
        AI model classification using fine-tuned DistilBERT for a single text.
        """
        if not text or not self._ensure_model_loaded():
            return None

        try:
            import torch
            encoding = self._ai_tokenizer(
                text,
                truncation=True,
                max_length=128,
                return_tensors="pt"
            ).to(self._ai_device)

            with torch.no_grad():
                outputs = self._ai_model(**encoding)
                probs = torch.softmax(outputs.logits, dim=1).cpu().squeeze(0).detach().numpy()

            predictions = []
            for idx, prob in enumerate(probs):
                cat_name = self._ai_model.config.id2label.get(idx) or self._ai_model.config.id2label.get(str(idx), str(idx))
                predictions.append(CategoryPredictionDTO(
                    category_name=cat_name,
                    confidence=float(round(prob, 4)),
                    matched_keywords=[]
                ))

            return sorted(predictions, key=lambda x: x.confidence, reverse=True)
        except Exception as inf_err:
            logger.debug(f"DistilBERT inference failed for '{text}': {inf_err}")
            return None

    def _try_ai_classify_batch(self, texts: List[str]) -> List[Optional[List[CategoryPredictionDTO]]]:
        """
        High-performance batched AI classification using fine-tuned DistilBERT.
        Executes a single forward pass for all inputs simultaneously.
        """
        if not texts or not self._ensure_model_loaded():
            return [None] * len(texts)

        try:
            import torch
            # Filter valid texts while preserving indices
            valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
            if not valid_indices:
                return [None] * len(texts)

            valid_texts = [texts[i].strip() for i in valid_indices]
            encoding = self._ai_tokenizer(
                valid_texts,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt"
            ).to(self._ai_device)

            with torch.no_grad():
                outputs = self._ai_model(**encoding)
                probs_batch = torch.softmax(outputs.logits, dim=1).cpu().detach().numpy()

            results: List[Optional[List[CategoryPredictionDTO]]] = [None] * len(texts)
            for batch_idx, original_idx in enumerate(valid_indices):
                probs = probs_batch[batch_idx]
                predictions = []
                for cat_idx, prob in enumerate(probs):
                    cat_name = self._ai_model.config.id2label.get(cat_idx) or self._ai_model.config.id2label.get(str(cat_idx), str(cat_idx))
                    predictions.append(CategoryPredictionDTO(
                        category_name=cat_name,
                        confidence=float(round(prob, 4)),
                        matched_keywords=[]
                    ))
                results[original_idx] = sorted(predictions, key=lambda x: x.confidence, reverse=True)

            return results
        except Exception as batch_err:
            logger.debug(f"Batched DistilBERT inference failed: {batch_err}")
            return [None] * len(texts)

    def classify_comment(self, comment_text: str, comment_id: str = '') -> ClassificationResultDTO:
        """Classify a single comment into categories with AI inference and keyword-grounded calibration"""
        if not comment_text or not comment_text.strip():
            return ClassificationResultDTO(
                comment_id=comment_id,
                text=comment_text,
                primary_category=CategoryPredictionDTO('Documentation', 0.0, []),
                alternative_categories=[],
                classification_method='rule_based',
                requires_human_review=True
            )

        clean_text = comment_text.strip()
        words = clean_text.lower().split()

        # 1. Rule-based keyword analysis
        rule_preds = self._rule_based_classify(clean_text)
        rule_map = {p.category_name: p for p in rule_preds}
        total_keywords_matched = sum(len(p.matched_keywords) for p in rule_preds)

        # 2. AI model prediction
        ai_preds = self._try_ai_classify(clean_text)

        if ai_preds:
            method = 'ai_model'
            final_predictions = []
            for p in ai_preds:
                kws = rule_map.get(p.category_name, CategoryPredictionDTO('', 0, [])).matched_keywords
                rule_conf = rule_map.get(p.category_name, CategoryPredictionDTO('', 0, [])).confidence

                # Grounding with matched engineering keywords
                if kws and p.category_name != 'Documentation':
                    combined_conf = min(1.0, 0.45 * p.confidence + 0.35 * rule_conf + 0.10 * len(kws))
                elif total_keywords_matched > 0 and p.category_name == 'Documentation':
                    combined_conf = max(0.01, p.confidence * 0.30)
                else:
                    combined_conf = p.confidence * 0.85

                final_predictions.append(CategoryPredictionDTO(
                    category_name=p.category_name,
                    confidence=float(round(combined_conf, 4)),
                    matched_keywords=kws
                ))

            final_predictions = sorted(final_predictions, key=lambda x: x.confidence, reverse=True)
            primary = final_predictions[0]
            alts = final_predictions[1:]

            # If input is very short/uninformative with 0 domain keywords, flag for review
            if len(words) <= 3 and total_keywords_matched == 0:
                primary.confidence = min(primary.confidence, 0.50)
                requires_review = True
            else:
                requires_review = primary.confidence < self.LOW_CONFIDENCE
        else:
            method = 'rule_based'
            primary = rule_preds[0] if rule_preds else CategoryPredictionDTO('Documentation', 0.0, [])
            alts = rule_preds[1:] if len(rule_preds) > 1 else []
            requires_review = (primary.confidence < self.LOW_CONFIDENCE) or (total_keywords_matched == 0)

        return ClassificationResultDTO(
            comment_id=comment_id,
            text=comment_text,
            primary_category=primary,
            alternative_categories=alts,
            classification_method=method,
            requires_human_review=requires_review
        )
        
    def classify_batch(self, comments: List[Any], drawing_id: str = '') -> BatchClassificationDTO:
        """Classify multiple comments in batch using accelerated single-pass tensor inference"""
        if not comments:
            return BatchClassificationDTO(
                drawing_id=drawing_id,
                total_classified=0,
                results=[],
                high_confidence_count=0,
                low_confidence_count=0,
                flagged_count=0
            )

        texts = []
        ids = []
        for i, c in enumerate(comments):
            if isinstance(c, dict):
                texts.append(c.get('text', ''))
                ids.append(str(c.get('id', '')))
            elif isinstance(c, str):
                texts.append(c)
                ids.append(str(i))
            else:
                texts.append(str(c))
                ids.append(str(i))

        # 1. Fast Batched AI predictions (1 forward pass)
        batch_ai_preds = self._try_ai_classify_batch(texts)

        results = []
        high = 0
        low = 0
        flagged = 0

        for i, comment_text in enumerate(texts):
            comment_id = ids[i]
            clean_text = comment_text.strip() if comment_text else ""
            if not clean_text:
                res = ClassificationResultDTO(
                    comment_id=comment_id,
                    text=comment_text,
                    primary_category=CategoryPredictionDTO('Documentation', 0.0, []),
                    alternative_categories=[],
                    classification_method='rule_based',
                    requires_human_review=True
                )
                results.append(res)
                flagged += 1
                low += 1
                continue

            words = clean_text.lower().split()
            rule_preds = self._rule_based_classify(clean_text)
            rule_map = {p.category_name: p for p in rule_preds}
            total_keywords_matched = sum(len(p.matched_keywords) for p in rule_preds)

            ai_preds = batch_ai_preds[i]
            if ai_preds:
                method = 'ai_model'
                final_predictions = []
                for p in ai_preds:
                    kws = rule_map.get(p.category_name, CategoryPredictionDTO('', 0, [])).matched_keywords
                    rule_conf = rule_map.get(p.category_name, CategoryPredictionDTO('', 0, [])).confidence

                    if kws and p.category_name != 'Documentation':
                        combined_conf = min(1.0, 0.45 * p.confidence + 0.35 * rule_conf + 0.10 * len(kws))
                    elif total_keywords_matched > 0 and p.category_name == 'Documentation':
                        combined_conf = max(0.01, p.confidence * 0.30)
                    else:
                        combined_conf = p.confidence * 0.85

                    final_predictions.append(CategoryPredictionDTO(
                        category_name=p.category_name,
                        confidence=float(round(combined_conf, 4)),
                        matched_keywords=kws
                    ))

                final_predictions = sorted(final_predictions, key=lambda x: x.confidence, reverse=True)
                primary = final_predictions[0]
                alts = final_predictions[1:]

                if len(words) <= 3 and total_keywords_matched == 0:
                    primary.confidence = min(primary.confidence, 0.50)
                    requires_review = True
                else:
                    requires_review = primary.confidence < self.LOW_CONFIDENCE
            else:
                method = 'rule_based'
                primary = rule_preds[0] if rule_preds else CategoryPredictionDTO('Documentation', 0.0, [])
                alts = rule_preds[1:] if len(rule_preds) > 1 else []
                requires_review = (primary.confidence < self.LOW_CONFIDENCE) or (total_keywords_matched == 0)

            res = ClassificationResultDTO(
                comment_id=comment_id,
                text=comment_text,
                primary_category=primary,
                alternative_categories=alts,
                classification_method=method,
                requires_human_review=requires_review
            )
            results.append(res)

            if res.primary_category.confidence >= self.HIGH_CONFIDENCE:
                high += 1
            else:
                low += 1

            if res.requires_human_review:
                flagged += 1

        return BatchClassificationDTO(
            drawing_id=drawing_id,
            total_classified=len(results),
            results=results,
            high_confidence_count=high,
            low_confidence_count=low,
            flagged_count=flagged
        )
