import React from "react";
import { Button } from "../ui/button";
import { Phone, Video, MoreVertical, ArrowLeft, Bookmark } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

export default function ChatHeader({ chat, onBack, isMobile = false, onProfileClick }) {
  if (!chat) {
    return null;
  }

  const getInitials = (name) => {
    if (!name) return '';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  return (
    <div className="h-16 bg-white border-b border-gray-200 px-4 flex items-center justify-between flex-shrink-0">
      <div className="flex items-center gap-3">
        {isMobile && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onBack}
            className="text-gray-500 hover:bg-gray-100 -ml-2"
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
        )}
        
        <div onClick={onProfileClick} className="flex items-center gap-3 cursor-pointer">
            {/* Chat Avatar */}
            {chat.type === 'favorites' ? (
                <div className="w-10 h-10 rounded-full flex items-center justify-center bg-telegramBlue">
                    <Bookmark className="w-5 h-5 text-white" />
                </div>
            ) : chat.avatar_url ? (
              <img
                src={chat.avatar_url}
                alt={chat.name}
                className="w-10 h-10 rounded-full object-cover"
              />
            ) : (
              <div className={`
                w-10 h-10 rounded-full flex items-center justify-center text-white font-medium text-sm
                ${chat.type === 'group'
                  ? 'bg-gradient-to-br from-avatarPurple-400 to-avatarPurple-600'
                  : 'bg-gradient-to-br from-avatarBlue-400 to-avatarBlue-600'
                }
              `}>
                {getInitials(chat.name)}
              </div>
            )}

            {/* Chat Info */}
            <div>
              <h2 className="font-medium text-gray-900">{chat.name}</h2>
              <p className="text-xs text-gray-500">
                {chat.type === 'favorites' 
                  ? 'Saved Messages' 
                  : chat.type === 'group' 
                    ? `${chat.participants?.length || 0} members` 
                    : 'last seen recently'}
              </p>
            </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-1">
        {chat.type !== 'favorites' && (
           <Button variant="ghost" size="icon" className="text-telegramBlue hover:bg-telegramBlueLight">
             <Phone className="w-5 h-5" />
           </Button>
        )}
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="text-telegramBlue hover:bg-telegramBlueLight">
                    <MoreVertical className="w-5 h-5" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={onProfileClick}>View Profile</DropdownMenuItem>
                <DropdownMenuItem>Mute Notifications</DropdownMenuItem>
                <DropdownMenuItem>Clear Chat History</DropdownMenuItem>
                <DropdownMenuItem className="text-red-600 focus:bg-red-50">Delete Chat</DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}