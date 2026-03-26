import { createContext, useState, useContext } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";

interface BenchmarkSelectionContextValue {
  selectedIds: (string | number)[];
  setSelectedIds: Dispatch<SetStateAction<(string | number)[]>>;
}

const BenchmarkSelectionContext = createContext<BenchmarkSelectionContextValue>({
  selectedIds: [],
  setSelectedIds: () => {},
});

interface BenchmarkSelectionProviderProps {
  children: ReactNode;
}

export function BenchmarkSelectionProvider({ children }: BenchmarkSelectionProviderProps): React.JSX.Element {
  const [selectedIds, setSelectedIds] = useState<(string | number)[]>([]);
  return (
    <BenchmarkSelectionContext.Provider value={{ selectedIds, setSelectedIds }}>
      {children}
    </BenchmarkSelectionContext.Provider>
  );
}

export function useBenchmarkSelection(): BenchmarkSelectionContextValue {
  return useContext(BenchmarkSelectionContext);
}
