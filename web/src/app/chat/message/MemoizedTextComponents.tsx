import { Citation } from "@/components/search/results/Citation";
import { LoadedOnyxDocument, OnyxDocument } from "@/lib/search/interfaces";
import React, { memo } from "react";
import isEqual from "lodash/isEqual";
import { SourceIcon } from "@/components/SourceIcon";
import { WebResultIcon } from "@/components/WebResultIcon";


export const MemoizedAnchor = memo(
  ({
    docs,
    updatePresentingDocument,
    children,
    href,
  }: {
    docs?: OnyxDocument[] | null;
    updatePresentingDocument: (doc: OnyxDocument) => void;
    children: React.ReactNode;
    href?: string;
  }) => {
    const value = children?.toString();
    
    //console.log("MemoizedAnchor called with:", { value, href, docs: docs?.length });
    
    // Check for citation patterns: [number] or [[number]](url)
    if (value?.startsWith("[") && value?.endsWith("]")) {
      const match = value.match(/\[(\d+)\]/);
      if (match) {
        const index = parseInt(match[1], 10) - 1;
        const associatedDoc = docs?.[index];
        //console.log("Found [number] citation:", { match: match[1], index, associatedDoc });
        if (!associatedDoc) {
          // If no associated doc, render as simple citation with href
          return (
            <a 
              href={href} 
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center cursor-pointer transition-all duration-200 ease-in-out no-underline"
              title={href}
            >
              <span className="flex items-center justify-center w-5 h-5 text-[11px] font-medium text-gray-700 bg-neutral-100 rounded-full border border-gray-300 hover:bg-gray-200 hover:text-gray-900 shadow-sm">
                {match[1]}
              </span>
            </a>
          );
        }

        let icon: React.ReactNode = null;
        if (associatedDoc.source_type === "web") {
          icon = <WebResultIcon url={associatedDoc.link} />;
        } else {
          icon = (
            <SourceIcon sourceType={associatedDoc.source_type} iconSize={18} />
          );
        }

        return (
          <MemoizedLink
            updatePresentingDocument={updatePresentingDocument}
            document={{
              ...associatedDoc,
              icon,
              url: associatedDoc.link,
            }}
          >
            {children}
          </MemoizedLink>
        );
      }
    }
    
    // Check for [[number]](url) format - this is a citation link
    if (value?.startsWith("[[") && value?.endsWith("]]") && href) {
      const match = value.match(/\[\[(\d+)\]\]/);
      if (match) {
        const index = parseInt(match[1], 10) - 1;
        const associatedDoc = docs?.[index];
        //console.log("Found [[number]](url) citation:", { match: match[1], index, associatedDoc, href });
        if (!associatedDoc) {
          // If no associated doc, render as simple citation with href
          return (
            <a 
              href={href} 
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center cursor-pointer transition-all duration-200 ease-in-out no-underline"
              title={href}
            >
              <span className="flex items-center justify-center w-5 h-5 text-[11px] font-medium text-gray-700 bg-neutral-100 rounded-full border border-gray-300 hover:bg-gray-200 hover:text-gray-900 shadow-sm">
                {match[1]}
              </span>
            </a>
          );
        }

        let icon: React.ReactNode = null;
        if (associatedDoc.source_type === "web") {
          icon = <WebResultIcon url={associatedDoc.link} />;
        } else {
          icon = (
            <SourceIcon sourceType={associatedDoc.source_type} iconSize={18} />
          );
        }

        return (
          <MemoizedLink
            updatePresentingDocument={updatePresentingDocument}
            document={{
              ...associatedDoc,
              icon,
              url: associatedDoc.link,
            }}
          >
            {children}
          </MemoizedLink>
        );
      }
    }

    //console.log("No citation pattern found, rendering as regular link");
    return (
      <MemoizedLink
        updatePresentingDocument={updatePresentingDocument}
        href={href}
      >
        {children}
      </MemoizedLink>
    );
  }
);

