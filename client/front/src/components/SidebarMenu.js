import React from "react";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { Archive, Settings, HelpCircle, LogOut } from "lucide-react";
import { Link } from "react-router-dom";
import { createPageUrl } from "../utils";

export default function SidebarMenu({ currentUser, onOpenSettings, onLogout }) {
  return (
    <>
      <div className="bg-telegramBlue text-white p-6">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center">
             <span className="text-white text-xl font-bold">{currentUser?.full_name?.[0]?.toUpperCase() || 'U'}</span>
          </div>
          <div>
            <h3 className="font-semibold text-lg">{currentUser?.full_name || 'User'}</h3>
            <p className="text-white/80 text-sm">{currentUser?.email}</p>
          </div>
        </div>
      </div>
      <div className="py-4">
        <div className="space-y-1 px-2">
          <Button asChild variant="ghost" className="w-full justify-start h-12 px-4 text-gray-700 hover:bg-gray-100">
            <Link to={createPageUrl('Archived')}>
              <Archive className="w-5 h-5 mr-4" />
              Archived Chats
            </Link>
          </Button>
          <Button onClick={onOpenSettings} variant="ghost" className="w-full justify-start h-12 px-4 text-gray-700 hover:bg-telegramBlueLight hover:text-telegramBlue">
            <Settings className="w-5 h-5 mr-4" />
            Settings
          </Button>
        </div>
        <Separator className="my-4" />
        <div className="space-y-1 px-2">
           <Button variant="ghost" className="w-full justify-start h-12 px-4 text-gray-700 hover:bg-gray-100">
            <HelpCircle className="w-5 h-5 mr-4" />
            Help
          </Button>
          <Button onClick={onLogout} variant="ghost" className="w-full justify-start h-12 px-4 text-red-600 hover:bg-red-50">
            <LogOut className="w-5 h-5 mr-4" />
            Log Out
          </Button>
        </div>
      </div>
    </>
  );
}