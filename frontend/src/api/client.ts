/**
 * API client for GeminiEditor backend.
 * Provides typed methods for all API endpoints.
 */

import axios, { type AxiosInstance } from 'axios';

// ==================== TYPE DEFINITIONS ====================

export interface Project {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  settings: Record<string, any>;
}

export interface SourceVideo {
  id: string;
  project_id: string;
  filename: string;
  file_path: string;
  file_size?: number;
  duration?: number;
  uploaded_at: string;
  video_codec?: string;
  audio_tracks: AudioTrack[];
  resolution?: { width: number; height: number };
  framerate?: number;
  transcript_path?: string;
  audio_preview_paths: string[];
  scope_start?: number;
  scope_end?: number;
}

export interface AudioTrack {
  index: number;
  codec: string;
  sample_rate: number;
  channels: number;
  language?: string;
}

export interface TranscriptSegment {
  id: string;
  source_video_id: string;
  start_time: number;
  end_time: number;
  text: string;
  words?: Word[];
  confidence?: number;
  speaker?: string;
}

export interface Word {
  word: string;
  start: number;
  end: number;
  confidence: number;
}

export interface Edit {
  id: string;
  project_id: string;
  name: string;
  version: number;
  created_at: string;
  updated_at: string;
  source_video_id: string;
  narrative_outline?: string[];
  user_prompt?: string;
  ai_processing_complete: boolean;
  multimodal_pass_complete: boolean;
  is_finalized: boolean;
  final_video_path?: string;
  finalized_at?: string;
  editing_settings: Record<string, any>;
}

export interface EditDecision {
  id: string;
  edit_id: string;
  order_index: number;
  segment_id: string;
  source_video_id: string;
  start_time: number;
  end_time: number;
  transcript_text: string;
  is_included: boolean;
  is_ai_selected: boolean;
  user_modified: boolean;
  clip_file_path?: string;
  thumbnail_path?: string;
}

export interface ClipPreview {
  decision_id: string;
  clip_url: string;
  start_time: number;
  end_time: number;
  duration: number;
  transcript_text: string;
  order_index: number;
}

export interface PreviewResponse {
  edit_id: string;
  clips: ClipPreview[];
  total_duration: number;
  clip_count: number;
}

// ==================== API CLIENT CLASS ====================

class ApiClient {
  private client: AxiosInstance;

  constructor(baseURL: string = '') {
    this.client = axios.create({
      baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
      maxRedirects: 5, // Follow redirects
    });
  }

  // ==================== PROJECTS ====================

  async getProjects(skip: number = 0, limit: number = 100): Promise<Project[]> {
    const response = await this.client.get('/api/projects', {
      params: { skip, limit },
    });
    return response.data;
  }

  async getProject(projectId: string): Promise<Project> {
    const response = await this.client.get(`/api/projects/${projectId}`);
    return response.data;
  }

  async getProjectWithVideos(projectId: string): Promise<Project & { source_videos: SourceVideo[] }> {
    const response = await this.client.get(`/api/projects/${projectId}/with-videos`);
    return response.data;
  }

  async getProjectWithEdits(projectId: string): Promise<Project & { edits: Edit[] }> {
    const response = await this.client.get(`/api/projects/${projectId}/with-edits`);
    return response.data;
  }

  async createProject(data: {
    name: string;
    description?: string;
    settings?: Record<string, any>;
  }): Promise<Project> {
    const response = await this.client.post('/api/projects', data);
    return response.data;
  }

  async updateProject(
    projectId: string,
    data: {
      name?: string;
      description?: string;
      settings?: Record<string, any>;
    }
  ): Promise<Project> {
    const response = await this.client.patch(`/api/projects/${projectId}`, data);
    return response.data;
  }

  async deleteProject(projectId: string): Promise<void> {
    await this.client.delete(`/api/projects/${projectId}`);
  }

  // ==================== SOURCE VIDEOS ====================

  async getSourceVideos(projectId: string): Promise<SourceVideo[]> {
    const response = await this.client.get(`/api/projects/${projectId}/source-videos`);
    return response.data;
  }

  async getSourceVideo(projectId: string, videoId: string): Promise<SourceVideo> {
    const response = await this.client.get(`/api/projects/${projectId}/source-videos/${videoId}`);
    return response.data;
  }

  async updateSourceVideo(
    projectId: string,
    videoId: string,
    data: Partial<SourceVideo>
  ): Promise<SourceVideo> {
    const response = await this.client.patch(`/api/projects/${projectId}/source-videos/${videoId}`, data);
    return response.data;
  }