export const MemoizedLink = memo((props: any) => {
  const { node, document, updatePresentingDocument, ...rest } = props;
  const value = rest.children;

  //console.log("MemoizedLink called with:", { value, document, rest });

  if (value?.toString().startsWith("*")) {
    return (
      <div className="flex-none bg-background-800 inline-block rounded-full h-3 w-3 ml-2" />
    );
  } else if (value?.toString().startsWith("[")) {
    // Check if this is a citation pattern that should be styled
    const citationMatch = value.toString().match(/\[\[?(\d+)\]\]?/);
    if (citationMatch && document) {
      //console.log("MemoizedLink found citation with document:", citationMatch[1], document);
      return (
        <Citation
          url={document?.url}
          icon={document?.icon as React.ReactNode}
          document={document as LoadedOnyxDocument}
          updatePresentingDocument={updatePresentingDocument}
        >
          {rest.children}
        </Citation>
      );
    }
    
    // If no document but it looks like a citation, try to find it in docs
    if (citationMatch && !document) {
      //console.log("MemoizedLink found citation without document:", citationMatch[1]);
      // This will be handled by MemoizedAnchor, so just render as regular link
    }
    
    return (
      <Citation
        url={document?.url}
        icon={document?.icon as React.ReactNode}
        document={document as LoadedOnyxDocument}
        updatePresentingDocument={updatePresentingDocument}
      >
        {rest.children}
      </Citation>
    );
  }

  const handleMouseDown = () => {
    let url = rest.href || rest.children?.toString();
    if (url && !url.startsWith("http://") && !url.startsWith("https://")) {
      // Try to construct a valid URL
      const httpsUrl = `https://${url}`;
      try {
        new URL(httpsUrl);
        url = httpsUrl;
      } catch {
        // If not a valid URL, don't modify original url
      }
    }
    window.open(url, "_blank");
  };
  const sanitizedHref = rest.href?.startsWith("http") ? rest.href : `https://${rest.href}`;

  return (
    <a
      href={sanitizedHref}
      onClick={(e) => {
        e.preventDefault();
        handleMouseDown();
      }}
      className="cursor-pointer text-link hover:text-link-hover"
    >
      {rest.children}
    </a>
  );
});

export const MemoizedParagraph = memo(
  function MemoizedParagraph({ children }: any) {
    return <p className="text-default">{children}</p>;
  },
  (prevProps, nextProps) => {
    const areEqual = isEqual(prevProps.children, nextProps.children);
    return areEqual;
  }
);

MemoizedAnchor.displayName = "MemoizedAnchor";
MemoizedLink.displayName = "MemoizedLink";
MemoizedParagraph.displayName = "MemoizedParagraph";

import {
  Citation,
  QuestionCardProps,
  DocumentCardProps,
} from "@/components/search/results/Citation";
import { LoadedOnyxDocument, OnyxDocument } from "@/lib/search/interfaces";
import React, { memo } from "react";
import isEqual from "lodash/isEqual";
import { SourceIcon } from "@/components/SourceIcon";
import { WebResultIcon } from "@/components/WebResultIcon";
import { SubQuestionDetail } from "../interfaces";
import { ValidSources } from "@/lib/types";
import { FileResponse } from "../my-documents/DocumentsContext";
import { BlinkingDot } from "./BlinkingDot";

