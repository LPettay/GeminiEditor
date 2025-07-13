import sys
import time

# ---- TOP LEVEL GOOGLE DIAGNOSTIC with print ----
print("--- [DIAG PRINT] Top-Level Google Package Diagnostics (in app/gemini.py) ---", flush=True)
try:
    import google
    print(f"--- [DIAG PRINT] Successfully imported top-level 'google' module.", flush=True)
    print(f"--- [DIAG PRINT] google.__path__: {google.__path__}", flush=True)
    if hasattr(google, '__file__'):
        print(f"--- [DIAG PRINT] google.__file__: {google.__file__}", flush=True)
    else:
        print("--- [DIAG PRINT] top-level 'google' module does not have a __file__ attribute.", flush=True)
except ImportError:
    print("--- [DIAG PRINT] FAILED to import top-level 'google' module. This is a major issue.", flush=True)
except Exception as e:
    print(f"--- [DIAG PRINT] Error inspecting top-level 'google' module: {e}", flush=True)
print("--- [DIAG PRINT] End Top-Level Google Package Diagnostics ---", flush=True)
# ---- END TOP LEVEL GOOGLE DIAGNOSTIC with print ----

from pydantic import BaseModel, Field # Field was imported but not used, removing
import os
import logging
import json

# Import necessary types for safety settings
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Setup logger for this module
logger = logging.getLogger(__name__)

# Load API key from environment variable ONCE when module is loaded
GEMINI_API_KEY_MODULE_LEVEL = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY_MODULE_LEVEL:
    logger.error("GEMINI_API_KEY environment variable not set at module load. Function calls will fail.")

# Pydantic model for the data WE SEND to Gemini (already cleaned in main.py)
# This class `InputSegment` is not directly used in the Gemini functions themselves for request/response schema.
# It's more of a conceptual model for the segment structure.
# class InputSegment(BaseModel):
# start: float
# end: float
# text: str

class VerbatimScriptPass1Input(BaseModel):
    full_transcript_text: str  # One transcript segment per line.
    user_prompt_for_video_theme: str
    allow_reordering: bool
    video_context: str | None = None  # e.g. "Dark Souls 1 livestream, Undead Parish, Bell Gargoyles boss"

# Pydantic model for what we EXPECT Gemini TO RETURN in Pass 2 (list of these)
# Revert to start-only marker to conserve tokens; end can be looked up from transcript
class SelectedSegmentMarker(BaseModel):
    start: float  # Unique start time of the segment to keep

# --- Pass 1: Generate Narrative Outline ---
def generate_narrative_outline(transcript_text: str, user_prompt: str) -> list[str]:
    """
    Pass 1: Analyzes the full transcript text to generate a narrative outline.
    Returns a list of strings, where each string is a narrative point.
    """
    try:
        import google.generativeai as local_genai
        # (Optional: Add diagnostics for local_genai as in the original process_with_gemini if needed)
        
        if not GEMINI_API_KEY_MODULE_LEVEL:
            logger.error("GEMINI_API_KEY not available for Pass 1 (Narrative Outline).")
            raise RuntimeError("GEMINI_API_KEY environment variable not set.")
        
        local_genai.configure(api_key=GEMINI_API_KEY_MODULE_LEVEL)
        logger.info("Pass 1 (Narrative Outline): Gemini API key configured.")

    except ImportError:
        logger.error("Pass 1 (Narrative Outline): Failed to import google.generativeai.")
        raise RuntimeError("Critical: google.generativeai library not found for Pass 1 (Narrative Outline).")
    except Exception as e_conf:
        logger.error(f"Pass 1 (Narrative Outline): Failed to configure Gemini API key: {e_conf}")
        raise RuntimeError(f"Pass 1 (Narrative Outline): Failed to configure Gemini API key: {e_conf}")

    SYSTEM_PROMPT_PASS_1 = f"""You are an expert comedic storyteller and video editor's assistant, specializing in identifying hilarious and engaging content in the style of top online entertainers like Jerma985, BedBanana, Habie147, Charborg, and General Sam.
Your goal is to analyze a full transcript and generate a "comedy blueprint" or "narrative outline" that will guide the creation of a fast-paced, funny, and personality-driven highlights video.
The user's specific instructions for this video (which might override or refine the general comedic style) are: {json.dumps(user_prompt)}.

Your main task: From the entire transcript, identify a sequence of 5 to 15 key comedic beats, narrative arcs (even short ones), personality-defining moments, absurd situations, or running gags that align with the user's prompt and would make for a highly entertaining video.
Think about:
-   Setups and punchlines for jokes; ensure both parts are noted if they form a single comedic idea.
-   Moments of genuine surprise, contagious laughter, or strong (funny) emotion from the speaker.
-   Absurd or out-of-context statements that are funny on their own or build a comedic theme.
-   Instances that uniquely showcase the speaker's personality, humor style (e.g., dry wit, sarcasm, slapstick), or quirks.
-   Running gags or recurring themes that build comedic value across the transcript.
-   Brief, engaging mini-stories or anecdotes with a clear beginning, middle, and (comedic) end.
-   Moments of clever wordplay or witty observations.

IMPORTANT:
-   Your output MUST be a JSON list of strings. Each string should be a concise description of a narrative point or comedic moment (e.g., "Speaker attempts X, fails hilariously," "Running joke about the rubber chicken begins," "Unexpected NPC reaction causes speaker to lose it," "Sarcastic comment about game difficulty and its immediate ironic payoff").
-   Do NOT refer to specific timestamps. Focus purely on the *content and narrative flow* of these comedic/engaging moments.
-   The points should ideally form a sequence that tells a small story or has a good comedic rhythm.
-   If the user prompt is very specific (e.g., "focus only on fails"), ensure your points directly reflect it. If it's more general (like the default funny/engaging prompt), use your expertise on comedic editing based on the inspirational creators.

Example Output:
`["Initial confusion about the game\\'s objective leads to a funny misinterpretation", "First attempt at task X results in an absurd chain reaction failure", "Speaker makes a self-deprecating joke about their lack of skill", "Unexpectedly, a bizarre game glitch occurs, leading to uncontrollable laughter and an out-of-context quote", "Running gag: the \'cursed\' item makes another ill-fated appearance", "A brief, witty observation about a nonsensical game character design", "Final attempt at task X, almost succeeds but for a comically timed distraction leading to a new, even funnier failure"]`

Your entire response MUST be ONLY this JSON list of strings, with no other text or explanations.
"""
    
    prompt_for_model_pass_1 = f"""Full Transcript Text:
{transcript_text}

---
User Prompt for desired video:
{json.dumps(user_prompt)} # Ensured user_prompt is also safely embedded here

---
Based on the SYSTEM PROMPT, the User Prompt, and the Full Transcript Text provided, generate the JSON list of narrative points.
Output ONLY the JSON list of strings and nothing else."""

    logger.info(f"Pass 1 (Narrative Outline): Sending request to Gemini. User prompt: '{user_prompt}'. Transcript length: {len(transcript_text)} chars.")
    
    try:
        model_identifier = 'models/gemini-2.5-pro-exp-03-25' 
        logger.info(f"Pass 1 (Narrative Outline): Using Gemini model: {model_identifier}")
        model = local_genai.GenerativeModel(model_identifier)
        
        generation_config_dict = {
            "response_mime_type": "application/json",
        }

        response = model.generate_content(
            contents=[SYSTEM_PROMPT_PASS_1, prompt_for_model_pass_1],
            generation_config=generation_config_dict
        )

        if not response.text: # Original handling for narrative outline, as it wasn't showing the 'no candidates' error
            logger.warning("Pass 1 (Narrative Outline) Gemini returned empty response text. Returning empty narrative outline.")
            # Log additional details if available, even if text is empty
            try:
                if response.prompt_feedback:
                    logger.warning(f"Pass 1 (Narrative Outline) Prompt Feedback (empty text): {response.prompt_feedback}")
                if response.candidates:
                    logger.warning(f"Pass 1 (Narrative Outline) Candidates (empty text): {response.candidates}")
                    for i, candidate in enumerate(response.candidates):
                        logger.warning(f"Pass 1 (Narrative Outline) Candidate {i} (empty text) Finish Reason: {candidate.finish_reason}")
                        if candidate.safety_ratings:
                            logger.warning(f"Pass 1 (Narrative Outline) Candidate {i} (empty text) Safety Ratings: {candidate.safety_ratings}")
            except Exception as e_log_narrative:
                logger.error(f"Pass 1 (Narrative Outline) Error during detailed logging of empty response: {e_log_narrative}")
            return []
        
        try:
            narrative_points_data = json.loads(response.text)
            if not (isinstance(narrative_points_data, list) and \
               all(isinstance(item, str) for item in narrative_points_data)):
                logger.error(f"Pass 1 (Narrative Outline) Gemini response not a list of strings as expected. Data: {str(narrative_points_data)[:500]}")
                logger.error(f"Full problematic Pass 1 (Narrative Outline) Gemini response text: '{response.text}'")
                return [] 
            logger.info(f"Pass 1 (Narrative Outline) Gemini returned {len(narrative_points_data)} narrative points.")
            return narrative_points_data
        except json.JSONDecodeError as json_e:
            logger.error(f"Pass 1 (Narrative Outline) Failed to decode JSON from Gemini: {json_e}.")
            logger.error(f"Problematic Pass 1 (Narrative Outline) Gemini response text: '{response.text[:5000]}'")
            raise RuntimeError("Pass 1 (Narrative Outline) Gemini returned malformed JSON for narrative outline.")

    except AttributeError as ae_model: 
        logger.error(f"Pass 1 (Narrative Outline) AttributeError: {ae_model}", exc_info=True)
        raise RuntimeError(f"Pass 1 (Narrative Outline) Gemini model instantiation or method call failed: {ae_model}")
    except Exception as e:
        logger.error(f"Pass 1 (Narrative Outline) Gemini API call failed: {e}", exc_info=True)
        raise RuntimeError(f"Pass 1 (Narrative Outline) Gemini content generation failed: {e}")