  async deleteSourceVideo(projectId: string, videoId: string): Promise<void> {
    await this.client.delete(`/api/projects/${projectId}/source-videos/${videoId}`);
  }

  getVideoStreamUrl(projectId: string, videoId: string): string {
    return `/api/projects/${projectId}/source-videos/${videoId}/play`;
  }

  async generateTranscript(projectId: string, videoId: string): Promise<{ job_id: string; message: string }> {
    const response = await this.client.post(`/api/projects/${projectId}/source-videos/${videoId}/generate-transcript`);
    return response.data;
  }

  async getTranscriptStatus(projectId: string, videoId: string, jobId: string): Promise<any> {
    // Add cache-busting timestamp to prevent stale responses
    const timestamp = Date.now();
    const response = await this.client.get(`/api/projects/${projectId}/source-videos/${videoId}/transcript-status/${jobId}?t=${timestamp}`);
    return response.data;
  }

  async getVideoTranscript(projectId: string, videoId: string): Promise<TranscriptSegment[]> {
    const response = await this.client.get(`/api/projects/${projectId}/source-videos/${videoId}/transcript`);
    return response.data;
  }

  async segmentVideo(projectId: string, videoId: string): Promise<{ job_id: string; message: string }> {
    const response = await this.client.post(`/api/projects/${projectId}/source-videos/${videoId}/segment`);
    return response.data;
  }

  async getSegmentationStatus(projectId: string, videoId: string, jobId: string): Promise<any> {
    // Add cache-busting timestamp to prevent stale responses
    const timestamp = Date.now();
    const response = await this.client.get(`/api/projects/${projectId}/source-videos/${videoId}/segmentation-status/${jobId}?t=${timestamp}`);
    return response.data;
  }

  async getPersistedClips(projectId: string, videoId: string): Promise<{ clips: ClipPreview[] }> {
    const response = await this.client.get(`/api/projects/${projectId}/source-videos/${videoId}/clips`);
    const data = response.data;
    // Normalize shape to ClipPreview
    const clips: ClipPreview[] = (data.clips || []).map((c: any) => ({
      decision_id: c.segment_id || c.id,
      clip_url: c.stream_url,
      start_time: c.start_time,
      end_time: c.end_time,
      duration: c.duration,
      transcript_text: c.transcript_text || '',
      order_index: c.order_index ?? 0,
    }));
    return { clips };
  }

  getClipStreamUrl(projectId: string, clipId: string): string {
    return `/api/projects/${projectId}/clips/${clipId}/play`;
  }

  async uploadSourceVideo(projectId: string, file: File, onProgress?: (progress: number) => void): Promise<SourceVideo> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('project_id', projectId);

