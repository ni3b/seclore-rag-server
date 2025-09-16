import { useState } from "react";
import { HoverableIcon } from "./Hoverable";
import { CheckmarkIcon, CopyMessageIcon } from "./icons/icons";

export function CopyButton({
  content,
  onClick,
}: {
  content?: string | { html: string; plainText: string };
  onClick?: () => void;
}) {
  const [copyClicked, setCopyClicked] = useState(false);

  const copyToClipboard = async (
    content: string | { html: string; plainText: string }
  ) => {
    try {
      if (navigator.clipboard && navigator.clipboard.write) {
        const clipboardItem = new ClipboardItem({
          "text/html": new Blob(
            [typeof content === "string" ? content : content.html],
            { type: "text/html" }
          ),
          "text/plain": new Blob(
            [typeof content === "string" ? content : content.plainText],
            { type: "text/plain" }
          ),
        });
        await navigator.clipboard.write([clipboardItem]);
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        // Fallback to plain text copy if ClipboardItem is unavailable
        await navigator.clipboard.writeText(
          typeof content === "string" ? content : content.plainText
        );
      } else {
        // Fallback for older browsers using textarea
        const textArea = document.createElement("textarea");
        textArea.value = typeof content === "string" ? content : content.plainText;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
      }
    } catch (err) {
      console.error("Copy to clipboard failed:", err);
    }
  };

  return (
    <HoverableIcon
      icon={copyClicked ? <CheckmarkIcon /> : <CopyMessageIcon />}
      onClick={() => {
        if (content) {
          copyToClipboard(content);
        }
        onClick && onClick();

        setCopyClicked(true);
        setTimeout(() => setCopyClicked(false), 3000);
      }}
    />
  );
}