# --- New Pass 1: Generate Verbatim Script ---
def generate_verbatim_script_pass1(input_data: VerbatimScriptPass1Input) -> str:
    """
    New Pass 1: Extracts verbatim text segments from the transcript based on the user's prompt
    to form a script-like output.
    Returns a single string with newlines separating segments/dialogue.
    """
    try:
        import google.generativeai as local_genai
        
        if not GEMINI_API_KEY_MODULE_LEVEL:
            logger.error("GEMINI_API_KEY not available for New Pass 1.")
            raise RuntimeError("GEMINI_API_KEY environment variable not set.")
        
        local_genai.configure(api_key=GEMINI_API_KEY_MODULE_LEVEL)
        logger.info("New Pass 1: Gemini API key configured.")

    except ImportError:
        logger.error("New Pass 1: Failed to import google.generativeai.")
        raise RuntimeError("Critical: google.generativeai library not found for New Pass 1.")
    except Exception as e_conf:
        logger.error(f"New Pass 1: Failed to configure Gemini API key: {e_conf}")
        raise RuntimeError(f"New Pass 1: Failed to configure Gemini API key: {e_conf}")

    # Destructure input for clarity in prompts
    transcript_text = input_data.full_transcript_text
    user_prompt = input_data.user_prompt_for_video_theme
    allow_reordering_flag = input_data.allow_reordering
    video_context = (input_data.video_context or "").strip()

    context_block = f"\nVideo Context:\n{video_context}\n" if video_context else ""

    SYSTEM_PROMPT_NEW_PASS_1 = f"""You are an AI assistant acting as the first-pass candidate selector in a multi-stage video editing pipeline.
Your goal is to broadly identify and extract ALL POTENTIALLY relevant verbatim segments from a video transcript that could be used in a final video.
A subsequent, more sophisticated multimodal AI pass will review these candidates alongside the video footage to make final selections and refinements.

{context_block}

Your main task for THIS pass:
Based on the user's prompt for the video's theme, and the full transcript provided, you must select and extract ALL DIRECT QUOTES (verbatim text) that MIGHT be suitable.
Err on the side of inclusion. If a segment has any potential to be funny, showcase personality, or align with the user's theme, include it.

IMPORTANT formatting rule:
Each line in the **Full Transcript** you receive is already a logical utterance separated by a noticeable pause in the video. **Do NOT merge two separate transcript lines into one output line.** Keep the same boundaries: one input line → at most one output line.

User-Provided Information (will be in the user message / next part of the prompt):
1.  **Full Transcript:** This will contain the text, possibly with speaker labels like "Speaker A: Hello world." or without specific speaker labels.
2.  **User Prompt for Video Theme:** This specifies the kind of video to create (e.g., "a summary of the main arguments," "a funny out-of-context video," "all segments where the speaker discusses topic X," "showcase streamer's humor and personality").
3.  **Allow Reordering Flag:** A boolean ({str(allow_reordering_flag).lower()}) indicates if you are allowed to change the original order of the transcript segments.
    - If `allow_reordering` is `true` (as it is {str(allow_reordering_flag).lower()} here), you can pick segments from different parts of the transcript and arrange them in a new order that best fits the user's prompt.
    - If `allow_reordering` is `false`, you must select segments in the order they appear in the original transcript. You can still OMIT segments, but you cannot change the relative order of the selected segments.

Instructions for Candidate Extraction:
-   Your output MUST be a single string.
-   Each extracted quote or segment must be on its own line.
-   If speaker labels were present in the input transcript for a selected segment, PRESERVE those speaker labels in your output (e.g., "Speaker A: [text]"). If no speaker labels, just output the text.
-   The selected quotes MUST be EXACTLY as they appear in the original transcript. Do not summarize, paraphrase, or add your own words.
-   **Broad Candidate Selection Focus:**
    -   **Narrative / Gameplay Context:** Pick segments that help a viewer understand what is happening in-game (progress, objectives, setbacks).
    -   **Humor & Personality:** Retain genuinely funny or characterful moments **when** they make sense given the surrounding gameplay.
    -   **Theme Alignment:** Ensure chosen lines support the user’s requested vibe or theme.
-   **Inclusivity Over Conciseness (for this pass):** While segments should be coherent, do not be overly aggressive in trimming them down at this stage. If a slightly longer segment contains a good candidate moment, include the surrounding context that makes it understandable. The next pass will handle fine-grained trimming.
-   **No Need for Perfect Narrative Yet:** While logical flow is good if `allow_reordering` is true, the primary goal is comprehensive candidate gathering. The next pass will focus more on narrative construction.

Your entire response MUST be ONLY the script-like text, with newlines separating segments/dialogue. No other explanations, headings, or introductory text.
"""
    
    prompt_for_model_new_pass_1 = f"""Full Transcript Text:
{transcript_text}

---
User Prompt for desired video theme:
{json.dumps(user_prompt)}

---
Allow Reordering of transcript segments: {str(allow_reordering_flag).lower()}
---
Based on the SYSTEM PROMPT, the User Prompt, the Allow Reordering flag, and the Full Transcript Text provided, generate the script-like text.
Output ONLY the text with newlines and nothing else."""

    logger.info(f"New Pass 1: Sending request to Gemini. User prompt: '{user_prompt}'. Reorder: {allow_reordering_flag}. Transcript length: {len(transcript_text)} chars.")
    
    try:
        model_identifier = 'gemini-2.5-flash' 
        logger.info(f"New Pass 1: Using Gemini model: {model_identifier}")
        model = local_genai.GenerativeModel(model_identifier)
        
        generation_config_dict = {
            "response_mime_type": "text/plain", 
        }

        response = model.generate_content(
            contents=[SYSTEM_PROMPT_NEW_PASS_1, prompt_for_model_new_pass_1],
            generation_config=generation_config_dict
        )

        # --- Safer response handling for New Pass 1 ---
        if not response.candidates:
            logger.warning("New Pass 1 Gemini returned no candidates. This usually indicates a safety block or other issue with the input.")
            try:
                if response.prompt_feedback:
                    logger.warning(f"New Pass 1 Prompt Feedback (no candidates): {response.prompt_feedback}")
                else:
                    logger.warning("New Pass 1 Prompt Feedback (no candidates): Not available.")
            except Exception as e_log_feedback:
                logger.error(f"New Pass 1 Error during detailed logging of no-candidate response: {e_log_feedback}")
            return "" 

        if not response.text:
            logger.warning("New Pass 1 Gemini returned empty response text (but candidates existed).")
            try:
                if response.prompt_feedback:
                    logger.warning(f"New Pass 1 Prompt Feedback (empty text): {response.prompt_feedback}")
                else:
                    logger.warning("New Pass 1 Prompt Feedback (empty text): Not available.")
                
                if response.candidates: 
                    logger.warning(f"New Pass 1 Candidates (empty text): {response.candidates}")
                    for i, candidate in enumerate(response.candidates):
                        logger.warning(f"New Pass 1 Candidate {i} (empty text) Finish Reason: {candidate.finish_reason}")
                        if candidate.safety_ratings:
                            logger.warning(f"New Pass 1 Candidate {i} (empty text) Safety Ratings: {candidate.safety_ratings}")
                        else:
                            logger.warning(f"New Pass 1 Candidate {i} (empty text) Safety Ratings: Not available or empty.")
                else: # Should ideally not be reached if the first `if not response.candidates:` was effective
                    logger.warning("New Pass 1 Candidates list was unexpectedly empty here (after non-empty check).")
            except Exception as e_log:
                logger.error(f"New Pass 1 Error during detailed logging of empty response text: {e_log}")
            return "" 
        
        logger.info(f"New Pass 1 Gemini returned script of length {len(response.text)} chars.")
        return response.text

    except AttributeError as ae_model: 
        logger.error(f"New Pass 1 AttributeError when trying to use local_genai.GenerativeModel or related: {ae_model}", exc_info=True)
        raise RuntimeError(f"New Pass 1 Gemini model instantiation or method call failed: {ae_model}")
    except Exception as e:
        logger.error(f"New Pass 1 Gemini API call failed: {e}", exc_info=True)
        # The original traceback showed the error occurring when accessing response.text,
        # which is now guarded. If an error occurs before that, this general catch will handle it.
        # We re-raise a RuntimeError to signal failure to the caller.
        raise RuntimeError(f"New Pass 1 Gemini content generation failed: {e}")

