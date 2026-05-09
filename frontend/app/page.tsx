"use client";

import React, { useState, useRef, useEffect } from 'react';
import { sendMessage, Message, Recommendation } from '../lib/api';
import MessageBubble from '../components/MessageBubble';
import TypingIndicator from '../components/TypingIndicator';
import InputBar from '../components/InputBar';

type UIMessage = Message & {
  recommendations?: Recommendation[];
};

const INITIAL_MESSAGE: UIMessage = {
  role: "assistant",
  content: "Hi! I can help you find the right SHL assessments. What role are you hiring for?",
};

export default function Home() {
  const [messages, setMessages] = useState<UIMessage[]>([INITIAL_MESSAGE]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEnded, setIsEnded] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, error]);

  const handleSend = async (text: string) => {
    const userMessage: UIMessage = { role: "user", content: text };
    const newMessages = [...messages, userMessage];
    
    setMessages(newMessages);
    setIsLoading(true);
    setError(null);

    try {
      // Map UIMessages to strictly what the API expects (strip recommendations)
      const apiMessages = newMessages.map(({ role, content }) => ({ role, content }));
      
      const response = await sendMessage(apiMessages);
      
      const assistantMessage: UIMessage = {
        role: "assistant",
        content: response.reply,
        recommendations: response.recommendations,
      };
      
      setMessages((prev) => [...prev, assistantMessage]);
      
      if (response.end_of_conversation) {
        setIsEnded(true);
      }
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setMessages([INITIAL_MESSAGE]);
    setIsEnded(false);
    setError(null);
  };

  return (
    <div className="flex flex-col h-[100dvh] bg-[#F8F9FA] text-[#1A1A2E] overflow-hidden">
      {/* Header */}
      <header className="bg-[#5BBB3F] text-white py-3.5 px-4 sm:px-6 flex justify-between items-center shrink-0 shadow-md z-10">
        <h1 className="text-lg sm:text-xl font-bold tracking-tight">SHL Assessment Recommender</h1>
        <button 
          onClick={handleReset}
          className="text-sm font-medium bg-white/20 hover:bg-white/30 transition-colors px-3 py-1.5 rounded-lg border border-white/30 active:scale-95"
        >
          Start over
        </button>
      </header>

      {/* Message List */}
      <main className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 scroll-smooth">
        <div className="max-w-4xl mx-auto flex flex-col gap-2">
          {messages.map((msg, idx) => (
            <MessageBubble 
              key={idx} 
              role={msg.role} 
              content={msg.content} 
              recommendations={msg.recommendations} 
            />
          ))}
          
          {isLoading && <TypingIndicator />}
          
          {error && (
            <div className="my-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-center text-sm shadow-sm max-w-4xl mx-auto">
              {error}
            </div>
          )}
          
          <div ref={messagesEndRef} className="h-4" />
        </div>
      </main>

      {/* Input Bar */}
      <div className="shrink-0 w-full bg-white">
        <InputBar 
          onSend={handleSend} 
          disabled={isLoading || isEnded} 
        />
      </div>
    </div>
  );
}
