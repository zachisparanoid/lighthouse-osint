import { create } from "zustand";

import type { EntityType, User } from "./types";

interface AuthState {
  user: User | null;
  ready: boolean; // session restore attempt finished
  setUser: (u: User | null) => void;
  setReady: (r: boolean) => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  ready: false,
  setUser: (user) => set({ user }),
  setReady: (ready) => set({ ready }),
}));

export interface GraphFilters {
  types: EntityType[];
  minConfidence: number;
  query: string;
}

interface UiState {
  cmdkOpen: boolean;
  setCmdkOpen: (o: boolean) => void;
  selectedEntityId: string | null;
  setSelectedEntityId: (id: string | null) => void;
  focusEntityId: string | null; // graph "search-to-focus" target
  setFocusEntityId: (id: string | null) => void;
  graphFilters: GraphFilters;
  setGraphFilters: (f: Partial<GraphFilters>) => void;
  graphSnapshot: string | null; // base64 PNG of the graph, for report embedding
  setGraphSnapshot: (png: string | null) => void;
}

export const useUi = create<UiState>((set) => ({
  cmdkOpen: false,
  setCmdkOpen: (cmdkOpen) => set({ cmdkOpen }),
  selectedEntityId: null,
  setSelectedEntityId: (selectedEntityId) => set({ selectedEntityId }),
  focusEntityId: null,
  setFocusEntityId: (focusEntityId) => set({ focusEntityId }),
  graphFilters: { types: [], minConfidence: 0, query: "" },
  setGraphFilters: (f) => set((s) => ({ graphFilters: { ...s.graphFilters, ...f } })),
  graphSnapshot: null,
  setGraphSnapshot: (graphSnapshot) => set({ graphSnapshot }),
}));
