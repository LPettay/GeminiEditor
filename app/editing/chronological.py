"""
Implements the chronological editing strategy.
Segments are processed to maintain their original chronological order.
If phrase-level editing is enabled, it can extract phrases but will keep them ordered.
"""

from typing import List, Dict, Any
from .base import EditingStrategy
from app.config import EditingFeatureFlags
from app.gemini import generate_scripted_word_edit
import logging

logger = logging.getLogger(__name__)

class ChronologicalEditingStrategy(EditingStrategy):
    """
    An editing strategy that processes segments while maintaining their original chronological order.
    If phrase-level editing is enabled, it uses Gemini Pass 3 to extract phrases,
    but ensures these phrases are then sorted chronologically before output.
    """
    def __init__(self, feature_flags: EditingFeatureFlags, strategy_specific_config: Dict[str, Any] = None):
        super().__init__(feature_flags, strategy_specific_config)
        logger.info("Initialized ChronologicalEditingStrategy.")
        logger.info(f"  Enable Phrase-Level Editing: {self.feature_flags.enable_phrase_level_editing}")
        # allow_reordering and allow_repetition flags are not directly used by Chronological strategy
        # for its primary logic, but they are part of the feature_flags object.

    def _process_edl_into_phrases(
        self,
        edl_from_pass_3: List[Dict[str, Any]],
        augmented_segments_lookup: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Helper function to convert an EDL from Gemini Pass 3 into a list of phrase dicts
        with absolute timings and text. This is similar to the one in CustomEditingStrategy.
        Adds 'original_coarse_segment_id' and 'original_start_word_index' for stable sorting if needed,
        though primary sorting will be by absolute start time.
        """
        final_phrases_for_cut = []
        if not edl_from_pass_3:
            return final_phrases_for_cut

        for edl_item_index, edl_item in enumerate(edl_from_pass_3):
            source_id = edl_item.get('source_segment_id')
            start_idx = edl_item.get('start_word_index')
            end_idx = edl_item.get('end_word_index')
            source_coarse_segment = augmented_segments_lookup.get(source_id)

            if source_coarse_segment is None or not isinstance(source_coarse_segment.get('word_level_details'), list):
                logger.warning(f"EDL item {edl_item_index} references unknown source_segment_id '{source_id}' or segment lacks word details. Skipping: {edl_item}")
                continue
            
            word_details_list = source_coarse_segment['word_level_details']
            coarse_segment_absolute_start_time = source_coarse_segment.get('start', 0.0)

            if not (
                isinstance(start_idx, int) and 0 <= start_idx < len(word_details_list) and \
                isinstance(end_idx, int) and 0 <= end_idx < len(word_details_list) and \
                start_idx <= end_idx
            ):
                logger.warning(
                    f"EDL item {edl_item_index} has invalid word indices for segment '{source_id}' (available words: {len(word_details_list)}). "
                    f"EDL item: {edl_item}. Skipping."
                )
                continue
            
            phrase_words = []
            try:
                phrase_absolute_start_time = coarse_segment_absolute_start_time + word_details_list[start_idx]['start']
                phrase_absolute_end_time = coarse_segment_absolute_start_time + word_details_list[end_idx]['end']
            except (TypeError, KeyError, IndexError) as e:
                logger.error(f"Error accessing word start/end times for EDL item {edl_item_index}, segment '{source_id}', indices {start_idx}-{end_idx}. Word details might be malformed or indices out of bounds. Error: {e}. Skipping phrase.", exc_info=True)
                continue

            for k in range(start_idx, end_idx + 1):
                try:
                    phrase_words.append(word_details_list[k].get('word', ''))
                except IndexError:
                    logger.error(f"IndexError accessing word at index {k} for segment '{source_id}' (EDL item {edl_item_index}). Word list length: {len(word_details_list)}. Skipping rest of this phrase's words.")
                    break # Stop processing words for this phrase if an index is out of bounds
            
            final_phrase_text = " ".join(w for w in phrase_words if w)
            
            final_phrases_for_cut.append({
                "start": round(phrase_absolute_start_time, 3),
                "end": round(phrase_absolute_end_time, 3),
                "text": final_phrase_text,
                "source_script_info": edl_item, 
                "original_coarse_segment_id": source_id,
                "original_start_word_index": start_idx,
                 # Storing original segment's start time and word start time for a multi-level stable sort if absolutely needed
                "_sort_key_coarse_start": coarse_segment_absolute_start_time,
                "_sort_key_word_start_relative": word_details_list[start_idx]['start' ] if start_idx < len(word_details_list) and 'start' in word_details_list[start_idx] else float('inf')
            })
        
        return final_phrases_for_cut

    def process_segments(
        self, 
        segments: List[Dict[str, Any]], 
        narrative_outline: List[str] = None, 
        user_prompt: str = None
    ) -> List[Dict[str, Any]]:
        logger.info(f"ChronologicalEditingStrategy processing {len(segments)} segments.")

        is_input_phrase_editable = (
            self.feature_flags.enable_phrase_level_editing and
            segments and isinstance(segments[0], dict) and
            segments[0].get('id', '').startswith('coarse_seg_') and
            isinstance(segments[0].get('word_level_details'), list)
        )

        if is_input_phrase_editable:
            logger.info("Phrase-level editing is enabled for Chronological style. Invoking Gemini Pass 3 with no reordering.")
            
            current_narrative_outline = narrative_outline if narrative_outline is not None else []
            current_user_prompt = user_prompt if user_prompt is not None else "Create an engaging video by extracting key phrases chronologically."
            
            try:
                edl_from_pass_3 = generate_scripted_word_edit(
                    augmented_coarse_segments=segments, 
                    narrative_outline=current_narrative_outline,
                    user_prompt=current_user_prompt,
                    allow_reordering_in_script=False # CRITICAL for chronological strategy
                )
                logger.info(f"Gemini Pass 3 (chronological) produced an EDL with {len(edl_from_pass_3)} phrase entries.")

                if edl_from_pass_3:
                    augmented_segments_lookup = {seg['id']: seg for seg in segments if 'id' in seg}
                    processed_phrases = self._process_edl_into_phrases(edl_from_pass_3, augmented_segments_lookup)
                    
                    if processed_phrases:
                        # CRITICAL: Sort phrases by their absolute start time to ensure chronological order
                        # This also implicitly handles order from original coarse segments if multiple phrases come from one.
                        processed_phrases.sort(key=lambda p: p.get('start', float('inf')))
                        logger.info(f"Successfully processed EDL into {len(processed_phrases)} phrases, sorted chronologically.")
                        return processed_phrases
                    else:
                        logger.warning("EDL processing resulted in no valid phrases. Returning empty list.")
                        return [] 
                else:
                    logger.warning("Gemini Pass 3 returned an empty EDL. Returning empty list of phrases.")
                    return [] 

            except Exception as e_pass3_pipeline:
                logger.error(f"Error during phrase-based editing pipeline for Chronological style: {e_pass3_pipeline}", exc_info=True)
                logger.warning("Returning empty list of phrases due to error.")
                return []
        
        else: # Phrase-level editing is NOT enabled or input not suitable
            logger.info("Phrase-level editing is NOT active or input not suitable for Chronological style. Returning segments as is.")
            # For chronological, if not doing phrase editing, we just return the segments as they are.
            # The base class or calling function ensures they are already chronologically ordered if they came from transcription.
            return list(segments) # Return a copy 