export const MemoizedAnchor = memo(
  ({
    docs,
    subQuestions,
    openQuestion,
    userFiles,
    href,
    updatePresentingDocument,
    children,
  }: {
    subQuestions?: SubQuestionDetail[];
    openQuestion?: (question: SubQuestionDetail) => void;
    docs?: OnyxDocument[] | null;
    userFiles?: FileResponse[] | null;
    updatePresentingDocument: (doc: OnyxDocument) => void;
    href?: string;
    children: React.ReactNode;
  }): JSX.Element => {
    const value = children?.toString();
    if (value?.startsWith("[") && value?.endsWith("]")) {
      const match = value.match(/\[(D|Q)?(\d+)\]/);
      if (match) {
        const match_item = match[2];
        if (match_item !== undefined) {
          const isUserFileCitation = userFiles?.length && userFiles.length > 0;
          if (isUserFileCitation) {
            const index = Math.min(
              parseInt(match_item, 10) - 1,
              userFiles?.length - 1
            );
            const associatedUserFile = userFiles?.[index];
            if (!associatedUserFile) {
              return <a href={children as string}>{children}</a>;
            }
          } else if (!isUserFileCitation) {
            const index = parseInt(match_item, 10) - 1;
            const associatedDoc = docs?.[index];
            if (!associatedDoc) {
              return <a href={children as string}>{children}</a>;
            }
          } else {
            const index = parseInt(match_item, 10) - 1;
            const associatedSubQuestion = subQuestions?.[index];
            if (!associatedSubQuestion) {
              return <a href={href || (children as string)}>{children}</a>;
            }
          }
        }
      }

      if (match) {
        const match_item = match[2];
        if (match_item !== undefined) {
          const isSubQuestion = match[1] === "Q";
          const isDocument = !isSubQuestion;

          // Fix: parseInt now uses match[2], which is the numeric part
          const index = parseInt(match_item, 10) - 1;

          const associatedDoc = isDocument ? docs?.[index] : null;
          const associatedSubQuestion = isSubQuestion
            ? subQuestions?.[index]
            : undefined;

          if (!associatedDoc && !associatedSubQuestion) {
            return <>{children}</>;
          }

          let icon: React.ReactNode = null;
          if (associatedDoc?.source_type === "web") {
            icon = <WebResultIcon url={associatedDoc.link} />;
          } else {
            icon = (
              <SourceIcon
                sourceType={associatedDoc?.source_type as ValidSources}
                iconSize={18}
              />
            );
          }
          const associatedDocInfo = associatedDoc
            ? {
                ...associatedDoc,
                icon: icon as any,
                link: associatedDoc.link,
              }
            : undefined;

          return (
            <MemoizedLink
              updatePresentingDocument={updatePresentingDocument}
              href={href}
              document={associatedDocInfo}
              question={associatedSubQuestion}
              openQuestion={openQuestion}
            >
              {children}
            </MemoizedLink>
          );
        }
      }
    }
    return (
      <MemoizedLink
        updatePresentingDocument={updatePresentingDocument}
        href={href}
      >
        {children}
      </MemoizedLink>
    );
  }
);

export const MemoizedLink = memo(
  ({
    node,
    document,
    updatePresentingDocument,
    question,
    href,
    openQuestion,
    ...rest
  }: Partial<DocumentCardProps & QuestionCardProps> & {
    node?: any;
    [key: string]: any;
  }) => {
    const value = rest.children;
    const questionCardProps: QuestionCardProps | undefined =
      question && openQuestion
        ? {
            question: question,
            openQuestion: openQuestion,
          }
        : undefined;

    const documentCardProps: DocumentCardProps | undefined =
      document && updatePresentingDocument
        ? {
            url: document.link,
            icon: document.icon as unknown as React.ReactNode,
            document: document as LoadedOnyxDocument,
            updatePresentingDocument: updatePresentingDocument!,
          }
        : undefined;

    if (value?.toString().startsWith("*")) {
      return <BlinkingDot addMargin />;
    } else if (value?.toString().startsWith("[")) {
      return (
        <>
          {documentCardProps ? (
            <Citation document_info={documentCardProps}>
              {rest.children}
            </Citation>
          ) : (
            <Citation question_info={questionCardProps}>
              {rest.children}
            </Citation>
          )}
        </>
      );
    }

    const handleMouseDown = () => {
      let url = href || rest.children?.toString();

      if (url && !url.includes("://")) {
        // Only add https:// if the URL doesn't already have a protocol
        const httpsUrl = `https://${url}`;
        try {
          new URL(httpsUrl);
          url = httpsUrl;
        } catch {
          // If not a valid URL, don't modify original url
        }
      }
      window.open(url, "_blank");
    };
    return (
      <a
        onMouseDown={handleMouseDown}
        className="cursor-pointer text-link hover:text-link-hover"
      >
        {rest.children}
      </a>
    );
  }
);

export const MemoizedParagraph = memo(
  function MemoizedParagraph({ children, fontSize }: any) {
    return (
      <p
        className={`text-neutral-900 dark:text-neutral-200 my-2.5 last:mb-0 first:mt-0 ${
          fontSize === "sm" ? "leading-tight text-sm" : ""
        }`}
      >
        {children}
      </p>
    );
  },
  (prevProps, nextProps) => {
    const areEqual = isEqual(prevProps.children, nextProps.children);
    return areEqual;
  }
);

MemoizedAnchor.displayName = "MemoizedAnchor";
MemoizedLink.displayName = "MemoizedLink";
MemoizedParagraph.displayName = "MemoizedParagraph";
