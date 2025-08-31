import React from 'react';
import { Archive, ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Link } from 'react-router-dom';
import { createPageUrl } from "../utils";

export default function ArchivedPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full bg-gray-50 text-center p-8">
      <Archive className="w-24 h-24 text-telegramBlueLight mb-6" />
      <h1 className="text-3xl font-bold text-telegramBlueDark mb-3">Archived Chats</h1>
      <p className="text-gray-600 max-w-md mb-8">
        Your past conversations and channels will appear here once archived.
        This feature is currently under development.
      </p>
      <Link to={createPageUrl('Messenger')}>
        <Button className="bg-telegramBlue hover:bg-telegramBlueDark text-white flex items-center gap-2 px-6 py-3 rounded-full shadow-md">
          <ArrowLeft className="w-5 h-5" />
          Back to Chats
        </Button>
      </Link>
    </div>
  );
}