"use client";

import {
  FiEdit2,
  FiChevronRight,
  FiChevronLeft,
  FiTool,
  FiGlobe,
} from "react-icons/fi";
import { ChatState, FeedbackType } from "../types";
import React, {
  Dispatch,
  SetStateAction,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import { OnyxDocument, FilteredOnyxDocument } from "@/lib/search/interfaces";
import { SearchSummary } from "./SearchSummary";
import {
  markdownToHtml,
  getMarkdownForSelection,
  stripNumericOnlyLinks,
  extractCodeText,
  preprocessLaTeX,
} from "@/app/chat/message/codeUtils";

// Function to clean citation numbers from HTML content
const cleanCitationNumbersFromHtml = (html: string): string => {
  if (!html) return html;

  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = html;

  // Remove elements that contain only numbers (likely citations)
  const walker = document.createTreeWalker(
    tempDiv,
    NodeFilter.SHOW_TEXT,
    null
  );

  const textNodesToRemove: Node[] = [];
  let node;
  while (node = walker.nextNode()) {
    const text = node.textContent?.trim();
    if (text && /^\d+$/.test(text)) {
      // Check if this is likely a citation number
      const parent = node.parentElement;
      if (parent && (
        parent.tagName === 'SPAN' ||
        parent.tagName === 'DIV' ||
        parent.tagName === 'P' ||
        parent.classList.contains('citation') ||
        parent.classList.contains('citation-number')
      )) {
        textNodesToRemove.push(node);
      }
    }
  }

  // Remove the identified citation text nodes
  textNodesToRemove.forEach(node => {
    if (node.parentNode) {
      node.parentNode.removeChild(node);
    }
  });

  return tempDiv.innerHTML;
};

// Function to handle copy operation for selected text
const handleCopySelection = async (
  content: string | JSX.Element,
  selection: Selection | null
): Promise<void> => {
  const selectedPlainText = selection?.toString() || "";

  if (!selectedPlainText) {
    // If no text is selected, copy the full content
    const contentStr =
      typeof content === "string"
        ? content
        : (content as JSX.Element).props?.children?.toString() || "";

    if (typeof ClipboardItem !== "undefined") {
      const clipboardItem = new ClipboardItem({
        "text/html": new Blob(
          [
            typeof content === "string"
              ? stripNumericOnlyLinks(markdownToHtml(content))
              : contentStr,
          ],
          { type: "text/html" }
        ),
        "text/plain": new Blob([contentStr], {
          type: "text/plain",
        }),
      });
      await navigator.clipboard.write([clipboardItem]);
    } else if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(typeof contentStr === "string" ? contentStr : contentStr.plainText);
    } else {
      const textArea = document.createElement("textarea");
      textArea.value = typeof contentStr === "string" ? contentStr : contentStr.plainText;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
    }
    return;
  }

  const contentStr =
    typeof content === "string"
      ? content
      : (content as JSX.Element).props?.children?.toString() || "";

  // For selected text, we need to preserve the formatting
  // Get the HTML content of the selection to preserve formatting
  const range = selection?.getRangeAt(0);
  let selectedHtml = "";
  if (range) {
    const tempDiv = document.createElement("div");
    tempDiv.appendChild(range.cloneContents());
    selectedHtml = tempDiv.innerHTML;

    // Strip numeric-only links and citation numbers from the selected HTML content
    selectedHtml = stripNumericOnlyLinks(selectedHtml);
    selectedHtml = cleanCitationNumbersFromHtml(selectedHtml);
  }

  // Try to get the markdown representation of the selected text
  let markdownText = selectedPlainText;
  try {
    // Use the existing function to get markdown for the selection
    markdownText = getMarkdownForSelection(contentStr, selectedPlainText);
  } catch (error) {
    // Fallback to plain text if markdown processing fails
    console.warn("Failed to process markdown for selection:", error);
    markdownText = selectedPlainText;
  }

  // Create a hidden div with the HTML content for copying
  if (typeof ClipboardItem !== "undefined") {
    const clipboardItem = new ClipboardItem({
      "text/html": new Blob(
        [selectedHtml || stripNumericOnlyLinks(markdownToHtml(markdownText))],
        { type: "text/html" }
      ),
      "text/plain": new Blob([selectedPlainText], {
        type: "text/plain",
      }),
    });
    await navigator.clipboard.write([clipboardItem]);
  } else if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(markdownText);
  } else {
    const textArea = document.createElement("textarea");
    textArea.value = markdownText;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
  }
};
import { SkippedSearch } from "./SkippedSearch";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { CopyButton } from "@/components/CopyButton";
import { ChatFileType, FileDescriptor, ToolCallMetadata } from "../interfaces";
import {
  IMAGE_GENERATION_TOOL_NAME,
  SEARCH_TOOL_NAME,
  INTERNET_SEARCH_TOOL_NAME,
} from "../tools/constants";
import { ToolRunDisplay } from "../tools/ToolRunningAnimation";
import { Hoverable, HoverableIcon } from "@/components/Hoverable";
import { DocumentPreview } from "../files/documents/DocumentPreview";
import { InMessageImage } from "../files/images/InMessageImage";
import { CodeBlock } from "./CodeBlock";
import rehypePrism from "rehype-prism-plus";
import rehypeKatex from "rehype-katex";
import "prismjs/themes/prism-tomorrow.css";
import "katex/dist/katex.min.css";
import "./custom-code-styles.css";
import { Persona } from "@/app/admin/assistants/interfaces";
import { AssistantIcon } from "@/components/assistants/AssistantIcon";
import { LikeFeedback, DislikeFeedback } from "@/components/icons/icons";
import {
  CustomTooltip,
  TooltipGroup,
} from "@/components/tooltip/CustomTooltip";
import { ValidSources } from "@/lib/types";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMouseTracking, useTypewriterEffect } from "./hooks";
import { SettingsContext } from "@/components/settings/SettingsProvider";
import GeneratingImageDisplay from "../tools/GeneratingImageDisplay";
import { timeAgo } from "@/lib/time";
import { LlmOverride } from "@/lib/hooks";
import ToolResult from "@/components/tools/ToolResult";
import CsvContent from "@/components/tools/CSVContent";
import { ContinueGenerating } from "./ContinueMessage";
import { MemoizedParagraph, MemoizedAnchor } from "./MemoizedTextComponents";
import SourceCard from "@/components/chat_search/sources/SourceCard";
import { SeeMoreBlock } from "@/components/chat_search/sources/SourceCard";
import RegenerateOption from "../RegenerateOption";

