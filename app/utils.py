import re
import logging
from typing import List, Tuple, Dict, Any, Optional
from thefuzz import fuzz # Import thefuzz
import sys # Import sys for stdout manipulation
from nltk.tokenize import sent_tokenize
import nltk
import os
import time
import json

# Define logger at the module level, before its first use
logger = logging.getLogger(__name__)

# Ensure nltk 'punkt' tokenizer is available
try:
    nltk.data.find('tokenizers/punkt')
except LookupError: # Changed from nltk.downloader.DownloadError
    logger.info("NLTK 'punkt' tokenizer not found. Attempting to download...")
    try:
        nltk.download('punkt', quiet=True)
        logger.info("NLTK 'punkt' tokenizer downloaded successfully.")
    except Exception as e_download:
        logger.error(f"Failed to download NLTK 'punkt' tokenizer: {e_download}. Sentence tokenization might fail.")

# from fuzzywuzzy import fuzz # Example for a fuzzy matching library

def normalize_text(text: str) -> str:
    """Converts text to lowercase and removes common punctuation for matching."""
    if not text:
        return ""
    text = text.lower()
    # Replace punctuation (and underscores) with a space, but keep apostrophes within words.
    # This regex looks for sequences of characters that are NOT word characters (alphanumeric),
    # NOT whitespace, and NOT an apostrophe. It also explicitly matches underscores.
    # It replaces them with a single space.
    text = re.sub(r"[^\w\s']+|_", " ", text)
    # Replace multiple spaces with a single space and strip leading/trailing spaces.
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