    const response = await this.client.post(`/api/projects/${projectId}/source-videos/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(progress);
        }
      },
    });

    return response.data;
  }

  // ==================== EDITS ====================

  async getEdits(projectId: string): Promise<Edit[]> {
    const response = await this.client.get(`/api/projects/${projectId}/edits`);
    return response.data;
  }

  async getEdit(projectId: string, editId: string): Promise<Edit> {
    const response = await this.client.get(`/api/projects/${projectId}/edits/${editId}`);
    return response.data;
  }

  async getEditWithDecisions(
    projectId: string,
    editId: string
  ): Promise<Edit & { edit_decisions: EditDecision[] }> {
    const response = await this.client.get(`/api/projects/${projectId}/edits/${editId}/with-decisions`);
    return response.data;
  }

  async createEdit(data: {
    project_id: string;
    source_video_id: string;
    name: string;
    user_prompt?: string;
    narrative_outline?: string[];
    editing_settings?: Record<string, any>;
  }): Promise<Edit> {
    const response = await this.client.post(`/api/projects/${data.project_id}/edits`, data);
    return response.data;
  }

  async updateEdit(
    projectId: string,
    editId: string,
    data: Partial<Edit>
  ): Promise<Edit> {
    const response = await this.client.patch(`/api/projects/${projectId}/edits/${editId}`, data);
    return response.data;
  }

  async duplicateEdit(projectId: string, editId: string, newName?: string): Promise<Edit> {
    const response = await this.client.post(
      `/api/projects/${projectId}/edits/${editId}/duplicate`,
      null,
      { params: { new_name: newName } }
    );
    return response.data;
  }

  async deleteEdit(projectId: string, editId: string): Promise<void> {
    await this.client.delete(`/api/projects/${projectId}/edits/${editId}`);
  }

  // ==================== EDIT DECISIONS (EDL) ====================

  async getEditDecisions(
    projectId: string,
    editId: string,
    includedOnly: boolean = false
  ): Promise<EditDecision[]> {
    const response = await this.client.get(`/api/projects/${projectId}/edits/${editId}/edl`, {
      params: { included_only: includedOnly },
    });
    return response.data;
  }

  async updateEditDecision(
    projectId: string,
    editId: string,
    decisionId: string,
    data: Partial<EditDecision>
  ): Promise<EditDecision> {
    const response = await this.client.patch(
      `/api/projects/${projectId}/edits/${editId}/edl/${decisionId}`,
      data
    );
    return response.data;
  }

  async reorderEditDecisions(
    projectId: string,
    editId: string,
    decisionOrder: string[]
  ): Promise<EditDecision[]> {
    const response = await this.client.post(
      `/api/projects/${projectId}/edits/${editId}/edl/reorder`,
      { decision_order: decisionOrder }
    );
    return response.data;
  }

  async deleteEditDecision(projectId: string, editId: string, decisionId: string): Promise<void> {
    await this.client.delete(`/api/projects/${projectId}/edits/${editId}/edl/${decisionId}`);
  }

  // ==================== PROCESSING ====================

  async processVideo(
    projectId: string,
    videoId: string,
    data: {
      edit_name: string;
      user_prompt?: string;
      whisper_model?: string;
      language?: string;
      audio_track?: number;
      pad_before_seconds?: number;
      pad_after_seconds?: number;
    }
  ): Promise<{ job_id: string; edit_id: string; status: string; message: string }> {
    const response = await this.client.post(
      `/api/projects/${projectId}/source-videos/${videoId}/process`,
      null,
      { params: data }
    );
    return response.data;
  }

  async getJobStatus(jobId: string): Promise<{
    status: string;
    progress: number;
    message: string;
    edit_id?: string;
  }> {
    const response = await this.client.get(`/api/jobs/${jobId}`);
    return response.data;
  }

  async getEditPreview(projectId: string, editId: string): Promise<PreviewResponse> {
    const response = await this.client.get(`/api/projects/${projectId}/edits/${editId}/preview`);
    return response.data;
  }

  async finalizeEdit(
    projectId: string,
    editId: string,
    data?: {
      output_name?: string;
      resolution?: string;
      codec?: string;
      bitrate?: string;
    }
  ): Promise<{ job_id: string; status: string; message: string }> {
    const response = await this.client.post(`/api/projects/${projectId}/edits/${editId}/finalize`, data);
    return response.data;
  }

  getDownloadUrl(projectId: string, editId: string): string {
    return `/api/projects/${projectId}/edits/${editId}/download`;
  }

  // ==================== Unified EDL HLS ====================

  async buildEdlStream(projectId: string, editId: string): Promise<{ success: boolean; edl_hash?: string; message?: string }> {
    const response = await this.client.post(`/api/projects/${projectId}/edits/${editId}/edl/build`);
    return response.data;
  }

  async getEdlStatus(projectId: string, editId: string): Promise<{ status: string; edl_hash?: string }> {
    const response = await this.client.get(`/api/projects/${projectId}/edits/${editId}/edl/status`);
    return response.data;
  }

  getEdlManifestUrl(projectId: string, editId: string): string {
    return `/api/projects/${projectId}/edits/${editId}/edl/manifest.m3u8`;
  }

  // Source video unified stream
  async buildSourceVideoEdl(projectId: string, videoId: string): Promise<{ status: string; message?: string }> {
    const response = await this.client.post(`/api/projects/${projectId}/source-videos/${videoId}/edl/build`);
    return response.data;
  }

  async getSourceVideoEdlStatus(projectId: string, videoId: string): Promise<{ status: string; edl_hash?: string }> {
    const response = await this.client.get(`/api/projects/${projectId}/source-videos/${videoId}/edl/status`);
    return response.data;
  }

  getSourceVideoEdlManifestUrl(projectId: string, videoId: string): string {
    return `/api/projects/${projectId}/source-videos/${videoId}/edl/manifest.m3u8`;
  }

}

// Get API base URL from environment or construct it dynamically
const getApiBaseUrl = (): string => {
  // Check if we have a custom API URL in environment
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  
  // If we're on localhost/127.0.0.1, use localhost:8000
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000';
  }
  
  // For network access, use the same hostname but port 8000
  const protocol = window.location.protocol;
  return `${protocol}//${hostname}:8000`;
};

// Export singleton instance
export const apiClient = new ApiClient(getApiBaseUrl());
export default apiClient;

