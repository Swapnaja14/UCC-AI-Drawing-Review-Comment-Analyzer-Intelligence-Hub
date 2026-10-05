import sys
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
    _models_cache: Dict[str, Dict[str, Any]] = {}
    _cache_lock = threading.Lock()

    @staticmethod
    def resolve_model_path(model_dir: Optional[Path] = None) -> Path:
        """
        Resolve DistilBERT model directory safely across standard dev environments
        and PyInstaller frozen bundles (both one-dir and one-file modes).
        """
        if model_dir is not None:
            return Path(model_dir)

        # 1. PyInstaller frozen executable environment
        if getattr(sys, "frozen", False):
            # One-file mode unzips into temporary _MEIPASS directory
            if hasattr(sys, "_MEIPASS"):
                meipass_model = Path(sys._MEIPASS) / "models" / "distilbert_engineering_classifier"
                if meipass_model.exists():
                    logger.info(f"Resolved DistilBERT model from PyInstaller _MEIPASS: {meipass_model}")
                    return meipass_model

            # One-dir mode keeps assets next to the executable
            exe_model = Path(sys.executable).resolve().parent / "models" / "distilbert_engineering_classifier"
            if exe_model.exists():
                logger.info(f"Resolved DistilBERT model from executable directory: {exe_model}")
                return exe_model

            # Fallback for frozen bundle if directories are being created or mounted
            if hasattr(sys, "_MEIPASS"):
                return Path(sys._MEIPASS) / "models" / "distilbert_engineering_classifier"
            return Path(sys.executable).resolve().parent / "models" / "distilbert_engineering_classifier"

        # 2. Standard development / source tree resolution
        dev_path = Path(__file__).resolve().parent.parent.parent / "models" / "distilbert_engineering_classifier"
        if dev_path.exists():
            return dev_path

        # 3. Current working directory fallback
        cwd_path = Path.cwd() / "models" / "distilbert_engineering_classifier"
        if cwd_path.exists():
            return cwd_path

        return dev_path

    def __init__(self, model_dir: Optional[Path] = None, category_repo: Optional[Any] = None):
        self.category_repo = category_repo
        self.keywords = self._build_category_keywords()
        self.keywords_tuples = {
            cat: [(kw, kw.lower()) for kw in kws]
            for cat, kws in self.keywords.items()
        }
        self.HIGH_CONFIDENCE = 0.80
        self.LOW_CONFIDENCE = 0.60
        self.model_dir = self.resolve_model_path(model_dir)
        self._model_load_failed = False
        self._model_load_error_msg = None
        
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
                'overlapping text', 'view mismatch', 'align', 'aligned', 'center', 'move this up',
                'move down', 'spacing', 'space between', 'terminal block'
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
                'revision note', 'ECN', 'revision history', 'cloud boundary',
                'revision', 'revision flag', 'revision flags', 'rev flag', 'rev flags',
                'revision a', 'revision b', 'revision c', 'revision d', 'revision e',
                'rev. a', 'rev. b', 'rev. c', 'flag', 'flags', 'revision update'
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

    def get_department_keywords(self, department_name: Optional[str] = None) -> Dict[str, List[tuple[str, str]]]:
        """
        Merge base category keywords with dynamic department-specific custom categories and keywords from DB.
        Returns mapping of category_name -> [(kw, kw_lower), ...]
        """
        # Start with standard category keywords
        all_kw_tuples = {cat: list(pairs) for cat, pairs in self.keywords_tuples.items()}

        if self.category_repo and hasattr(self.category_repo, "get_categories_for_department"):
            try:
                dept_cats = self.category_repo.get_categories_for_department(department_name)
                for cat in dept_cats:
                    cname = cat.get("name")
                    if not cname:
                        continue
                    kws: List[str] = []
                    # 1. Check explicit keywords field
                    raw_kws = cat.get("keywords") or ""
                    if raw_kws:
                        for k in raw_kws.split(","):
                            k_clean = k.strip()
                            if k_clean and k_clean not in kws:
                                kws.append(k_clean)

                    # 2. Check pre-configured suggestion keywords if empty
                    if not kws and hasattr(self.category_repo, "get_suggestion_keywords"):
                        sugg_kws = self.category_repo.get_suggestion_keywords(cname)
                        if sugg_kws:
                            for k in sugg_kws.split(","):
                                k_clean = k.strip()
                                if k_clean and k_clean not in kws:
                                    kws.append(k_clean)

                    # 3. Use category name itself as a keyword pattern
                    if cname not in kws:
                        kws.append(cname)

                    # 4. Check description field
                    desc = cat.get("description") or ""
                    if desc and len(desc.split()) <= 5 and desc not in kws:
                        kws.append(desc)

                    if cname in all_kw_tuples:
                        # Extend existing category keywords
                        existing_tuples = list(all_kw_tuples[cname])
                        existing_kws_lower = {t[1] for t in existing_tuples}
                        for k in kws:
                            if k.lower() not in existing_kws_lower:
                                existing_tuples.append((k, k.lower()))
                        all_kw_tuples[cname] = existing_tuples
                    else:
                        # New custom category
                        all_kw_tuples[cname] = [(k, k.lower()) for k in kws]
            except Exception as exc:
                logger.warning(f"Error loading department categories into classifier: {exc}")

        return all_kw_tuples

    def _rule_based_classify(
        self,
        text: str,
        department_name: Optional[str] = None,
        custom_kw_tuples: Optional[Dict[str, List[tuple[str, str]]]] = None,
    ) -> List[CategoryPredictionDTO]:
        """
        Rule-based classification using keyword and phrase matching with multi-word weighting.
        """
        predictions = []
        text_lower = text.lower()
        words = set(text_lower.split())

        kw_dict = custom_kw_tuples if custom_kw_tuples is not None else self.get_department_keywords(department_name)

        for category, kw_pairs in kw_dict.items():
            matches = []
            match_score = 0.0

            for kw, kw_lower in kw_pairs:
                # Multi-word exact phrase match (high quality)
                if " " in kw_lower:
                    if kw_lower in text_lower:
                        if kw not in matches:
                            matches.append(kw)
                        match_score += 2.0
                else:
                    # Single word exact match
                    if kw_lower in words:
                        if kw not in matches:
                            matches.append(kw)
                        match_score += 1.0
                    elif kw_lower in text_lower and len(kw_lower) >= 4:
                        if kw not in matches:
                            matches.append(kw)
                        match_score += 0.4

            if matches:
                # Logarithmic confidence scaling
                # 1 match ≈ 70%, 2 matches ≈ 80%, multi-word/3+ matches ≈ 85-95%
                conf = min(0.98, 0.42 + (0.35 * math.log(match_score + 1)))
                predictions.append(CategoryPredictionDTO(category, round(conf, 4), matches))
            else:
                predictions.append(CategoryPredictionDTO(category, 0.0, []))

        return sorted(predictions, key=lambda x: x.confidence, reverse=True)

    @property
    def _load_error(self) -> Optional[str]:
        return getattr(self, "_model_load_error_msg", None)

    def is_model_loaded(self) -> bool:
        """Check if DistilBERT model is loaded in memory."""
        return self._ai_model is not None

    def ensure_loaded(self) -> bool:
        """Ensure the DistilBERT model is loaded and ready."""
        return self._ensure_model_loaded()

    def get_model_status(self) -> Dict[str, Any]:
        """Return diagnostic status of DistilBERT model, architecture, weights, and classes."""
        weights_file = self.model_dir / "model.safetensors"
        weights_exist = weights_file.exists()
        is_loaded = self.ensure_loaded()
        
        total_params = 0
        architecture = "DistilBertForSequenceClassification"
        num_classes = 13
        classes = list(self.keywords.keys())

        if is_loaded and self._ai_model is not None:
            try:
                total_params = sum(p.numel() for p in self._ai_model.parameters())
                if hasattr(self._ai_model, "config"):
                    cfg = self._ai_model.config
                    num_classes = getattr(cfg, "num_labels", 13)
                    if hasattr(cfg, "id2label") and cfg.id2label:
                        classes = [cfg.id2label[k] if isinstance(k, int) else cfg.id2label[str(k)] for k in sorted([int(x) for x in cfg.id2label.keys()])]
                    if hasattr(cfg, "architectures") and cfg.architectures:
                        architecture = cfg.architectures[0]
            except Exception as e:
                logger.debug(f"Error inspecting model parameters: {e}")

        return {
            "model_name": "distilbert-base-uncased",
            "model_path": str(self.model_dir),
            "architecture": architecture,
            "weights_exist": weights_exist,
            "weights_size_bytes": weights_file.stat().st_size if weights_exist else 0,
            "is_loaded": is_loaded,
            "num_classes": num_classes,
            "total_parameters": total_params,
            "classes": classes,
            "device": str(self._ai_device) if self._ai_device else "uninitialized",
            "load_error": self._load_error if not is_loaded else None
        }

    def predict_ai_only(self, text: str) -> List[CategoryPredictionDTO]:
        """Return raw softmax predictions from DistilBERT without rule weighting."""
        preds = self._try_ai_classify(text)
        if preds is not None:
            return preds
        return []

    def predict_rules_only(
        self,
        text: str,
        department_name: Optional[str] = None
    ) -> List[CategoryPredictionDTO]:
        """Return pure rule-based predictions."""
        return self._rule_based_classify(text, department_name=department_name)

    @property
    def _ai_model(self):
        key = str(self.model_dir.resolve()) if self.model_dir else ""
        entry = ClassificationService._models_cache.get(key)
        return entry.get("model") if entry else None

    @property
    def _ai_tokenizer(self):
        key = str(self.model_dir.resolve()) if self.model_dir else ""
        entry = ClassificationService._models_cache.get(key)
        return entry.get("tokenizer") if entry else None

    @property
    def _ai_device(self):
        key = str(self.model_dir.resolve()) if self.model_dir else ""
        entry = ClassificationService._models_cache.get(key)
        return entry.get("device") if entry else None

    def _ensure_model_loaded(self) -> bool:
        """Helper to ensure DistilBERT is loaded once on target device in a thread-safe manner."""
        if not TRANSFORMERS_AVAILABLE:
            return False

        key = str(self.model_dir.resolve()) if self.model_dir else ""
        if key in ClassificationService._models_cache:
            return True

        if self._model_load_failed:
            return False

        with ClassificationService._cache_lock:
            if key in ClassificationService._models_cache:
                return True

            if not self.model_dir.exists():
                self._model_load_error_msg = f"Model directory not found: {self.model_dir}"
                self._model_load_failed = True
                return False
            if not (self.model_dir / "model.safetensors").exists():
                self._model_load_error_msg = f"Model weights not found: {self.model_dir / 'model.safetensors'}"
                self._model_load_failed = True
                return False

            try:
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
                model = AutoModelForSequenceClassification.from_pretrained(str(self.model_dir))
                model.to(device)
                model.eval()
                self._model_load_error_msg = None
                ClassificationService._models_cache[key] = {
                    "model": model,
                    "tokenizer": tokenizer,
                    "device": device
                }
                logger.info(f"Loaded fine-tuned DistilBERT classifier from: {self.model_dir}")
                return True
            except Exception as e:
                err_msg = f"Could not load DistilBERT model: {e}"
                logger.warning(err_msg)
                self._model_load_error_msg = err_msg
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

    def classify_comment(
        self,
        comment_text: str,
        comment_id: str = '',
        department_name: Optional[str] = None,
        force_method: Optional[str] = None,
    ) -> ClassificationResultDTO:
        """Classify a single comment into categories with AI inference, department scoping, and keyword-grounded calibration"""
        if not comment_text or not comment_text.strip():
            return ClassificationResultDTO(
                comment_id=comment_id,
                text=comment_text,
                primary_category=CategoryPredictionDTO('Documentation', 0.0, []),
                alternative_categories=[],
                classification_method='rule_based',
                requires_human_review=True,
                fallback_used=False,
                fallback_reason=""
            )

        clean_text = comment_text.strip()
        words = clean_text.lower().split()

        # 1. Rule-based keyword analysis (including department-scoped custom categories)
        rule_preds = self._rule_based_classify(clean_text, department_name=department_name)
        rule_map = {p.category_name: p for p in rule_preds}
        matched_rule_preds = [p for p in rule_preds if p.matched_keywords]
        total_keywords_matched = sum(len(p.matched_keywords) for p in rule_preds)

        # 2. AI model prediction or forced rule evaluation
        if force_method == "rule_based":
            method = "rule_based"
            fallback_used = False
            fallback_reason = ""
            primary = rule_preds[0] if rule_preds else CategoryPredictionDTO('Documentation', 0.0, [])
            alts = rule_preds[1:] if len(rule_preds) > 1 else []
            requires_review = (primary.confidence < self.LOW_CONFIDENCE) or (total_keywords_matched == 0)
        else:
            try:
                ai_preds = self._try_ai_classify(clean_text)
            except Exception as e:
                logger.warning(f"AI classification exception for '{clean_text}': {e}")
                self._model_load_error_msg = str(e)
                ai_preds = None

            if ai_preds:
                method = 'ai_model'
                fallback_used = False
                fallback_reason = ""
                final_predictions = []
                seen_categories = set()

                for p in ai_preds:
                    seen_categories.add(p.category_name)
                    rule_p = rule_map.get(p.category_name, CategoryPredictionDTO('', 0, []))
                    kws = rule_p.matched_keywords
                    rule_conf = rule_p.confidence

                    # Grounding with matched engineering keywords
                    if kws and p.category_name != 'Documentation':
                        combined_conf = min(0.99, 0.40 * p.confidence + 0.45 * rule_conf + 0.05 * len(kws))
                    elif total_keywords_matched > 0 and p.category_name == 'Documentation':
                        combined_conf = max(0.01, p.confidence * 0.30)
                    elif total_keywords_matched > 0 and not kws:
                        # Other categories matched explicit keywords, but this AI pred had none
                        combined_conf = p.confidence * 0.40
                    else:
                        combined_conf = p.confidence * 0.85

                    final_predictions.append(CategoryPredictionDTO(
                        category_name=p.category_name,
                        confidence=float(round(combined_conf, 4)),
                        matched_keywords=kws
                    ))

                # Include any custom categories or rule matches not present in AI model classes
                for p in matched_rule_preds:
                    if p.category_name not in seen_categories:
                        final_predictions.append(CategoryPredictionDTO(
                            category_name=p.category_name,
                            confidence=float(round(p.confidence, 4)),
                            matched_keywords=p.matched_keywords
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
                method = 'rule_based_fallback'
                fallback_used = True
                if not self.model_dir.exists():
                    fallback_reason = f"DistilBERT model directory not found: {self.model_dir}"
                elif not (self.model_dir / "model.safetensors").exists():
                    fallback_reason = f"DistilBERT weights not found in: {self.model_dir}"
                elif not TRANSFORMERS_AVAILABLE:
                    fallback_reason = "Transformers / PyTorch library not available"
                else:
                    fallback_reason = getattr(self, "_model_load_error_msg", None) or "DistilBERT inference unavailable"

                primary = rule_preds[0] if rule_preds else CategoryPredictionDTO('Documentation', 0.0, [])
                alts = rule_preds[1:] if len(rule_preds) > 1 else []
                requires_review = (primary.confidence < self.LOW_CONFIDENCE) or (total_keywords_matched == 0)

        return ClassificationResultDTO(
            comment_id=comment_id,
            text=comment_text,
            primary_category=primary,
            alternative_categories=alts,
            classification_method=method,
            requires_human_review=requires_review,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason
        )
        
    def classify_batch(
        self,
        comments: List[Any],
        drawing_id: str = '',
        department_name: Optional[str] = None,
        force_method: Optional[str] = None,
    ) -> BatchClassificationDTO:
        """Classify multiple comments in batch using accelerated single-pass tensor inference and department keywords"""
        if not comments:
            return BatchClassificationDTO(
                drawing_id=drawing_id,
                total_classified=0,
                results=[],
                high_confidence_count=0,
                low_confidence_count=0,
                flagged_count=0,
                ai_classified_count=0,
                fallback_count=0,
                rule_classified_count=0
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

        # Pre-load department keywords once for entire batch
        dept_kw_tuples = self.get_department_keywords(department_name)

        # 1. Fast Batched AI predictions (1 forward pass) if not forcing rule-based
        if force_method == "rule_based":
            batch_ai_preds = [None] * len(texts)
        else:
            try:
                batch_ai_preds = self._try_ai_classify_batch(texts)
            except Exception as e:
                logger.warning(f"Batched AI classification exception: {e}")
                self._model_load_error_msg = str(e)
                batch_ai_preds = [None] * len(texts)


        results = []
        high = 0
        low = 0
        flagged = 0
        ai_count = 0
        fallback_count = 0
        rule_count = 0

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
                    requires_human_review=True,
                    fallback_used=False,
                    fallback_reason=""
                )
                results.append(res)
                rule_count += 1
                flagged += 1
                low += 1
                continue

            words = clean_text.lower().split()
            rule_preds = self._rule_based_classify(clean_text, custom_kw_tuples=dept_kw_tuples)
            rule_map = {p.category_name: p for p in rule_preds}
            matched_rule_preds = [p for p in rule_preds if p.matched_keywords]
            total_keywords_matched = sum(len(p.matched_keywords) for p in rule_preds)

            if force_method == "rule_based":
                method = "rule_based"
                fallback_used = False
                fallback_reason = ""
                rule_count += 1
                primary = rule_preds[0] if rule_preds else CategoryPredictionDTO('Documentation', 0.0, [])
                alts = rule_preds[1:] if len(rule_preds) > 1 else []
                requires_review = (primary.confidence < self.LOW_CONFIDENCE) or (total_keywords_matched == 0)
            else:
                ai_preds = batch_ai_preds[i]
                if ai_preds:
                    method = 'ai_model'
                    fallback_used = False
                    fallback_reason = ""
                    ai_count += 1
                    final_predictions = []
                    seen_categories = set()

                    for p in ai_preds:
                        seen_categories.add(p.category_name)
                        rule_dto = rule_map.get(p.category_name, CategoryPredictionDTO('', 0, []))
                        kws = rule_dto.matched_keywords
                        rule_conf = rule_dto.confidence

                        if kws and p.category_name != 'Documentation':
                            combined_conf = min(0.99, 0.40 * p.confidence + 0.45 * rule_conf + 0.05 * len(kws))
                        elif total_keywords_matched > 0 and p.category_name == 'Documentation':
                            combined_conf = max(0.01, p.confidence * 0.30)
                        elif total_keywords_matched > 0 and not kws:
                            combined_conf = p.confidence * 0.40
                        else:
                            combined_conf = p.confidence * 0.85

                        final_predictions.append(CategoryPredictionDTO(
                            category_name=p.category_name,
                            confidence=float(round(combined_conf, 4)),
                            matched_keywords=kws
                        ))

                    # Include any custom categories or rule matches not present in AI model classes
                    for p in matched_rule_preds:
                        if p.category_name not in seen_categories:
                            final_predictions.append(CategoryPredictionDTO(
                                category_name=p.category_name,
                                confidence=float(round(p.confidence, 4)),
                                matched_keywords=p.matched_keywords
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
                    method = 'rule_based_fallback'
                    fallback_used = True
                    fallback_count += 1
                    if not self.model_dir.exists():
                        fallback_reason = f"DistilBERT model directory not found: {self.model_dir}"
                    elif not (self.model_dir / "model.safetensors").exists():
                        fallback_reason = f"DistilBERT weights not found in: {self.model_dir}"
                    elif not TRANSFORMERS_AVAILABLE:
                        fallback_reason = "Transformers / PyTorch library not available"
                    else:
                        fallback_reason = getattr(self, "_model_load_error_msg", None) or "DistilBERT inference unavailable"

                    primary = rule_preds[0] if rule_preds else CategoryPredictionDTO('Documentation', 0.0, [])
                    alts = rule_preds[1:] if len(rule_preds) > 1 else []
                    requires_review = (primary.confidence < self.LOW_CONFIDENCE) or (total_keywords_matched == 0)

            res = ClassificationResultDTO(
                comment_id=comment_id,
                text=comment_text,
                primary_category=primary,
                alternative_categories=alts,
                classification_method=method,
                requires_human_review=requires_review,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason
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
            flagged_count=flagged,
            ai_classified_count=ai_count,
            fallback_count=fallback_count,
            rule_classified_count=rule_count
        )

