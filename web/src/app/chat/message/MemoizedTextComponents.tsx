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
