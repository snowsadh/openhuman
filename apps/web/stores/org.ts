import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface OrgState {
  orgId: string | null;
  orgName: string | null;
  loaded: boolean;

  setOrg: (id: string, name: string) => void;
  clearOrg: () => void;
}

export const useOrgStore = create<OrgState>()(
  persist(
    (set) => ({
      orgId: null,
      orgName: null,
      loaded: false,

      setOrg: (id, name) =>
        set({ orgId: id, orgName: name, loaded: true }),

      clearOrg: () =>
        set({
          orgId: null,
          orgName: null,
          loaded: false,
        }),
    }),
    {
      name: "oh-org",
      partialize: (state) => ({
        orgId: state.orgId,
        orgName: state.orgName,
        loaded: state.loaded,
      }),
    },
  ),
);
