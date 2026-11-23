import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header';
import Footer from './components/Footer';
import Dashboard from './pages/Dashboard';
import ReviewWorkspace from './pages/ReviewWorkspace';
import ExportView from './pages/ExportView';
import SummaryView from './pages/SummaryView';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100 font-sans">
        <Header />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/review/:documentId" element={<ReviewWorkspace />} />
            <Route path="/export/:documentId" element={<ExportView />} />
            <Route path="/summary/:documentId" element={<SummaryView />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  );
}
