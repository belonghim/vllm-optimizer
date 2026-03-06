import { createContext, useState, useEffect, useMemo, useContext } from "react";

const STORAGE_KEY = "vllm-opt-mock-enabled";

const MockDataContext = createContext({
  isMockEnabled: true,
  toggleMockEnabled: () => {},
});

export function MockDataProvider({ children }) {
  const [isMockEnabled, setIsMockEnabled] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? true : stored === "true";
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

export function useMockData() {
  return useContext(MockDataContext);
}