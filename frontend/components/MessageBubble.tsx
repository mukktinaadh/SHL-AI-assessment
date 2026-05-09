import React from 'react';
import { Recommendation } from '../lib/api';
import AssessmentCard from './AssessmentCard';

type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
  recommendations?: Recommendation[];
};

export default function MessageBubble({ role, content, recommendations }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"} my-4`}>
      <div className={`max-w-[90%] sm:max-w-[80%] rounded-2xl px-5 py-4 ${
        isUser 
          ? "bg-[#5BBB3F] text-white rounded-br-sm shadow-sm" 
          : "bg-white text-[#1A1A2E] border border-[#E2E8F0] shadow-sm rounded-bl-sm"
      }`}>
        <div className="whitespace-pre-wrap leading-relaxed text-sm sm:text-base font-inter">
          {content}
        </div>
        
        {recommendations && recommendations.length > 0 && (
          <div className="mt-5 flex flex-col gap-3">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
              Recommended Assessments
            </div>
            {recommendations.map((rec, idx) => (
              <AssessmentCard 
                key={idx}
                name={rec.name}
                url={rec.url}
                test_type={rec.test_type}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
