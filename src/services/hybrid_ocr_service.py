"""
Hybrid OCR Service for Engineering Drawing Processing
Uses Tesseract for printed text and TrOCR for handwritten text
"""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal
import pymupdf as fitz
from PIL import Image
import pytesseract
import io
try:
    import torch
    from transformers import (
        TrOCRProcessor, 
        VisionEncoderDecoderModel,
        RobertaTokenizer,
        ViTImageProcessor
    )
    TROCR_AVAILABLE = True
except (ImportError, OSError, Exception):
    torch = None
    TrOCRProcessor = None
    VisionEncoderDecoderModel = None
    RobertaTokenizer = None
    ViTImageProcessor = None
    TROCR_AVAILABLE = False


logger = logging.getLogger(__name__)


class HybridOCRService:
    """
    Hybrid OCR service combining Tesseract and TrOCR
    - Tesseract: Fast, accurate for printed text
    - TrOCR: Better for handwritten text and annotations
    """
    
    def __init__(
        self,
        tesseract_cmd: Optional[str] = None,
        lang: str = 'eng',
        trocr_model: str = 'microsoft/trocr-base-printed',
        use_gpu: bool = False
    ):
        """
        Initialize Hybrid OCR engine
        
        Args:
            tesseract_cmd: Path to tesseract executable
            lang: Language for Tesseract (default: 'eng')
            trocr_model: TrOCR model to use:
                - 'microsoft/trocr-base-printed' (recommended, works well for both)
                - 'microsoft/trocr-small-printed' (faster)
                - 'microsoft/trocr-large-printed' (more accurate)
            use_gpu: Use GPU if available
        """
        self.lang = lang
        self.device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'
        
        # Initialize Tesseract
        self._init_tesseract(tesseract_cmd)
        
        # Initialize TrOCR
        self._init_trocr(trocr_model)
        
        logger.info(f"Hybrid OCR initialized (device: {self.device})")
    
    def _init_tesseract(self, tesseract_cmd: Optional[str]):
        """Initialize Tesseract OCR"""
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        else:
            # Auto-detect Tesseract on Windows
            possible_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME')),
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break
        
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract {version} initialized")
        except Exception as e:
            raise RuntimeError(f"Tesseract not found: {e}")
    
    def _init_trocr(self, model_name: str):
        """Initialize TrOCR model"""
        try:
            logger.info(f"Loading TrOCR model: {model_name}")
            
            # Workaround for transformers 5.x tokenizer issue
            # Load tokenizer and image processor separately
            logger.info("Loading tokenizer and image processor separately...")
            self.trocr_tokenizer = RobertaTokenizer.from_pretrained(model_name)
            self.trocr_image_processor = ViTImageProcessor.from_pretrained(model_name)
            
            logger.info("Loading TrOCR model...")
            self.trocr_model = VisionEncoderDecoderModel.from_pretrained(model_name)
            self.trocr_model.to(self.device)
            self.trocr_model_name = model_name
            
            logger.info(f"TrOCR model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load TrOCR: {e}")
            raise
    
    def process_pdf(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        dpi: int = 300,
        ocr_engine: Literal['auto', 'tesseract', 'trocr', 'both'] = 'auto'
    ) -> Dict[str, any]:
        """
        Process entire PDF with hybrid OCR
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Optional directory to save results
            dpi: DPI for image conversion
            ocr_engine: Which engine to use:
                - 'auto': Automatically choose best engine (default)
                - 'tesseract': Use only Tesseract (fast, printed text)
                - 'trocr': Use only TrOCR (slow, handwritten text)
                - 'both': Run both and combine results
        
        Returns:
            Dictionary with extraction results
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        logger.info(f"Processing PDF: {pdf_path.name} (engine: {ocr_engine})")
        
        results = {
            'file_name': pdf_path.name,
            'file_path': str(pdf_path),
            'pages': [],
            'total_text': '',
            'metadata': {
                'ocr_engine': ocr_engine
            }
        }
        
        try:
            doc = fitz.open(pdf_path)
            results['metadata']['total_pages'] = len(doc)
            
            for page_num in range(len(doc)):
                page_result = self._process_page(doc, page_num, dpi, ocr_engine)
                results['pages'].append(page_result)
                results['total_text'] += page_result['text'] + '\n\n'
                
                logger.info(f"Processed page {page_num + 1}/{len(doc)}")
            
            doc.close()
            
            if output_dir:
                self._save_results(results, output_dir)
            
            logger.info(f"Successfully processed {pdf_path.name}")
            return results
            
        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path.name}: {e}")
            raise
    
    def _process_page(
        self,
        doc: fitz.Document,
        page_num: int,
        dpi: int = 300,
        ocr_engine: str = 'auto'
    ) -> Dict[str, any]:
        """Process a single PDF page"""
        page = doc[page_num]
        
        # Convert to image
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        page_result = {
            'page_number': page_num + 1,
            'text': '',
            'engines_used': [],
            'confidence_scores': []
        }
        
        if ocr_engine == 'auto':
            # Auto-detect: use Tesseract first, fallback to TrOCR if low confidence
            tesseract_result = self._run_tesseract(img)
            page_result['engines_used'].append('tesseract')
            
            if tesseract_result['avg_confidence'] < 0.5:  # Low confidence threshold
                logger.info(f"Page {page_num + 1}: Low Tesseract confidence, trying TrOCR")
                trocr_result = self._run_trocr(img)
                page_result['engines_used'].append('trocr')
                # Use TrOCR result if better
                page_result.update(trocr_result)
            else:
                page_result.update(tesseract_result)
        
        elif ocr_engine == 'tesseract':
            result = self._run_tesseract(img)
            page_result.update(result)
            page_result['engines_used'].append('tesseract')
        
        elif ocr_engine == 'trocr':
            result = self._run_trocr(img)
            page_result.update(result)
            page_result['engines_used'].append('trocr')
        
        elif ocr_engine == 'both':
            tesseract_result = self._run_tesseract(img)
            trocr_result = self._run_trocr(img)
            
            # Combine results
            page_result['text'] = f"=== Tesseract ===\n{tesseract_result['text']}\n\n=== TrOCR ===\n{trocr_result['text']}"
            page_result['tesseract_confidence'] = tesseract_result['avg_confidence']
            page_result['trocr_text'] = trocr_result['text']
            page_result['avg_confidence'] = (tesseract_result['avg_confidence'] + 1.0) / 2  # TrOCR doesn't provide confidence
            page_result['engines_used'] = ['tesseract', 'trocr']
        
        return page_result
    
    def _run_tesseract(self, img: Image.Image) -> Dict[str, any]:
        """Run Tesseract OCR on image"""
        # Get detailed data
        ocr_data = pytesseract.image_to_data(
            img,
            lang=self.lang,
            output_type=pytesseract.Output.DICT
        )
        
        # Get text
        text = pytesseract.image_to_string(img, lang=self.lang)
        
        # Calculate confidence
        confidences = [
            int(ocr_data['conf'][i]) / 100.0
            for i in range(len(ocr_data['conf']))
            if int(ocr_data['conf'][i]) > 0
        ]
        
        return {
            'text': text.strip(),
            'avg_confidence': sum(confidences) / len(confidences) if confidences else 0.0,
            'word_count': len([c for c in confidences if c > 0])
        }
    
    def _run_trocr(self, img: Image.Image) -> Dict[str, any]:
        """Run TrOCR on image"""
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Process image using image processor
        pixel_values = self.trocr_image_processor(
            images=img,
            return_tensors="pt"
        ).pixel_values.to(self.device)
        
        # Generate text
        generated_ids = self.trocr_model.generate(pixel_values)
        
        # Decode using tokenizer
        text = self.trocr_tokenizer.batch_decode(
            generated_ids,
            skip_special_tokens=True
        )[0]
        
        return {
            'text': text.strip(),
            'avg_confidence': 1.0,  # TrOCR doesn't provide confidence scores
            'word_count': len(text.split())
        }
    
    def process_region(
        self,
        pdf_path: str,
        page_num: int = 0,
        region: Optional[Tuple[int, int, int, int]] = None,
        ocr_engine: str = 'auto'
    ) -> Dict[str, str]:
        """
        Process specific region (e.g., title block, handwritten annotations)
        
        Args:
            pdf_path: Path to PDF
            page_num: Page number (0-indexed)
            region: (x, y, width, height) in pixels, None for bottom-right 30%
            ocr_engine: 'tesseract', 'trocr', or 'auto'
        
        Returns:
            Extracted text and metadata
        """
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # Get page as image
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        width, height = img.size
        
        # Define region if not provided
        if region is None:
            x = int(width * 0.7)
            y = int(height * 0.7)
            w = width - x
            h = height - y
            region = (x, y, w, h)
        
        # Crop to region
        cropped = img.crop((region[0], region[1], region[0] + region[2], region[1] + region[3]))
        
        # Run OCR
        if ocr_engine == 'tesseract' or ocr_engine == 'auto':
            result = self._run_tesseract(cropped)
        elif ocr_engine == 'trocr':
            result = self._run_trocr(cropped)
        else:
            raise ValueError(f"Unknown engine: {ocr_engine}")
        
        doc.close()
        
        return {
            'text': result['text'],
            'confidence': result['avg_confidence'],
            'engine': ocr_engine,
            'region': region
        }
    
    def batch_process_drawings(
        self,
        input_dir: str,
        output_dir: str,
        file_pattern: str = "*.pdf",
        dpi: int = 300,
        ocr_engine: str = 'auto'
    ) -> List[Dict[str, any]]:
        """Batch process multiple PDFs"""
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        pdf_files = list(input_path.glob(file_pattern))
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        results = []
        for i, pdf_file in enumerate(pdf_files, 1):
            logger.info(f"Processing {i}/{len(pdf_files)}: {pdf_file.name}")
            try:
                result = self.process_pdf(
                    str(pdf_file),
                    str(output_path),
                    dpi=dpi,
                    ocr_engine=ocr_engine
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {pdf_file.name}: {e}")
                results.append({
                    'file_name': pdf_file.name,
                    'error': str(e),
                    'status': 'failed'
                })
        
        logger.info(f"Batch processing complete: {len(results)} files processed")
        return results
    
    def _save_results(self, results: Dict[str, any], output_dir: str):
        """Save OCR results to text file"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        file_stem = Path(results['file_name']).stem
        txt_path = output_path / f"{file_stem}_hybrid_ocr.txt"
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"File: {results['file_name']}\n")
            f.write(f"Total Pages: {results['metadata'].get('total_pages', 0)}\n")
            f.write(f"OCR Engine: {results['metadata'].get('ocr_engine', 'unknown')}\n")
            f.write("=" * 80 + "\n\n")
            
            for page in results['pages']:
                f.write(f"Page {page['page_number']}\n")
                f.write(f"Engines: {', '.join(page.get('engines_used', []))}\n")
                if 'avg_confidence' in page:
                    f.write(f"Confidence: {page['avg_confidence']:.2%}\n")
                f.write("-" * 80 + "\n")
                f.write(page['text'] + "\n\n")
        
        logger.info(f"Results saved to {txt_path}")


def main():
    """Example usage"""
    logging.basicConfig(level=logging.INFO)
    
    # Initialize hybrid OCR
    ocr_service = HybridOCRService(
        lang='eng',
        trocr_model='microsoft/trocr-base-printed',
        use_gpu=False
    )
    
    # Process with automatic engine selection
    result = ocr_service.process_pdf(
        'dataset/raw_drawings/Electrical Engineering/5-1307-137_F_RJY.pdf',
        output_dir='dataset/extracted_text/test',
        dpi=300,
        ocr_engine='auto'  # or 'tesseract', 'trocr', 'both'
    )
    
    print(f"Processed {result['file_name']}")
    print(f"Engines used: {[p['engines_used'] for p in result['pages']]}")


if __name__ == "__main__":
    main()
