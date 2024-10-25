#!/usr/bin/env python
# coding: utf-8

import fitz  # PyMuPDF
import json
import random
from typing import List
import colorsys
import logging
import argparse
import sys

# Use coloredlogs for colored logging output
import coloredlogs

# Configure colored logging
coloredlogs.install(
    level='INFO',
    fmt='%(asctime)s - %(levelname)s - %(message)s',
    logger=logging.getLogger()
)
logger = logging.getLogger(__name__)

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

def confidence_to_color(confidence: float) -> tuple:
    """Convert confidence score to a color gradient from red to yellow to green."""
    if confidence < 0.5:
        # Red to Yellow gradient for lower confidence
        return (1.0, confidence * 2, 0)
    else:
        # Yellow to Green gradient for higher confidence
        return ((1.0 - confidence) * 2, 1.0, 0)

def draw_confidence_indicator(page: fitz.Page, rect: fitz.Rect, confidence: float):
    """Draw a thin confidence indicator bar to the right of the rectangle."""
    # Define dimensions for confidence visualization
    bar_width = 2  # Thinner bar
    bar_height = rect.height
    # Position indicator to the right of the rectangle with small gap
    bar_rect = fitz.Rect(
        rect.x1 + 2,  # 2 points gap
        rect.y0,
        rect.x1 + 2 + bar_width,
        rect.y0 + bar_height
    )
    # Get color based on confidence
    color = confidence_to_color(confidence)
    # Draw the confidence bar
    page.draw_rect(bar_rect, color=color, fill=color)

def mark_up_document(input_pdf_path: str, json_data: dict, output_pdf_path: str):
    """Mark up PDF with key-value pairs, tables, and paragraphs."""
    try:
        doc = fitz.open(input_pdf_path)
        logger.info(f"Processing document: {input_pdf_path}")
        # Generate distinct colors for different KV pairs
        kv_pairs = json_data['analyzeResult'].get('keyValuePairs', [])
        if len(kv_pairs) > 0:
            colors = generate_distinct_colors(len(kv_pairs))
        else:
            colors = []
            logger.warning("No key-value pairs found in JSON data.")
        for page_num in range(doc.page_count):
            page = doc[page_num]
            logger.info(f"Processing page {page_num + 1}")
            # Process key-value pairs
            for idx, kv_pair in enumerate(kv_pairs):
                color = colors[idx % len(colors)]
                confidence = kv_pair.get('confidence', 0.5)
                # Process key
                if 'key' in kv_pair:
                    for region in kv_pair['key'].get('boundingRegions', []):
                        if region['pageNumber'] == page_num + 1:
                            points = region['polygon']
                            points = [point * 72 for point in points]
                            rect = fitz.Rect(
                                min(points[0::2]),
                                min(points[1::2]),
                                max(points[0::2]),
                                max(points[1::2])
                            )
                            # Draw key with solid fill and border
                            page.draw_rect(rect, color=color, fill=color, fill_opacity=0.2)
                            page.draw_rect(rect, color=color, width=1.0)
                # Process value and draw confidence indicator
                if 'value' in kv_pair:
                    for region in kv_pair['value'].get('boundingRegions', []):
                        if region['pageNumber'] == page_num + 1:
                            points = region['polygon']
                            points = [point * 72 for point in points]
                            rect = fitz.Rect(
                                min(points[0::2]),
                                min(points[1::2]),
                                max(points[0::2]),
                                max(points[1::2])
                            )
                            # Draw value with lighter fill
                            page.draw_rect(rect, color=color, fill=color, fill_opacity=0.1)
                            page.draw_rect(rect, color=color, width=0.5)
                            # Draw confidence indicator next to value
                            draw_confidence_indicator(page, rect, confidence)
            # Process tables
            logger.info("Processing tables")
            for table in json_data['analyzeResult'].get('tables', []):
                for cell in table.get('cells', []):
                    for region in cell.get('boundingRegions', []):
                        if region['pageNumber'] == page_num + 1:
                            points = region['polygon']
                            points = [point * 72 for point in points]
                            rect = fitz.Rect(
                                min(points[0::2]),
                                min(points[1::2]),
                                max(points[0::2]),
                                max(points[1::2])
                            )
                            # Different styling for header cells
                            if cell.get('kind') == 'columnHeader':
                                page.draw_rect(rect, color=(0, 0, 0.8), fill=(0, 0, 0.8), fill_opacity=0.1)
                                page.draw_rect(rect, color=(0, 0, 0.8), width=1)
                            else:
                                page.draw_rect(rect, color=(0.5, 0.5, 0.5), width=0.5)
            # Process paragraphs
            logger.info("Processing paragraphs")
            for para in json_data['analyzeResult'].get('paragraphs', []):
                for region in para.get('boundingRegions', []):
                    if region['pageNumber'] == page_num + 1:
                        points = region['polygon']
                        points = [point * 72 for point in points]
                        rect = fitz.Rect(
                            min(points[0::2]),
                            min(points[1::2]),
                            max(points[0::2]),
                            max(points[1::2])
                        )
                        # Draw light gray background for paragraphs
                        page.draw_rect(rect, color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9), fill_opacity=0.05)
                        page.draw_rect(rect, color=(0.5, 0.5, 0.5), width=0.3)
        # Save the marked-up PDF
        doc.save(output_pdf_path)
        doc.close()
        logger.info(f"Successfully saved marked-up PDF to: {output_pdf_path}")
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Mark up PDF documents based on JSON data.")
    parser.add_argument('input_pdf', help='Path to the input PDF file.')
    parser.add_argument('input_json', help='Path to the JSON file with markup data.')
    parser.add_argument('output_pdf', help='Path to save the marked-up PDF file.')

    args = parser.parse_args()

    try:
        # Load JSON data
        with open(args.input_json, 'r') as f:
            json_data = json.load(f)
        logger.info("Successfully loaded JSON data")
        # Process the PDF
        mark_up_document(
            args.input_pdf,
            json_data,
            args.output_pdf
        )
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()