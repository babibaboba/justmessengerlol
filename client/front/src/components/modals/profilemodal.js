import React from 'react';
import { Dialog, DialogContent, DialogOverlay } from "../ui/dialog";
import { Button } from '../ui/button';
import { User, Mail, Phone, Bell, X, Camera } from 'lucide-react';
import { Switch } from '../ui/switch';

export default function ProfileModal({ isOpen, onOpenChange, user }) {
  if (!user) return null;

  const getInitials = (name) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };
  
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogOverlay className="bg-black/60 backdrop-blur-sm" />
      <DialogContent className="max-w-sm w-full bg-gray-50 p-0 rounded-2xl shadow-2xl border-0">
        <div className="relative">
          <div className="h-24 bg-gradient-to-br from-telegramBlue to-telegramBlueDark"></div>
          <div className="absolute top-12 left-1/2 -translate-x-1/2 w-24 h-24 rounded-full bg-white border-4 border-gray-50 flex items-center justify-center">
             {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.full_name} className="w-full h-full rounded-full object-cover" />
             ) : (
                <span className="text-3xl font-bold text-telegramBlue">{getInitials(user.full_name)}</span>
             )}
             <Button size="icon" className="absolute bottom-0 right-0 w-8 h-8 bg-telegramBlue hover:bg-telegramBlueDark rounded-full border-2 border-gray-50">
                <Camera className="w-4 h-4 text-white"/>
             </Button>
          </div>
        </div>
        
        <div className="pt-20 pb-8 px-6 text-center">
            <h2 className="text-2xl font-bold text-gray-800">{user.full_name}</h2>
            <p className="text-sm text-gray-500">last seen recently</p>
        </div>

        <div className="px-6 pb-6 space-y-4">
            <div className="flex items-start gap-4">
                <Mail className="w-5 h-5 text-gray-400 mt-1"/>
                <div>
                    <p className="font-medium text-gray-800">{user.email}</p>
                    <p className="text-xs text-gray-400">Email</p>
                </div>
            </div>
             <div className="flex items-start gap-4">
                <Phone className="w-5 h-5 text-gray-400 mt-1"/>
                <div>
                    <p className="font-medium text-gray-800">{user.phone_number || 'N/A'}</p>
                    <p className="text-xs text-gray-400">Mobile</p>
                </div>
            </div>
             <div className="flex items-center gap-4">
                <Bell className="w-5 h-5 text-gray-400"/>
                <p className="font-medium text-gray-800">Notifications</p>
                <Switch defaultChecked className="ml-auto" /> {/* Replaced Button with Switch */}
            </div>
        </div>

      </DialogContent>
    </Dialog>
  );
}