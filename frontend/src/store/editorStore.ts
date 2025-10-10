/**
 * Zustand store for editor state (EDL management, playback, etc.)
 */

import { create } from 'zustand';
import { Edit, EditDecision } from '../api/client';

interface EditorStore {
  // Current edit
  currentEdit: Edit | null;
  editDecisions: EditDecision[];
  
  // Playback state
  isPlaying: boolean;
  currentTime: number;
  currentClipIndex: number;
  
  // UI state
  selectedDecisions: string[];
  showExcluded: boolean;
  
  // Undo/Redo stacks
  undoStack: EditDecision[][];
  redoStack: EditDecision[][];
  
  // Actions
  setCurrentEdit: (edit: Edit | null) => void;
  setEditDecisions: (decisions: EditDecision[]) => void;
  
  // Playback actions
  setIsPlaying: (playing: boolean) => void;
  setCurrentTime: (time: number) => void;
  setCurrentClipIndex: (index: number) => void;
  
  // Selection actions
  toggleDecisionSelection: (decisionId: string) => void;
  clearSelection: () => void;
  selectMultiple: (decisionIds: string[]) => void;
  
  // UI actions
  setShowExcluded: (show: boolean) => void;
  
  // EDL manipulation
  toggleDecisionInclusion: (decisionId: string) => void;
  reorderDecisions: (newOrder: EditDecision[]) => void;
  updateDecision: (decisionId: string, updates: Partial<EditDecision>) => void;
  removeDecision: (decisionId: string) => void;
  
  // Undo/Redo
  undo: () => void;
  redo: () => void;
  saveToHistory: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  // Initial state
  currentEdit: null,
  editDecisions: [],
  
  // Playback state
  isPlaying: false,
  currentTime: 0,
  currentClipIndex: 0,
  
  // UI state
  selectedDecisions: [],
  showExcluded: false,
  
  // Undo/Redo
  undoStack: [],
  redoStack: [],
  
  // Actions
  setCurrentEdit: (edit) => set({ currentEdit: edit }),
  
  setEditDecisions: (decisions) => set({ editDecisions: decisions }),
  
  // Playback
  setIsPlaying: (playing) => set({ isPlaying: playing }),
  
  setCurrentTime: (time) => set({ currentTime: time }),
  
  setCurrentClipIndex: (index) => set({ currentClipIndex: index }),
  
  // Selection
  toggleDecisionSelection: (decisionId) =>
    set((state) => ({
      selectedDecisions: state.selectedDecisions.includes(decisionId)
        ? state.selectedDecisions.filter((id) => id !== decisionId)
        : [...state.selectedDecisions, decisionId],
    })),
  
  clearSelection: () => set({ selectedDecisions: [] }),
  
  selectMultiple: (decisionIds) => set({ selectedDecisions: decisionIds }),
  
  // UI
  setShowExcluded: (show) => set({ showExcluded: show }),
  
  // EDL manipulation
  toggleDecisionInclusion: (decisionId) => {
    const state = get();
    state.saveToHistory();
    
    set({
      editDecisions: state.editDecisions.map((d) =>
        d.id === decisionId
          ? { ...d, is_included: !d.is_included, user_modified: true }
          : d
      ),
    });
  },
  
  reorderDecisions: (newOrder) => {
    const state = get();
    state.saveToHistory();
    
    set({
      editDecisions: newOrder.map((d, index) => ({
        ...d,
        order_index: index,
        user_modified: true,
      })),
    });
  },
  
  updateDecision: (decisionId, updates) => {
    const state = get();
    state.saveToHistory();
    
    set({
      editDecisions: state.editDecisions.map((d) =>
        d.id === decisionId ? { ...d, ...updates, user_modified: true } : d
      ),
    });
  },
  
  removeDecision: (decisionId) => {
    const state = get();
    state.saveToHistory();
    
    set({
      editDecisions: state.editDecisions.filter((d) => d.id !== decisionId),
    });
  },
  
  // Undo/Redo
  saveToHistory: () =>
    set((state) => ({
      undoStack: [...state.undoStack, state.editDecisions],
      redoStack: [], // Clear redo stack on new action
    })),
  
  undo: () =>
    set((state) => {
      if (state.undoStack.length === 0) return state;
      
      const previous = state.undoStack[state.undoStack.length - 1];
      const newUndoStack = state.undoStack.slice(0, -1);
      
      return {
        editDecisions: previous,
        undoStack: newUndoStack,
        redoStack: [...state.redoStack, state.editDecisions],
      };
    }),
  
  redo: () =>
    set((state) => {
      if (state.redoStack.length === 0) return state;
      
      const next = state.redoStack[state.redoStack.length - 1];
      const newRedoStack = state.redoStack.slice(0, -1);
      
      return {
        editDecisions: next,
        redoStack: newRedoStack,
        undoStack: [...state.undoStack, state.editDecisions],
      };
    }),
  
  canUndo: () => get().undoStack.length > 0,
  
  canRedo: () => get().redoStack.length > 0,
}));

