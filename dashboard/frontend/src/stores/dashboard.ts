/**
 * Zustand Store for Dashboard UI State
 * Manages sidebar, theme, and other UI-related state
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

export type Theme = 'light' | 'dark' | 'system';

export interface DashboardState {
  // Sidebar state
  sidebarOpen: boolean;
  mobileSidebarOpen: boolean;

  // Theme state
  theme: Theme;
  mounted: boolean;

  // Layout state
  activePage: string;
  activeTab: string;

  // Modal state
  modals: {
    createExperiment: boolean;
    deleteExperiment: boolean;
    settings: boolean;
  };

  // UI state
  showNotifications: boolean;
  showSSE: boolean;

  // Actions
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleMobileSidebar: () => void;
  setMobileSidebarOpen: (open: boolean) => void;
  setTheme: (theme: Theme) => void;
  setActivePage: (page: string) => void;
  setActiveTab: (tab: string) => void;
  setModal: (name: keyof DashboardState['modals'], open: boolean) => void;
  setShowNotifications: (show: boolean) => void;
  setMounted: (mounted: boolean) => void;
  initializeTheme: () => void;
}

export const useDashboardStore = create<DashboardState>()(
  devtools((set, get) => ({
    // Initial state
    sidebarOpen: true,
    mobileSidebarOpen: false,
    theme: 'system',
    mounted: false,
    activePage: '/',
    activeTab: 'overview',
    modals: {
      createExperiment: false,
      deleteExperiment: false,
      settings: false,
    },
    showNotifications: true,
    showSSE: false,

    // Actions
    toggleSidebar: () => {
      const { sidebarOpen } = get();
      set({ sidebarOpen: !sidebarOpen });
    },

    setSidebarOpen: (open) => set({ sidebarOpen: open }),

    setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),

    toggleMobileSidebar: () => {
      const { mobileSidebarOpen } = get();
      set({ mobileSidebarOpen: !mobileSidebarOpen });
    },

    setTheme: (theme) => {
      const { mounted } = get();
      set({ theme });

      // Update localStorage
      localStorage.setItem('airfed-theme', theme);

      // Apply theme class to HTML element
      if (mounted) {
        const html = document.documentElement;
        if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
          html.classList.add('dark');
        } else {
          html.classList.remove('dark');
        }
      }
    },

    setActivePage: (page) => set({ activePage: page }),

    setActiveTab: (tab) => set({ activeTab: tab }),

    setModal: (name, open) =>
      set((state) => ({
        modals: {
          ...state.modals,
          [name]: open,
        },
      })),

    setShowNotifications: (show) => set({ showNotifications: show }),

    setMounted: (mounted) => set({ mounted }),

    initializeTheme: () => {
      const { theme, setMounted } = get();
      const storedTheme = localStorage.getItem('airfed-theme') as Theme | null;
      const effectiveTheme = storedTheme || theme;

      setMounted(true);

      const html = document.documentElement;
      if (effectiveTheme === 'dark' || (effectiveTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        html.classList.add('dark');
      } else {
        html.classList.remove('dark');
      }

      // Listen for system theme changes
      if (effectiveTheme === 'system') {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
          const html = document.documentElement;
          if (e.matches) {
            html.classList.add('dark');
          } else {
            html.classList.remove('dark');
          }
        });
      }
    },
  })),
);

// Export selectors
export const useSidebarState = (state: DashboardState) => state.sidebarOpen;
export const useThemeState = (state: DashboardState) => state.theme;
export const useActivePageState = (state: DashboardState) => state.activePage;

// Export hooks for convenience
export const useToggleSidebar = () => {
  const { toggleSidebar } = useDashboardStore.getState();
  return toggleSidebar;
};

export const useSetSidebarOpen = () => {
  const { setSidebarOpen } = useDashboardStore.getState();
  return setSidebarOpen;
};

export const useSetMobileSidebarOpen = () => {
  const { setMobileSidebarOpen } = useDashboardStore.getState();
  return setMobileSidebarOpen;
};

export const useSetTheme = () => {
  const { setTheme } = useDashboardStore.getState();
  return setTheme;
};

export default useDashboardStore;