
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import CosmicBackground from './components/CosmicBackground.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <>
      <CosmicBackground />
      <div className="app-content">
        <App />
      </div>
    </>
  </React.StrictMode>
);
