import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

import Layout from './layout';
import MessengerPage from './pages/messenger';
import ArchivedPage from './pages/archived';

// We need to define User entity here for initial rendering, or pass it from a context/provider
// For now, let's create a dummy User entity or ensure it's loaded by MessengerPage/Layout
// In a real app, you'd likely have an AuthProvider or similar.
// For demonstration, we'll assume User.me() in Layout fetches it.

function MainApp() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout currentPageName="Messenger"><MessengerPage /></Layout>} />
        <Route path="/archived" element={<Layout currentPageName="Archived"><ArchivedPage /></Layout>} />
        {/* Add more routes here as needed */}
      </Routes>
    </Router>
  );
}

export default MainApp;