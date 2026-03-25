import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { MockDataProvider } from "./contexts/MockDataContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { ClusterConfigProvider } from "./contexts/ClusterConfigContext";
import ErrorBoundary from "./components/ErrorBoundary";

import './index.css';


ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <ClusterConfigProvider>
          <MockDataProvider><App /></MockDataProvider>
        </ClusterConfigProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
