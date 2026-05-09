import React from 'react';

type AssessmentCardProps = {
  name: string;
  url: string;
  test_type: string;
};

export default function AssessmentCard({ name, url, test_type }: AssessmentCardProps) {
  return (
    <div className="border border-[#E2E8F0] bg-white rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start gap-4">
        <a 
          href={url} 
          target="_blank" 
          rel="noopener noreferrer"
          className="text-[#1A1A2E] font-medium hover:text-[#5BBB3F] transition-colors line-clamp-2"
        >
          {name}
        </a>
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-[#F8F9FA] text-[#1A1A2E] border border-[#E2E8F0] whitespace-nowrap">
          {test_type}
        </span>
      </div>
    </div>
  );
}