# --- Pass 2: Select Segments for Narrative ---
def select_segments_for_narrative(
    current_transcript_chunk: list[dict],
    narrative_outline: list[str],
    user_prompt: str,
    past_text_context: str
) -> list[dict]:
    """
    Pass 2: Selects segments from the current_transcript_chunk that align with the narrative_outline.
    current_transcript_chunk is a list of dicts with {'start', 'end', 'text'}
    narrative_outline is a list of strings from Pass 1.
    past_text_context is a string of joined text from previous Pass 2 chunks.
    Returns a list of original segment dicts selected by Gemini.
    """
    try:
        import google.generativeai as local_genai
        # (Optional: Add diagnostics for local_genai as in the original process_with_gemini if needed)

        if not GEMINI_API_KEY_MODULE_LEVEL:
            logger.error("GEMINI_API_KEY not available for Pass 2.")
            raise RuntimeError("GEMINI_API_KEY environment variable not set.")
        
        local_genai.configure(api_key=GEMINI_API_KEY_MODULE_LEVEL)
        logger.info("Pass 2: Gemini API key configured.")

    except ImportError:
        logger.error("Pass 2: Failed to import google.generativeai.")
        raise RuntimeError("Critical: google.generativeai library not found for Pass 2.")
    except Exception as e_conf:
        logger.error(f"Pass 2: Failed to configure Gemini API key: {e_conf}")
        raise RuntimeError(f"Pass 2: Failed to configure Gemini API key: {e_conf}")

    # Build lookup using both start and end for higher accuracy (handles duplicate start times)
    original_segments_lookup = {seg['start']: seg for seg in current_transcript_chunk}

    SYSTEM_PROMPT_PASS_2 = f"""You are an expert video editor tasked with selecting specific video segments to create a highly entertaining, fast-paced, and funny highlights reel. Your editing style should emulate successful online entertainers like Jerma985, BedBanana, Habie147, Charborg, and General Sam. You are working with specific chunks of a transcript.

You have four key pieces of information for this task:
1.  "Past Text Context": Text from previous transcript chunks in this editing session. Use this for immediate conversational context and flow, but DO NOT select segments or timestamps from it.
2.  "User Prompt": The user's overall vision for this video, which provides overarching style guidance. The user prompt is: {json.dumps(user_prompt)}.
3.  "Narrative Outline": A JSON list of key comedic/engaging moments (e.g., "Speaker attempts X, fails hilariously"). This outline was previously generated from the *entire* transcript and represents the core story beats or funny ideas we MUST try to include.
4.  "Current Transcript Chunk": A JSON list of transcript segments (with 'start', 'end', 'text') from the *current part of the video*. YOUR SELECTIONS AND TIMESTAMPS MUST COME EXCLUSIVELY FROM THIS CHUNK.

Your Core Task for This Chunk:
Based on ALL the provided information, your job is to meticulously select segments *from the "Current Transcript Chunk"* that:
    a. Directly and effectively realize or contribute to one or more points in the "Narrative Outline". This is your HIGHEST priority.
    b. Align with the overall comedic style and goals of the "User Prompt".
    c. Maintain excellent comedic timing, pacing, and impact.

Key Instructions for Segment Selection:
-   **Prioritize Narrative Outline Points:** If a segment (or a sequence of segments) in the "Current Transcript Chunk" clearly and humorously matches a point in the "Narrative Outline", it's a very strong candidate for selection.
-   **Capture Complete Comedic Ideas:** If a Narrative Outline point (e.g., "Setup and punchline for X joke," "Story about Y with a funny ending") requires multiple *consecutive* segments from the "Current Transcript Chunk" to be understood and be funny, YOU MUST SELECT ALL of those necessary consecutive segments. Do not leave a setup hanging, cut off a punchline, or break a mini-story.
-   **Emphasize Personality & Humor in Support of Outline:** Select segments that showcase the speaker's unique personality, witty remarks, genuine reactions (contagious laughter, comedic surprise/frustration), absurd statements, or self-deprecating humor, *especially when these directly support or enhance a Narrative Outline point or the User Prompt's comedic goals*.
-   **Brevity and Impact:** While capturing complete thoughts, still aim for conciseness. Each selected segment (or sequence) should be high-impact. Ruthlessly cut fluff or moments that drag, unless the "drag" itself is a clearly intentional comedic element aligned with the Narrative Outline or User Prompt.
-   **Context is King:** Use the "Past Text Context" to understand the immediate lead-up to the current chunk, helping you identify if a segment in the current chunk is a continuation or payoff that aligns with the Narrative Outline.
-   **Gameplay Footage:** Minimize routine or unexciting gameplay. Only include it if it's *essential visual context* for a joke being told, a highlighted reaction, or a specific Narrative Outline point about a game event. The focus is on the speaker and the comedic/engaging content, not the gameplay itself unless it's the source of comedy.
-   **Exclusions (Strict):**
    -   Do **NOT** select lines that exist solely to greet or respond to individual chat users, read out donation/sub/follow messages, or give meta-stream housekeeping ("thanks for the raid", "hang on chat", etc.) **unless** the line is independently funny or critical to the narrative. If in doubt, leave it out.

Output Format:
You MUST return a JSON list of objects. Each object MUST contain ONLY a "start" key (double quotes) with the segment's start time (a float). These 'start' times MUST correspond exactly to segments from the "Current Transcript Chunk".
Example: `[{{"start": 10.50}}, {{"start": 22.35}}]`
If no segments qualify, return `[]`.

Your entire response MUST be ONLY this JSON list. No other text or explanations.
"""

    current_chunk_json_str = json.dumps(current_transcript_chunk)
    narrative_outline_json_str = json.dumps(narrative_outline)
    
    prompt_for_model_pass_2 = f"""Past Text Context (for immediate local flow, do not select from this):
{past_text_context}

---
User Prompt (overall style and focus for the video):
{json.dumps(user_prompt)} # Ensured user_prompt is also safely embedded here

---
Narrative Outline (key points to realize from the Current Transcript Chunk):
{narrative_outline_json_str}

---
Current Transcript Chunk (select segments ONLY from this list, matching the Narrative Outline and User Prompt):
{current_chunk_json_str}

Considering the SYSTEM PROMPT instructions, the Narrative Outline, the User Prompt, and Past Text Context, identify all segments *from the Current Transcript Chunk* that are relevant.
Your response MUST be a JSON list of objects, where each object has a single key "start" (with double quotes) and the value is the floating-point start time of a selected original segment from the Current Transcript Chunk.
Output ONLY the JSON list and nothing else."""
    
    logger.info(f"Pass 2: Sending request to Gemini. User prompt: '{user_prompt}'. Narrative points: {len(narrative_outline)}. Current chunk: {len(current_transcript_chunk)} segments. Past context: {len(past_text_context)} chars.")

    try:
        model_identifier = 'models/gemini-2.5-pro-exp-03-25' # Using existing model
        logger.info(f"Pass 2: Using Gemini model: {model_identifier}")
        model = local_genai.GenerativeModel(model_identifier)

        generation_config_dict = {
            "response_mime_type": "application/json",
            "response_schema": list[SelectedSegmentMarker] # Expecting a list of objects with just 'start'
        }
        
        response = model.generate_content(
            contents=[SYSTEM_PROMPT_PASS_2, prompt_for_model_pass_2],
            generation_config=generation_config_dict
        )
        
        if not response.text:
            logger.warning("Pass 2 Gemini returned an empty response text. Returning empty list of segments.")
            return []

        try:
            selected_markers_data = json.loads(response.text) 
        except json.JSONDecodeError as json_e:
            logger.error(f"Pass 2 Failed to decode JSON response from Gemini. Error: {json_e}")
            logger.error(f"Problematic Pass 2 Gemini response text (first 5000 chars): '{response.text[:5000]}'")
            if len(response.text) > 5000:
                logger.error(f"Problematic Pass 2 Gemini response text (last 5000 chars): '{response.text[-5000:]}'")
            else:
                logger.error(f"Full problematic Pass 2 Gemini response text: '{response.text}'")
            raise RuntimeError(f"Pass 2 Gemini returned malformed JSON: {json_e}. Check logs for Gemini's raw output.")

        if not isinstance(selected_markers_data, list):
            logger.error(f"Pass 2 Gemini response was not a list as expected. Type: {type(selected_markers_data)}. Data: '{str(selected_markers_data)[:200]}'")
            raise RuntimeError("Pass 2 Gemini response was not a list of selection markers.")

        final_selected_segments = []
        for i, marker_data in enumerate(selected_markers_data):
            if not isinstance(marker_data, dict) or 'start' not in marker_data:
                logger.warning(f"Pass 2 Item {i} in Gemini response is missing 'start'. Skipping: '{str(marker_data)[:100]}'")
                continue
            try:
                selected_marker = SelectedSegmentMarker(**marker_data)
                original_segment = original_segments_lookup.get(selected_marker.start)
                if original_segment:
                    final_selected_segments.append(original_segment)
                else:
                    logger.warning(f"Pass 2 Gemini returned a start time {selected_marker.start} not found in original transcript chunk. Skipping.")
            except Exception as pydantic_e: 
                logger.warning(f"Pass 2 Marker item {i} ('{str(marker_data)[:100]}') failed Pydantic validation. Error: {pydantic_e}. Skipping.")
                continue
        
        logger.info(f"Pass 2 Gemini selected {len(final_selected_segments)} segments from chunk based on narrative outline.")
        return final_selected_segments

    except AttributeError as ae_model: 
        logger.error(f"Pass 2 AttributeError when trying to use local_genai.GenerativeModel or related: {ae_model}", exc_info=True)
        raise RuntimeError(f"Pass 2 Gemini model instantiation or method call failed: {ae_model}")
    except Exception as e:
        logger.error(f"Pass 2 Gemini API call or processing failed: {e}", exc_info=True)
        raise RuntimeError(f"Pass 2 Gemini content generation failed: {e}")

