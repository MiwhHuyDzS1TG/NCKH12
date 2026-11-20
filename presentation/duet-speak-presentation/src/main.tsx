import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource-variable/manrope';
import '@fontsource-variable/newsreader';
import './styles/base.css';
import './styles/slides.css';
import './styles/print.css';
import { App } from './app/App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