def match_quotes_to_timestamps(
    pass1_quotes: List[str],
    transcript_segments: List[Dict[str, Any]]
) -> List[Tuple[float, float]]:
    """
    Matches verbatim quotes from Pass 1 output to segments in the full transcript
    to retrieve their original start and end timestamps.
    """
    edl: List[Tuple[float, float]] = []

    if not pass1_quotes:
        logger.warning("match_quotes_to_timestamps: No Pass 1 quotes provided.")
        return edl
    if not transcript_segments:
        logger.warning("match_quotes_to_timestamps: No transcript segments provided.")
        return edl

    searchable_segments = []
    for i, seg in enumerate(transcript_segments):
        text = seg.get('text')
        start_time = seg.get('start')
        end_time = seg.get('end')
        if text is not None and start_time is not None and end_time is not None:
            searchable_segments.append({
                'id': i,
                'norm_text': normalize_text(text),
                'start': start_time,
                'end': end_time,
                'original_text': text,
                # 'used': False # Removed 'used' flag
            })
        else:
            logger.warning(f"Skipping transcript segment due to missing data: {str(seg)[:100]}")

    matched_count = 0
    total_quotes_to_process = len([q for q in pass1_quotes if q and q.strip()]) # Count non-empty quotes
    processed_quotes_count = 0

    for i, p1_quote_raw in enumerate(pass1_quotes):
        if not p1_quote_raw or not p1_quote_raw.strip():
            # logger.debug(f"Skipping empty or whitespace-only Pass 1 quote at index {i}") # Already debug, or can be removed if progress covers it
            continue
        
        processed_quotes_count +=1
        # Update progress on the same line
        progress_message = f"Matching Pass 1 quotes to transcript: {processed_quotes_count}/{total_quotes_to_process}... \r"
        sys.stdout.write(progress_message)
        sys.stdout.flush()

        norm_p1_quote = normalize_text(p1_quote_raw)
        if not norm_p1_quote:
            logger.debug(f"Skipping Pass 1 quote at index {i} as it became empty after normalization: '{p1_quote_raw}'")
            continue

        best_match_info = None # (score, start, end, segment_id, match_type_debug)

        for seg_info in searchable_segments:
            # Strategy 1: Exact match of normalized texts
            if norm_p1_quote == seg_info['norm_text']:
                logger.debug(f"P1 Quote '{norm_p1_quote[:50]}...' EXACT match with T-Seg '{seg_info['norm_text'][:50]}...'")
                # Exact match is highest priority, so we can potentially break early
                # if we are sure no other segment can offer a *better* exact match (which is true, as segments are unique)
                best_match_info = (1.0, seg_info['start'], seg_info['end'], seg_info['id'], "exact")
                break # Perfect match for this p1_quote

            current_best_score = best_match_info[0] if best_match_info else 0.0

            # Strategy 2: Normalized P1 quote is contained within normalized transcript segment
            if norm_p1_quote in seg_info['norm_text']:
                score_s2 = 0.9 # Score for P1 quote found in transcript segment
                if score_s2 > current_best_score:
                    logger.debug(f"P1 Quote '{norm_p1_quote[:50]}...' CONTAINED in T-Seg '{seg_info['norm_text'][:50]}...' (Score: {score_s2})")
                    best_match_info = (score_s2, seg_info['start'], seg_info['end'], seg_info['id'], "p1_in_transcript")
                    current_best_score = score_s2
                    # Don't break, an exact match in a later segment is still possible and preferred.
            
            # Strategy 3: Normalized transcript segment is contained within normalized P1 quote
            # This can happen if Pass 1 concatenated multiple small transcript lines into one Pass 1 quote
            if seg_info['norm_text'] and seg_info['norm_text'] in norm_p1_quote: # Added check for non-empty seg_info['norm_text']
                SHORT_SEGMENT_WORD_THRESHOLD = 4 # Define threshold for short segments
                
                score_s3 = 0.85 # Default score for transcript segment in P1 quote
                if len(seg_info['norm_text'].split()) < SHORT_SEGMENT_WORD_THRESHOLD:
                    score_s3 = 0.70 # Reduced score for very short transcript segments
                
                if score_s3 > current_best_score:
                    logger.debug(f"T-Seg '{seg_info['norm_text'][:50]}...' (len: {len(seg_info['norm_text'].split())} words) CONTAINED in P1 Quote '{norm_p1_quote[:50]}...' (Score: {score_s3})")
                    best_match_info = (score_s3, seg_info['start'], seg_info['end'], seg_info['id'], "transcript_in_p1")
                    current_best_score = score_s3

            # Strategy 4: Fuzzy matching using token_set_ratio
            FUZZY_SCORE_THRESHOLD = 80 # Minimum raw fuzzy score to consider
            
            # Check if both strings are non-empty before fuzzy matching
            if norm_p1_quote and seg_info['norm_text']:
                fuzzy_score_raw = fuzz.token_set_ratio(norm_p1_quote, seg_info['norm_text'])
                if fuzzy_score_raw >= FUZZY_SCORE_THRESHOLD:
                    # Scale: raw 80 -> 0.65; raw 100 -> 0.65 + 0.199 = 0.849
                    score_s4 = 0.65 + (fuzzy_score_raw - FUZZY_SCORE_THRESHOLD) / (100.0 - FUZZY_SCORE_THRESHOLD) * 0.199
                    if score_s4 > current_best_score:
                        logger.debug(f"P1 Quote '{norm_p1_quote[:50]}...' FUZZY match (raw: {fuzzy_score_raw}/100 -> effective: {score_s4:.3f}) with T-Seg '{seg_info['norm_text'][:50]}...'")
                        best_match_info = (score_s4, seg_info['start'], seg_info['end'], seg_info['id'], f"fuzzy_{fuzzy_score_raw}")
                        current_best_score = score_s4

        if best_match_info:
            _score, start_time, end_time, matched_segment_id, match_type = best_match_info

            # --- Greedy extension: include following transcript segments that are still part of the same quote ---
            # The searchable_segments list is in original transcript order (id ascending).
            MAX_PAUSE_BETWEEN_SEGMENTS = 2.0  # seconds – treat longer gaps as a new moment
            next_idx = matched_segment_id + 1
            while next_idx < len(searchable_segments):
                next_seg = searchable_segments[next_idx]
                next_text = next_seg.get('norm_text', '')

                # Stop if there is a long temporal gap – we don't want to include silence/background.
                if next_seg['start'] - end_time > MAX_PAUSE_BETWEEN_SEGMENTS:
                    break

                # Include the segment if its text continues the quote.
                if next_text and next_text in norm_p1_quote:
                    end_time = next_seg['end']
                    next_idx += 1
                    continue
                break

            edl.append((start_time, end_time))
            # Mark the transcript segment as used so it cannot be matched again by another P1 quote.
            # This logic has been removed to allow segments to be matched multiple times.
            # for seg_info_mut in searchable_segments:
            #     if seg_info_mut['id'] == matched_segment_id:
            #         seg_info_mut['used'] = True
            #         break
            matched_count += 1
            # Changed from logger.info to logger.debug for less verbose output on successful match
            logger.debug(f"Matched P1 quote (idx {i}): '{norm_p1_quote[:50]}...' to transcript segment (idx {matched_segment_id}, type: {match_type}, score: {_score:.3f}) -> EDL: ({start_time}, {end_time})")
        else:
            logger.warning(f"Could not find a suitable match for P1 quote (idx {i}): '{norm_p1_quote[:100]}...' (Original: '{p1_quote_raw[:100]}...')")

    sys.stdout.write("\n") # Ensure the next log appears on a new line
    sys.stdout.flush()
    logger.info(f"match_quotes_to_timestamps: Matched {matched_count} out of {total_quotes_to_process} non-empty Pass 1 quotes to transcript segments.")
    return edl