# --- Pass 3: Generate Scripted Word Edit (New Definition) ---
def generate_scripted_word_edit(
    augmented_coarse_segments: list[dict], # Each dict is a coarse segment with an 'id' and potentially 'word_level_details' list
    narrative_outline: list[str],
    user_prompt: str,
    allow_reordering_in_script: bool # New parameter
) -> list[dict]: # Returns an EDL: list of {"source_segment_id": str, "start_word_index": int, "end_word_index": int}
    """
    Pass 3: Takes coarse segments (augmented with their own word-level details) and 
    generates a script of precisely chosen phrases by specifying start/end word indices from these details.

    Args:
        augmented_coarse_segments: List of coarse segment dictionaries. Each should have an 'id' 
                                   and a 'word_level_details' key containing a list of word objects 
                                   ({'word', 'start', 'end'} relative to coarse segment start).
        narrative_outline: High-level narrative points from Pass 1.
        user_prompt: User's overall instructions for video style and content.
        allow_reordering_in_script: If True, Gemini can reorder phrases creatively. 
                                     If False, Gemini should extract phrases while generally 
                                     maintaining chronological order of parent segments.

    Returns:
        An Edit Decision List (EDL). Each item is a dictionary:
        {"source_segment_id": str, "start_word_index": int, "end_word_index": int}
        This list defines the sequence of phrases to be extracted and concatenated.
        Returns an empty list on failure.
    """
    try:
        import google.generativeai as local_genai
        
        if not GEMINI_API_KEY_MODULE_LEVEL:
            logger.error("GEMINI_API_KEY not available for Pass 3.")
            raise RuntimeError("GEMINI_API_KEY environment variable not set.")
        
        local_genai.configure(api_key=GEMINI_API_KEY_MODULE_LEVEL)
        # logger.info("Pass 3: Gemini API key configured.") # Already logged if previous passes ran

    except ImportError:
        logger.error("Pass 3: Failed to import google.generativeai.")
        raise RuntimeError("Critical: google.generativeai library not found for Pass 3.")
    except Exception as e_conf:
        logger.error(f"Pass 3: Failed to configure Gemini API key: {e_conf}")
        raise RuntimeError(f"Pass 3: Failed to configure Gemini API key: {e_conf}")

    if not augmented_coarse_segments:
        logger.warning("Pass 3: No augmented coarse segments provided. Returning empty script.")
        return []

    # Filter out segments that don't have word_level_details for the LLM prompt
    # Also, simplify the structure for the prompt to only include necessary info for LLM
    prompt_friendly_segments = []
    for seg in augmented_coarse_segments:
        if seg.get('word_level_details') and seg.get('id'):
            # For the LLM, provide the coarse segment ID, its full text (for context), and its words list
            prompt_friendly_segments.append({
                "id": seg['id'],
                "full_text_of_coarse_segment": seg.get('text', ''),
                "words": seg['word_level_details'] # List of {'word', 'start', 'end'}
            })
    
    if not prompt_friendly_segments:
        logger.warning("Pass 3: No coarse segments with word-level details found after filtering. Returning empty script.")
        return []

    reordering_instruction = ""
    if allow_reordering_in_script:
        reordering_instruction = "You have complete freedom to reorder these extracted phrases in any sequence you deem most effective for the `User Prompt`. Out-of-context hilarity by reordering is highly encouraged."
    else:
        reordering_instruction = "You should select and script phrases while generally preserving the chronological order of the parent coarse segments they come from. The goal is to extract the most impactful or funny phrases *within* their original sequence, not to reorder them across the entire video. Focus on precise phrase extraction for concise, impactful delivery, even if it means shortening original segments."

    SYSTEM_PROMPT_PASS_3 = f"""
You are an expert comedic video editor and scriptwriter. Your task is to create a video script by selecting precise phrases from a list of provided transcript segments. Each of these segments has already been broken down into individual words with timings.

Your Input:
1.  `User Prompt`: The user's overall vision for this video. Current User Prompt: {json.dumps(user_prompt)}
2.  `Narrative Outline`: A list of key comedic/engaging moments previously identified. This provides thematic guidance. Narrative Outline: {json.dumps(narrative_outline)}
3.  `Available Coarse Segments`: A JSON list of dictionaries. Each dictionary represents an original transcript segment and contains:
    *   `"id"`: A unique string identifier for this coarse segment (e.g., "coarse_seg_0").
    *   `"full_text_of_coarse_segment"`: The complete original text of this segment (for your contextual understanding).
    *   `"words"`: A list of word objects `{{"word": "text", "start": float, "end": float}}`. These are the individual words within this coarse segment, and their `start`/`end` times are RELATIVE TO THE BEGINNING OF THIS COARSE SEGMENT.

Your Task: Construct a new video script by creating an ordered list of PHRASES. Each phrase is defined by selecting a sequence of words from ONE of the `Available Coarse Segments`.
For each phrase you want in your final script, you must specify:
    a.  The `id` of the coarse segment from which the phrase is extracted.
    b.  The 0-based `start_word_index` of the first word of your chosen phrase within that segment's `"words"` list.
    c.  The 0-based `end_word_index` of the last word of your chosen phrase within that segment's `"words"` list (inclusive).

Editing Style Mandate for This Script:
{reordering_instruction}

Key Principles for Phrase Selection:
-   **Impact and Comedy:** Prioritize phrases that are funny, impactful, absurd, or highly characteristic of the speaker, aligned with the `User Prompt` and `Narrative Outline`.
-   **Brevity:** Extract concise phrases. "Less is more." For example, from "Just because you have a micropenis, doesn't mean you can't be happy," you might extract just "you have a micropenis,".
-   **Narrative Alignment:** Use the `Narrative Outline` to guide which themes or moments to emphasize with your phrase selections.
-   **Select Phrases:** You do not have to use all coarse segments or all words within them. Pick the most impactful phrases.
-   **Repeat Phrases:** You can decide to use the same extracted phrase multiple times in your script if it enhances the comedy or narrative (respect the reordering mandate above).
-   **Respect Word Sequence within a Phrase:** When you define a phrase using `start_word_index` and `end_word_index`, the words from the original segment between those indices (inclusive) will be used in their original order to form that phrase.

Output Format (Strictly Enforced):
-   Your entire response MUST be a single JSON list.
-   Each item in this list MUST be a JSON object representing one phrase in your new script.
-   Each phrase object MUST have exactly these three keys:
    *   `"source_segment_id"`: The string `id` of the coarse segment from which the phrase is extracted.
    *   `"start_word_index"`: The integer 0-based starting index of the phrase in the `"words"` list of the `source_segment_id`.
    *   `"end_word_index"`: The integer 0-based ending index of the phrase (inclusive) in the `"words"` list of the `source_segment_id`.
-   Ensure `end_word_index` is greater than or equal to `start_word_index` and both are valid indices for the `"words"` list of the specified `source_segment_id`.
-   Do NOT add any other keys, explanations, or text outside of this JSON list of phrase objects.

Example of `Available Coarse Segments` (simplified for one segment):
`[ {{"id": "coarse_seg_0", 
    "full_text_of_coarse_segment": "Just because you have a micropenis, doesn't mean you can't be happy.", 
    "words": [ 
        {{"word": "Just", "start": 0.0, "end": 0.2}}, {{"word": "because", "start": 0.2, "end": 0.5}}, 
        {{"word": "you", "start": 0.5, "end": 0.6}}, {{"word": "have", "start": 0.6, "end": 0.8}}, 
        {{"word": "a", "start": 0.8, "end": 0.9}}, {{"word": "micropenis,", "start": 0.9, "end": 1.5}}, 
        {{"word": "doesn't", "start": 1.6, "end": 2.0}}, {{"word": "mean", "start": 2.0, "end": 2.2}} 
        /* ... more words ... */ 
    ]}} ]`

Example of YOUR valid JSON Output (the Edit Decision List of phrases) if `allow_reordering_in_script` was true:
`[ 
  {{"source_segment_id": "coarse_seg_0", "start_word_index": 2, "end_word_index": 5}},  // Corresponds to "you have a micropenis,"
  {{"source_segment_id": "coarse_seg_0", "start_word_index": 0, "end_word_index": 1}}   // Corresponds to "Just because"
]`
(This script would play "you have a micropenis," then "Just because")

Example of YOUR valid JSON Output (the Edit Decision List of phrases) if `allow_reordering_in_script` was false (and assuming the above was the only available segment):
`[ 
  {{"source_segment_id": "coarse_seg_0", "start_word_index": 2, "end_word_index": 5}} // "you have a micropenis," - extracted phrase, order maintained.
]` 
(Or potentially multiple phrases from this segment, but kept in order of their appearance in `coarse_seg_0`)

Now, analyze the provided `User Prompt`, `Narrative Outline`, and `Available Coarse Segments` and generate your script as a JSON list of phrase objects, adhering to the reordering mandate.
"""

    prompt_friendly_segments_json = json.dumps(prompt_friendly_segments)
    prompt_for_model_pass_3 = (
        f"User Prompt:\n{json.dumps(user_prompt)}\n\n"
        f"Narrative Outline:\n{json.dumps(narrative_outline)}\n\n"
        f"Available Coarse Segments (with their word breakdowns):\n{prompt_friendly_segments_json}\n\n"
        f"Based on all the instructions in the System Prompt, the User Prompt, the Narrative Outline, and these Available Coarse Segments, "
        f"generate the JSON list of phrase objects for the video script. "
        f"Your entire response MUST be this JSON list and nothing else."
    )

    num_input_segments = len(prompt_friendly_segments)
    total_input_words = sum(len(seg.get('words', [])) for seg in prompt_friendly_segments)
    logger.info(
        f"Pass 3: Sending request to Gemini for phrase-based script. "
        f"User prompt: '{user_prompt if len(user_prompt) < 70 else user_prompt[:67] + '...'}'. "
        f"Narrative points: {len(narrative_outline)}. "
        f"Input Coarse Segments: {num_input_segments}. Total Input Words: {total_input_words}."
    )
    
    try:
        # Using a model potentially better at instruction following and JSON output, like 1.0 Pro or 1.5 Pro if available.
        model_identifier = 'models/gemini-2.5-pro-exp-03-25' # Changed to match Pass 1 and Pass 2
        logger.info(f"Pass 3: Using Gemini model: {model_identifier}")
        model = local_genai.GenerativeModel(model_identifier)
        
        generation_config_dict = {
            "response_mime_type": "application/json",
        }

        response = model.generate_content(
            contents=[SYSTEM_PROMPT_PASS_3, prompt_for_model_pass_3],
            generation_config=generation_config_dict,
        )

        if not response.text:
            logger.warning("Pass 3 Gemini returned empty response text. Returning empty EDL.")
            return []
        
        try:
            edl_data = json.loads(response.text)
            if not isinstance(edl_data, list):
                logger.error(f"Pass 3 Gemini response not a list as expected for EDL. Type: {type(edl_data)}. Data: {str(edl_data)[:500]}")
                logger.error(f"Full problematic Pass 3 Gemini response text: \n{response.text}")
                return [] 
            
            valid_edl = []
            # Create a quick lookup for segment word counts to validate indices
            segment_word_counts = {seg['id']: len(seg['words']) for seg in prompt_friendly_segments}

            for item in edl_data:
                if not (isinstance(item, dict) and 
                        'source_segment_id' in item and isinstance(item['source_segment_id'], str) and 
                        item['source_segment_id'] in segment_word_counts and
                        'start_word_index' in item and isinstance(item['start_word_index'], int) and 
                        'end_word_index' in item and isinstance(item['end_word_index'], int)):
                    logger.warning(f"Pass 3 EDL item malformed or missing required keys: {str(item)[:200]}. Skipping.")
                    continue
                
                seg_id = item['source_segment_id']
                start_idx = item['start_word_index']
                end_idx = item['end_word_index']
                max_words_in_seg = segment_word_counts[seg_id]

                if not (0 <= start_idx < max_words_in_seg and 
                        0 <= end_idx < max_words_in_seg and 
                        start_idx <= end_idx):
                    logger.warning(
                        f"Pass 3 EDL item has invalid word indices for segment '{seg_id}' (words: {max_words_in_seg}): "
                        f"start_idx={start_idx}, end_idx={end_idx}. Skipping. Item: {str(item)[:200]}"
                    )
                    continue
                
                valid_edl.append(item)
            
            if not valid_edl and edl_data: 
                 logger.error(f"Pass 3 EDL was non-empty but contained no valid phrase objects after validation. Full response: \n{response.text}")
                 return []

            logger.info(f"Pass 3 Gemini returned an EDL with {len(valid_edl)} phrases.")
            return valid_edl
            
        except json.JSONDecodeError as json_e:
            logger.error(f"Pass 3 Failed to decode JSON EDL from Gemini: {json_e}. Response text:\n{response.text}")
            raise RuntimeError(f"Pass 3 Gemini returned malformed JSON for EDL: {json_e}")

    except AttributeError as ae_model: 
        logger.error(f"Pass 3 AttributeError (model issue): {ae_model}", exc_info=True)
        raise RuntimeError(f"Pass 3 Gemini model instantiation or method call failed: {ae_model}")
    except Exception as e:
        logger.error(f"Pass 3 Gemini API call failed: {e}", exc_info=True)
        raise RuntimeError(f"Pass 3 Gemini content generation failed: {e}")

