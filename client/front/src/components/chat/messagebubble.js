
import React from "react";
import { format } from "date-fns";
import { Check, CheckCheck, Clock, File } from "lucide-react";
import { User } from "../../entities/User";

export default function MessageBubble({ message, showAvatar = true, isFavoritesChat = false }) {
  const [currentUser, setCurrentUser] = React.useState(null);

  React.useEffect(() => {
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

  const formatTime = (dateString) => {
    if (!dateString) return format(new Date(), "HH:mm");
    return format(new Date(dateString), "HH:mm");
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'sending':
        return <Clock className="w-4 h-4 text-gray-400" />;
      case 'sent':
        return <Check className="w-4 h-4 text-gray-400" />;
      case 'delivered':
        return <CheckCheck className="w-4 h-4 text-gray-400" />;
      case 'read':
        return <CheckCheck className="w-4 h-4 text-[#0088cc]" />;
      default:
        return null;
    }
  };

  const isOwnMessage = !isFavoritesChat && currentUser && message.sender_id === currentUser.id;

  const renderContent = () => {
    switch (message.message_type) {
      case 'image':
        return (
          <a href={message.file_url} target="_blank" rel="noopener noreferrer">
            <img
              src={message.file_url}
              alt="Shared image"
              className="rounded-lg max-w-full h-auto cursor-pointer max-w-xs"
            />
          </a>
        );
      case 'file':
        return (
          <div className="flex items-center gap-3 bg-gray-100 p-3 rounded-lg max-w-xs">
            <File className="w-8 h-8 text-gray-500 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800 truncate">{message.content}</p>
              <a 
                href={message.file_url} 
                target="_blank" 
                rel="noopener noreferrer" 
                download={message.content}
                className="text-xs text-[#0088cc] hover:underline"
              >
                Download
              </a>
            </div>
          </div>
        );
      default:
        return (
          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
            {message.content}
          </p>
        );
    }
  };

  if (isFavoritesChat) {
     return (
        <div className="flex justify-start gap-2 mb-3">
             <div className="max-w-xs sm:max-w-md">
                <div className="px-3 py-2 rounded-2xl shadow-sm relative bg-white text-gray-900 border border-gray-200 rounded-bl-md">
                    <div className="space-y-1">
                        {renderContent()}
                        <div className="flex items-center gap-1 justify-end text-xs mt-1 text-gray-400">
                            <span>{formatTime(message.timestamp || message.created_date)}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
  }

  return (
    <div className={`flex gap-2 mb-3 ${isOwnMessage ? 'justify-end' : 'justify-start'}`}>
      {/* Avatar (placeholder for alignment) */}
      {!isOwnMessage && (
        <div className={`w-8 flex-shrink-0 ${showAvatar ? '' : 'invisible'}`}>
          {/* Avatar would be here in a group chat */}
        </div>
      )}
      
      {/* Message Container */}
      <div className={`max-w-xs sm:max-w-md ${isOwnMessage ? 'order-1' : ''}`}>
        {/* Message Bubble */}
        <div
          className={`
            px-3 py-2 rounded-2xl shadow-sm relative
            ${isOwnMessage
              ? 'bg-[#e1ffc7] text-gray-900 rounded-br-md'
              : 'bg-white text-gray-900 border border-gray-200 rounded-bl-md'
            }
          `}
        >
          {/* Message Content */}
          <div className="space-y-1">
            {renderContent()}

            {/* Message Meta */}
            <div className={`flex items-center gap-1 justify-end text-xs mt-1 ${
              isOwnMessage ? 'text-gray-500' : 'text-gray-400'
            }`}>
              <span>{formatTime(message.timestamp || message.created_date)}</span>
              {isOwnMessage && getStatusIcon(message.status)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