// Timestamp component to display message timestamps
const MessageTimestamp = ({ timestamp, className }: { timestamp?: string; className?: string }) => {
  if (!timestamp) return null;

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const timeString = date.toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });

    // Check if it's today
    const isToday = date.toDateString() === now.toDateString();
    if (isToday) {
      return `Today ${timeString}`; // Show "Today hh:mm" for today
    }

    // Check if it's yesterday
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();
    if (isYesterday) {
      return `Yesterday ${timeString}`;
    }

    // Check if it's within the last week
    const oneWeekAgo = new Date(now);
    oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
    const isWithinWeek = date > oneWeekAgo;
    if (isWithinWeek) {
      const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const dayName = dayNames[date.getDay()];
      return `${dayName} ${timeString}`;
    }

    // For older dates, show date-month-year hh:mm
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    return `${day}-${month}-${year} ${timeString}`;
  };

  return (
    <div className={`text-xs text-gray-400 mt-1 ${className || ''}`}>
      {formatTime(timestamp)}
    </div>
  );
};

const TOOLS_WITH_CUSTOM_HANDLING = [
  SEARCH_TOOL_NAME,
  INTERNET_SEARCH_TOOL_NAME,
  IMAGE_GENERATION_TOOL_NAME,
];

function FileDisplay({
  files,
  alignBubble,
}: {
  files: FileDescriptor[];
  alignBubble?: boolean;
}) {
  const [close, setClose] = useState(true);
  const imageFiles = files.filter((file) => file.type === ChatFileType.IMAGE);
  const nonImgFiles = files.filter(
    (file) => file.type !== ChatFileType.IMAGE && file.type !== ChatFileType.CSV
  );

  const csvImgFiles = files.filter((file) => file.type == ChatFileType.CSV);

  return (
    <>
      {nonImgFiles && nonImgFiles.length > 0 && (
        <div
          id="onyx-file"
          className={` ${alignBubble && "ml-auto"} mt-2 auto mb-4`}
        >
          <div className="flex flex-col gap-2">
            {nonImgFiles.map((file) => {
              return (
                <div key={file.id} className="w-fit">
                  <DocumentPreview
                    fileName={file.name || file.id}
                    alignBubble={alignBubble}
                    fileUrl={`/api/chat/file/${file.id}`}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {imageFiles && imageFiles.length > 0 && (
        <div
          id="onyx-image"
          className={` ${alignBubble && "ml-auto"} mt-2 auto mb-4`}
        >
          <div className="flex flex-col gap-2">
            {imageFiles.map((file) => {
              return <InMessageImage key={file.id} fileId={file.id} />;
            })}
          </div>
        </div>
      )}

      {csvImgFiles && csvImgFiles.length > 0 && (
        <div className={` ${alignBubble && "ml-auto"} mt-2 auto mb-4`}>
          <div className="flex flex-col gap-2">
            {csvImgFiles.map((file) => {
              return (
                <div key={file.id} className="w-fit">
                  {close ? (
                    <>
                      <ToolResult
                        csvFileDescriptor={file}
                        close={() => setClose(false)}
                        contentComponent={CsvContent}
                      />
                    </>
                  ) : (
                    <DocumentPreview
                      open={() => setClose(true)}
                      fileName={file.name || file.id}
                      maxWidth="max-w-64"
                      alignBubble={alignBubble}
                      fileUrl={`/api/chat/file/${file.id}`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

export const AIMessage = ({
  regenerate,
  overriddenModel,
  continueGenerating,
  shared,
  isActive,
  toggleDocumentSelection,
  alternativeAssistant,
  docs,
  messageId,
  content,
  files,
  selectedDocuments,
  query,
  citedDocuments,
  toolCall,
  isComplete,
  hasDocs,
  handleFeedback,
  handleSearchQueryEdit,
  handleForceSearch,
  retrievalDisabled,
  currentPersona,
  otherMessagesCanSwitchTo,
  onMessageSelection,
  setPresentingDocument,
  index,
  toggledDocumentSidebar,
  timestamp,
  setChatState,
  chatSessionId,
  stopGeneratingDisplayString,
  setStopGeneratingDisplayString,
  completeMessageID,
  setCompleteMessageID,
}: {
  index?: number;
  shared?: boolean;
  isActive?: boolean;
  continueGenerating?: () => void;
  otherMessagesCanSwitchTo?: number[];
  onMessageSelection?: (messageId: number) => void;
  selectedDocuments?: OnyxDocument[] | null;
  toggleDocumentSelection?: () => void;
  docs?: OnyxDocument[] | null;
  alternativeAssistant?: Persona | null;
  currentPersona: Persona;
  messageId: number | null;
  content: string | JSX.Element;
  files?: FileDescriptor[];
  query?: string;
  citedDocuments?: [string, OnyxDocument][] | null;
  toolCall?: ToolCallMetadata | null;
  isComplete?: boolean;
  toggledDocumentSidebar?: boolean;
  hasDocs?: boolean;
  handleFeedback?: (feedbackType: FeedbackType) => void;
  handleSearchQueryEdit?: (query: string) => void;
  handleForceSearch?: () => void;
  retrievalDisabled?: boolean;
  overriddenModel?: string;
  regenerate?: (modelOverRide: LlmOverride) => Promise<void>;
  setPresentingDocument?: (document: OnyxDocument) => void;
  timestamp?: string;
  setChatState?: Dispatch<SetStateAction<Map<string | null, ChatState>>>;
  chatSessionId?: string | null;
  stopGeneratingDisplayString?: boolean;
  setStopGeneratingDisplayString?: (stopGeneratingDisplayString: boolean) => void
  completeMessageID?: boolean;
  setCompleteMessageID?: (state: boolean) => void;
}) => {
  
  const [isMessageSwitcherComplete, setIsMessageSwitcherComplete] = useState(false);
  const contentString = typeof content === "string" ? content : "";
  
  // Use the simplified typewriter effect hook
  const {
    displayedContent,
    isTypingComplete,
    setDisplayedContent,
    setIsTypingComplete
  } = useTypewriterEffect(
    contentString,
    isComplete || false,
    shared || false,
    chatSessionId,
    messageId,
    currentPersona,
    setChatState,
    setCompleteMessageID
  );

  // Handle stop generating display string
  useEffect(() => {
    if (stopGeneratingDisplayString && setStopGeneratingDisplayString) {
      //console.log("stopGeneratingDisplayString", stopGeneratingDisplayString);
      setDisplayedContent(contentString);
      setIsTypingComplete(true);
      if (setCompleteMessageID) setCompleteMessageID(true);
      if (setChatState && chatSessionId !== undefined) {
        setChatState((prevState: Map<string | null, ChatState>) =>
          new Map(prevState).set(chatSessionId, "input")
        );
      }
      setStopGeneratingDisplayString(false);
    }
  }, [stopGeneratingDisplayString, contentString, setStopGeneratingDisplayString, setCompleteMessageID, setChatState, chatSessionId, setDisplayedContent, setIsTypingComplete]);

  // Handle message switcher completion
  useEffect(() => {
    if (isMessageSwitcherComplete) {
      //console.log("isMessageSwitcherComplete", isMessageSwitcherComplete);
      setDisplayedContent(contentString);
      setIsTypingComplete(true);
      if (setChatState && chatSessionId !== undefined) {
        setChatState((prevState: Map<string | null, ChatState>) =>
          new Map(prevState).set(chatSessionId, "input")
        );
      }
      setIsMessageSwitcherComplete(false);
    }
  }, [isMessageSwitcherComplete, contentString, setChatState, chatSessionId, setDisplayedContent, setIsTypingComplete]);

  // Handle completion state changes - consolidated logic
  useEffect(() => {
    if (isComplete) {
      //console.log("isComplete", isComplete);
      // Clear any ongoing typing and set final state
      if (setCompleteMessageID) setCompleteMessageID(true);
      setDisplayedContent(contentString);
      setIsTypingComplete(true);
      if (setChatState && chatSessionId !== undefined) {
        setChatState((prevState: Map<string | null, ChatState>) => {
          return new Map(prevState).set(
            chatSessionId,
            "input"
          );
        });
      }
    }
  }, [isComplete, contentString, setCompleteMessageID, setChatState, chatSessionId, setDisplayedContent, setIsTypingComplete]);


  const toolCallGenerating = toolCall && !toolCall.tool_result;

  const processContent = (content: string | JSX.Element) => {
    if (typeof content !== "string") {
      return content;
    }

    const codeBlockRegex = /```(\w*)\n[\s\S]*?```|```[\s\S]*?$/g;
    const matches = content.match(codeBlockRegex);

    if (matches) {
      content = matches.reduce((acc, match) => {
        if (!match.match(/```\w+/)) {
          return acc.replace(match, match.replace("```", "```plaintext"));
        }
        return acc;
      }, content);

      const lastMatch = matches[matches.length - 1];
      if (!lastMatch.endsWith("```")) {
        return preprocessLaTeX(content);
      }
    }

    return (
      preprocessLaTeX(content) +
      (!isComplete && !toolCallGenerating ? " [*]() " : "")
    );
  };

  const finalContent = processContent(displayedContent as string);
  // const finalContent = processContent(content as string);

  const [isRegenerateHovered, setIsRegenerateHovered] = useState(false);
  const [isRegenerateDropdownVisible, setIsRegenerateDropdownVisible] =
    useState(false);
  const { isHovering, trackedElementRef, hoverElementRef } = useMouseTracking();

  const settings = useContext(SettingsContext);
  // this is needed to give Prism a chance to load

  const selectedDocumentIds =
    selectedDocuments?.map((document) => document.document_id) || [];
  const citedDocumentIds: string[] = [];

  citedDocuments?.forEach((doc) => {
    citedDocumentIds.push(doc[1].document_id);
  });

  if (!isComplete) {
    const trimIncompleteCodeSection = (
      content: string | JSX.Element
    ): string | JSX.Element => {
      if (typeof content === "string") {
        const pattern = /```[a-zA-Z]+[^\s]*$/;
        const match = content.match(pattern);
        if (match && match.index && match.index > 3) {
          const newContent = content.slice(0, match.index - 3);
          return newContent;
        }
        return content;
      }
      return content;
    };
    content = trimIncompleteCodeSection(content);
  }

  let filteredDocs: FilteredOnyxDocument[] = [];

  if (docs) {
    filteredDocs = docs
      .filter(
        (doc, index, self) =>
          doc.document_id &&
          doc.document_id !== "" &&
          index === self.findIndex((d) => d.document_id === doc.document_id)
      )
      .filter((doc) => {
        return citedDocumentIds.includes(doc.document_id);
      })
      .map((doc: OnyxDocument, ind: number) => {
        return {
          ...doc,
          included: selectedDocumentIds.includes(doc.document_id),
        };
      });
  }

  const paragraphCallback = useCallback(
    (props: any) => <MemoizedParagraph>{props.children}</MemoizedParagraph>,
    []
  );

  const anchorCallback = useCallback(
    (props: any) => (
      <MemoizedAnchor
        updatePresentingDocument={setPresentingDocument!}
        docs={docs}
        href={props.href}
      >
        {props.children}
      </MemoizedAnchor>
    ),
    [docs]
  );

  const currentMessageInd = messageId
    ? otherMessagesCanSwitchTo?.indexOf(messageId)
    : undefined;

  const uniqueSources: ValidSources[] = Array.from(
    new Set((docs || []).map((doc) => doc.source_type))
  ).slice(0, 3);

  const webSourceDomains: string[] = Array.from(
    new Set(
      docs
        ?.filter((doc) => doc.source_type === "web")
        .map((doc) => {
          try {
            const url = new URL(doc.link);
            return `https://${url.hostname}`;
          } catch {
            return doc.link; // fallback to full link if parsing fails
          }
        }) || []
    )
  );

  const markdownComponents = useMemo(
    () => ({
      a: anchorCallback,
      p: paragraphCallback,
      code: ({ node, className, children }: any) => {
        const codeText = extractCodeText(
          node,
          finalContent as string,
          children
        );

        return (
          <CodeBlock className={className} codeText={codeText}>
            {children}
          </CodeBlock>
        );
      },
    }),
    [anchorCallback, paragraphCallback, finalContent]
  );

  const renderedMarkdown = useMemo(() => {
    if (typeof finalContent !== "string") {
      return finalContent;
    }
    // Clean up broken citations - remove malformed [number], [number-number], or [number, number] patterns that aren't proper [[number]](url)
    const cleanContent = finalContent.replace(/(?<!\[)\[(\d+([,-]\s*\d+)*)\](?!\()/g, '');

    // Create a hidden div with the HTML content for copying
    const htmlContent = markdownToHtml(cleanContent);

    return (
      <>
        <div
          style={{
            position: "absolute",
            left: "-9999px",
            display: "none",
          }}
          dangerouslySetInnerHTML={{ __html: htmlContent }}
        />
        <ReactMarkdown
          className="prose max-w-full text-base"
          components={markdownComponents}
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[[rehypePrism, { ignoreMissing: true }], rehypeKatex]}
        >
          {cleanContent}
        </ReactMarkdown>
      </>
    );
  }, [finalContent, markdownComponents]);

  const includeMessageSwitcher =
    currentMessageInd !== undefined &&
    onMessageSelection &&
    otherMessagesCanSwitchTo &&
    otherMessagesCanSwitchTo.length > 1;

  return (
    <div
      id="onyx-ai-message"
      ref={trackedElementRef}
      className={`py-5 ml-4 lg:px-5 relative flex `}
    >
      <div
        className={`mx-auto ${shared ? "w-full" : "w-[90%]"
          }  max-w-message-max`}
      >
        <div className={`lg:mr-12 ${!shared && "mobile:ml-0 md:ml-8"}`}>
          <div className="flex">
            <AssistantIcon
              className="mobile:hidden"
              size={24}
              assistant={alternativeAssistant || currentPersona}
            />

            <div className="w-full">
              <div className="max-w-message-max break-words">
                <div className="w-full desktop:ml-4">
                  <div className="max-w-message-max break-words">
                    {!toolCall || toolCall.tool_name === SEARCH_TOOL_NAME ? (
                      <>
                        {query !== undefined && !retrievalDisabled && (
                          <div className="mb-1">
                            <SearchSummary
                              index={index || 0}
                              query={query}
                              finished={toolCall?.tool_result != undefined}
                              handleSearchQueryEdit={handleSearchQueryEdit}
                              docs={docs || []}
                              toggleDocumentSelection={toggleDocumentSelection!}
                            />
                          </div>
                        )}
                        {handleForceSearch &&
                          content &&
                          query === undefined &&
                          !hasDocs &&
                          !retrievalDisabled && (
                            <div className="mb-1">
                              <SkippedSearch
                                handleForceSearch={handleForceSearch}
                              />
                            </div>
                          )}
                      </>
                    ) : null}

                    {toolCall &&
                      !TOOLS_WITH_CUSTOM_HANDLING.includes(
                        toolCall.tool_name
                      ) && (
                        <ToolRunDisplay
                          toolName={
                            toolCall.tool_result && content
                              ? `Used "${toolCall.tool_name}"`
                              : `Using "${toolCall.tool_name}"`
                          }
                          toolLogo={
                            <FiTool size={15} className="my-auto mr-1" />
                          }
                          isRunning={!toolCall.tool_result || !content}
                        />
                      )}

                    {toolCall &&
                      (!files || files.length == 0) &&
                      toolCall.tool_name === IMAGE_GENERATION_TOOL_NAME &&
                      !toolCall.tool_result && <GeneratingImageDisplay />}

                    {toolCall &&
                      toolCall.tool_name === INTERNET_SEARCH_TOOL_NAME && (
                        <ToolRunDisplay
                          toolName={
                            toolCall.tool_result
                              ? `Searched the internet`
                              : `Searching the internet`
                          }
                          toolLogo={
                            <FiGlobe size={15} className="my-auto mr-1" />
                          }
                          isRunning={!toolCall.tool_result}
                        />
                      )}



                    {content || files ? (
                      <>
                        <FileDisplay files={files || []} />

                        {typeof content === "string" ? (
                          <div className="overflow-x-visible max-w-content-max">
                            <div
                              contentEditable="true"
                              suppressContentEditableWarning
                              className="focus:outline-none cursor-text select-text"
                              style={{
                                MozUserModify: "read-only",
                                WebkitUserModify: "read-only",
                              }}
                              onCopy={async (e) => {
                                e.preventDefault();
                                await handleCopySelection(content, window.getSelection());
                              }}
                            >
                              {renderedMarkdown}
                            </div>
                          </div>
                        ) : (
                          content
                        )}
                      </>
                    ) : isComplete ? null : (
                      <></>
                    )}
                    {docs &&
                      docs.length > 0 &&
                      isComplete === true &&
                      typeof content === "string" &&
                      contentString.length > 0 &&
                      isTypingComplete && 
                      !toolCallGenerating &&
                      (!toolCall || toolCall.tool_result) &&
                      displayedContent === contentString && (
                        <div className="mobile:hidden mt-2 -mx-8 w-full mb-4 flex relative">
                          <div className="w-full">
                            <div className="px-8 flex gap-x-2">
                              {!settings?.isMobile &&
                                docs.length > 0 &&
                                docs
                                  .slice(0, 2)
                                  .map((doc: OnyxDocument, ind: number) => (
                                    <SourceCard
                                      doc={doc}
                                      key={ind}
                                      setPresentingDocument={
                                        setPresentingDocument
                                      }
                                    />
                                  ))}
                              <SeeMoreBlock
                                toggled={toggledDocumentSidebar!}
                                toggleDocumentSelection={toggleDocumentSelection!}
                                uniqueSources={uniqueSources}
                                webSourceDomains={webSourceDomains}
                              />
                            </div>
                          </div>
                        </div>
                      )}
                  </div>

                  {contentString.length > 0 &&
                    handleFeedback &&
                    isTypingComplete && 
                    displayedContent === contentString &&
                    (isActive ? (
                      <div
                        className={`
                        flex md:flex-row gap-x-0.5 mt-1
                        transition-transform duration-300 ease-in-out
                        transform opacity-100 "
                        `}
                      >
                        <TooltipGroup>
                          <div className="flex justify-start w-full gap-x-0.5">
                            {includeMessageSwitcher && (
                              <div className="-mx-1 mr-auto">
                                <MessageSwitcher
                                  setIsMessageSwitcherComplete={setIsMessageSwitcherComplete}
                                  currentPage={currentMessageInd + 1}
                                  totalPages={otherMessagesCanSwitchTo.length}
                                  handlePrevious={() => {
                                    onMessageSelection(
                                      otherMessagesCanSwitchTo[
                                      currentMessageInd - 1
                                      ]
                                    );
                                  }}
                                  handleNext={() => {
                                    onMessageSelection(
                                      otherMessagesCanSwitchTo[
                                      currentMessageInd + 1
                                      ]
                                    );
                                  }}
                                />
                              </div>
                            )}
                          </div>
                          <CustomTooltip showTick line content="Copy">
                            <CopyButton
                              content={
                                typeof content === "string"
                                  ? {
                                    html: stripNumericOnlyLinks(markdownToHtml(content)),
                                    plainText: stripNumericOnlyLinks(content),
                                  }
                                  : content.toString()
                              }
                            />
                          </CustomTooltip>
                          <CustomTooltip showTick line content="Good response">
                            <HoverableIcon
                              icon={<LikeFeedback />}
                              onClick={() => handleFeedback("like")}
                            />
                          </CustomTooltip>
                          <CustomTooltip showTick line content="Bad response">
                            <HoverableIcon
                              icon={<DislikeFeedback size={16} />}
                              onClick={() => handleFeedback("dislike")}
                            />
                          </CustomTooltip>
                          {regenerate && (
                            <CustomTooltip
                              disabled={isRegenerateDropdownVisible}
                              showTick
                              line
                              content="Regenerate"
                            >
                              <RegenerateOption
                                onDropdownVisibleChange={
                                  setIsRegenerateDropdownVisible
                                }
                                onHoverChange={setIsRegenerateHovered}
                                selectedAssistant={currentPersona!}
                                regenerate={regenerate}
                                overriddenModel={overriddenModel}
                              />
                            </CustomTooltip>
                          )}
                        </TooltipGroup>
                      </div>
                    ) : (
                      <div
                        ref={hoverElementRef}
                        className={`
                        absolute -bottom-5
                        z-10
                        invisible ${(isHovering ||
                            isRegenerateHovered ||
                            settings?.isMobile) &&
                          "!visible"
                          }
                        opacity-0 ${(isHovering ||
                            isRegenerateHovered ||
                            settings?.isMobile) &&
                          "!opacity-100"
                          }
                        flex md:flex-row gap-x-0.5 bg-background-125/40 -mx-1.5 p-1.5 rounded-lg
                        `}
                      >
                        {isTypingComplete && 
                         displayedContent === contentString && (
                        <TooltipGroup>
                          <div className="flex justify-start w-full gap-x-0.5">
                            {includeMessageSwitcher && (
                              <div className="-mx-1 mr-auto">
                                <MessageSwitcher
                                  setIsMessageSwitcherComplete={setIsMessageSwitcherComplete}
                                  currentPage={currentMessageInd + 1}
                                  totalPages={otherMessagesCanSwitchTo.length}
                                  handlePrevious={() => {
                                    onMessageSelection(
                                      otherMessagesCanSwitchTo[
                                      currentMessageInd - 1
                                      ]
                                    );
                                  }}
                                  handleNext={() => {
                                    onMessageSelection(
                                      otherMessagesCanSwitchTo[
                                      currentMessageInd + 1
                                      ]
                                    );
                                  }}
                                />
                              </div>
                            )}
                          </div>
                          <CustomTooltip showTick line content="Copy">
                            <CopyButton
                              content={
                                typeof content === "string"
                                  ? {
                                    html: stripNumericOnlyLinks(markdownToHtml(content)),
                                    plainText: stripNumericOnlyLinks(content),
                                  }
                                  : content.toString()
                              }
                            />
                          </CustomTooltip>

                          <CustomTooltip showTick line content="Good response">
                            <HoverableIcon
                              icon={<LikeFeedback />}
                              onClick={() => handleFeedback("like")}
                            />
                          </CustomTooltip>

                          <CustomTooltip showTick line content="Bad response">
                            <HoverableIcon
                              icon={<DislikeFeedback size={16} />}
                              onClick={() => handleFeedback("dislike")}
                            />
                          </CustomTooltip>
                          {regenerate && (
                            <CustomTooltip
                              disabled={isRegenerateDropdownVisible}
                              showTick
                              line
                              content="Regenerate"
                            >
                              <RegenerateOption
                                selectedAssistant={currentPersona!}
                                onDropdownVisibleChange={
                                  setIsRegenerateDropdownVisible
                                }
                                regenerate={regenerate}
                                overriddenModel={overriddenModel}
                                onHoverChange={setIsRegenerateHovered}
                              />
                            </CustomTooltip>
                          )}
                        </TooltipGroup>
                        )}
                      </div>
                    ))}

                                    {/* Timestamp positioned below the tooltip group - only show when message is complete */}
                  {contentString.length > 0 &&
                    handleFeedback &&
                    isTypingComplete && <MessageTimestamp timestamp={timestamp} className="mt-2" />}
                </div>
              </div>
            </div>
          </div>
        </div>
        {(!toolCall || toolCall.tool_name === SEARCH_TOOL_NAME) &&
          !query &&
          continueGenerating && (
            <ContinueGenerating handleContinueGenerating={continueGenerating} />
          )}
      </div>
    </div>
  );
};

function MessageSwitcher({
  setIsMessageSwitcherComplete,
  currentPage,
  totalPages,
  handlePrevious,
  handleNext,
}: {
  setIsMessageSwitcherComplete?: (state: boolean) => void
  currentPage: number;
  totalPages: number;
  handlePrevious: () => void;
  handleNext: () => void;
}) {
  return (
    <div className="flex items-center text-sm space-x-0.5">
      <Hoverable
        icon={FiChevronLeft}
        onClick={currentPage === 1 ? undefined : () => {
          handlePrevious();
          if (setIsMessageSwitcherComplete) setIsMessageSwitcherComplete(true);
        }}
      />

      <span className="text-emphasis select-none">
        {currentPage} / {totalPages}
      </span>

      <Hoverable
        icon={FiChevronRight}
        onClick={currentPage === totalPages ? undefined : () => {
          handleNext();
          if (setIsMessageSwitcherComplete) setIsMessageSwitcherComplete(true);
        }}
      />
    </div>
  );
}

export const HumanMessage = ({
  content,
  files,
  messageId,
  otherMessagesCanSwitchTo,
  onEdit,
  onMessageSelection,
  shared,
  stopGenerating = () => null,
  timestamp,
}: {
  shared?: boolean;
  content: string;
  files?: FileDescriptor[];
  messageId?: number | null;
  otherMessagesCanSwitchTo?: number[];
  onEdit?: (editedContent: string) => void;
  onMessageSelection?: (messageId: number) => void;
  stopGenerating?: () => void;
  timestamp?: string;
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [isHovered, setIsHovered] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState(content);

  useEffect(() => {
    if (!isEditing) {
      setEditedContent(content);
    }
  }, [content, isEditing]);

  useEffect(() => {
    if (textareaRef.current) {
      // Focus the textarea
      textareaRef.current.focus();
      // Move the cursor to the end of the text
      textareaRef.current.selectionStart = textareaRef.current.value.length;
      textareaRef.current.selectionEnd = textareaRef.current.value.length;
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [isEditing]);

  const handleEditSubmit = () => {
    if (editedContent.trim() !== "") {
      onEdit?.(editedContent);
      setIsEditing(false);
    }
  };

  const currentMessageInd = messageId
    ? otherMessagesCanSwitchTo?.indexOf(messageId)
    : undefined;

  return (
    <div
      id="onyx-human-message"
      className="pt-5 pb-1 w-full lg:px-5 flex -mr-6 relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className={`text-user-text mx-auto ${shared ? "w-full" : "w-[90%]"
          } max-w-[790px]`}
      >
        <div className="xl:ml-8">
          <div className="flex flex-col desktop:mr-4">
            <FileDisplay alignBubble files={files || []} />

            <div className="flex justify-end">
              <div className="w-full ml-8 flex w-full w-[800px] break-words">
                {isEditing ? (
                  <div className="w-full">
                    <div
                      className={`
                      opacity-100
                      w-full
                      flex
                      flex-col
                      border 
                      border-border 
                      rounded-lg 
                      pb-2
                      [&:has(textarea:focus)]::ring-1
                      [&:has(textarea:focus)]::ring-black
                    `}
                    >
                      <textarea
                        ref={textareaRef}
                        className={`                        m-0 
                        w-full 
                        h-auto
                        shrink
                        border-0
                        rounded-lg 
                        overflow-y-hidden
                        whitespace-normal 
                        break-word
                        overscroll-contain
                        outline-none 
                        placeholder-gray-400 
                        resize-none
                        text-text-editing-message
                        pl-4
                        overflow-y-auto
                        bg-background
                        pr-12 
                        py-4`}
                        aria-multiline
                        role="textarea"
                        value={editedContent}
                        style={{ scrollbarWidth: "thin" }}
                        onChange={(e) => {
                          setEditedContent(e.target.value);
                          textareaRef.current!.style.height = "auto";
                          e.target.style.height = `${e.target.scrollHeight}px`;
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") {
                            e.preventDefault();
                            setEditedContent(content);
                            setIsEditing(false);
                          }
                          // Submit edit if "Command Enter" is pressed, like in ChatGPT
                          if (e.key === "Enter" && e.metaKey) {
                            handleEditSubmit();
                          }
                        }}
                      />
                      <div className="flex justify-end mt-2 gap-2 pr-4">
                        <button
                          className={`
                            w-fit
                            bg-accent 
                            text-inverted 
                            text-sm
                            rounded-lg 
                            inline-flex 
                            items-center 
                            justify-center 
                            flex-shrink-0 
                            font-medium 
                            min-h-[38px]
                            py-2
                            px-3
                            ${editedContent.trim() !== "" ? "hover:bg-accent-hover" : ""}
                            ${editedContent.trim() !== "" ? "bg-submit-background" : "bg-disabled-submit-background"}
                          `}
                          onClick={handleEditSubmit}
                          disabled={editedContent.trim() === ""}
                        >
                          Submit
                        </button>
                        <button
                          className={`
                          inline-flex 
                          items-center 
                          justify-center 
                          flex-shrink-0 
                          font-medium 
                          min-h-[38px] 
                          py-2 
                          px-3 
                          w-fit 
                          bg-background-strong 
                          text-sm
                          rounded-lg
                          hover:bg-hover-emphasis
                        `}
                          onClick={() => {
                            setEditedContent(content);
                            setIsEditing(false);
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                ) : typeof content === "string" ? (
                  <>
                    <div className="ml-auto flex items-center mr-1 h-fit my-auto">
                      {onEdit &&
                        isHovered &&
                        !isEditing &&
                        (!files || files.length === 0) ? (
                        <TooltipProvider delayDuration={1000}>
                          <Tooltip>
                            <TooltipTrigger>
                              <HoverableIcon
                                icon={<FiEdit2 className="text-gray-600" />}
                                onClick={() => {
                                  setIsEditing(true);
                                  setIsHovered(false);
                                }}
                              />
                            </TooltipTrigger>
                            <TooltipContent>Edit</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      ) : (
                        <div className="w-7" />
                      )}
                    </div>

                    <div
                      className={`${!(
                        onEdit &&
                        isHovered &&
                        !isEditing &&
                        (!files || files.length === 0)
                      ) && "ml-auto"
                        } relative flex-none max-w-[70%] mb-auto whitespace-break-spaces rounded-3xl bg-user px-5 py-2.5`}
                    >
                      {content}
                    </div>
                  </>
                ) : (
                  <>
                    {onEdit &&
                      isHovered &&
                      !isEditing &&
                      (!files || files.length === 0) ? (
                      <div className="my-auto">
                        <Hoverable
                          icon={FiEdit2}
                          onClick={() => {
                            setIsEditing(true);
                            setIsHovered(false);
                          }}
                        />
                      </div>
                    ) : (
                      <div className="h-[27px]" />
                    )}
                    <div className="ml-auto rounded-lg p-1">{content}</div>
                  </>
                )}
              </div>
            </div>
            <MessageTimestamp timestamp={timestamp} className="flex justify-end" />
          </div>

          <div className="flex flex-col md:flex-row gap-x-0.5 mt-1">
            {currentMessageInd !== undefined &&
              onMessageSelection &&
              otherMessagesCanSwitchTo &&
              otherMessagesCanSwitchTo.length > 1 && (
                <div className="ml-auto mr-3">
                  <MessageSwitcher
                    currentPage={currentMessageInd + 1}
                    totalPages={otherMessagesCanSwitchTo.length}
                    handlePrevious={() => {
                      stopGenerating();
                      onMessageSelection(
                        otherMessagesCanSwitchTo[currentMessageInd - 1]
                      );
                    }}
                    handleNext={() => {
                      stopGenerating();
                      onMessageSelection(
                        otherMessagesCanSwitchTo[currentMessageInd + 1]
                      );
                    }}
                  />
                </div>
              )}
          </div>
        </div>
      </div>
    </div>
  );
};