# Original process_with_gemini (now select_segments_for_narrative) has been modified above.
# The InputSegment class definition was commented out as it's not directly used by the Gemini call schemas.
# If it's used elsewhere for data validation before calling these functions, it can be kept.
# For now, assuming the input dicts are correctly formatted by the calling code in main.py. 

# --- START OF MULTIMODAL PASS 2 ---

# REMOVED/COMMENTED OUT as Pass 2 input is now just the video, user prompt, and flags.
# The candidate video's content is implicitly defined by Pass 1's output.
# class MultimodalPass2InputSegment(BaseModel):
#     """Represents a single segment in the transcript of the candidate video."""
#     start: float
#     end: float
#     text: str

# class MultimodalPass2Input(BaseModel):
#     """Conceptual input for the multimodal Pass 2 function."""
#     candidate_video_path: str # Path to the compiled candidate video
#     # candidate_video_transcript: list[MultimodalPass2InputSegment] # Transcript OF THE CANDIDATE VIDEO - REMOVED
#     pass1_script_lines: List[str] # List of verbatim quotes from Pass 1 - REPLACED by direct video analysis
#     user_prompt_for_video_theme: str
#     allow_reordering: bool
#     allow_repetition: bool

class MultimodalPass2Response(BaseModel):
    """Pydantic model for the full response from Gemini in Pass 2, now expecting selected text strings."""
    selected_text_segments: list[str] = Field(description="A list of verbatim text strings. Each string is a segment selected from the candidate video. The order in this list defines the final video order.")

