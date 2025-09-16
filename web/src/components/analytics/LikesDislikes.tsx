"use client";

import { ThumbsUp, ThumbsDown } from "lucide-react";

export function LikesDislikes({
  likes,
  dislikes,
}: {
  likes: number;
  dislikes: number;
}) {
  return (
    <div className="flex items-center gap-6">
      {/* Likes */}
      <div className="flex items-center gap-2 text-green-600">
        <ThumbsUp className="w-6 h-6" />
        <span className="text-lg font-semibold">{likes}</span>
      </div>

      {/* Dislikes */}
      <div className="flex items-center gap-2 text-red-600">
        <ThumbsDown className="w-6 h-6" />
        <span className="text-lg font-semibold">{dislikes}</span>
      </div>
    </div>
  );
}
