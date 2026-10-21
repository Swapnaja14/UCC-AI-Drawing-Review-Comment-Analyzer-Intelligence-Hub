"""
OCR Service for Engineering Drawing Processing
Uses Tesseract OCR for text extraction from PDF drawings
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pymupdf as fitz
from PIL import Image
import pytesseract
import io
import os


logger = logging.getLogger(__name__)


class OCRService:
    """Service for performing OCR on engineering drawings using Tesseract"""
    
    def __init__(
        self,
        tesseract_cmd: Optional[str] = None,
        lang: str = 'eng'
    ):
        """
        Initialize Tesseract OCR engine
        
        Args:
            tesseract_cmd: Path to tesseract executable (auto-detect if None)
            lang: Language code (default: 'eng' for English)
        """
        self.lang = lang
        
        # Try to find Tesseract executable
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        else:
            # Common Tesseract installation paths on Windows
            possible_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME')),
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    logger.info(f"Found Tesseract at: {path}")
                    break
        
        # Verify Tesseract is available
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract OCR initialized successfully (version {version}, lang={lang})")
        except Exception as e:
            logger.error(f"Tesseract not found. Please install Tesseract OCR: {e}")
            raise RuntimeError(
                "Tesseract not found. Please install from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
    
    def process_pdf(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        dpi: int = 300
    ) -> Dict[str, any]:
        """
        Process entire PDF and extract text from all pages
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Optional directory to save extracted text
            dpi: DPI for PDF to image conversion (higher = better quality)
        
        Returns:
            Dictionary with extraction results
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        logger.info(f"Processing PDF: {pdf_path.name}")
        
        results = {
            'file_name': pdf_path.name,
            'file_path': str(pdf_path),
            'pages': [],
            'total_text': '',
            'metadata': {}
        }
        
        try:
            # Open PDF
            doc = fitz.open(pdf_path)
            results['metadata']['total_pages'] = len(doc)
            
            # Process each page
            for page_num in range(len(doc)):
                page_result = self._process_page(doc, page_num, dpi)
                results['pages'].append(page_result)
                results['total_text'] += page_result['text'] + '\n\n'
                
                logger.info(f"Processed page {page_num + 1}/{len(doc)}")
            
            doc.close()
            
            # Save results if output directory specified
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
        dpi: int = 300
    ) -> Dict[str, any]:
        """
        Process a single PDF page
        
        Args:
            doc: PyMuPDF document
            page_num: Page number (0-indexed)
            dpi: DPI for rendering
        
        Returns:
            Dictionary with page results
        """
        page = doc[page_num]
        
        # Convert page to image
        zoom = dpi / 72  # PDF default is 72 DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # Perform OCR with detailed data and safe timeout
        timeout_sec = getattr(self, "timeout", 45)
        try:
            ocr_data = pytesseract.image_to_data(
                img,
                lang=self.lang,
                output_type=pytesseract.Output.DICT,
                timeout=timeout_sec,
            )
        except Exception as e:
            logger.warning(f"OCR image_to_data timed out or failed on page {page_num + 1}: {e}")
            ocr_data = {'text': [], 'conf': [], 'left': [], 'top': [], 'width': [], 'height': []}
        
        # Extract text with safe timeout
        try:
            text = pytesseract.image_to_string(img, lang=self.lang, timeout=timeout_sec)
        except Exception as e:
            logger.warning(f"OCR image_to_string timed out or failed on page {page_num + 1}: {e}")
            text = ""
        
        # Parse results
        page_result = {
            'page_number': page_num + 1,
            'text': text.strip(),
            'lines': [],
            'words': [],
            'confidence_scores': []
        }
        
        # Process OCR data to extract words with confidence
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            if int(ocr_data['conf'][i]) > 0:  # Only include words with positive confidence
                word_data = {
                    'text': ocr_data['text'][i],
                    'confidence': int(ocr_data['conf'][i]) / 100.0,  # Convert to 0-1 scale
                    'box': (
                        ocr_data['left'][i],
                        ocr_data['top'][i],
                        ocr_data['width'][i],
                        ocr_data['height'][i]
                    )
                }
                page_result['words'].append(word_data)
                page_result['confidence_scores'].append(word_data['confidence'])
        
        # Calculate average confidence
        if page_result['confidence_scores']:
            page_result['avg_confidence'] = sum(page_result['confidence_scores']) / len(page_result['confidence_scores'])
        else:
            page_result['avg_confidence'] = 0.0
        
        return page_result
    
    def extract_title_block(
        self,
        pdf_path: str,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Dict[str, str]:
        """
        Extract text from title block region (usually bottom-right corner)
        
        Args:
            pdf_path: Path to PDF file
            region: Tuple of (x, y, width, height) in pixels
                   If None, assumes bottom-right 30% of page
        
        Returns:
            Dictionary with title block information
        """
        pdf_path = Path(pdf_path)
        doc = fitz.open(pdf_path)
        page = doc[0]  # Title block usually on first page
        
        # Get page dimensions
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        width, height = img.size
        
        # Define title block region if not provided
        if region is None:
            # Bottom-right 30% of page (typical for engineering drawings)
            x = int(width * 0.7)
            y = int(height * 0.7)
            w = width - x
            h = height - y
            region = (x, y, w, h)
        
        # Crop to title block region
        title_block = img.crop((region[0], region[1], region[0] + region[2], region[1] + region[3]))
        
        # Perform OCR on title block with safe timeout
        try:
            text = pytesseract.image_to_string(title_block, lang=self.lang, timeout=20)
        except Exception as e:
            logger.warning(f"Title block OCR timed out or failed: {e}")
            text = ""
        
        # Extract key information
        title_info = {
            'drawing_number': '',
            'revision': '',
            'title': '',
            'date': '',
            'raw_text': text.strip()
        }
        
        # TODO: Add regex patterns to extract specific fields
        
        doc.close()
        return title_info
    
    def batch_process_drawings(
        self,
        input_dir: str,
        output_dir: str,
        file_pattern: str = "*.pdf",
        dpi: int = 300
    ) -> List[Dict[str, any]]:
        """
        Process multiple PDF drawings in batch
        
        Args:
            input_dir: Directory containing PDF files
            output_dir: Directory to save results
            file_pattern: Glob pattern for files to process
            dpi: DPI for image conversion
        
        Returns:
            List of results for each processed file
        """
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        pdf_files = list(input_path.glob(file_pattern))
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        results = []
        for i, pdf_file in enumerate(pdf_files, 1):
            logger.info(f"Processing {i}/{len(pdf_files)}: {pdf_file.name}")
            try:
                result = self.process_pdf(str(pdf_file), str(output_path), dpi=dpi)
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
        
        # Save as text file
        file_stem = Path(results['file_name']).stem
        txt_path = output_path / f"{file_stem}_ocr.txt"
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"File: {results['file_name']}\n")
            f.write(f"Total Pages: {results['metadata'].get('total_pages', 0)}\n")
            f.write("=" * 80 + "\n\n")
            
            for page in results['pages']:
                f.write(f"Page {page['page_number']}\n")
                f.write(f"Confidence: {page['avg_confidence']:.2%}\n")
                f.write("-" * 80 + "\n")
                f.write(page['text'] + "\n\n")
        
        logger.info(f"Results saved to {txt_path}")


def main():
    """Example usage"""
    # Initialize OCR service
    ocr_service = OCRService(lang='eng')
    
    # Process single PDF
    # result = ocr_service.process_pdf(
    #     'dataset/raw_drawings/Electrical Engineering/5-1307-137_F_RJY.pdf',
    #     output_dir='dataset/extracted_text'
    # )
    
    # Batch process all drawings in a category
    results = ocr_service.batch_process_drawings(
        input_dir='dataset/raw_drawings/Electrical Engineering',
        output_dir='dataset/extracted_text/Electrical Engineering',
        dpi=300
    )
    
    print(f"Processed {len(results)} files")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
