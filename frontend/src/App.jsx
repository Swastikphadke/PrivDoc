import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header';
import Footer from './components/Footer';
import Dashboard from './pages/Dashboard';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100 font-sans">
        <Header />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  );
}
