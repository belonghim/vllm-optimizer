import { createContext, useState, useEffect, useMemo, useContext } from "react";
import type { ReactNode } from "react";

const STORAGE_KEY = "vllm-opt-mock-enabled";

interface MockDataContextValue {
  isMockEnabled: boolean;
  toggleMockEnabled: () => void;
}

const MockDataContext = createContext<MockDataContextValue>({
  isMockEnabled: true,
  toggleMockEnabled: () => {},
});

interface MockDataProviderProps {
  children: ReactNode;
}

export function MockDataProvider({ children }: MockDataProviderProps) {
  const [isMockEnabled, setIsMockEnabled] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? false : stored === "true";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(isMockEnabled));
  }, [isMockEnabled]);

  const toggleMockEnabled = () => setIsMockEnabled(prev => !prev);

  const value = useMemo(
    () => ({ isMockEnabled, toggleMockEnabled }),
    [isMockEnabled]
  );

  return (
    <MockDataContext.Provider value={value}>
      {children}
    </MockDataContext.Provider>
  );
}

export function useMockData(): MockDataContextValue {
  return useContext(MockDataContext);
}