def refine_video_with_multimodal_pass2(
    candidate_video_path: str,
    user_prompt: str,
    allow_reordering: bool,
    allow_repetition: bool, 
    gemini_api_key: str | None = None
) -> list[str]:
    """
    Pass 2: Uses a multimodal Gemini model to refine a candidate video.
    The candidate video is already a compilation of segments selected by Pass 1.
    This pass watches the candidate video and selects the best sub-segments from it
    to create a final, polished EDL (Edit Decision List).

    Args:
        candidate_video_path: Path to the candidate video file.
        user_prompt: The original user prompt for the overall video theme and style.
        allow_reordering: Boolean flag indicating if reordering of segments from the candidate video is allowed.
        allow_repetition: Boolean flag indicating if repetition of segments from the candidate video is allowed.
        gemini_api_key: Optional Gemini API key.

    Returns:
        A list of verbatim text strings representing the selected segments from the candidate video.
        The order of strings in the list dictates the final video sequence.
        Returns an empty list if no segments are selected or an error occurs.
    """
    try:
        import google.generativeai as local_genai
        if not GEMINI_API_KEY_MODULE_LEVEL and not gemini_api_key:
            logger.error("Multimodal Pass 2: GEMINI_API_KEY not available (neither module level nor passed).")
            raise RuntimeError("GEMINI_API_KEY environment variable not set and not provided to function.")
        
        current_api_key = gemini_api_key if gemini_api_key else GEMINI_API_KEY_MODULE_LEVEL
        local_genai.configure(api_key=current_api_key)
        logger.info("Multimodal Pass 2: Gemini API key configured.")

    except ImportError:
        logger.error("Multimodal Pass 2: Failed to import google.generativeai.")
        raise RuntimeError("Critical: google.generativeai library not found for Multimodal Pass 2.")
    except Exception as e_conf:
        logger.error(f"Multimodal Pass 2: Failed to configure Gemini API key: {e_conf}")
        raise RuntimeError(f"Multimodal Pass 2: Failed to configure Gemini API key: {e_conf}")

    video_file_gemini = None # Initialize to None
    try:
        logger.info(f"Multimodal Pass 2: Uploading video file: {candidate_video_path}...")
        if not os.path.exists(candidate_video_path):
            logger.error(f"Multimodal Pass 2: Candidate video file not found at path: {candidate_video_path}")
            return []
        
        video_file_gemini = local_genai.upload_file(path=candidate_video_path, display_name="Candidate Video for Pass 2")
        logger.info(f"Multimodal Pass 2: Uploaded file '{video_file_gemini.display_name}' as URI: {video_file_gemini.uri}. MIME type: {video_file_gemini.mime_type}. Initial state: {video_file_gemini.state}")

        wait_time_seconds = 0
        max_wait_time_seconds = 300 # 5 minutes
        poll_interval_seconds = 5

        while video_file_gemini.state.name != 'ACTIVE':
            if video_file_gemini.state.name == 'FAILED':
                logger.error(f"Multimodal Pass 2: File upload failed for {video_file_gemini.name}. State: {video_file_gemini.state.name}. Reason: {video_file_gemini.error if hasattr(video_file_gemini, 'error') else 'Unknown'}")
                # No need to delete here, finally block will handle it.
                return [] 

            logger.info(f"Multimodal Pass 2: Waiting for file {video_file_gemini.name} to become active. Current state: {video_file_gemini.state.name}. Waited {wait_time_seconds}s...")
            
            if wait_time_seconds >= max_wait_time_seconds:
                logger.error(f"Multimodal Pass 2: Timeout waiting for file {video_file_gemini.name} to become active after {max_wait_time_seconds}s. Last state: {video_file_gemini.state.name}")
                # No need to delete here, finally block will handle it.
                return []

            time.sleep(poll_interval_seconds)
            wait_time_seconds += poll_interval_seconds
            video_file_gemini = local_genai.get_file(name=video_file_gemini.name)

        logger.info(f"Multimodal Pass 2: File {video_file_gemini.name} is now ACTIVE after {wait_time_seconds}s.")

        # Now that video_file_gemini is active and defined, construct the system prompt and log.
        # With response_schema configured, the prompt can be less focused on strict JSON formatting instructions
        # and more on the content and logic for segment selection.
        SYSTEM_PROMPT_MULTIMODAL_PASS_2 = f'''You are an expert video editor\\'s assistant with advanced multimodal capabilities.
Your task is to analyze the provided CANDIDATE VIDEO and the original user\\'s request to select the best segments to create a final, compelling short video.
The candidate video was created from a longer source, based on an initial text-only pass that broadly selected potentially relevant clips. Your job is to refine this.

User\\'s original request for the video\\'s theme and style:
{json.dumps(user_prompt)}

Allow Reordering: {str(allow_reordering).lower()}
Allow Repetition: {str(allow_repetition).lower()}

Your Instructions:
1.  **Analyze the CANDIDATE VIDEO:** Watch the video to understand its content, pacing, visual cues, humor, and speaker dynamics.
2.  **Select Segments:** Based on the user\\'s original request, identify the most impactful segments from the CANDIDATE VIDEO.
    -   Consider humor, personality, key information, visual gags, and overall engagement.
    -   If a segment from the candidate video is good but too long, select only the essential part.
3.  **Extract Verbatim Text:** For each selected segment, you must extract its EXACT VERBATIM TEXT.
4.  **Order Segments:**
    -   If "Allow Reordering" is true, arrange the selected text segments in the order that best fulfills the user\\'s request and creates the most engaging narrative or comedic flow. The order in your list will be the final order.
    -   If "Allow Reordering" is false, the selected text segments must maintain their relative order from how they appeared in the CANDIDATE VIDEO.
5.  **Repetition:**
    -   If "Allow Repetition" is true, you MAY reuse parts of the candidate video (and thus their text) if it enhances the final product.
    -   If "Allow Repetition" is false, each part of the candidate video can only be used once in the final selection.

Your output MUST be a JSON object structured according to the `MultimodalPass2Response` schema.
Specifically, it should contain a single key `selected_text_segments` which is a list of strings.
Each string in the list is the verbatim text of a segment you have selected from the CANDIDATE VIDEO.
The order of the strings in this list will define the final video order.

Example of expected JSON output:
`{{
  "selected_text_segments": [
    "This is the first selected funny quote.",
    "And here\\'s another interesting moment from the video.",
    "A final hilarious line to end with."
  ]
}}`

If no segments from the candidate video are suitable, return an empty list for `selected_text_segments`.
'''

        contents_for_model = [SYSTEM_PROMPT_MULTIMODAL_PASS_2]
        if video_file_gemini: 
            contents_for_model.append(video_file_gemini)
        else: 
            logger.error("Multimodal Pass 2: video_file_gemini is not defined after upload attempt. Cannot proceed.")
            return []
            
        logger.info(f"Multimodal Pass 2: SYSTEM_PROMPT_MULTIMODAL_PASS_2 (condensed for logging): {SYSTEM_PROMPT_MULTIMODAL_PASS_2[:500]}...")
        logger.info(f"Multimodal Pass 2: Sending request to Gemini model with user prompt: '{user_prompt[:100]}...', Reorder: {allow_reordering}, Repetition: {allow_repetition}")
        logger.info(f"Multimodal Pass 2: Video file URI being sent: {video_file_gemini.uri}") 

        model_identifier = "gemini-2.5-flash"
        logger.info(f"Multimodal Pass 2: Using Gemini model: {model_identifier} with structured output schema: MultimodalPass2Response")
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]
        model = local_genai.GenerativeModel(model_identifier, safety_settings=safety_settings)
        
        generation_config = {
            "temperature": 0.2, 
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192, 
            "response_mime_type": "application/json",
            "response_schema": MultimodalPass2Response 
        }
        
        response = model.generate_content(
            contents=contents_for_model, 
            generation_config=generation_config,
            safety_settings=safety_settings 
        )

        if not response.candidates or not response.candidates[0].content.parts:
            logger.warning("Multimodal Pass 2 Gemini returned no candidates or no parts in candidate.")
            try:
                if response.prompt_feedback:
                    logger.warning(f"Multimodal Pass 2 Prompt Feedback: {response.prompt_feedback}")
                else:
                    logger.warning("Multimodal Pass 2 Prompt Feedback was not available.")
                if hasattr(response, 'candidates') and response.candidates:
                     for i, candidate in enumerate(response.candidates):
                        logger.warning(f"Multimodal Pass 2 Candidate {i} Finish Reason: {candidate.finish_reason}")
                        if candidate.safety_ratings:
                            logger.warning(f"Multimodal Pass 2 Candidate {i} Safety Ratings: {candidate.safety_ratings}")
                else:
                    logger.warning("Multimodal Pass 2 Candidates list was empty or not available.")
            except Exception as e_log_empty:
                logger.error(f"Multimodal Pass 2 Error during detailed logging of empty/no-candidate response: {e_log_empty}")
            return []
        
        parsed_response_data = None
        json_to_parse = None
        try:
            first_part = response.candidates[0].content.parts[0]
            if hasattr(first_part, 'text') and first_part.text: 
                json_to_parse = first_part.text
                logger.info("Multimodal Pass 2: Found JSON in first_part.text. Will attempt to parse.")
            elif response.text: 
                json_to_parse = response.text
                logger.info("Multimodal Pass 2: Found JSON in response.text. Will attempt to parse.")
            else:
                logger.warning("Multimodal Pass 2: Model did not return JSON in .text or first part's .text. Cannot proceed.")
                # Log candidate details if text is missing, as this might indicate a safety block or other issue with the generation
                try:
                    candidate = response.candidates[0]
                    logger.warning(f"Multimodal Pass 2: Candidate (no text) Finish Reason: {candidate.finish_reason}")
                    if candidate.safety_ratings:
                        logger.warning(f"Multimodal Pass 2: Candidate (no text) Safety Ratings: {candidate.safety_ratings}")
                    else:
                        logger.warning("Multimodal Pass 2: Candidate (no text) Safety Ratings: Not available or empty.")
                    if response.prompt_feedback:
                        logger.warning(f"Multimodal Pass 2: Prompt Feedback (no text): {response.prompt_feedback}")
                    else:
                        logger.warning("Multimodal Pass 2: Prompt Feedback (no text): Not available.")
                except Exception as e_log_detail:
                    logger.error(f"Multimodal Pass 2: Error during detailed logging for no-text response: {e_log_detail}")
                return []

            if json_to_parse:
                temp_parsed_dict = json.loads(json_to_parse)
                parsed_response_data = MultimodalPass2Response(**temp_parsed_dict)
            else: # Should have been caught by the check above, but as a safeguard
                logger.warning("Multimodal Pass 2: json_to_parse was unexpectedly None.")
                return []

        except json.JSONDecodeError as json_e:
            logger.error(f"Multimodal Pass 2: Failed to decode JSON. Error: {json_e}")
            problematic_text = json_to_parse if json_to_parse else "N/A"
            logger.error(f"Problematic Multimodal Pass 2 Gemini response text (first 1000 chars): '{problematic_text[:1000]}'")
            return []
        except Exception as e_parse:
            logger.error(f"Multimodal Pass 2: Error parsing/instantiating Pydantic model from response. Error: {e_parse}", exc_info=True)
            return []

        if not parsed_response_data or not isinstance(parsed_response_data, MultimodalPass2Response):
            logger.error("Multimodal Pass 2: Parsed data is not a valid MultimodalPass2Response object.")
            return []

        validated_segments = parsed_response_data.selected_text_segments
        if not isinstance(validated_segments, list):
             logger.error(f"Multimodal Pass 2: 'selected_text_segments' field in parsed response was not a list. Type: {type(validated_segments)}.")
             return []

        # Ensure all items in the list are strings
        if not all(isinstance(s, str) for s in validated_segments):
            logger.error(f"Multimodal Pass 2: Not all items in 'selected_text_segments' are strings.")
            # Log the first few non-string items for debugging
            for i, item in enumerate(validated_segments):
                if not isinstance(item, str):
                    logger.error(f"Item {i} type: {type(item)}, value: {str(item)[:100]}")
                if i > 4: # Log up to 5 problematic items
                    break
            return []

        logger.info(f"Multimodal Pass 2: Successfully obtained {len(validated_segments)} text segments using structured output schema.")
        return validated_segments

    except AttributeError as ae_model: 
        logger.error(f"Multimodal Pass 2: AttributeError (likely model or local_genai issue): {ae_model}", exc_info=True)
        # video_file_gemini might be defined or None here, finally block handles cleanup.
        return []
    except Exception as e_api: # More general exception catch for API call issues or other unhandled issues in try block
        logger.error(f"Multimodal Pass 2: Gemini API call or processing failed: {e_api}", exc_info=True)
        if hasattr(e_api, 'response') and hasattr(e_api.response, 'prompt_feedback'):
             logger.error(f"Multimodal Pass 2: Prompt Feedback from API error: {e_api.response.prompt_feedback}")
        # video_file_gemini might be defined or None here, finally block handles cleanup.
        return []
    finally:
        if video_file_gemini and video_file_gemini.name: # Check if it has a name (was likely uploaded)
            try:
                local_genai.delete_file(video_file_gemini.name) # name is usually 'files/file_id'
                logger.info(f"Multimodal Pass 2: Successfully deleted uploaded file '{video_file_gemini.name}' from Gemini storage.")
            except Exception as e_delete:
                logger.warning(f"Multimodal Pass 2: Failed to delete uploaded file '{video_file_gemini.name}' from Gemini storage. Error: {e_delete}")
    
    # Fallback if something went wrong before returning
    # logger.warning("Multimodal Pass 2: Reached end of function unexpectedly, returning empty list.")
    # return [] # This line should ideally not be reached if logic above is correct

# --- END OF MULTIMODAL PASS 2 --- 