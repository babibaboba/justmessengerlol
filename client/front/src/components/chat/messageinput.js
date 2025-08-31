
import React, { useState, useRef } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Send, Paperclip, Smile, Mic, MicOff } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { UploadFile } from "../../integrations/Core";

const emojis = ['😀', '😂', '❤️', '👍', '🙏', '🎉', '🔥', '🤔', '😢', '😡', '🥰', '😎'];

export default function MessageInput({ onSendMessage, disabled = false }) {
  const [message, setMessage] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleSendMessageInternal = (messageData) => {
    if (disabled) return;
    onSendMessage(messageData);
    setMessage("");
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (message.trim()) {
      handleSendMessageInternal({
        content: message.trim(),
        message_type: "text"
      });
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsUploading(true);
    try {
      const { file_url } = await UploadFile({ file });
      const messageType = file.type.startsWith("image/") ? "image" : "file";
      
      handleSendMessageInternal({
        content: file.name,
        message_type: messageType,
        file_url: file_url,
      });
    } catch (error) {
      console.error("Error uploading file:", error);
    } finally {
      setIsUploading(false);
      if(fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleEmojiClick = (emoji) => {
    setMessage(prev => prev + emoji);
  };

  return (
    <div className="border-t border-gray-200 bg-white p-2 sm:p-4">
      <form onSubmit={handleSubmit} className="flex items-end gap-2 sm:gap-3">
        {/* File Input */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
        />
        
        {/* Attachment Button */}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={handleAttachClick}
          disabled={isUploading || disabled}
          className="text-gray-500 hover:text-gray-700 hover:bg-gray-100 flex-shrink-0"
        >
          <Paperclip className="w-5 h-5" />
        </Button>

        {/* Message Input */}
        <div className="flex-1 relative">
          <Input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isUploading ? "Uploading..." : "Message"}
            disabled={disabled || isUploading}
            className="pr-12 py-3 rounded-full border-gray-300 bg-gray-50 focus:bg-white transition-colors h-12"
          />
          
          <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="text-gray-400 hover:text-gray-600 w-9 h-9"
                >
                  <Smile className="w-5 h-5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-3">
                <div className="grid grid-cols-6 gap-2">
                  {emojis.map(emoji => (
                    <button
                      key={emoji}
                      onClick={() => handleEmojiClick(emoji)}
                      className="text-xl hover:bg-gray-100 rounded-md p-1 transition-colors"
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>

        {/* Send / Mic Button */}
        <Button
          type={message.trim() ? "submit" : "button"}
          disabled={disabled || isUploading}
          size="icon"
          className="bg-[#0088cc] hover:bg-[#0077b5] text-white rounded-full flex-shrink-0 w-12 h-12 transition-all duration-300 ease-in-out"
        >
          {message.trim() ? (
            <Send className="w-5 h-5" />
          ) : (
            <Mic className="w-5 h-5" />
          )}
        </Button>
      </form>
    </div>
  );
}
