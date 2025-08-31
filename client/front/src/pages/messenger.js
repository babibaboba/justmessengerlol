
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Chat } from "../entities/chat";
import { Message } from "../entities/message";
import { User } from "../entities/user";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Search, Plus, Menu } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "../components/ui/sheet";

import ChatList from "../components/chat/chatList";
import MessageBubble from "../components/chat/messageBubble";
import MessageInput from "../components/chat/messageInput";
import ChatHeader from "../components/chat/chatHeader";
import ProfileModal from "../components/modals/profileModal";
import SettingsModal from "../components/modals/settingsModal"; // New import
import SidebarMenu from "../components/SidebarMenu"; // New import

export default function MessengerPage() {
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [currentUser, setCurrentUser] = useState(null);
  const [showMobileChat, setShowMobileChat] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [profileUser, setProfileUser] = useState(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false); // New state for SettingsModal
  const messagesEndRef = useRef(null);

  const loadChats = useCallback(async () => {
    try {
      const chatList = await Chat.list('-last_message_time');
      setChats(chatList);
    } catch (error) {
      console.error("Error loading chats:", error);
    }
  }, []);

  useEffect(() => {
    const ensureFavoritesChatExists = async (userId) => {
      const existingFavorites = await Chat.filter({
        type: 'favorites',
        participants: [userId]
      });
      if (existingFavorites.length === 0) {
        await Chat.create({
          name: 'Favorites',
          type: 'favorites',
          participants: [userId],
          last_message: 'Saved Messages'
        });
      }
    };

    const loadCurrentUserAndData = async () => {
      try {
        const user = await User.me();
        setCurrentUser(user);
        await ensureFavoritesChatExists(user.id);
        await loadChats();
      } catch (error) {
        console.error("Error loading user and data:", error);
      }
    };
    
    loadCurrentUserAndData();
  }, [loadChats]);

  useEffect(() => {
    if (activeChat) {
      loadMessages(activeChat.id);
      setShowMobileChat(true);
    } else {
      setShowMobileChat(false);
    }
  }, [activeChat]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const loadMessages = async (chatId) => {
    try {
      const messageList = await Message.filter({ chat_id: chatId }, 'timestamp');
      setMessages(messageList);
    } catch (error) {
      console.error("Error loading messages:", error);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleChatSelect = (chat) => {
    setActiveChat(chat);
    if (chat.unread_count > 0) {
      Chat.update(chat.id, { unread_count: 0 });
      loadChats();
    }
  };

  const handleSendMessage = async (messageData) => {
    if (!activeChat || !currentUser) return;

    try {
      const newMessage = {
        ...messageData,
        chat_id: activeChat.id,
        sender_id: currentUser.id,
        timestamp: new Date().toISOString(),
        status: 'sent'
      };

      const tempMessage = { ...newMessage, id: `temp-${Date.now()}` };
      setMessages(prev => [...prev, tempMessage]);
      scrollToBottom();

      const createdMessage = await Message.create(newMessage);
      
      setMessages(prev => prev.map(m => m.id === tempMessage.id ? { ...createdMessage, id: createdMessage.id } : m));
      
      await Chat.update(activeChat.id, {
        last_message: messageData.message_type === 'text' ? messageData.content : 'Sent an attachment',
        last_message_time: newMessage.timestamp
      });
      
      setTimeout(loadChats, 300);

    } catch (error) {
      console.error("Error sending message:", error);
      setMessages(prev => prev.filter(m => !m.id.startsWith('temp-')));
    }
  };

  const handleBackToChats = () => {
    setShowMobileChat(false);
    setActiveChat(null);
  };
  
  const handleOpenProfile = async () => {
      // For now, it opens the current user's profile.
      // This can be expanded to show other users' profiles.
      if(activeChat.type === 'direct'){
          // This part is a placeholder for fetching the other participant's data
          // Currently opens the current user's profile as a fallback
          setProfileUser(currentUser);
      } else {
          setProfileUser(currentUser); // Default to own profile for group/favorites
      }
      setIsProfileOpen(true);
  }

  return (
    <>
      <div className="h-full flex w-full">
        {/* Chat List Panel */}
        <div className={`
          w-full lg:w-full lg:flex-shrink-0 bg-white flex flex-col border-r border-gray-200
          ${showMobileChat ? 'hidden lg:flex' : 'flex'}
        `}>
          {/* Header for Mobile - includes menu */}
           <div className="lg:hidden p-2 h-16 flex items-center bg-telegramBlue text-white">
                <Sheet>
                    <SheetTrigger asChild>
                        <Button variant="ghost" size="icon" className="text-white hover:bg-white/20"><Menu /></Button>
                    </SheetTrigger>
                    <SheetContent side="left" className="w-full sm:max-w-xs p-0 bg-white">
                       <SidebarMenu
                         currentUser={currentUser}
                         onOpenSettings={() => setIsSettingsOpen(true)}
                         onLogout={async () => { await User.logout(); window.location.reload(); }}
                       />
                    </SheetContent>
                </Sheet>
                <div className="relative flex-1 mx-2">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/70" />
                    <Input
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search"
                      className="pl-10 bg-white/30 text-white placeholder:text-white/70 border-0 rounded-full h-10 text-sm focus:bg-white/40"
                    />
                </div>
           </div>

          {/* Search Header for Desktop */}
          <div className="hidden lg:flex p-2 h-16 items-center border-b border-gray-200 bg-white">
            <div className="relative flex-1 mx-2">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search"
                className="pl-10 bg-gray-50 border-gray-200 rounded-full h-10 text-sm focus:bg-white"
              />
            </div>
          </div>

          {/* Chat List */}
          <div className="flex-1 overflow-y-auto">
            <ChatList
              chats={chats}
              activeChat={activeChat}
              onChatSelect={handleChatSelect}
              searchQuery={searchQuery}
              currentUser={currentUser}
            />
          </div>

          {/* Floating Action Button */}
          <div className="absolute bottom-6 right-6 lg:hidden">
            <Button className="w-14 h-14 rounded-full bg-telegramBlue hover:bg-telegramBlueDark shadow-lg">
              <Plus className="w-6 h-6" />
            </Button>
          </div>
        </div>

        {/* Chat Area */}
        <div className={`
          flex-1 flex flex-col bg-gray-50 border-l border-gray-200
          ${showMobileChat ? 'flex' : 'hidden lg:flex'}
        `}>
          {activeChat ? (
            <>
              {/* Chat Header */}
              <ChatHeader
                chat={activeChat}
                onBack={handleBackToChats}
                isMobile={showMobileChat}
                onProfileClick={handleOpenProfile}
              />

              {/* Messages Area */}
              <div className="flex-1 overflow-y-auto p-4 bg-gray-50">
                {messages.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center h-full">
                    <div className="text-center">
                      <div className="text-6xl mb-4">💬</div>
                      <p className="text-gray-500 text-lg">No messages here yet...</p>
                      <p className="text-gray-400 text-sm">Send a message to start the conversation</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {messages.map((message, index) => {
                      const prevMessage = messages[index - 1];
                      const showAvatar = activeChat.type !== 'favorites' && (!prevMessage || prevMessage.sender_id !== message.sender_id);
                      
                      return (
                        <MessageBubble
                          key={message.id}
                          message={message}
                          showAvatar={showAvatar}
                          isFavoritesChat={activeChat.type === 'favorites'}
                        />
                      );
                    })}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              {/* Message Input */}
              <MessageInput
                onSendMessage={handleSendMessage}
                disabled={!currentUser}
              />
            </>
          ) : (
            <div className="flex-1 hidden lg:flex items-center justify-center bg-gray-50">
              <div className="text-center">
                <div className="text-8xl mb-6">💌</div>
                <h3 className="text-2xl font-medium text-gray-900 mb-2">JustMessenger</h3>
                <p className="text-gray-500">Select a chat to start messaging</p>
              </div>
            </div>
          )}
        </div>
      </div>
      <ProfileModal isOpen={isProfileOpen} onOpenChange={setIsProfileOpen} user={profileUser} />
      <SettingsModal isOpen={isSettingsOpen} onOpenChange={setIsSettingsOpen} currentUser={currentUser} />
    </>
  );
}