# --- NEW UTILITY FUNCTION for Pass 2 Text to Candidate Transcript Timestamps ---
def match_text_segments_to_transcript_timestamps(
    selected_text_segments: List[str], 
    candidate_transcript_segments: List[Dict[str, Any]], # Expects list of {'start': float, 'end': float, 'text': str}
    similarity_threshold: int = 80 # Threshold for matching text segments
) -> List[Dict[str, Any]]:
    """
    Matches selected text segments (from Multimodal Pass 2) to a candidate video's transcript
    to derive an Edit Decision List (EDL) with timestamps.

    Args:
        selected_text_segments: A list of verbatim text strings selected by Pass 2.
        candidate_transcript_segments: The full transcript of the candidate video, where each
                                       segment is a dict with 'start', 'end', and 'text'.
        similarity_threshold: Minimum similarity score (0-100) to consider a match.

    Returns:
        A list of dictionaries, forming an EDL. Each dict has 'start' and 'end' keys
        representing the timestamps from the candidate video transcript.
        Order is preserved from selected_text_segments.
    """
    final_edl = []
    
    if not selected_text_segments:
        logger.warning("match_text_segments_to_transcript_timestamps: selected_text_segments list is empty. Returning empty EDL.")
        return []
    if not candidate_transcript_segments:
        logger.warning("match_text_segments_to_transcript_timestamps: candidate_transcript_segments list is empty. Returning empty EDL.")
        return []

    # Normalize all candidate transcript texts once for efficiency
    normalized_candidate_segments = [
        {**seg, 'normalized_text': normalize_text(seg.get('text', ''))} 
        for seg in candidate_transcript_segments
    ]
    
    # To prevent using the exact same candidate transcript segment for multiple *different* selected texts,
    # if selected texts are very similar or subsets.
    # This is a simple approach; more sophisticated handling might be needed if multiple unique selected texts
    # genuinely map to the same short candidate segment. For now, unique matches are preferred.
    used_candidate_indices = set()

    num_selected = len(selected_text_segments)
    logger.info(f"Attempting to match {num_selected} selected text segments (from Pass 2) against {len(candidate_transcript_segments)} candidate transcript segments.")

    for i, p2_text in enumerate(selected_text_segments):
        normalized_p2_text = normalize_text(p2_text)
        if not normalized_p2_text:
            logger.debug(f"Skipping empty normalized P2 text from original: '{p2_text[:50]}...' ")
            continue

        best_match_info_p2 = None
        highest_score_p2 = 0
        
        # Dynamic progress logging
        if (i + 1) % 5 == 0 or (i + 1) == num_selected:
             print(f"\rMatching P2 text progress: Segment {i+1}/{num_selected}... ", end="")

        for cand_idx, cand_seg in enumerate(normalized_candidate_segments):
            if cand_idx in used_candidate_indices: # Try to find a unique match first
                 continue

            candidate_text_to_match = cand_seg['normalized_text']
            if not candidate_text_to_match:
                continue

            # Using token_set_ratio as it's good for phrase matching and some reordering/subset handling.
            score = fuzz.token_set_ratio(normalized_p2_text, candidate_text_to_match)

            # If P2 text is a direct substring of candidate segment, that's a strong indicator
            if len(normalized_p2_text) <= len(candidate_text_to_match) and normalized_p2_text in candidate_text_to_match:
                score = 100 # Prioritize direct containment
                logger.debug(f"Direct substring match for P2 text: '{normalized_p2_text[:30]}...' in Candidate TS '{candidate_text_to_match[:50]}...'. Score set to 100.")

            if score > highest_score_p2:
                highest_score_p2 = score
                best_match_info_p2 = {
                    "start": cand_seg["start"],
                    "end": cand_seg["end"],
                    "matched_candidate_text_original": cand_seg["text"],
                    "normalized_p2_text": normalized_p2_text,
                    "normalized_candidate_text": candidate_text_to_match,
                    "score": score,
                    "original_p2_text": p2_text,
                    "candidate_segment_index": cand_idx
                }
            
            if highest_score_p2 == 100: # Confident match
                break
        
        # If no unique match found above threshold, retry allowing reuse of candidate segments
        if not best_match_info_p2 or best_match_info_p2["score"] < similarity_threshold:
            logger.debug(f"Initial pass for P2 text '{normalized_p2_text[:30]}...' didn't find a unique match >= threshold {similarity_threshold}. Best was {highest_score_p2}. Retrying with reuse allowed.")
            highest_score_p2_retry = 0 # Reset for retry
            best_match_info_p2_retry = None

            for cand_idx_retry, cand_seg_retry in enumerate(normalized_candidate_segments):
                # No 'used_candidate_indices' check here
                candidate_text_to_match_retry = cand_seg_retry['normalized_text']
                if not candidate_text_to_match_retry:
                    continue
                
                score_retry = fuzz.token_set_ratio(normalized_p2_text, candidate_text_to_match_retry)
                if len(normalized_p2_text) <= len(candidate_text_to_match_retry) and normalized_p2_text in candidate_text_to_match_retry:
                    score_retry = 100
                
                if score_retry > highest_score_p2_retry:
                    highest_score_p2_retry = score_retry
                    best_match_info_p2_retry = {
                        "start": cand_seg_retry["start"],
                        "end": cand_seg_retry["end"],
                        "matched_candidate_text_original": cand_seg_retry["text"],
                        "normalized_p2_text": normalized_p2_text,
                        "normalized_candidate_text": candidate_text_to_match_retry,
                        "score": score_retry,
                        "original_p2_text": p2_text,
                        "candidate_segment_index": cand_idx_retry 
                    }
                if highest_score_p2_retry == 100:
                    break
            
            # Use the retry result if it's better or if the initial pass had no good match
            if best_match_info_p2_retry and (not best_match_info_p2 or best_match_info_p2_retry["score"] > best_match_info_p2.get("score",0)):
                 if best_match_info_p2_retry["score"] >= similarity_threshold:
                    best_match_info_p2 = best_match_info_p2_retry # Replace with retry if it's good enough
                    logger.debug(f"Retry with reuse found a match for P2 text '{normalized_p2_text[:30]}...' with score {best_match_info_p2['score']}.")


        if best_match_info_p2 and best_match_info_p2["score"] >= similarity_threshold:
            final_edl.append({
                "start": best_match_info_p2["start"],
                "end": best_match_info_p2["end"],
                # "text": best_match_info_p2["original_p2_text"], # Pass 2 text for reference if needed
                # "matched_score": best_match_info_p2["score"],
                # "source_candidate_segment_text": best_match_info_p2["matched_candidate_text_original"]
            })
            # Only add to used_candidate_indices if we are confident and want to enforce uniqueness
            # And if the match was from the first pass (prefer unique matches)
            # This logic needs to be careful: if best_match_info_p2 came from retry, cand_idx might be from original loop.
            # Let's use the index from the actual best_match_info_p2
            used_candidate_indices.add(best_match_info_p2["candidate_segment_index"])

            logger.debug(
                f"Matched P2 Text: '{best_match_info_p2['original_p2_text'][:50]}...' \n"
                f"  Normalized P2: '{best_match_info_p2['normalized_p2_text'][:50]}...' \n"
                f"  To Candidate Seg Idx: {best_match_info_p2['candidate_segment_index']}, Score: {best_match_info_p2['score']} \n"
                f"  Normalized Candidate TS: '{best_match_info_p2['normalized_candidate_text'][:70]}...' \n"
                f"  Timestamp: {best_match_info_p2['start']:.2f}s - {best_match_info_p2['end']:.2f}s"
            )
        else:
            logger.warning(
                f"No good match found for P2 text segment (best score < {similarity_threshold}): "
                f"'{p2_text[:100]}...' (Normalized: '{normalized_p2_text[:100]}...'). "
                f"Best score was {best_match_info_p2['score'] if best_match_info_p2 else 'N/A'}."
            )

    print() # Newline after progress indicator
    logger.info(f"Finished matching Pass 2 text. Generated final EDL with {len(final_edl)} segments from {num_selected} selected text segments.")
    if num_selected > 0 and len(final_edl) / num_selected < 0.5: # Check match rate
        logger.warning(f"Low match rate for Pass 2 text: Only {len(final_edl)}/{num_selected} selected texts were matched to candidate transcript.")
    
    return final_edl

