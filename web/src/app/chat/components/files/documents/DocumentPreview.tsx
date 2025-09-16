import { FiFileText, FiLoader } from "react-icons/fi";
import { useState, useRef, useEffect } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ExpandTwoIcon } from "@/components/icons/icons";

export function DocumentPreview({
  fileName,
  maxWidth,
  alignBubble,
  open,
  fileUrl,
}: {
  fileName: string;
  open?: () => void;
  maxWidth?: string;
  alignBubble?: boolean;
  fileUrl?: string;
}) {
  const fileNameRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(!fileUrl);

  // Show spinner when file is being uploaded (no fileUrl yet)
  useEffect(() => {
    setIsLoading(!fileUrl);
  }, [fileUrl]);

  const handleFileClick = async () => {
    if (fileUrl) {
      try {
        // Fetch the file
        const response = await fetch(fileUrl);
        const blob = await response.blob();
        
        // Create a download link
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        
        // Trigger the download
        document.body.appendChild(link);
        link.click();
        
        // Cleanup
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } catch (error) {
        console.error('Error downloading file:', error);
      }
    }
  };

  return (
    <div
      className={`
        ${alignBubble && "min-w-52 max-w-48"}
        flex
        items-center
        bg-hover-light/50
        border
        border-border
        rounded-lg
        box-border
        py-4
        h-12
        hover:shadow-sm
        transition-all
        px-2
        ${fileUrl ? 'cursor-pointer' : ''}
      `}
      onClick={fileUrl ? handleFileClick : undefined}
    >
      <div className="flex-shrink-0">
        <div
          className="
            w-8
            h-8
            bg-document
            flex
            items-center
            justify-center
            rounded-lg
            transition-all
            duration-200
            hover:bg-document-dark
          "
        >
          {isLoading ? (
            <FiLoader className="w-5 h-5 text-white animate-spin" />
          ) : (
            <FiFileText className="w-5 h-5 text-white" />
          )}
        </div>
      </div>
      <div className="ml-2 h-8 flex flex-col flex-grow">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                ref={fileNameRef}
                className={`font-medium text-sm line-clamp-1 break-all ellipsis ${
                  maxWidth ? maxWidth : "max-w-48"
                }`}
              >
                {fileName}
              </div>
            </TooltipTrigger>
            <TooltipContent side="top" align="start">
              {fileName}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <div className="text-subtle text-xs">
          {isLoading ? 'Uploading...' : 'Document'}
        </div>
      </div>
      {open && (
        <button
          onClick={(e) => {
            e.stopPropagation(); // Prevent triggering the parent's onClick
            open();
          }}
          className="ml-2 p-2 rounded-full hover:bg-gray-200 transition-colors duration-200"
          aria-label="Expand document"
        >
          <ExpandTwoIcon className="w-5 h-5 text-gray-600" />
        </button>
      )}
    </div>
  );
}

export function InputDocumentPreview({
  fileName,
  maxWidth,
  alignBubble,
  fileUrl,
}: {
  fileName: string;
  maxWidth?: string;
  alignBubble?: boolean;
  fileUrl?: string;
}) {
  const [isOverflowing, setIsOverflowing] = useState(false);
  const fileNameRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(!fileUrl);

  useEffect(() => {
    if (fileNameRef.current) {
      setIsOverflowing(
        fileNameRef.current.scrollWidth > fileNameRef.current.clientWidth
      );
    }
  }, [fileName]);

  // Show spinner when file is being uploaded (no fileUrl yet)
  useEffect(() => {
    setIsLoading(!fileUrl);
  }, [fileUrl]);

  const handleFileClick = async () => {
    if (fileUrl) {
      try {
        // Fetch the file
        const response = await fetch(fileUrl);
        const blob = await response.blob();
        
        // Create a download link
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        
        // Trigger the download
        document.body.appendChild(link);
        link.click();
        
        // Cleanup
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } catch (error) {
        console.error('Error downloading file:', error);
      }
    }
  };

  return (
    <div
      className={`
        ${alignBubble && "w-64"}
        flex
        items-center
        p-2
        bg-hover
        border
        border-border
        rounded-md
        box-border
        h-10
        ${fileUrl ? 'cursor-pointer' : ''}
      `}
      onClick={fileUrl ? handleFileClick : undefined}
    >
      <div className="flex-shrink-0">
        <div
          className="
            w-6
            h-6
            bg-document
            flex
            items-center
            justify-center
            rounded-md
          "
        >
          {isLoading ? (
            <FiLoader className="w-4 h-4 text-white animate-spin" />
          ) : (
            <FiFileText className="w-4 h-4 text-white" />
          )}
        </div>
      </div>
      <div className="ml-2 relative">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                ref={fileNameRef}
                className={`font-medium text-sm line-clamp-1 break-all ellipses ${
                  maxWidth ? maxWidth : "max-w-48"
                }`}
              >
                {fileName}
              </div>
            </TooltipTrigger>
            <TooltipContent side="top" align="start">
              {fileName}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        {isLoading && (
          <div className="text-subtle text-xs mt-1">
            Uploading...
          </div>
        )}
      </div>
    </div>
  );
}
