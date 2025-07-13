"""
Implements the custom editing strategy.
This strategy allows for dynamic segment manipulation based on feature flags,
including reordering and repetition of segments/phrases.
"""

from typing import List, Dict, Any
from .base import EditingStrategy
from app.config import EditingFeatureFlags # Ensure this path is correct
# Import the new Gemini Pass 3 function
from app.gemini import generate_scripted_word_edit 
import logging
# random is not used anymore, can be removed if no other logic needs it.
# import random 

logger = logging.getLogger(__name__)

class CustomEditingStrategy(EditingStrategy):
    """
    An editing strategy that allows for custom manipulation of segments based on feature flags.
    If phrase_level_editing is enabled, it uses Gemini Pass 3 to generate an EDL.
    The 'allow_reordering' flag dictates if Gemini Pass 3 can reorder phrases.
    If phrase_level_editing is disabled, it can perform segment-level repetition.
    """
    def __init__(self, feature_flags: EditingFeatureFlags, strategy_specific_config: Dict[str, Any] = None):
        super().__init__(feature_flags, strategy_specific_config)
        logger.info("Initialized CustomEditingStrategy.")
        logger.info(f"  Enable Phrase-Level Editing: {self.feature_flags.enable_phrase_level_editing}")
        logger.info(f"  Allow Reordering (for phrases if phrase editing enabled): {self.feature_flags.allow_reordering}")
        logger.info(f"  Allow Segment-Level Repetition (fallback if no phrase editing): {self.feature_flags.allow_repetition}")
        if self.feature_flags.allow_repetition:
            logger.info(f"  Max Segment Repetitions (fallback): {self.feature_flags.max_segment_repetitions}")

    def _find_segments_for_repetition( # This is for segment-level repetition fallback
        self, 
        segments: List[Dict[str, Any]], 
        narrative_outline: List[str]
    ) -> List[int]: # Returns list of indices of segments to consider for repetition
        """
        Identifies segments that are good candidates for repetition based on the narrative outline.
        This is a basic implementation that looks for partial matches in segment text.
        Used only if phrase_level_editing is False.
        """
        if not narrative_outline or not segments:
            return []

        candidate_indices = []
        for i, segment in enumerate(segments):
            segment_text_lower = segment.get("text", "").lower()
            if not segment_text_lower:
                continue
            for narrative_point in narrative_outline:
                narrative_point_lower = narrative_point.lower()
                # Basic check: if a significant part of the narrative point is in the segment text
                if narrative_point_lower in segment_text_lower or segment_text_lower in narrative_point_lower:
                    if len(narrative_point_lower) > 10 and len(segment_text_lower) > 10: # Avoid trivial matches
                        logger.debug(f"Segment {i} ('{segment_text_lower[:30]}...') matches narrative point for potential repetition: '{narrative_point_lower[:30]}...'")
                        candidate_indices.append(i)
                        break 
        return list(set(candidate_indices))

    def _process_edl_into_phrases(
        self,
        edl_from_pass_3: List[Dict[str, Any]],
        augmented_segments_lookup: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Helper function to convert an EDL from Gemini Pass 3 into a list of phrase dicts
        with absolute timings and text.
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
            # Ensure 'start' time exists for the coarse segment, default to 0.0 if not (though it should always exist)
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
            # Calculate absolute start and end times for the phrase
            # Word start/end times are relative to the coarse segment's start
            try:
                phrase_absolute_start_time = coarse_segment_absolute_start_time + word_details_list[start_idx]['start']
                phrase_absolute_end_time = coarse_segment_absolute_start_time + word_details_list[end_idx]['end']
            except (TypeError, KeyError) as e:
                logger.error(f"Error accessing word start/end times for EDL item {edl_item_index}, segment '{source_id}', indices {start_idx}-{end_idx}. Word details might be malformed. Error: {e}. Skipping phrase.", exc_info=True)
                continue

            for k in range(start_idx, end_idx + 1):
                phrase_words.append(word_details_list[k].get('word', '')) # Safely get word
            
            final_phrase_text = " ".join(w for w in phrase_words if w) # Join non-empty words
            
            final_phrases_for_cut.append({
                "start": round(phrase_absolute_start_time, 3),
                "end": round(phrase_absolute_end_time, 3),
                "text": final_phrase_text,
                "source_script_info": edl_item, # Keep original EDL item for traceability
                # Store original coarse segment id and word indices for potential sorting later if needed
                "original_coarse_segment_id": source_id, 
                "original_start_word_index": start_idx 
            })
        
        return final_phrases_for_cut

    def process_segments(
        self, 
        segments: List[Dict[str, Any]], 
        narrative_outline: List[str] = None, 
        user_prompt: str = None
    ) -> List[Dict[str, Any]]:
        """
        Processes segments. If phrase_level_editing is enabled, uses Gemini Pass 3.
        Otherwise, falls back to segment-level operations like repetition.
        """
        logger.info(f"CustomEditingStrategy processing {len(segments)} segments.")
        
        # Check if input segments are augmented coarse segments suitable for phrase editing
        # This check relies on the structure set up in main.py when enable_phrase_level_editing is true
        is_input_phrase_editable = (
            self.feature_flags.enable_phrase_level_editing and
            segments and isinstance(segments[0], dict) and
            segments[0].get('id', '').startswith('coarse_seg_') and
            isinstance(segments[0].get('word_level_details'), list)
        )

        if is_input_phrase_editable:
            logger.info("Phrase-level editing is enabled and input segments are suitable. Invoking Gemini Pass 3.")
            
            # Prepare for Pass 3
            current_narrative_outline = narrative_outline if narrative_outline is not None else []
            current_user_prompt = user_prompt if user_prompt is not None else "Create a funny and engaging video."
            # The 'allow_reordering' flag for the Custom strategy directly maps to Gemini's script reordering ability
            allow_gemini_reordering = self.feature_flags.allow_reordering
            logger.info(f"  Gemini Pass 3 will be instructed with allow_reordering_in_script={allow_gemini_reordering}")

            try:
                edl_from_pass_3 = generate_scripted_word_edit(
                    augmented_coarse_segments=segments, 
                    narrative_outline=current_narrative_outline,
                    user_prompt=current_user_prompt,
                    allow_reordering_in_script=allow_gemini_reordering
                )
                logger.info(f"Gemini Pass 3 produced an EDL with {len(edl_from_pass_3)} phrase entries.")

                if edl_from_pass_3:
                    augmented_segments_lookup = {seg['id']: seg for seg in segments if 'id' in seg}
                    processed_segments = self._process_edl_into_phrases(edl_from_pass_3, augmented_segments_lookup)
                    
                    if processed_segments:
                        logger.info(f"Successfully processed EDL into {len(processed_segments)} phrases for video cutting.")
                    else:
                        logger.warning("EDL processing resulted in no valid phrases. No phrases to cut.")
                        # Fallback: if Pass 3 or EDL processing yields nothing, return empty list,
                        # as we can't use the original augmented segments directly for phrase cutting.
                        processed_segments = [] 
                else:
                    logger.warning("Gemini Pass 3 returned an empty EDL. No phrases to cut.")
                    processed_segments = [] 

            except Exception as e_pass3_pipeline:
                logger.error(f"Error during phrase-based editing pipeline (Pass 3 + EDL processing): {e_pass3_pipeline}", exc_info=True)
                logger.warning("No phrases to cut due to error in phrase editing pipeline.")
                processed_segments = []
        
        else: # Phrase-level editing is NOT enabled or input not suitable
            logger.info("Phrase-level editing is NOT active or input segments are not suitable. Considering segment-level operations.")
            processed_segments = list(segments) # Start with the original (non-augmented) segments

            if self.feature_flags.allow_repetition and self.feature_flags.max_segment_repetitions > 1:
                logger.info("Attempting segment-level repetition.")
                if not narrative_outline:
                     logger.info("No narrative outline provided for segment-level repetition, skipping this step.")
                else:
                    segments_to_repeat_indices = self._find_segments_for_repetition(processed_segments, narrative_outline)
                    
                    if segments_to_repeat_indices:
                        # Simple strategy: repeat the first identified candidate segment.
                        # More complex logic could be added here (e.g., repeat multiple, choose randomly, etc.)
                        
                        # Sort by original index to keep some predictability if multiple candidates
                        segments_to_repeat_indices.sort() 
                        chosen_segment_original_index = segments_to_repeat_indices[0] 
                        
                        segment_to_repeat_data = None
                        if 0 <= chosen_segment_original_index < len(processed_segments): # Basic check
                             segment_to_repeat_data = processed_segments[chosen_segment_original_index]
                        
                        if segment_to_repeat_data:
                            segment_text_preview = segment_to_repeat_data.get("text", "")[:50]
                            logger.info(f"Selected segment at original index {chosen_segment_original_index} for repetition: '{segment_text_preview}...' ")
                            
                            insertion_point_in_processed_list = -1
                            for i, seg_data in enumerate(processed_segments):
                                if seg_data.get('start') == segment_to_repeat_data.get('start') and \
                                   seg_data.get('end') == segment_to_repeat_data.get('end') and \
                                   seg_data.get('text') == segment_to_repeat_data.get('text'):
                                    insertion_point_in_processed_list = i + 1
                                    break
                            
                            if insertion_point_in_processed_list != -1:
                                num_repetitions_to_add = self.feature_flags.max_segment_repetitions - 1
                                for _ in range(num_repetitions_to_add):
                                    processed_segments.insert(insertion_point_in_processed_list, dict(segment_to_repeat_data))
                                    insertion_point_in_processed_list += 1 
                                logger.info(f"Repeated segment {num_repetitions_to_add} times.")
                            else:
                                logger.warning(f"Could not reliably find chosen segment (original index {chosen_segment_original_index}) for repetition in the current list. Skipping segment-level repetition.")
                        else:
                            logger.warning(f"Segment data for repetition (original index {chosen_segment_original_index}) not found. Skipping repetition.")
                    else:
                        logger.info("No specific segments identified for segment-level repetition based on narrative outline.")
            else:
                logger.info("Segment-level repetition not enabled or max_repetitions <= 1.")

            if self.feature_flags.allow_reordering:
                logger.warning("CustomEditingStrategy: 'allow_reordering' is True, but phrase-level editing was not active/input not suitable. Segment-level reordering is not implemented in this strategy. Segments will remain in original order.")
        
        logger.info(f"CustomEditingStrategy produced {len(processed_segments)} segments for output.")
        return processed_segments 