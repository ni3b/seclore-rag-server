"use client";

import React, { useEffect, useMemo, useRef } from "react";
import { XIcon } from "lucide-react";
import { ResizableSection } from "@/components/resizable/ResizableSection";
import { DocumentSet } from "@/lib/types";
import { BookIcon } from "@/components/icons/icons";
import { SourceIcon } from "@/components/SourceIcon";
import { ValidSources } from "@/lib/types";

type SectionItem = {
  key: string;
  url?: string;
  text: string;
  source: string;
  description?: string;
};

function extractExternalLinksFromConnectorConfig(config: unknown): string[] {
  if (!config || typeof config !== "object") return [];

  const cfg = config as Record<string, unknown>;
  const candidates: (string | string[] | undefined)[] = [
    cfg.base_url as string | undefined,
    cfg.wiki_base as string | undefined,
    cfg.jira_project_url as string | undefined,
    cfg.realm_url as string | undefined,
    typeof cfg.hostname === "string" && cfg.hostname ? `https://${cfg.hostname}` : undefined,
    (cfg.shared_drive_urls as string[] | undefined),
    (cfg.shared_folder_urls as string[] | undefined),
    (cfg.sites as string[] | undefined),
    (cfg.pages as string[] | undefined),
  ];

  const flattened = candidates
    .flatMap((c) => (Array.isArray(c) ? c : c ? [c] : []))
    .filter((v): v is string => typeof v === "string");

  return flattened.filter((u) => /^https?:\/\//i.test(u));
}

export default function ConnectorCanvas({
  open,
  onClose,
  documentSets,
  personaName,
}: {
  open: boolean;
  onClose: () => void;
  documentSets: DocumentSet[];
  personaName: string
}) {
  const overlayRef = useRef<HTMLDivElement | null>(null);

  const itemsDictionary: Record<string, SectionItem[]> = useMemo(() => {
    const result: Record<string, SectionItem[]> = {};

    for (const ds of documentSets) {
      for (const d of ds.cc_pair_descriptors ?? []) {
        if (result[d.id]) continue;

        const connector = d.connector as unknown as {
          id: number;
          name: string;
          source: string;
          connector_specific_config?: unknown;
        };
        const links = extractExternalLinksFromConnectorConfig(connector?.connector_specific_config);

        const items: SectionItem[] = [];
        if (links.length === 0) {
          items.push({
            key: `${connector?.id}-nolink`,
            text: d?.name ?? "Unknown",
            source: connector?.source ?? "",
            description: d?.description ?? "",
          });
        } else {
          for (const url of links) {
            items.push({
              key: `${connector?.id}-${url}`,
              url,
              text: d?.name ?? url,
              source: connector?.source ?? "",
              description: d?.description ?? "",
            });
          }
        }

        result[d.id] = items;
      }
    }

    return result;
  }, [documentSets]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (!open) return;
      if (overlayRef.current && e.target instanceof Node) {
        if (e.target === overlayRef.current) onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[1.5px]"
      aria-modal
      role="dialog"
    >
      <div
        className="absolute right-0 top-0 h-full w-full bg-background border-l border-border shadow-xl sm:w-auto"
        onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
      >
        <ResizableSection intialWidth={420} minWidth={320} maxWidth={780}>
          <div className="flex flex-col h-full w-full">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-background sticky top-0 z-10">
              <BookIcon size={25} className="text-text-700" />
              <h1 className="text-base font-bold text-text-1100 sm:text-base">
                <span style={{ display: "block", width: "100%", textAlign: "center" }}>
                  Data Sources Connected To
                  <br />
                  {personaName}
                </span>
              </h1>
              <button
                aria-label="Close Data Sources"
                className="p-1 rounded hover:bg-hover-light text-text-700"
                onClick={onClose}
              >
                <XIcon size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
              {Object.keys(itemsDictionary).length === 0 ? (
                <div className="text-sm text-text-muted px-2 py-1 flex justify-center items-center">No Data Sources</div>
              ) : (
                <div className="space-y-2">
                  {Object.values(itemsDictionary).flat().map((item) => (
                    <div key={item.key} className="group">
                      <div className="flex items-start gap-2 px-3 py-2 border border-border rounded-lg bg-background-100/60">
                        <SourceIcon sourceType={item.source as ValidSources} iconSize={14} /> {/* className="mt-0.5 text-text-600" */}
                        <div className="min-w-0">
                          <div className="text-text-800 truncate">{item.text}</div>
                          <div className="text-[11px] text-text-muted">{item.source}</div>
                          {item.description !== "" && (
                            <div className="text-xs text-text-600 mt-0.5 truncate">
                              {item.description}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </ResizableSection>
      </div>
    </div>
  );
}
