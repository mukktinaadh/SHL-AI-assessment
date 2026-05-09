import React from 'react';

export default function TypingIndicator() {
  return (
    <div className="flex w-full justify-start my-4">
      <div className="bg-[#F8F9FA] border border-[#E2E8F0] rounded-2xl rounded-bl-sm px-5 py-4 flex items-center gap-1.5 h-12 shadow-sm">
        <div className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }}></div>
        <div className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '150ms' }}></div>
        <div className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '300ms' }}></div>
      </div>
    </div>
  );
}
