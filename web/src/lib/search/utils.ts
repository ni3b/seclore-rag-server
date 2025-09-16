import { Tag, ValidSources } from "../types";
import { Filters, OnyxDocument, SourceMetadata } from "./interfaces";
import { DateRangePickerValue } from "@/app/ee/admin/performance/DateRangeSelector";

const adjustDateForTimezone = (date: Date, isEndOfDay: boolean = false): Date => {
  const newDate = new Date(date);
  console.log('Input date:', newDate.toLocaleString());
  
  if (isEndOfDay) {
    newDate.setHours(23, 59, 59, 999);
  } else {
    newDate.setHours(0, 0, 0, 0);
  }
  const offset = newDate.getTimezoneOffset();
  const adjustedDate = new Date(newDate.getTime() - (offset * 60000));  
  return adjustedDate;
};

export const buildFilters = (
  sources: SourceMetadata[],
  documentSets: string[],
  timeRange: DateRangePickerValue | null,
  tags: Tag[]
): Filters => {
  const filters = {
    source_type:
      sources.length > 0 ? sources.map((source) => source.internalName) : null,
    document_set: documentSets.length > 0 ? documentSets : null,
    // Previous implementation used a single cutoff date
    // time_cutoff: timeRange?.from ? timeRange.from : null,
    // New implementation uses a date range
    time_range: timeRange
      ? {
          start_date: timeRange.from ? adjustDateForTimezone(timeRange.from) : null,
          end_date: timeRange.to ? adjustDateForTimezone(timeRange.to, true) : null,
        }
      : null,
    tags: tags,
  };

  return filters;
};

export function endsWithLetterOrNumber(str: string) {
  return /[a-zA-Z0-9]$/.test(str);
}

// If we have a link, open it in a new tab (including if it's a file)
// If above fails and we have a file, update the presenting document
export const openDocument = (
  document: OnyxDocument,
  updatePresentingDocument?: (document: OnyxDocument) => void
) => {
  if (document.link) {
    window.open(document.link, "_blank");
  } else if (document.source_type === ValidSources.File) {
    updatePresentingDocument?.(document);
  }
};
