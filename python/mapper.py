import json
import os
import difflib
import numpy as np
from scipy.optimize import linear_sum_assignment
from typing import List, Tuple, Dict, Optional
import logging

# Rich imports for logging and visualization
from rich import print
from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table
from rich.columns import Columns

# ------------------------------------------------------------------------------
# Configure Logging with RichHandler
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger("json_matcher")

# ------------------------------------------------------------------------------
# 1. Utilities to Load and Flatten JSON
# ------------------------------------------------------------------------------

def load_json(file_path: str) -> dict:
    """
    Load a JSON file from disk and return as a Python dictionary.
    """
    logger.debug(f"Loading JSON from: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.debug(f"Loaded JSON keys: {list(data.keys())}")
    return data

def flatten_json(nested_json: dict, parent_key: str = "", sep: str = ".") -> dict:
    """
    Recursively flatten a nested JSON object into a single-level dict 
    with dot-separated keys (e.g., "buyer_information.name").
    """
    items = []
    for k, v in nested_json.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        else:
            # Convert everything to string for matching; if value is None, use empty string.
            items.append((new_key, str(v) if v is not None else ""))
    flat = dict(items)
    logger.debug(f"Flattened JSON contains {len(flat)} fields.")
    return flat

# ------------------------------------------------------------------------------
# 2. Extract Fields from JSON-1 *Without* Hardcoding
# ------------------------------------------------------------------------------

def extract_fields_from_json1(json1: dict, max_fields: Optional[int] = 20) -> List[Tuple[str, str]]:
    """
    Flatten the entire JSON-1 and return non-empty fields as (key, value) pairs.
    
    - If max_fields is provided (an integer), only the first that many fields (in natural order)
      are returned; if None, all fields are returned.
    """
    flattened = flatten_json(json1)
    # Filter out empty or whitespace-only values
    non_empty = {k: v for k, v in flattened.items() if v.strip()}
    # Preserve the natural insertion order rather than sorting alphabetically.
    keys = list(non_empty.keys())
    if max_fields is not None:
        keys = keys[:max_fields]
    fields = [(k, non_empty[k]) for k in keys]
    logger.debug(f"Extracted {len(fields)} non-empty field(s) from JSON-1.")
    return fields

# ------------------------------------------------------------------------------
# 3. Extract Candidates from Document Intelligence JSON (JSON-2)
# ------------------------------------------------------------------------------

def parse_doc_intelligence_json(doc_json: dict) -> dict:
    """
    Parse the top-level structure of the Document Intelligence JSON.
    Typically, your relevant data is in 'analyzeResult'.
    """
    result = doc_json.get("analyzeResult", {})
    logger.debug(f"Parsed analyzeResult with keys: {list(result.keys())}")
    return result

def extract_candidates_from_layout(analyze_result: dict) -> List[Tuple[str, str, dict]]:
    """
    Extract candidate text from the 'tables' in the Document Intelligence JSON.
    
    Instead of only taking column headers, we now extract every non-empty cell
    so that candidates from second or third rows are included.
    
    Returns a list of (candidate_id, candidate_text, metadata).
    """
    candidates = []
    tables = analyze_result.get("tables", [])
    for table in tables:
        for cell in table.get("cells", []):
            text = cell.get("content", "").strip()
            if text:
                candidate_id = f"cand_{len(candidates)}"
                candidates.append((candidate_id, text, cell))
    logger.debug(f"Extracted {len(candidates)} candidate(s) from Document Intelligence.")
    return candidates

# ------------------------------------------------------------------------------
# 4. Matching Algorithms
# ------------------------------------------------------------------------------

def hungarian_matching(
    fields: List[Tuple[str, str]], 
    candidates: List[Tuple[str, str, dict]], 
    threshold: float = 0.7
) -> Dict[str, dict]:
    """
    Use the Hungarian algorithm for optimal one-to-one matching.
    Note: When there are more fields than candidates, only len(candidates) pairs are returned.
    """
    n = len(fields)
    m = len(candidates)
    cost_matrix = np.zeros((n, m), dtype=np.float32)
    
    logger.debug("Building cost matrix for Hungarian matching...")
    # Build cost matrix based on (1 - similarity)
    for i, (_, f_val) in enumerate(fields):
        for j, (_, cand_text, _) in enumerate(candidates):
            sim = difflib.SequenceMatcher(None, f_val, cand_text).ratio()
            cost_matrix[i, j] = 1.0 - sim
    
    logger.debug("Solving assignment problem using linear_sum_assignment...")
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    matches = {}
    for i, j in zip(row_ind, col_ind):
        sim = 1.0 - cost_matrix[i, j]
        review = sim < threshold
        field_key = fields[i][0]
        matches[field_key] = {
            "field_value": fields[i][1],
            "candidate_id": candidates[j][0],
            "candidate_text": candidates[j][1],
            "similarity": sim,
            "human_review": review
        }
    logger.debug(f"Hungarian matching produced {len(matches)} match(es).")
    return matches

def greedy_matching(
    fields: List[Tuple[str, str]], 
    candidates: List[Tuple[str, str, dict]], 
    threshold: float = 0.7
) -> Dict[str, dict]:
    """
    For each field, find the candidate with the highest similarity,
    regardless of whether that candidate is used more than once.
    """
    matches = {}
    for field_key, field_value in fields:
        best_sim = 0.0
        best_candidate = None
        for candidate in candidates:
            candidate_id, candidate_text, _ = candidate
            sim = difflib.SequenceMatcher(None, field_value, candidate_text).ratio()
            if sim > best_sim:
                best_sim = sim
                best_candidate = candidate
        if best_candidate is not None:
            review = best_sim < threshold
            matches[field_key] = {
                "field_value": field_value,
                "candidate_id": best_candidate[0],
                "candidate_text": best_candidate[1],
                "similarity": best_sim,
                "human_review": review
            }
    logger.debug(f"Greedy matching produced {len(matches)} match(es).")
    return matches

# ------------------------------------------------------------------------------
# 5. High-Level Function to Do It All Dynamically
# ------------------------------------------------------------------------------

def match_jsons_dynamic(
    json1_path: str,
    json2_path: str,
    max_fields: Optional[int] = 20,
    algorithm: str = "greedy",  # choose between "hungarian" and "greedy"
    threshold: float = 0.7
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, dict]], Dict[str, dict]]:
    """
    - Loads JSON-1 (structured data) from json1_path.
    - Loads JSON-2 (Document Intelligence) from json2_path.
    - Dynamically flattens and filters fields from JSON-1.
    - Extracts candidate text from JSON-2 tables (all non-empty cells).
    - Matches them using the chosen algorithm.
    - Returns a tuple of (fields, candidates, matches).
    
    Pass max_fields as None to extract all fields.
    """
    logger.debug("Starting dynamic matching...")
    # Load JSONs
    structured_data = load_json(json1_path)
    doc_intelligence_data = load_json(json2_path)
    
    # Extract fields from JSON-1 (avoid hardcoded keys)
    fields = extract_fields_from_json1(structured_data, max_fields=max_fields)
    
    # Extract candidates from Document Intelligence
    analyze_result = parse_doc_intelligence_json(doc_intelligence_data)
    candidates = extract_candidates_from_layout(analyze_result)
    
    # Matching based on selected algorithm
    if algorithm == "hungarian":
        matches = hungarian_matching(fields, candidates, threshold)
    elif algorithm == "greedy":
        matches = greedy_matching(fields, candidates, threshold)
    else:
        raise ValueError(f"Unknown matching algorithm: {algorithm}")
    
    logger.debug("Dynamic matching completed.")
    return fields, candidates, matches