def generate_unique_filename(base_name: str, extension: str, directory: str = ".", add_timestamp: bool = True) -> str:
    """
    Generates a unique filename by appending a timestamp (optional) and a counter.
    Example: myvideo_20231027_153000.mp4, or myvideo_20231027_153000_1.mp4 if the first exists.
    If add_timestamp is False, it will be like: myvideo.mp4, or myvideo_1.mp4.
    """
    if not extension.startswith('.'):
        extension = '.' + extension

    name_part = base_name
    if add_timestamp:
        ts = time.strftime("%Y%m%d_%H%M%S")
        name_part = f"{base_name}_{ts}"
    else:
        name_part = base_name # Use base_name directly if no timestamp

    # Ensure the directory exists
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            # logger.info(f"Created directory for unique filename: {directory}") # Assuming logger is available
        except Exception as e:
            # logger.error(f"Could not create directory {directory} for unique filename: {e}")
            # Fallback to current directory if creation fails
            pass # Let os.path.join handle it, might write to current dir or raise OS error later

    filename = os.path.join(directory, f"{name_part}{extension}")
    
    # Check if the initial filename (with or without timestamp) exists
    if not os.path.exists(filename):
        return filename

    # If it exists, start adding a counter
    counter = 1
    while True:
        # The unique part with counter is always appended after the (potentially timestamped) name_part
        unique_filename = os.path.join(directory, f"{name_part}_{counter}{extension}")
        if not os.path.exists(unique_filename):
            return unique_filename
        counter += 1

