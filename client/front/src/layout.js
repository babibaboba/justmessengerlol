import React, { useState, useEffect } from "react";
import { User } from "./entities/user";
import { Button } from "./components/ui/button";
import { Menu } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "./components/ui/sheet";
import SettingsModal from "./components/modals/settingsModal";
import { createPageUrl } from "./utils";
import { Link } from "react-router-dom";
import SidebarMenu from "./components/SidebarMenu";

export default function Layout({ children, currentPageName }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const user = await User.me();
        setCurrentUser(user);
      } catch (error) {
        console.error("Error loading user:", error);
      }
    };
    loadUser();
  }, []);

  const handleLogout = async () => {
    await User.logout();
    window.location.reload();
  };

  const handleOpenSettings = () => {
    setIsSettingsOpen(true);
  };

  // Simple wrapper for non-messenger pages
  if (currentPageName !== 'Messenger') {
    return (
      <div className="h-screen bg-white flex flex-col">
        <header className="bg-telegramBlue text-white px-4 py-3 flex items-center gap-4">
           <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/20">
                <Menu className="w-6 h-6" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-80 p-0 bg-white">
              <SidebarMenu
                currentUser={currentUser}
                onOpenSettings={handleOpenSettings}
                onLogout={handleLogout}
              />
            </SheetContent>
          </Sheet>
          <h1 className="font-medium text-lg">{currentPageName}</h1>
        </header>
        <main className="flex-1 overflow-auto">{children}</main>
        <SettingsModal isOpen={isSettingsOpen} onOpenChange={setIsSettingsOpen} currentUser={currentUser} />
      </div>
    )
  }

  // Telegram-like layout for Messenger page
  return (
    <div className="h-screen bg-white flex flex-row overflow-hidden">
      <div className="hidden lg:flex flex-col w-[320px] border-r border-gray-200">
          <div className="p-2 h-16 flex items-center">
             <Sheet>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="text-gray-500">
                      <Menu className="w-6 h-6" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="w-80 p-0 bg-white">
                  <SidebarMenu
                    currentUser={currentUser}
                    onOpenSettings={handleOpenSettings}
                    onLogout={handleLogout}
                  />
                </SheetContent>
              </Sheet>
          </div>
      </div>
      
      <main className="flex-1 flex overflow-hidden">
        {children}
      </main>

      <SettingsModal isOpen={isSettingsOpen} onOpenChange={setIsSettingsOpen} currentUser={currentUser} />
    </div>
  );
}