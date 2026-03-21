import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { MockDataProvider } from "./contexts/MockDataContext";
import { ClusterConfigProvider } from "./contexts/ClusterConfigContext";

import './index.css';


ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClusterConfigProvider>
      <MockDataProvider><App /></MockDataProvider>
    </ClusterConfigProvider>
  </React.StrictMode>,
)