def save_json_to_file(data: Any, file_path: str, indent: int = 2) -> bool:
    """Saves Python data (dict, list, etc.) to a JSON file."""
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            # logger.info(f"Created directory for JSON file: {directory}")

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        # logger.info(f"Successfully saved JSON data to: {file_path}")
        return True
    except IOError as e:
        # logger.error(f"IOError saving JSON to {file_path}: {e}", exc_info=True)
        return False
    except TypeError as e:
        # logger.error(f"TypeError (data not serializable) saving JSON to {file_path}: {e}", exc_info=True)
        return False
    except Exception as e:
        # logger.error(f"Unexpected error saving JSON to {file_path}: {e}", exc_info=True)
        return False

def load_json_from_file(file_path: str) -> Optional[Any]:
    """Loads Python data (dict, list, etc.) from a JSON file."""
    if not os.path.exists(file_path):
        # logger.warning(f"JSON file not found for loading: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # logger.info(f"Successfully loaded JSON data from: {file_path}")
        return data
    except json.JSONDecodeError as e:
        # logger.error(f"JSONDecodeError loading from {file_path}: {e}", exc_info=True)
        return None
    except IOError as e:
        # logger.error(f"IOError loading JSON from {file_path}: {e}", exc_info=True)
        return None
    except Exception as e:
        # logger.error(f"Unexpected error loading JSON from {file_path}: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    print("Testing app/utils.py - match_quotes_to_timestamps")

    sample_pass1_quotes = [
        "Hello world this is a test",
        "Another interesting segment, perhaps.",
        "This one might not match.",
        "gonna test this one!!", # Added punctuation
        "short one",
        "  leading and trailing spaces quote  ",
        "it's a good day, isn't it?"
    ]

    sample_transcript_segments = [
        {"text": "This is the first segment.", "start": 0.0, "end": 2.0},
        {"text": "Hello world, this is a test! And some more.", "start": 2.5, "end": 5.0},
        {"text": "An uninterested segment, perhaps, with different phrasing.", "start": 5.5, "end": 8.0},
        {"text": "Then we are GONNA TEST THIS ONE extensively.", "start": 8.5, "end": 11.0}, # Different case
        {"text": "A very short one here.", "start": 11.5, "end": 12.5},
        {"text": "Segment with extra words around a core idea, like a leading and trailing spaces quote for example.", "start": 13.0, "end": 18.0},
        {"text": "This is a segment that should not match anything.", "start": 18.5, "end": 20.0},
        {"text": None, "start": 20.5, "end": 21.0},
        {"text": "Valid text", "start": None, "end": 22.0},
        {"text": "It's a good day, isn_t it?", "start": 22.5, "end": 25.0} # Underscore and apostrophe variation
    ]

    logging.basicConfig(level=logging.DEBUG) # To see debug logs from the function
    logger.info("--- Running Test with improved normalize_text ---")

    edl_result = match_quotes_to_timestamps(sample_pass1_quotes, sample_transcript_segments)

    print("\n--- EDL Result ---")
    if edl_result:
        print(f"Generated EDL (length {len(edl_result)}): {edl_result}")
        # Simple mapping for test output - assumes edl_result corresponds sequentially to quotes that DID match
        matched_p1_indices = []
        temp_searchable = [normalize_text(s.get('text','')) for s in sample_transcript_segments if s.get('text')]       
        
        current_edl_item = 0
        for i, p1_q in enumerate(sample_pass1_quotes):
            norm_p1_q = normalize_text(p1_q)
            if not norm_p1_q: continue
            # This test print logic is tricky because of the 'used' flag and match ordering.
            # It's easier to just print the EDL and rely on the function's internal logging for detailed matches.
        
    else:
        print("No matches found or EDL is empty.")

    print("\n--- Testing with empty inputs ---")
    edl_empty_quotes = match_quotes_to_timestamps([], sample_transcript_segments)
    print(f"EDL from empty quotes: {edl_empty_quotes}")
    edl_empty_segments = match_quotes_to_timestamps(sample_pass1_quotes, [])
    print(f"EDL from empty segments: {edl_empty_segments}")
    edl_both_empty = match_quotes_to_timestamps([], [])
    print(f"EDL from both empty: {edl_both_empty}")

    print("\n--- Test with repeated quotes matching same segment ---")
    repeated_quotes = [
        "Hello world this is a test",
        "Hello world this is a test"
    ]
    # Create a fresh list of searchable segments for this specific test to avoid state from previous calls
    fresh_repeated_transcript_segments = [{
        'id': 0,
        'norm_text': normalize_text(sample_transcript_segments[1]['text']),
        'start': sample_transcript_segments[1]['start'],
        'end': sample_transcript_segments[1]['end'],
        'original_text': sample_transcript_segments[1]['text'],
        # 'used': False # Removed 'used' flag
    }]
    # The match_quotes_to_timestamps function creates its own 'searchable_segments' internally,
    # so passing sample_transcript_segments[1] is correct. The 'used' flag is internal to one call.
    edl_repeated = match_quotes_to_timestamps(repeated_quotes, [sample_transcript_segments[1]])
    print(f"EDL from repeated quotes (current 'used' logic): {edl_repeated}")
    # Expected: only one match because the transcript segment is marked 'used' after the first match within a single call. 
    # With 'used' flag removed, both quotes should now match and appear in the EDL. 

    # Basic test for match_text_segments_to_transcript_timestamps
    mock_p2_selected_texts = [
        "This is a segment from candidate video, part one.",
        "Another selected part, perhaps slightly modified.",
        "This one is very different and should not match well.",
        "exact match segment"
    ]
    mock_candidate_transcript = [
        {"start": 0.5, "end": 2.8, "text": "This is a segment from candidate video, part one. It has some extra words."},
        {"start": 3.0, "end": 5.2, "text": "Another selected part, perhaps slightly modified text from the candidate video."},
        {"start": 5.5, "end": 7.0, "text": "Completely different content in candidate transcript."},
        {"start": 7.1, "end": 8.0, "text": "exact match segment"}
    ]
    print("\n--- Testing match_text_segments_to_transcript_timestamps ---")
    edl_result_p2 = match_text_segments_to_transcript_timestamps(mock_p2_selected_texts, mock_candidate_transcript, similarity_threshold=75)
    print("Pass 2 (Text to Candidate Transcript) EDL Result:")
    for item in edl_result_p2:
        print(item)
    
    # Test with empty P2 selected texts
    print("\n--- Testing match_text_segments_to_transcript_timestamps (empty P2 selected) ---")
    edl_empty_p2 = match_text_segments_to_transcript_timestamps([], mock_candidate_transcript)
    print(f"EDL for empty P2 selected texts: {edl_empty_p2}")

    # Test with empty candidate transcript
    print("\n--- Testing match_text_segments_to_transcript_timestamps (empty candidate transcript) ---")
    edl_empty_cand = match_text_segments_to_transcript_timestamps(mock_p2_selected_texts, [])
    print(f"EDL for empty candidate transcript: {edl_empty_cand}")

    # Test for near identical segments in P2 selected text to see if `used_candidate_indices` works as intended
    mock_p2_selected_texts_duplicates = [
        "This is a specific phrase.",
        "This is a specific phrase.", # Identical
        "This is a specific phrase, slightly longer."
    ]
    mock_candidate_transcript_single_source = [
        {"start": 0.0, "end": 2.0, "text": "Here is the text containing: This is a specific phrase."},
        {"start": 2.1, "end": 4.0, "text": "Another segment entirely."},
        {"start": 4.1, "end": 6.0, "text": "This is a specific phrase, slightly longer and also here."}
    ]
    print("\n--- Testing match_text_segments_to_transcript_timestamps (duplicate P2 texts, limited sources) ---")
    edl_duplicates_result = match_text_segments_to_transcript_timestamps(
        mock_p2_selected_texts_duplicates, 
        mock_candidate_transcript_single_source,
        similarity_threshold=85 # Higher threshold
    )
    print("Pass 2 (Duplicate P2 texts) EDL Result:")
    for item in edl_duplicates_result:
        print(item) 