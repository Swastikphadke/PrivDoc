import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header';
import Footer from './components/Footer';
import Dashboard from './pages/Dashboard';
import ReviewWorkspace from './pages/ReviewWorkspace';
import ExportView from './pages/ExportView';
import SummaryView from './pages/SummaryView';

export default function App() {
  return (
    <div className="min-h-screen flex flex-col bg-[#070b14] text-slate-100 font-sans selection:bg-sky-500/30 selection:text-sky-100">
      <Header />
      <main className="flex-1 flex flex-col">
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
  );
}
