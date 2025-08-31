import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogOverlay } from "../ui/dialog";
import { Button } from '../ui/button';
import { User, Bell, Lock, Palette, HelpCircle, X, Edit2, Shield, Eye } from 'lucide-react';
import { Switch } from '../ui/switch';
import { Separator } from '../ui/separator';

export default function SettingsModal({ isOpen, onOpenChange, currentUser }) {
  const [activeTab, setActiveTab] = useState('general'); // 'general', 'notifications', 'privacy', 'appearance'

  const renderTabContent = () => {
    switch (activeTab) {
      case 'general':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-800">General Settings</h3>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Language</span>
              <Button variant="ghost" size="sm" className="text-blue-600">English</Button>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Theme</span>
              <Button variant="ghost" size="sm" className="text-blue-600">System Default</Button>
            </div>
          </div>
        );
      case 'notifications':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-800">Notification Settings</h3>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Message Alerts</span>
              <Switch defaultChecked />
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Sound</span>
              <Switch />
            </div>
          </div>
        );
      case 'privacy':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-800">Privacy & Security</h3>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Last Seen & Online</span>
              <Button variant="ghost" size="sm" className="text-blue-600">Everybody</Button>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Blocked Users</span>
              <Button variant="ghost" size="sm" className="text-blue-600">Manage</Button>
            </div>
          </div>
        );
      case 'appearance':
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-800">Appearance Settings</h3>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Chat Background</span>
              <Button variant="ghost" size="sm" className="text-blue-600">Default</Button>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-blue-50/50 border border-blue-100">
              <span className="font-medium text-blue-800">Message Text Size</span>
              <Button variant="ghost" size="sm" className="text-blue-600">Medium</Button>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  const TabButton = ({ tabName, icon: Icon, label }) => (
    <Button
      variant="ghost"
      className={`w-full justify-start h-12 px-4 text-gray-700 ${activeTab === tabName ? 'bg-telegramBlueLight text-telegramBlue' : 'hover:bg-gray-100'}`}
      onClick={() => setActiveTab(tabName)}
    >
      <Icon className="w-5 h-5 mr-4" />
      {label}
    </Button>
  );

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogOverlay className="bg-black/60 backdrop-blur-sm" />
      <DialogContent className="max-w-3xl w-full h-[90vh] flex flex-col bg-white p-0 rounded-2xl shadow-2xl border-telegramBlueLight border">
        <DialogHeader className="p-6 pb-4 border-b border-gray-200 flex-row items-center justify-between">
          <DialogTitle className="text-2xl font-bold text-telegramBlueDark">Settings</DialogTitle>
          <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)} className="text-gray-500 hover:bg-gray-100">
            <X className="w-6 h-6" />
          </Button>
        </DialogHeader>

        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar for tabs */}
          <div className="w-64 border-r border-gray-200 p-4 space-y-1 overflow-y-auto">
            <TabButton tabName="general" icon={User} label="General" />
            <TabButton tabName="notifications" icon={Bell} label="Notifications" />
            <TabButton tabName="privacy" icon={Lock} label="Privacy and Security" />
            <TabButton tabName="appearance" icon={Palette} label="Appearance" />
            <Separator className="my-2" />
            <TabButton tabName="help" icon={HelpCircle} label="Help" />
          </div>

          {/* Content Area */}
          <div className="flex-1 p-6 overflow-y-auto">
            {renderTabContent()}
          </div>
        </div>

        <div className="p-4 bg-gray-50 border-t border-gray-200 flex justify-end rounded-b-2xl">
            <Button onClick={() => onOpenChange(false)} className="bg-telegramBlue hover:bg-telegramBlueDark text-white">Save Changes</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}