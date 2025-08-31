
import React from "react";
import { format, isToday, isYesterday } from "date-fns";
import { Check, CheckCheck, Bookmark } from "lucide-react";
import { Badge } from "../ui/badge";

export default function ChatList({ chats, activeChat, onChatSelect, searchQuery, currentUser }) {
  const filteredChats = chats.filter(chat => 
    chat.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (chat.last_message && chat.last_message.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const formatTime = (dateString) => {
    if (!dateString) return "";
    const date = new Date(dateString);
    if (isToday(date)) return format(date, "HH:mm");
    if (isYesterday(date)) return "Yesterday";
    return format(date, "dd.MM.yy");
  };

  const getInitials = (name) => {
    if (!name) return '';
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  const sortedChats = [...filteredChats].sort((a, b) => {
    if (a.type === 'favorites' && b.type !== 'favorites') return -1;
    if (a.type !== 'favorites' && b.type === 'favorites') return 1;
    if (a.is_pinned !== b.is_pinned) return b.is_pinned - a.is_pinned;
    if (!a.last_message_time) return 1;
    if (!b.last_message_time) return -1;
    return new Date(b.last_message_time) - new Date(a.last_message_time);
  });

  const renderLastMessage = (chat) => {
    if (chat.type === 'favorites') {
      return <span className="text-sm text-gray-500">{chat.last_message || "Saved Messages"}</span>
    }

    const isOwnLastMessage = chat.last_message_sender_id === currentUser?.id;
    // For now, sender name is not available on chat object
    const senderName = isOwnLastMessage ? "You" : ""; // Placeholder
    const prefix = senderName ? `${senderName}: ` : "";
    
    return (
       <p className={`text-sm truncate ${
          chat.unread_count > 0 ? 'text-telegramBlue font-medium' : 'text-gray-500'
        }`}>
          {prefix}{chat.last_message || "No messages yet"}
        </p>
    )
  }

  return (
    <div className="h-full">
      {sortedChats.length === 0 ? (
        <div className="p-8 text-center">
          <p className="text-gray-400">No chats found</p>
        </div>
      ) : (
        <div className="divide-y divide-gray-100">
          {sortedChats.map((chat) => (
            <div
              key={chat.id}
              onClick={() => onChatSelect(chat)}
              className={`
                px-4 py-3 cursor-pointer hover:bg-telegramBlueLight transition-colors flex items-center gap-3
                ${activeChat?.id === chat.id ? 'bg-telegramBlueLight' : ''}
              `}
            >
              {/* Avatar */}
              <div className="relative flex-shrink-0">
                 {chat.type === 'favorites' ? (
                   <div className="w-12 h-12 rounded-full flex items-center justify-center bg-telegramBlue">
                     <Bookmark className="w-6 h-6 text-white" />
                   </div>
                 ) : chat.avatar_url ? (
                    <img
                      src={chat.avatar_url}
                      alt={chat.name}
                      className="w-12 h-12 rounded-full object-cover"
                    />
                  ) : (
                    <div className={`
                      w-12 h-12 rounded-full flex items-center justify-center text-white font-medium text-lg
                      ${chat.type === 'group'
                        ? 'bg-gradient-to-br from-avatarPurple-400 to-avatarPurple-600'
                        : 'bg-gradient-to-br from-avatarBlue-400 to-avatarBlue-600'
                      }
                    `}>
                      {getInitials(chat.name)}
                    </div>
                  )}
                  {chat.type === 'direct' && (
                    <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 bg-green-500 rounded-full border-2 border-white"></div>
                  )}
                </div>

                {/* Chat Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <h3 className={`font-semibold truncate text-base ${
                      chat.unread_count > 0 ? 'text-gray-900' : 'text-gray-800'
                    }`}>
                      {chat.name}
                    </h3>
                    <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                      {chat.unread_count === 0 && chat.type !== 'favorites' && (
                          <CheckCheck className="w-4 h-4 text-telegramBlue" />
                      )}
                      <span className="text-xs text-gray-500">
                        {formatTime(chat.last_message_time)}
                      </span>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between">
                      {renderLastMessage(chat)}
                      {chat.unread_count > 0 && (
                        <Badge className="bg-telegramBlue hover:bg-telegramBlue text-white text-xs px-1.5 py-0.5 rounded-full min-w-[20px] h-[20px] flex items-center justify-center">
                          {chat.unread_count > 99 ? '99+' : chat.unread_count}
                        </Badge>
                      )}
                  </div>
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
