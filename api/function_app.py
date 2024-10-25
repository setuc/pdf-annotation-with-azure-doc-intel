# function_app.py
import azure.functions as func
import logging
from typing import Dict, List, Optional, TypedDict, Union
import json
import fitz
import colorsys
import random
import base64
from io import BytesIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# region: Function App Utility functions
def generate_distinct_colors(n: int) -> List[tuple]:
    """Generate n visually distinct colors using HSV color space."""
    colors = []
    for i in range(n):
        hue = i / n
        saturation = 0.7 + random.uniform(-0.2, 0.2)
        value = 0.9 + random.uniform(-0.1, 0.1)
        rgb = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append(rgb)
    return colors

def draw_confidence_indicator(page: fitz.Page, rect: fitz.Rect, confidence: float):
    """Draw a thin confidence indicator bar to the right of the rectangle."""
    bar_width = 2
    bar_height = rect.height
    
    bar_rect = fitz.Rect(
        rect.x1 + 2,
        rect.y0,
        rect.x1 + 2 + bar_width,
        rect.y0 + bar_height
    )
    
    color = (1.0, confidence * 2, 0) if confidence < 0.5 else ((1.0 - confidence) * 2, 1.0, 0)
    page.draw_rect(bar_rect, color=color, fill=color)

def process_pdf(pdf_data: bytes, json_data: dict) -> bytes:
    """Process PDF with markup based on JSON data."""
    try:
        # Load PDF from bytes
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        logger.info(f"Processing document with {doc.page_count} pages")
        
        analyze_result = json_data.get('analyzeResult', {})
        
        # Generate colors for key-value pairs
        kv_pairs = analyze_result.get('keyValuePairs', [])
        colors = generate_distinct_colors(len(kv_pairs))
        logger.info(f"Processing {len(kv_pairs)} key-value pairs")
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            logger.info(f"Processing page {page_num + 1}")
            
            # Process key-value pairs
            for idx, kv_pair in enumerate(kv_pairs):
                color = colors[idx]
                confidence = kv_pair.get('confidence', 0.5)
                
                # Process key
                if 'key' in kv_pair:
                    for region in kv_pair['key'].get('boundingRegions', []):
                        if region['pageNumber'] == page_num + 1:
                            points = [point * 72 for point in region['polygon']]
                            rect = fitz.Rect(
                                min(points[0::2]),
                                min(points[1::2]),
                                max(points[0::2]),
                                max(points[1::2])
                            )
                            page.draw_rect(rect, color=color, fill=color, fill_opacity=0.2)
                            page.draw_rect(rect, color=color, width=1.0)
                
                # Process value
                if 'value' in kv_pair:
                    for region in kv_pair['value'].get('boundingRegions', []):
                        if region['pageNumber'] == page_num + 1:
                            points = [point * 72 for point in region['polygon']]
                            rect = fitz.Rect(
                                min(points[0::2]),
                                min(points[1::2]),
                                max(points[0::2]),
                                max(points[1::2])
                            )
                            page.draw_rect(rect, color=color, fill=color, fill_opacity=0.1)
                            page.draw_rect(rect, color=color, width=0.5)
                            draw_confidence_indicator(page, rect, confidence)
            
            # Process tables
            tables = analyze_result.get('tables', [])
            logger.info(f"Processing {len(tables)} tables")
            for table in tables:
                for cell in table.get('cells', []):
                    for region in cell.get('boundingRegions', []):
                        if region['pageNumber'] == page_num + 1:
                            points = [point * 72 for point in region['polygon']]
                            rect = fitz.Rect(
                                min(points[0::2]),
                                min(points[1::2]),
                                max(points[0::2]),
                                max(points[1::2])
                            )
                            if cell.get('kind') == 'columnHeader':
                                page.draw_rect(rect, color=(0, 0, 0.8), fill=(0, 0, 0.8), fill_opacity=0.1)
                                page.draw_rect(rect, color=(0, 0, 0.8), width=1)
                            else:
                                page.draw_rect(rect, color=(0.5, 0.5, 0.5), width=0.5)
            
            # Process paragraphs
            paragraphs = analyze_result.get('paragraphs', [])
            logger.info(f"Processing {len(paragraphs)} paragraphs")
            for para in paragraphs:
                for region in para.get('boundingRegions', []):
                    if region['pageNumber'] == page_num + 1:
                        points = [point * 72 for point in region['polygon']]
                        rect = fitz.Rect(
                            min(points[0::2]),
                            min(points[1::2]),
                            max(points[0::2]),
                            max(points[1::2])
                        )
                        page.draw_rect(rect, color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9), fill_opacity=0.05)
                        page.draw_rect(rect, color=(0.5, 0.5, 0.5), width=0.3)

        # Save to bytes
        output = BytesIO()
        doc.save(output)
        doc.close()
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise ValueError("Error processing PDF") from e
    
# endregion

app = func.FunctionApp()

@app.route(route="parse_form", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def process_form(req: func.HttpRequest) -> func.HttpResponse:
    """
    Process PDF form and return marked up version.
    
    Args:
        req: HTTP request containing PDF file and JSON data
        
    Returns:
        HTTP response with processed PDF or error message
    """
    logging.info('Processing form request.')
    
    try:
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
        
        # Handle preflight requests
        if req.method == "OPTIONS":
            return func.HttpResponse(
                status_code=200,
                headers=headers
            )
            
        # Get PDF file and JSON data from request
        try:
            form_data = req.get_json()
            logger.info("Successfully parsed request JSON")
        except ValueError as e:
            logger.error(f"Failed to parse request JSON: {str(e)}")
            return func.HttpResponse(
                "Invalid JSON in request body",
                status_code=400,
                headers=headers
            )
            
        if not form_data:
            return func.HttpResponse(
                "Empty request body",
                status_code=400,
                headers=headers
            )
            
        # Validate required fields
        if 'pdf_base64' not in form_data:
            return func.HttpResponse(
                "Missing PDF data in request",
                status_code=400,
                headers=headers
            )
            
        if 'analyzeResult' not in form_data:
            return func.HttpResponse(
                "Missing analyzeResult in request",
                status_code=400,
                headers=headers
            )
        
        # Log request structure for debugging
        logger.info(f"Request contains: {', '.join(form_data.keys())}")
        if 'analyzeResult' in form_data:
            analyze_result = form_data['analyzeResult']
            logger.info(f"analyzeResult contains: {', '.join(analyze_result.keys())}")
        
        # Decode PDF from base64
        try:
            pdf_data = base64.b64decode(form_data['pdf_base64'])
            logger.info("Successfully decoded PDF data")
        except Exception as e:
            logger.error(f"Failed to decode PDF data: {str(e)}")
            return func.HttpResponse(
                "Invalid PDF data encoding",
                status_code=400,
                headers=headers
            )
        
        # Process the PDF
        try:
            processed_pdf = process_pdf(pdf_data, form_data)
            logger.info("Successfully processed PDF")
        except ValueError as e:
            logger.error(f"PDF processing error: {str(e)}")
            return func.HttpResponse(
                str(e),
                status_code=400,
                headers=headers
            )
        except Exception as e:
            logger.error(f"Unexpected error in PDF processing: {str(e)}")
            return func.HttpResponse(
                "Error processing PDF",
                status_code=500,
                headers=headers
            )
        
        # Return processed PDF as base64
        response_data = {
            'processed_pdf': base64.b64encode(processed_pdf).decode('utf-8')
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            mimetype="application/json",
            status_code=200,
            headers=headers
        )
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return func.HttpResponse(
            "Internal server error",
            status_code=500,
            headers=headers
        )