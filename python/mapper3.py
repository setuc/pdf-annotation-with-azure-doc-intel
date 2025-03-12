import json
import os
import re
import difflib
import numpy as np
from scipy.optimize import linear_sum_assignment
from typing import List, Tuple, Dict, Optional
import logging
import time

# Advanced NLP similarity imports
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Optional: For stopword removal & stemming
try:
    from nltk.corpus import stopwords
    from nltk.stem import PorterStemmer
except ImportError:
    stopwords = None
    PorterStemmer = None

# Global variable for SentenceTransformer model.
st_model = None

# Rich imports for logging and visualization
from rich import print
from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn

# ------------------------------------------------------------------------------
# Custom JSON Encoder to handle NumPy types
# ------------------------------------------------------------------------------
class NumpyEncoder(json.JSONEncoder):
    """
    Custom encoder to convert NumPy data types (e.g. float32, bool) to native Python types.
    """
    def default(self, obj):
        if isinstance(obj, (np.float16, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, (np.int_, np.int16, np.int32, np.int64)):
            return int(obj)
        if isinstance(obj, (np.bool_)):
            return bool(obj)
        return super().default(obj)

def save_matches_to_json(matches: Dict[str, dict], output_path: str) -> None:
    """
    Save the final matches to a JSON file, converting NumPy types to native Python types.
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(matches, f, indent=2, cls=NumpyEncoder)
        console.print(f"[bold green]Saved matches to {output_path}[/bold green]")
    except Exception as e:
        logger.exception(f"Error saving matches to {output_path}: {e}")

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
console = Console()

# ------------------------------------------------------------------------------
# 0. Helper: Composite Field Text
# ------------------------------------------------------------------------------
def composite_field_text(field_key: str, field_value: str) -> str:
    """
    Create a composite text using the field key and field value.
    This gives more context to the matching process.
    """
    return f"{field_key} {field_value}"

# ------------------------------------------------------------------------------
# 1. Data Normalization and Preprocessing
# ------------------------------------------------------------------------------
def preprocess_text(text: str) -> str:
    """
    Normalize text by lowercasing, trimming, removing punctuation,
    normalizing numeric symbols, and optionally removing stopwords and stemming.
    """
    try:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"[\$,]", "", text)
        text = text.replace("%", "")
        words = text.split()
        if stopwords and PorterStemmer and len(words) > 3:
            sw = set(stopwords.words('english'))
            ps = PorterStemmer()
            words = [ps.stem(word) for word in words if word not in sw]
            text = " ".join(words)
        return text
    except Exception as e:
        logger.exception(f"Error in preprocessing text: {e}")
        return text

def compute_similarity_matrix(
    field_texts: List[str],
    candidate_texts: List[str],
    similarity_method: str = "hybrid",
    weight_char: float = 0.5,
    weight_other: float = 0.5
) -> np.ndarray:
    """
    Compute a similarity matrix of shape (len(field_texts), len(candidate_texts)).
    For methods "sentence_transformers" and "hybrid", embeddings are computed in batch.
    For "tfidf", a vectorizer is fit on the concatenated list.
    For "difflib", we fall back to nested loops.
    In "hybrid" mode, the final similarity is:
        weight_char * difflib_similarity + weight_other * st_similarity
    """
    n = len(field_texts)
    m = len(candidate_texts)
    sim_matrix = np.zeros((n, m), dtype=np.float32)
    
    if similarity_method in ["sentence_transformers", "hybrid"]:
        global st_model
        if st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                st_model = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L6-v2")
            except Exception as e:
                logger.exception("Error loading SentenceTransformer model; falling back to difflib.")
                similarity_method = "difflib"
        if similarity_method in ["sentence_transformers", "hybrid"]:
            embeddings_fields = st_model.encode(
                [preprocess_text(txt) for txt in field_texts],
                convert_to_tensor=False, show_progress_bar=False
            )
            embeddings_candidates = st_model.encode(
                [preprocess_text(txt) for txt in candidate_texts],
                convert_to_tensor=False, show_progress_bar=False
            )
            embeddings_fields = np.array(embeddings_fields)
            embeddings_candidates = np.array(embeddings_candidates)
            norm_fields = embeddings_fields / np.linalg.norm(embeddings_fields, axis=1, keepdims=True)
            norm_cands = embeddings_candidates / np.linalg.norm(embeddings_candidates, axis=1, keepdims=True)
            st_sim_matrix = np.dot(norm_fields, norm_cands.T)
            if similarity_method == "sentence_transformers":
                sim_matrix = st_sim_matrix.astype(np.float32)
            else:
                difflib_matrix = np.zeros((n, m), dtype=np.float32)
                for i, f_txt in enumerate(field_texts):
                    pf = preprocess_text(f_txt)
                    for j, c_txt in enumerate(candidate_texts):
                        difflib_matrix[i, j] = difflib.SequenceMatcher(None, pf, preprocess_text(c_txt)).ratio()
                sim_matrix = weight_char * difflib_matrix + weight_other * st_sim_matrix
    elif similarity_method == "tfidf":
        try:
            all_texts = field_texts + candidate_texts
            vectorizer = TfidfVectorizer()
            tfidf_all = vectorizer.fit_transform(all_texts)
            tfidf_fields = tfidf_all[:n]
            tfidf_cands = tfidf_all[n:]
            tfidf_sim_matrix = cosine_similarity(tfidf_fields, tfidf_cands)
            difflib_matrix = np.zeros((n, m), dtype=np.float32)
            for i, f_txt in enumerate(field_texts):
                pf = preprocess_text(f_txt)
                for j, c_txt in enumerate(candidate_texts):
                    difflib_matrix[i, j] = difflib.SequenceMatcher(None, pf, preprocess_text(c_txt)).ratio()
            sim_matrix = weight_char * difflib_matrix + weight_other * tfidf_sim_matrix
        except Exception as e:
            logger.exception("TF-IDF batch processing failed; falling back to difflib.")
            similarity_method = "difflib"
    if similarity_method == "difflib":
        for i, f_txt in enumerate(field_texts):
            pf = preprocess_text(f_txt)
            for j, c_txt in enumerate(candidate_texts):
                sim_matrix[i, j] = difflib.SequenceMatcher(None, pf, preprocess_text(c_txt)).ratio()
    return sim_matrix

def compute_similarity(
    text1: str,
    text2: str,
    similarity_method: str = "hybrid",
    weight_char: float = 0.5,
    weight_other: float = 0.5
) -> float:
    """
    Compute similarity between two texts by calling compute_similarity_matrix on a single pair.
    """
    return compute_similarity_matrix([text1], [text2], similarity_method, weight_char, weight_other)[0, 0]

def adjust_similarity_for_domain(field_key: str, sim: float) -> float:
    """
    Adjust similarity based on domain knowledge (car loan applications).
    You might boost candidates from certain sources or roles.
    """
    domain_weights = {
         "finance": 1.2,
         "vehicle": 1.1,
         "insurance": 1.1,
         "buyer": 1.0,
         "seller": 1.0,
         "phone": 1.2,
         "email": 1.2,
         "date": 1.1,
         "first_payment_due": 1.1,
    }
    max_weight = 1.0
    for key, weight in domain_weights.items():
        if key in field_key.lower():
            max_weight = max(max_weight, weight)
    return min(sim * max_weight, 1.0)

# ------------------------------------------------------------------------------
# 2. Utilities to Load and Flatten JSON
# ------------------------------------------------------------------------------
def load_json(file_path: str) -> dict:
    try:
        logger.debug(f"Loading JSON from: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug(f"Loaded JSON keys: {list(data.keys())}")
        return data
    except Exception as e:
        logger.exception(f"Error loading JSON from {file_path}: {e}")
        raise

def flatten_json(nested_json: dict, parent_key: str = "", sep: str = ".") -> dict:
    items = []
    for k, v in nested_json.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, str(v) if v is not None else ""))
    flat = dict(items)
    logger.debug(f"Flattened JSON contains {len(flat)} fields.")
    return flat

# ------------------------------------------------------------------------------
# 3. Extract Fields from JSON-1 *Without* Hardcoding
# ------------------------------------------------------------------------------
def extract_fields_from_json1(json1: dict, max_fields: Optional[int] = 20) -> List[Tuple[str, str]]:
    flattened = flatten_json(json1)
    non_empty = {k: v for k, v in flattened.items() if v.strip()}
    keys = list(non_empty.keys())
    if max_fields is not None:
        keys = keys[:max_fields]
    fields = [(k, non_empty[k]) for k in keys]
    logger.debug(f"Extracted {len(fields)} non-empty field(s) from JSON-1.")
    return fields

# ------------------------------------------------------------------------------
# 3.5 Parse Document Intelligence JSON
# ------------------------------------------------------------------------------
def parse_doc_intelligence_json(doc_json: dict) -> dict:
    """
    Parse the top-level structure of the Document Intelligence JSON.
    Typically, the relevant data is stored under the key 'analyzeResult'.
    """
    return doc_json.get("analyzeResult", {})

# ------------------------------------------------------------------------------
# 4. Extract Candidates from Document Intelligence JSON (all sources)
# ------------------------------------------------------------------------------
def extract_all_candidates(analyze_result: dict) -> List[Tuple[str, str, dict]]:
    """
    Extract candidate text from various parts of the Document Intelligence JSON.
    This includes 'tables', 'paragraphs', 'sections', 'figures', and 'documents'.
    Metadata now includes the source type and additional attributes.
    """
    candidates = []
    candidate_sources = ["tables", "paragraphs", "sections", "figures", "documents"]
    
    for source in candidate_sources:
        items = analyze_result.get(source, [])
        if source == "tables":
            for table in items:
                for cell in table.get("cells", []):
                    text = cell.get("content", "").strip()
                    if text:
                        candidate_id = f"{source}_cand_{len(candidates)}"
                        metadata = {"source": source, "role": cell.get("kind", None)}
                        candidates.append((candidate_id, text, metadata))
        else:
            for item in items:
                text = item.get("content", "").strip()
                if text:
                    candidate_id = f"{source}_cand_{len(candidates)}"
                    metadata = {
                        "source": source,
                        "role": item.get("role", None),
                        "boundingRegions": item.get("boundingRegions", None)
                    }
                    candidates.append((candidate_id, text, metadata))
    logger.debug(f"Extracted {len(candidates)} candidate(s) from Document Intelligence across all sources.")
    return candidates

# ------------------------------------------------------------------------------
# 5. Matching Algorithms
# ------------------------------------------------------------------------------
def hungarian_matching(
    fields: List[Tuple[str, str]], 
    candidates: List[Tuple[str, str, dict]], 
    threshold: float = 0.7,
    similarity_method: str = "hybrid",
    weight_char: float = 0.5,
    weight_other: float = 0.5,
    dynamic_threshold: bool = False,
    dynamic_offset: float = 0.1
) -> Dict[str, dict]:
    # Use composite field texts to incorporate field key context.
    field_texts = [composite_field_text(k, v) for (k, v) in fields]
    candidate_texts = [txt for (_, txt, _) in candidates]
    
    sim_matrix = compute_similarity_matrix(field_texts, candidate_texts, similarity_method, weight_char, weight_other)
    for i, (f_key, _) in enumerate(fields):
        for j in range(sim_matrix.shape[1]):
            sim_matrix[i, j] = adjust_similarity_for_domain(f_key, sim_matrix[i, j])
    
    avg_sim = float(np.mean(sim_matrix))
    logger.debug(f"Average similarity across matrix: {avg_sim:.2f}")
    
    cost_matrix = 1.0 - sim_matrix
    logger.debug("Solving assignment problem using linear_sum_assignment...")
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    assigned_sims = [sim_matrix[i, j] for i, j in zip(row_ind, col_ind)]
    if dynamic_threshold and assigned_sims:
        mean_sim = np.mean(assigned_sims)
        std_sim = np.std(assigned_sims)
        threshold = mean_sim - dynamic_offset * std_sim
        logger.debug(f"Dynamic threshold set to: {threshold:.2f} (mean: {mean_sim:.2f}, std: {std_sim:.2f})")
    
    matches = {}
    for i, j in zip(row_ind, col_ind):
        sim = sim_matrix[i, j]
        review = sim < threshold
        f_key = fields[i][0]
        f_value = fields[i][1]
        matches[f_key] = {
            "field_value": f_value,
            "candidate_id": candidates[j][0],
            "candidate_text": candidates[j][1],
            "similarity": sim,
            "human_review": review,
            "metadata": candidates[j][2]
        }
    logger.debug(f"Hungarian matching produced {len(matches)} match(es).")
    return matches

def greedy_matching(
    fields: List[Tuple[str, str]], 
    candidates: List[Tuple[str, str, dict]], 
    threshold: float = 0.7,
    similarity_method: str = "hybrid",
    weight_char: float = 0.5,
    weight_other: float = 0.5,
    dynamic_threshold: bool = False,
    dynamic_offset: float = 0.1
) -> Dict[str, dict]:
    field_texts = [composite_field_text(k, v) for (k, v) in fields]
    candidate_texts = [txt for (_, txt, _) in candidates]
    
    sim_matrix = compute_similarity_matrix(field_texts, candidate_texts, similarity_method, weight_char, weight_other)
    for i, (f_key, _) in enumerate(fields):
        for j in range(sim_matrix.shape[1]):
            sim_matrix[i, j] = adjust_similarity_for_domain(f_key, sim_matrix[i, j])
    
    best_similarities = []
    temp_matches = {}
    for i, (f_key, f_val) in enumerate(fields):
        j_best = np.argmax(sim_matrix[i, :])
        best_sim = sim_matrix[i, j_best]
        best_similarities.append(best_sim)
        temp_matches[f_key] = {
            "field_value": f_val,
            "candidate_id": candidates[j_best][0],
            "candidate_text": candidates[j_best][1],
            "similarity": best_sim,
            "human_review": False,
            "metadata": candidates[j_best][2]
        }
    if dynamic_threshold and best_similarities:
        mean_sim = np.mean(best_similarities)
        std_sim = np.std(best_similarities)
        threshold = mean_sim - dynamic_offset * std_sim
        logger.debug(f"Dynamic threshold set to: {threshold:.2f} (mean: {mean_sim:.2f}, std: {std_sim:.2f})")
    
    matches = {}
    for key, match in temp_matches.items():
        match["human_review"] = match["similarity"] < threshold
        matches[key] = match
    logger.debug(f"Greedy matching produced {len(matches)} match(es).")
    return matches

def gale_shapley_matching(
    fields: List[Tuple[str, str]], 
    candidates: List[Tuple[str, str, dict]],
    **kwargs
) -> Dict[str, dict]:
    logger.debug("Gale-Shapley matching is not implemented; falling back to greedy matching.")
    return greedy_matching(fields, candidates, **kwargs)

# ------------------------------------------------------------------------------
# 6. High-Level Function to Do It All Dynamically (with user feedback)
# ------------------------------------------------------------------------------
def match_jsons_dynamic(
    json1_path: str,
    json2_path: str,
    max_fields: Optional[int] = 20,
    algorithm: str = "greedy",  # "hungarian", "greedy", "gale_shapley"
    threshold: float = 0.7,
    similarity_method: str = "hybrid",  # Options: "difflib", "tfidf", "sentence_transformers", "hybrid"
    weight_char: float = 0.5,
    weight_other: float = 0.5,
    dynamic_threshold: bool = False,
    dynamic_offset: float = 0.1
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, dict]], Dict[str, dict]]:
    start_time = time.time()
    logger.debug("Starting dynamic matching... (Pass 1)")
    
    with console.status("[bold green]Matching fields... (Pass 1)[/bold green]", spinner="dots"):
        try:
            structured_data = load_json(json1_path)
            doc_intelligence_data = load_json(json2_path)
        except Exception as e:
            logger.exception("Error loading JSON files.")
            raise
        
        fields = extract_fields_from_json1(structured_data, max_fields=max_fields)
        analyze_result = parse_doc_intelligence_json(doc_intelligence_data)
        candidates = extract_all_candidates(analyze_result)
        
        if algorithm == "hungarian":
            matches = hungarian_matching(fields, candidates, threshold, similarity_method, weight_char, weight_other, dynamic_threshold, dynamic_offset)
        elif algorithm == "greedy":
            matches = greedy_matching(fields, candidates, threshold, similarity_method, weight_char, weight_other, dynamic_threshold, dynamic_offset)
        elif algorithm == "gale_shapley":
            matches = gale_shapley_matching(fields, candidates, threshold=threshold, similarity_method=similarity_method,
                                            weight_char=weight_char, weight_other=weight_other, dynamic_threshold=dynamic_threshold, dynamic_offset=dynamic_offset)
        else:
            raise ValueError(f"Unknown matching algorithm: {algorithm}")
    
    elapsed = time.time() - start_time
    logger.debug(f"Dynamic matching completed in {elapsed:.2f} seconds.")
    console.print(f"[bold yellow]First pass completed.[/bold yellow] Found [bold]{len(matches)}[/bold] matches.")
    flagged = sum(1 for m in matches.values() if m["human_review"])
    console.print(f"[blue]Number requiring review:[/blue] [bold red]{flagged}[/bold red].")
    
    # Warn if any match is extremely low or if a field with digits gets a candidate without digits
    def contains_digit(text: str) -> bool:
        return any(ch.isdigit() for ch in text)
    
    for k, m in matches.items():
        if m["similarity"] < 0.2:
            logger.warning(f"Field '{k}' has extremely low similarity ({m['similarity']:.2f}). Possibly missing in Document Intelligence or GPT JSON.")
        # If the field value has digits but candidate text does not, warn the user.
        if contains_digit(m["field_value"]) and not contains_digit(m["candidate_text"]):
            logger.warning(f"Field '{k}' appears to be numeric but the candidate text '{m['candidate_text']}' may be missing numeric information.")
    
    console.print("[bold green]Finalizing results...[/bold green]")
    return fields, candidates, matches

# ------------------------------------------------------------------------------
# 7. Human-in-the-Loop and Feedback (Refinement for Human Review)
# ------------------------------------------------------------------------------
def refine_human_review_matches(
    matches: Dict[str, dict],
    fields: List[Tuple[str, str]],
    candidates: List[Tuple[str, str, dict]],
    threshold: float = 0.7,
    similarity_method: str = "hybrid",
    weight_char: float = 0.5,
    weight_other: float = 0.5
) -> Dict[str, dict]:
    """
    For matches requiring human review, attempt to re-rank or refine by
    exploring additional candidate context. For example, for name, phone, email, or date fields,
    the composite query (field key + field value) is used to search candidates in richer sources.
    """
    refined = matches.copy()
    # Build an index of candidates by source type.
    source_index = {}
    for cid, text, meta in candidates:
        source = meta.get("source", "unknown")
        source_index.setdefault(source, []).append((cid, text, meta))
    
    console.print("[bold yellow]Starting second pass refinement...[/bold yellow]")
    best_improvements = 0
    
    for field_key, match in matches.items():
        if match["human_review"]:
            composite_query = composite_field_text(field_key, match["field_value"])
            if any(x in field_key.lower() for x in ["name", "phone", "email", "date", "first_payment_due"]):
                best_sim = match["similarity"]
                best_candidate = match
                for source in ["paragraphs", "sections"]:
                    for cid, text, meta in source_index.get(source, []):
                        sim = compute_similarity(composite_query, text, similarity_method, weight_char, weight_other)
                        sim = adjust_similarity_for_domain(field_key, sim)
                        if sim > best_sim:
                            best_sim = sim
                            best_candidate = {
                                "field_value": match["field_value"],
                                "candidate_id": cid,
                                "candidate_text": text,
                                "similarity": sim,
                                "human_review": sim < threshold,
                                "metadata": meta
                            }
                if best_candidate != match:
                    best_improvements += 1
                refined[field_key] = best_candidate
    console.print(f"[bold yellow]Second pass completed. Found {best_improvements} improved matches.[/bold yellow]")
    return refined

# ------------------------------------------------------------------------------
# 7.5 Multi-Pass Approach
# ------------------------------------------------------------------------------
def multi_pass_dynamic_matching(
    json1_path: str,
    json2_path: str,
    max_fields: Optional[int] = 20,
    algorithm: str = "greedy",
    threshold: float = 0.7,
    similarity_method: str = "hybrid",
    weight_char: float = 0.5,
    weight_other: float = 0.5,
    dynamic_threshold: bool = False,
    dynamic_offset: float = 0.1
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, dict]], Dict[str, dict]]:
    # First pass
    fields, candidates, matches = match_jsons_dynamic(
        json1_path=json1_path,
        json2_path=json2_path,
        max_fields=max_fields,
        algorithm=algorithm,
        threshold=threshold,
        similarity_method=similarity_method,
        weight_char=weight_char,
        weight_other=weight_other,
        dynamic_threshold=dynamic_threshold,
        dynamic_offset=dynamic_offset
    )
    # Second pass refinement with a slightly looser threshold
    refined = refine_human_review_matches(
        matches,
        fields,
        candidates,
        threshold=threshold - 0.05,
        similarity_method=similarity_method,
        weight_char=weight_char,
        weight_other=weight_other
    )
    return fields, candidates, refined

# ------------------------------------------------------------------------------
# 8. Visualization Helpers using Rich Tables
# ------------------------------------------------------------------------------
def display_side_by_side_tables(fields: List[Tuple[str, str]], 
                                candidates: List[Tuple[str, str, dict]], 
                                matches: Dict[str, dict]):
    console = Console()
    
    table_fields = Table(title="Extracted Fields (JSON-1)", style="cyan")
    table_fields.add_column("Field Key", style="magenta", no_wrap=True)
    table_fields.add_column("Field Value", style="green")
    for key, value in fields:
        table_fields.add_row(key, value)
    
    table_candidates = Table(title="Extracted Candidates (JSON-2)", style="cyan")
    table_candidates.add_column("Candidate ID", style="magenta", no_wrap=True)
    table_candidates.add_column("Candidate Text", style="green")
    for cand in candidates:
        candidate_id, candidate_text, _ = cand
        table_candidates.add_row(candidate_id, candidate_text)
    
    console.print(Columns([table_fields, table_candidates]))
    
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

def display_match_review_tables(matches: Dict[str, dict]) -> None:
    console = Console()
    flagged = {k: v for k, v in matches.items() if v["human_review"]}
    accepted = {k: v for k, v in matches.items() if not v["human_review"]}
    
    if flagged:
        flagged_table = Table(title="Matches Requiring Human Review", style="red")
        flagged_table.add_column("Field Key", style="magenta", no_wrap=True)
        flagged_table.add_column("Field Value", style="green")
        flagged_table.add_column("Candidate ID", style="yellow")
        flagged_table.add_column("Candidate Text", style="green")
        flagged_table.add_column("Similarity", style="blue")
        for key, info in flagged.items():
            flagged_table.add_row(
                key,
                info["field_value"],
                info["candidate_id"],
                info["candidate_text"],
                f"{info['similarity']:.2f}"
            )
        console.print(flagged_table)
    else:
        console.print("[green]No matches require human review.[/green]")
    
    if accepted:
        accepted_table = Table(title="Accepted Matches", style="green")
        accepted_table.add_column("Field Key", style="magenta", no_wrap=True)
        accepted_table.add_column("Field Value", style="green")
        accepted_table.add_column("Candidate ID", style="yellow")
        accepted_table.add_column("Candidate Text", style="green")
        accepted_table.add_column("Similarity", style="blue")
        for key, info in accepted.items():
            accepted_table.add_row(
                key,
                info["field_value"],
                info["candidate_id"],
                info["candidate_text"],
                f"{info['similarity']:.2f}"
            )
        console.print(accepted_table)
    else:
        console.print("[red]No accepted matches.[/red]")

# ------------------------------------------------------------------------------
# 9. Example Main Usage
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    json1_file = os.path.join(os.getcwd(), "../examples/Connecticut.gpt.json")
    json2_file = os.path.join(os.getcwd(), "../examples/Connecticut.layout.json")
    
    try:
        # Multi-pass matching with feedback and spinner.
        fields, candidates, matches_refined = multi_pass_dynamic_matching(
            json1_path=json1_file,
            json2_path=json2_file,
            max_fields=None,
            algorithm="hungarian",
            threshold=0.7,
            similarity_method="hybrid",
            weight_char=0.5,
            weight_other=0.5,
            dynamic_threshold=True,
            dynamic_offset=0.1
        )
        
        display_side_by_side_tables(fields, candidates, matches_refined)
        display_match_review_tables(matches_refined)
        
        # Save final matches to JSON output
        output_file = os.path.join(os.getcwd(), "matched_results.json")
        save_matches_to_json(matches_refined, output_file)
        
        # Output metrics
        total_matches = len(matches_refined)
        flagged_count = sum(1 for m in matches_refined.values() if m["human_review"])
        console.print(f"[bold blue]Total Matches:[/bold blue] {total_matches}")
        console.print(f"[bold blue]Matches Requiring Review:[/bold blue] {flagged_count}")
        
        # Additional note: If a field seems numeric but the candidate text does not contain digits,
        # warn the user that Document Intelligence may have missed the value.
        def contains_digit(text: str) -> bool:
            return any(ch.isdigit() for ch in text)
        
        for k, m in matches_refined.items():
            if contains_digit(m["field_value"]) and not contains_digit(m["candidate_text"]):
                console.print(f"[bold red]Warning:[/bold red] Field '{k}' appears numeric ('{m['field_value']}') but candidate text '{m['candidate_text']}' lacks digits. Check if the value is missing in the Document Intelligence or GPT JSON.")
        
    except Exception as e:
        logger.exception(f"An error occurred during matching: {e}")