# ------------------------------------------------------------------------------
# 6. Visualization Helpers using Rich Tables
# ------------------------------------------------------------------------------

def display_side_by_side_tables(fields: List[Tuple[str, str]], 
                                candidates: List[Tuple[str, str, dict]], 
                                matches: Dict[str, dict]):
    console = Console()
    
    # Table for extracted fields from JSON-1
    table_fields = Table(title="Extracted Fields (JSON-1)", style="cyan")
    table_fields.add_column("Field Key", style="magenta", no_wrap=True)
    table_fields.add_column("Field Value", style="green")
    for key, value in fields:
        table_fields.add_row(key, value)
    
    # Table for extracted candidates from JSON-2
    table_candidates = Table(title="Extracted Candidates (JSON-2)", style="cyan")
    table_candidates.add_column("Candidate ID", style="magenta", no_wrap=True)
    table_candidates.add_column("Candidate Text", style="green")
    for cand in candidates:
        candidate_id, candidate_text, _ = cand
        table_candidates.add_row(candidate_id, candidate_text)
    
    # Display the two tables side by side
    console.print(Columns([table_fields, table_candidates]))
    
    # Table for match results
    table_matches = Table(title="Match Results", style="cyan")
    table_matches.add_column("Field Key", style="magenta", no_wrap=True)
    table_matches.add_column("Field Value", style="green")
    table_matches.add_column("Candidate ID", style="yellow")
    table_matches.add_column("Candidate Text", style="green")
    table_matches.add_column("Similarity", style="blue")
    table_matches.add_column("Human Review Needed", style="red")
    for key, info in matches.items():
        row_style = "red" if info["human_review"] else "green"
        table_matches.add_row(
            key,
            info["field_value"],
            info["candidate_id"],
            info["candidate_text"],
            f"{info['similarity']:.2f}",
            str(info["human_review"]),
            style=row_style
        )
    
    console.print(table_matches)

# ------------------------------------------------------------------------------
# 7. Example Main Usage
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Example file paths (adjust if necessary)
    json1_file = os.path.join(os.getcwd(), "../examples/Connecticut.gpt.json")  # JSON-1 file
    json2_file = os.path.join(os.getcwd(), "../examples/Connecticut.layout.json")  # JSON-2 file
    
    try:
        # For full debugging, you might set max_fields to None to see all JSON-1 fields.
        fields, candidates, matches = match_jsons_dynamic(
            json1_path=json1_file,
            json2_path=json2_file,
            max_fields=None,        # Set to None to extract all fields from JSON-1
            algorithm="hungarian",     # "greedy" ensures every field finds its best candidate
            threshold=0.7
        )
        
        # Use Rich to display the tables side by side and the match results
        display_side_by_side_tables(fields, candidates, matches)
        
    except Exception as e:
        logger.exception(f"An error occurred during matching: {e}")
