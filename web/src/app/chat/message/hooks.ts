import { useEffect, useRef, useState } from "react";
import { ChatState } from "../types";

export function useMouseTracking() {
  const [isHovering, setIsHovering] = useState<boolean>(false);
  const trackedElementRef = useRef<HTMLDivElement>(null);
  const hoverElementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (trackedElementRef.current && hoverElementRef.current) {
        const trackedRect = trackedElementRef.current.getBoundingClientRect();
        const hoverRect = hoverElementRef.current.getBoundingClientRect();

        const isOverTracked =
          event.clientX >= trackedRect.left &&
          event.clientX <= trackedRect.right &&
          event.clientY >= trackedRect.top &&
          event.clientY <= trackedRect.bottom;

        const isOverHover =
          event.clientX >= hoverRect.left &&
          event.clientX <= hoverRect.right &&
          event.clientY >= hoverRect.top &&
          event.clientY <= hoverRect.bottom;

        setIsHovering(isOverTracked || isOverHover);
      }
    };

    document.addEventListener("mousemove", handleMouseMove);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
    };
  }, []);

  return { isHovering, trackedElementRef, hoverElementRef };
}

// Custom hook for typewriter effect - true streaming approach
export const useTypewriterEffect = (
  content: string,
  isComplete: boolean,
  shared: boolean,
  chatSessionId: string | null | undefined,
  messageId: number | null,
  currentPersona: any,
  setChatState?: (value: React.SetStateAction<Map<string | null, ChatState>>) => void,
  setCompleteMessageID?: (value: boolean) => void
) => {
  const [displayedContent, setDisplayedContent] = useState("");
  const [isTypingComplete, setIsTypingComplete] = useState(false);
  
  // Simple refs for typing state
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);
  const lastContentRef = useRef("");
  const currentTypingIndexRef = useRef(0);
  const typingDisabledRef = useRef(false);

  // On mount, if we previously left while typing, disable typewriter and show direct streaming
  useEffect(() => {
    const key = chatSessionId != null && messageId != null
      ? `disableTyping:${chatSessionId}:${messageId}`
      : null;
    if (key && typeof window !== 'undefined') {
      const disabled = window.sessionStorage.getItem(key) === '1';
      if (disabled) {
        typingDisabledRef.current = true;
        // Immediately reflect current content without animation
        setDisplayedContent(content || "");
        if (isComplete) setIsTypingComplete(true);
        lastContentRef.current = content;
      }
    }
  }, []);

  // Handle streaming content - immediate incremental typing
  useEffect(() => {
    /*console.log('Content changed:', { 
      content, 
      contentLength: content?.length, 
      lastContentLength: lastContentRef.current.length,
      currentTypingIndex: currentTypingIndexRef.current,
      displayedContentLength: displayedContent.length
    });*/

    // If typing is disabled for this message/session, just mirror content (no typewriter)
    if (typingDisabledRef.current) {
      setDisplayedContent(content);
      lastContentRef.current = content;
      if (isComplete) setIsTypingComplete(true);
      return;
    }
    
    // If this is completely new content, reset everything
    if (content !== lastContentRef.current && !content.startsWith(lastContentRef.current)) {
      //console.log('Completely new content, resetting');
      setDisplayedContent("");
      setIsTypingComplete(false);
      isTypingRef.current = false;
      currentTypingIndexRef.current = 0;
      lastContentRef.current = content;
      
      if (content && content.length > 0) {
        startTyping(content, 0);
      }
      return;
    }
    
    // If content is growing (streaming), continue typing from where we left off
    if (content.length > lastContentRef.current.length && content.startsWith(lastContentRef.current)) {
      //console.log('Content growing, continuing typing from:', currentTypingIndexRef.current);
      
      // Continue typing the new portion
      const newContent = content.substring(currentTypingIndexRef.current);
      if (newContent.length > 0) {
        continueTyping(content, currentTypingIndexRef.current);
      }
      
      lastContentRef.current = content;
    }
  }, [content, isComplete]);

  // When unmounting, if typing was in progress, mark to disable typewriter next time
  useEffect(() => {
    return () => {
      const key = chatSessionId != null && messageId != null
        ? `disableTyping:${chatSessionId}:${messageId}`
        : null;
      if (key && typeof window !== 'undefined') {
        if (!isTypingComplete) {
          window.sessionStorage.setItem(key, '1');
        } else {
          window.sessionStorage.removeItem(key);
        }
      }
    };
  }, [chatSessionId, messageId, isTypingComplete]);

  // Function to handle final display with citations when streaming is complete
  const showFinalContentWithCitations = () => {
    // When streaming is complete, show the full content with citations
    setDisplayedContent(content);
    setIsTypingComplete(true);
    currentTypingIndexRef.current = content.length;
  };

  // Handle completion
  useEffect(() => {
    if (isComplete || shared) {
      // Clear any ongoing typing
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      isTypingRef.current = false;
      
      // Show final content with citations
      showFinalContentWithCitations();
      
      if (setCompleteMessageID) setCompleteMessageID(true);
      if (setChatState && chatSessionId !== undefined) {
        setChatState((prevState: Map<string | null, ChatState>) =>
          new Map(prevState).set(chatSessionId, "input")
        );
      }
    }
  }, [isComplete, shared, content, setCompleteMessageID, setChatState, chatSessionId]);

  // Function to start typing from beginning
  const startTyping = (fullContent: string, startIndex: number) => {
    if (isTypingRef.current) return;
    
    isTypingRef.current = true;
    currentTypingIndexRef.current = startIndex;
    
    // Set streaming state
    if (setChatState && chatSessionId !== undefined) {
      setChatState((prevState: Map<string | null, ChatState>) => {
        const currentState = prevState.get(chatSessionId);
        if (currentState !== "streaming") {
          const newState = new Map(prevState);
          newState.set(chatSessionId, "streaming");
          return newState;
        }
        return prevState;
      });
    }
    
    continueTyping(fullContent, startIndex);
  };

  // Function to filter out citations during typing for clean display
  const filterCitationsForTyping = (content: string): string => {
    // Remove markdown citation patterns like [[2]](https://...), [[1,2]](https://...), etc.
    // Also handle numeric citations like [2](https://...) and orphaned (https://...) that can remain
    return content
      // Remove [[...]](url) with support for nested parentheses inside URL
      .replace(/\[\[[\d,\s-]+\]\]\((?:[^()]|\([^()]*\))*\)/g, '')
      // Remove [number or number lists](url)
      .replace(/\[(\d+(?:[,\s-]\s*\d+)*)\]\((?:[^()]|\([^()]*\))*\)/g, '')
      // Remove orphan (url) not part of [text](url)
      .replace(/(^|[^\]])\((https?:\/\/[^\s)]+)\)/g, '$1');
  };

  // Function to continue typing from current position
  const continueTyping = (fullContent: string, startIndex: number) => {
    if (isTypingRef.current) return;
    
    isTypingRef.current = true;
    let currentIndex = startIndex;
    
    const typeNextChar = () => {
      if (currentIndex < fullContent.length && !isTypingComplete && isTypingRef.current) {
        currentIndex++;
        currentTypingIndexRef.current = currentIndex;
        
        // Get the content up to current position and filter citations for typing
        fullContent = filterCitationsForTyping(fullContent);
        const filteredContent = fullContent.substring(0, currentIndex);
        
        setDisplayedContent(filteredContent);
        
        /*console.log('Typing character:', { 
          currentIndex, 
          contentLength: fullContent.length,
          displayedLength: fullContent.substring(0, currentIndex).length
        });*/
        
        if (currentIndex < fullContent.length) {
          timeoutRef.current = setTimeout(typeNextChar, 3.5);
        } else {
          // Typing complete for current content
          isTypingRef.current = false;
          //console.log('Typing complete for current content');
        }
      } else {
        isTypingRef.current = false;
      }
    };

    // Start typing
    typeNextChar();
  };

  // Handle tab visibility changes - don't stop streaming when tab becomes inactive
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        // Don't stop typing when tab becomes hidden - let streaming continue
        // Only set complete content if we're not in the middle of streaming
        if (isTypingComplete || content === displayedContent) {
          setDisplayedContent(content);
          setIsTypingComplete(true);
        }
        // If we're still streaming, don't interfere - let it continue
      } else if (document.visibilityState === "visible") {
        // Tab became visible again - resume typing if we were streaming
        if (!isTypingComplete && content.length > displayedContent.length && !isTypingRef.current) {
          //console.log('Tab became visible, resuming typing from:', displayedContent.length);
          
          // Clear any existing typing state to ensure clean resumption
          if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
            timeoutRef.current = null;
          }
          isTypingRef.current = false;
          
          const remainingContent = content.substring(displayedContent.length);
          if (remainingContent.length > 0) {
            startTyping(content, displayedContent.length);
          }
        }
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [content, isTypingComplete]);

  return {
    displayedContent,
    isTypingComplete,
    setDisplayedContent,
    setIsTypingComplete
  };
};
