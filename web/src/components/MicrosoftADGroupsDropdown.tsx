import React, { useState, useRef, useEffect, ChangeEvent, useMemo } from "react";
import { ChevronDownIcon } from "@/components/icons/icons";
import { StringOrNumberOption } from "./Dropdown";

// Extended option type for Microsoft AD groups that includes membership status
interface MicrosoftADGroupOption extends StringOrNumberOption {
  is_member?: boolean;
  type?: string;
  mail?: string;
}

interface MicrosoftADGroupsDropdownProps {
  options: MicrosoftADGroupOption[];
  onSelect: (selected: MicrosoftADGroupOption) => void;
  onSearchChange: (searchTerm: string) => void;
  searchQuery: string;
  isLoading?: boolean;
  placeholder?: string;
}

export function MicrosoftADGroupsDropdown({
  options,
  onSelect,
  onSearchChange,
  searchQuery,
  isLoading = false,
  placeholder = "Search and select groups...",
}: MicrosoftADGroupsDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [localSearchTerm, setLocalSearchTerm] = useState(searchQuery);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Sync local search term with prop
  useEffect(() => {
    setLocalSearchTerm(searchQuery);
  }, [searchQuery]);

  const handleSelect = (option: MicrosoftADGroupOption) => {
    onSelect(option);
    setIsOpen(false);
    setLocalSearchTerm("");
    onSearchChange(""); // Also clear parent search
  };

  const handleSearchChange = (e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setLocalSearchTerm(value);
    onSearchChange(value);
    setIsOpen(true);
  };

  const filteredOptions = useMemo(() => {
    return options
    .filter(option => {
      const search = localSearchTerm.trim().toLowerCase();
      const optionNameLower = option.name.toLowerCase();
      const matches = search === "" || optionNameLower.includes(search);
      return matches;
    })
    .sort((a, b) => {
      const search = localSearchTerm.trim().toLowerCase();
      
      if (search === "") {
        // If no search term, sort alphabetically
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      }
      
      // If there's a search term, prioritize exact matches and matches at the beginning
      const aName = a.name.toLowerCase();
      const bName = b.name.toLowerCase();
      
      const aStartsWith = aName.startsWith(search);
      const bStartsWith = bName.startsWith(search);
      
      // First priority: exact matches at the beginning
      if (aStartsWith && !bStartsWith) return -1;
      if (!aStartsWith && bStartsWith) return 1;
      
      // Second priority: contains the search term
      const aContains = aName.includes(search);
      const bContains = bName.includes(search);
      
      if (aContains && !bContains) return -1;
      if (!aContains && bContains) return 1;
      
      // Third priority: alphabetical order
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
  }, [options, localSearchTerm]);


  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <div className="relative text-left w-full" ref={dropdownRef}>
      <div>
        <input
          type="text"
          placeholder={placeholder}
          value={localSearchTerm}
          onChange={handleSearchChange}
          onFocus={() => setIsOpen(true)}
          className="inline-flex justify-between w-full px-4 py-2 text-sm bg-background border border-border rounded-md shadow-sm"
        />
        <button
          type="button"
          className="absolute top-0 right-0 text-sm h-full px-2 border-l border-border"
          aria-expanded={isOpen}
          aria-haspopup="true"
          onClick={() => setIsOpen(!isOpen)}
        >
          <ChevronDownIcon className="my-auto w-4 h-4" />
        </button>
      </div>

      {isOpen && (
        <div className="absolute z-10 mt-1 w-full rounded-md shadow-lg bg-background border border-border max-h-60 overflow-y-auto">
          <div
            role="menu"
            aria-orientation="vertical"
            aria-labelledby="options-menu"
          >
            {isLoading ? (
              <div className="px-4 py-2 text-sm text-text-muted">
                Loading groups...
              </div>
            ) : filteredOptions.length > 0 ? (
              filteredOptions.map((option, index) => (
                <div
                  key={`${option.name}-${localSearchTerm}-${index}`}
                  onClick={() => handleSelect(option)}
                  className="px-4 py-2 text-sm hover:bg-hover cursor-pointer"
                >
                  <div className="flex items-center">
                    <div className="flex-1">
                      <div className="flex items-center">
                        <div className="font-medium">{option.name}</div>
                        {option.is_member && (
                          <span className="ml-2 px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded-full">
                            Member
                          </span>
                        )}
                      </div>
                      {option.mail && (
                        <div className="text-xs text-text-muted mt-1">
                          {option.mail}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="px-4 py-2 text-sm text-text-muted">
                {localSearchTerm ? "No groups found" : "No groups available"}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
} 