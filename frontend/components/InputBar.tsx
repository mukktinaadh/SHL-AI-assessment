"use client";

import React, { useState, useRef, useEffect, KeyboardEvent } from 'react';

type InputBarProps = {
  onSend: (text: string) => void;
  disabled: boolean;
};

export default function InputBar({ onSend, disabled }: InputBarProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setText("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.focus();
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="p-4 bg-[#F8F9FA] border-t border-[#E2E8F0] w-full">
      <div className="max-w-4xl mx-auto flex items-end gap-3 bg-white p-2 rounded-2xl border border-[#E2E8F0] focus-within:border-[#5BBB3F] focus-within:ring-1 focus-within:ring-[#5BBB3F] transition-all shadow-sm">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Ask about SHL assessments..."
          className="flex-1 max-h-[120px] bg-transparent resize-none outline-none py-2.5 px-4 text-[#1A1A2E] placeholder-gray-400 disabled:opacity-50"
          rows={1}
        />
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className="p-3 rounded-xl bg-[#5BBB3F] text-white hover:bg-[#4ea335] disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0 mb-0.5"
          aria-label="Send message"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
            <path d="M3.478 2.404a.75.75 0 00-.926.941l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.404z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
