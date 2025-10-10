/**
 * Zustand store for project management state.
 */

import { create } from 'zustand';
import { Project, SourceVideo, Edit } from '../api/client';

interface ProjectStore {
  // Current state
  projects: Project[];
  currentProject: Project | null;
  currentProjectVideos: SourceVideo[];
  currentProjectEdits: Edit[];
  isLoading: boolean;
  error: string | null;

  // Actions
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project | null) => void;
  setCurrentProjectVideos: (videos: SourceVideo[]) => void;
  setCurrentProjectEdits: (edits: Edit[]) => void;
  setIsLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  
  // Optimistic updates
  addProject: (project: Project) => void;
  updateProject: (projectId: string, updates: Partial<Project>) => void;
  removeProject: (projectId: string) => void;
}

export const useProjectStore = create<ProjectStore>((set) => ({
  // Initial state
  projects: [],
  currentProject: null,
  currentProjectVideos: [],
  currentProjectEdits: [],
  isLoading: false,
  error: null,

  // Actions
  setProjects: (projects) => set({ projects }),
  
  setCurrentProject: (project) => set({ currentProject: project }),
  
  setCurrentProjectVideos: (videos) => set({ currentProjectVideos: videos }),
  
  setCurrentProjectEdits: (edits) => set({ currentProjectEdits: edits }),
  
  setIsLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  clearError: () => set({ error: null }),
  
  // Optimistic updates
  addProject: (project) =>
    set((state) => ({
      projects: [project, ...state.projects],
    })),
  
  updateProject: (projectId, updates) =>
    set((state) => ({
      projects: state.projects.map((p) =>
        p.id === projectId ? { ...p, ...updates } : p
      ),
      currentProject:
        state.currentProject?.id === projectId
          ? { ...state.currentProject, ...updates }
          : state.currentProject,
    })),
  
  removeProject: (projectId) =>
    set((state) => ({
      projects: state.projects.filter((p) => p.id !== projectId),
      currentProject:
        state.currentProject?.id === projectId ? null : state.currentProject,
    })),
}));

