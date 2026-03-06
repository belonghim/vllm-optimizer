import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { MockDataProvider } from "./contexts/MockDataContext";

import './index.css';


ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
      <MockDataProvider><App /></MockDataProvider>
  </React.StrictMode>,
)
