"use client";

import React, { useState, useEffect } from "react";
import { ArrayHelpers, Field, useFormikContext } from "formik";
import { FiTrash2, FiPlus } from "react-icons/fi";
import { Button } from "@/components/ui/button";
import { TextFormField } from "@/components/admin/connectors/Field";
import { Textarea } from "@/components/ui/textarea";
import { InputPrompt } from "@/app/chat/interfaces";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SourceChip } from "@/app/chat/input/ChatInputBar";
import { MoreVertical, XIcon } from "lucide-react";
import { usePopup } from "@/components/admin/connectors/Popup";

export default function PromptShortcutsList({
  values,
  arrayHelpers,
  setFieldValue,
  assistantId,
}: {
  values: InputPrompt[];
  arrayHelpers: ArrayHelpers;
  setFieldValue: any;
  assistantId: number | null;
}) {
  const [existingPrompts, setExistingPrompts] = useState<InputPrompt[]>([]);
  const [editingPromptId, setEditingPromptId] = useState<number | null>(null);
  const [shortcutsToUpdate, setShortcutsToUpdate] = useState<InputPrompt[]>([]);
  const [shortcutsToDelete, setShortcutsToDelete] = useState<number[]>([]);

  const { popup, setPopup } = usePopup();

  // Fetch existing admin prompts on component mount
  useEffect(() => {
    fetchExistingPrompts();
  }, [assistantId]);

  const fetchExistingPrompts = async () => {
    try {
      const response = await fetch("/api/input_prompt");
      if (response.ok) {
        const data = await response.json();
        // Filter prompts to only show those that belong to the current assistant
        const filteredData = assistantId 
          ? data.filter((prompt: InputPrompt) => prompt.assistant_id === assistantId)
          : data;
        setExistingPrompts(filteredData);
      } else {
        throw new Error("Failed to fetch existing admin prompts");
      }
    } catch (error) {
      console.error("Failed to fetch existing admin prompts:", error);
    }
  };

  const isPromptPublic = (prompt: InputPrompt): boolean => {
    return prompt.is_public;
  };

  const handleEdit = (promptId: number) => {
    setEditingPromptId(promptId);
  };

  const handleDelete = async (id: number) => {
    const promptToDelete = existingPrompts.find((p: InputPrompt) => p.id === id);
    if (!promptToDelete) return;

    // Add to list of shortcuts to delete
    const newShortcutsToDelete = [...shortcutsToDelete, id];
    setShortcutsToDelete(newShortcutsToDelete);
    
    // Remove from list of shortcuts to update if it was there
    const newShortcutsToUpdate = shortcutsToUpdate.filter((shortcut: InputPrompt) => shortcut.id !== id);
    setShortcutsToUpdate(newShortcutsToUpdate);
    
    // Update form values directly
    setFieldValue('shortcuts_to_delete', newShortcutsToDelete);
    
    // Only remove from UI display, don't call database API
    setExistingPrompts((prevPrompts: InputPrompt[]) =>
      prevPrompts.filter((prompt: InputPrompt) => prompt.id !== id)
    );

    setPopup({ message: "Prompt deleted, please update the Assistant to see the changes", type: "success" });

  };

  const handleInputChange = (index: number, field: 'prompt' | 'content', value: string) => {
    setFieldValue(`prompt_shortcuts.${index}.${field}`, value);
  };

  const handleRemove = (index: number) => {
    arrayHelpers.remove(index);
  };

  const handleAddNew = () => {
    // Add a new empty prompt to the form for persona creation/update
    arrayHelpers.push({ prompt: "", content: "", active: true, is_public: false, assistant_id: assistantId });
    
    // Auto-scroll to the bottom after adding new prompt
    setTimeout(() => {
      const container = document.querySelector('.prompt-shortcuts-container');
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }, 100);
  };



  // Determine if we need scroll functionality (more than 2 items)
  const needsScroll = values.length > 2;
  const maxHeight = "400px"; // Fixed height for scrollable container

  const PromptCard = ({ prompt }: { prompt: InputPrompt }) => {
    const isEditing = editingPromptId === prompt.id;
    const [localPrompt, setLocalPrompt] = useState(prompt.prompt);
    const [localContent, setLocalContent] = useState(prompt.content);

    // Sync local edits with any prompt changes from outside
    useEffect(() => {
      if (isEditing) {
        setLocalPrompt(prompt.prompt);
        setLocalContent(prompt.content);
      }
    }, [prompt.prompt, prompt.content, isEditing]);

    const handleLocalEdit = (field: "prompt" | "content", value: string) => {
      if (field === "prompt") {
        setLocalPrompt(value);
      } else {
        setLocalContent(value);
      }
    };

    return (
      <div className="border rounded-lg p-4 mb-4 relative">
        {isEditing ? (
          <>
            <div className="absolute top-2 right-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditingPromptId(null);
                  fetchExistingPrompts(); // Revert changes from server
                }}
              >
                <XIcon size={14} />
              </Button>
            </div>
            <div className="flex flex-col gap-4">
              <input
                type="text"
                name="localPrompt"
                value={localPrompt}
                onChange={(e) => handleLocalEdit("prompt", e.target.value)}
                placeholder="Prompt"
                className="mb-2 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <Textarea
                name="localContent"
                value={localContent}
                onChange={(e) => handleLocalEdit("content", e.target.value)}
                placeholder="Content"                
              />
              <div className="flex justify-end mt-4">
                <Button onClick={async () => {
                  // Only update UI display and form values, don't call database API
                  
                  // Update local state
                  setExistingPrompts((prevPrompts: InputPrompt[]) =>
                    prevPrompts.map((p: InputPrompt) =>
                      p.id === prompt.id
                        ? { ...p, prompt: localPrompt, content: localContent }
                        : p
                    )
                  );
                  
                  // Add to list of shortcuts to update
                  const updatedShortcut = {
                    ...prompt,
                    prompt: localPrompt,
                    content: localContent,
                    assistant_id: assistantId
                  };
                  
                  // Create new array with updated shortcut
                  const newShortcutsToUpdate = [
                    ...shortcutsToUpdate.filter((shortcut: InputPrompt) => shortcut.id !== prompt.id),
                    updatedShortcut
                  ];
                  
                  setShortcutsToUpdate(newShortcutsToUpdate);
                  setFieldValue('shortcuts_to_update', newShortcutsToUpdate);
                  
                  setEditingPromptId(null);
                  setPopup({ message: "Prompt updated. Please update the Assistant to see the changes", type: "success" });
                }}>
                  Save Changes
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="mb-2 flex gap-x-2">
                    <p className="font-semibold">{prompt.prompt}</p>
                  </div>
                </TooltipTrigger>
              </Tooltip>
            </TooltipProvider>
            <Textarea
              value={prompt.content}
              readOnly
              className="whitespace-pre-wrap resize-y bg-gray-50 h-[120px]"
            />
            <div className="absolute top-2 right-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <MoreVertical size={14} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  {!isPromptPublic(prompt) && (
                    <DropdownMenuItem onClick={() => handleEdit(prompt.id)}>
                      Edit
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={() => handleDelete(prompt.id)}>
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      
      {/* Display existing admin prompts */}
      {existingPrompts.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-medium mb-3">Existing Admin Prompt Shortcuts</h3>
          {existingPrompts.map((prompt) => (
            <PromptCard key={prompt.id} prompt={prompt} />
          ))}
        </div>
      )}

      {/* New prompt shortcuts section */}
      <div>
        {values.length === 0 ? (
          <div className="flex">
            <Button
              type="button"
              onClick={handleAddNew}
              className="flex"
            >
              <FiPlus className="h-4 w-4" />
              Add Prompt Shortcut
            </Button>
          </div>
        ) : (
          <>
            <div 
              className={`flex flex-col gap-4 prompt-shortcuts-container ${needsScroll ? 'overflow-y-auto' : ''}`}
              style={needsScroll ? { maxHeight, scrollbarWidth: 'thin' } : {}}
            >
              {values.map((promptShortcut, index) => (
                <div key={index} className="border rounded-lg p-4 relative">
                  <div className="flex items-start gap-2 mb-3">
                    <TextFormField
                      name={`prompt_shortcuts.${index}.prompt`}
                      label="Prompt Shortcut"
                      placeholder="e.g. Summarize"
                      value={promptShortcut.prompt}
                      onChange={(e) => handleInputChange(index, 'prompt', e.target.value)}
                      className="flex-grow"
                      
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => handleRemove(index)}
                      className="text-gray-400 hover:text-red-500"
                    >
                      <FiTrash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  
                  <Textarea
                    name={`prompt_shortcuts.${index}.content`}
                    placeholder="Actual prompt content (e.g. Summarize the uploaded document and highlight key points.)"
                    value={promptShortcut.content}
                    onChange={(e) => handleInputChange(index, 'content', e.target.value)}
                    className="resize-y min-h-[80px]"
                  />
                </div>
              ))}
            </div>
            
            <div className="flex mt-4">
              <Button
                type="button"
                onClick={handleAddNew}
                className="flex items-center gap-2"
                disabled={values.length >= 10}
              >
                <FiPlus className="h-4 w-4" />
                Add Prompt Shortcut
              </Button>
            </div>
          </>
        )}
      </div>

      {/* Popup for notifications */}
      {popup}
    </div>
  );
} 