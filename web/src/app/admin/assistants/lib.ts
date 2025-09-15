import { FullLLMProvider } from "../configuration/llm/interfaces";
import { Persona, StarterMessage } from "./interfaces";
import { InputPrompt } from "@/app/chat/interfaces";

interface PersonaUpsertRequest {
  name: string;
  description: string;
  system_prompt: string;
  task_prompt: string;
  search_tool_description: string;
  history_query_rephrase: string;
  custom_tool_argument_system_prompt: string;
  search_query_prompt: string;
  search_data_source_selector_prompt: string;
  datetime_aware: boolean;
  document_set_ids: number[];
  num_chunks: number | null;
  include_citations: boolean;
  is_public: boolean;
  recency_bias: string;
  prompt_ids: number[];
  llm_filter_extraction: boolean;
  llm_relevance_filter: boolean | null;
  llm_model_provider_override: string | null;
  llm_model_version_override: string | null;
  starter_messages: StarterMessage[] | null;
  users?: string[];
  groups: number[];
  microsoft_ad_groups?: string[];
  tool_ids: number[];
  icon_color: string | null;
  icon_shape: number | null;
  remove_image?: boolean;
  uploaded_image_id: string | null;
  search_start_date: Date | null;
  is_default_persona: boolean;
  display_priority: number | null;
  label_ids: number[] | null;
}

export interface PersonaUpsertParameters {
  name: string;
  description: string;
  system_prompt: string;
  search_tool_description: string;
  history_query_rephrase: string;
  custom_tool_argument_system_prompt: string;
  search_query_prompt: string;
  search_data_source_selector_prompt: string;
  existing_prompt_id: number | null;
  task_prompt: string;
  datetime_aware: boolean;
  document_set_ids: number[];
  num_chunks: number | null;
  include_citations: boolean;
  is_public: boolean;
  llm_relevance_filter: boolean | null;
  llm_model_provider_override: string | null;
  llm_model_version_override: string | null;
  starter_messages: StarterMessage[] | null;
  prompt_shortcuts: InputPrompt[];
  shortcuts_to_update?: InputPrompt[];
  shortcuts_to_delete?: number[];
  users?: string[];
  groups: number[];
  microsoft_ad_groups?: string[];
  tool_ids: number[];
  icon_color: string | null;
  icon_shape: number | null;
  remove_image?: boolean;
  search_start_date: Date | null;
  uploaded_image: File | null;
  is_default_persona: boolean;
  label_ids: number[] | null;
}

// Helper function to create new prompt shortcuts during persona creation/update
async function createPromptShortcuts(
  promptShortcuts: InputPrompt[], 
  assistantId: number | null
): Promise<void> 
{  
  // Loop through all new prompt shortcuts and create them
  for (const shortcut of promptShortcuts) {    
    // Only create shortcuts that don't have an id (new shortcuts) and have content
    if (!shortcut.id && shortcut.prompt.trim() && shortcut.content.trim()) {      
      try {
        const response = await fetch("/api/input_prompt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: shortcut.prompt,
            content: shortcut.content,
            active: shortcut.active,
            is_public: shortcut.is_public,
            assistant_id: assistantId,
          }),
        });
        
        if (!response.ok) {
          console.error("Failed to create prompt shortcut:", await response.text());
        }
      } catch (error) {
        console.error("Failed to create prompt shortcut:", error);
      }
    }
  }
}

// Helper function to update existing prompt shortcuts
async function updatePromptShortcuts(
  promptShortcuts: InputPrompt[], 
  assistantId: number | null
): Promise<void> {  
  // Update existing shortcuts that have an id
  for (const shortcut of promptShortcuts) {
    if (shortcut.id && shortcut.id > 0 && shortcut.prompt.trim() && shortcut.content.trim()) {
      try {
        const response = await fetch(`/api/input_prompt/${shortcut.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: shortcut.prompt,
            content: shortcut.content,
            active: shortcut.active,
            is_public: shortcut.is_public,
            assistant_id: assistantId,
          }),
        });
        
        if (!response.ok) {
          console.error(`Failed to update prompt shortcut ${shortcut.id}:`, await response.text());
        }
      } catch (error) {
        console.error("Failed to update prompt shortcut:", error);
      }
    }
  }
}

export const createPersonaLabel = (name: string) => {
  return fetch("/api/persona/labels", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
};

export const deletePersonaLabel = (labelId: number) => {
  return fetch(`/api/admin/persona/label/${labelId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
  });
};

export const updatePersonaLabel = (
  id: number,
  name: string
): Promise<Response> => {
  return fetch(`/api/admin/persona/label/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      label_name: name,
    }),
  });
};

function buildPersonaUpsertRequest(
  creationRequest: PersonaUpsertParameters,
  uploaded_image_id: string | null
): PersonaUpsertRequest {
  const {
    name,
    description,
    system_prompt,
    search_tool_description,
    history_query_rephrase,
    custom_tool_argument_system_prompt,
    search_query_prompt,
    search_data_source_selector_prompt,
    task_prompt,
    document_set_ids,
    num_chunks,
    include_citations,
    is_public,
    groups,
    microsoft_ad_groups,
    existing_prompt_id,
    datetime_aware,
    users,
    tool_ids,
    icon_color,
    icon_shape,
    remove_image,
    search_start_date,
  } = creationRequest;
  return {
    name,
    description,
    system_prompt,
    search_tool_description,
    history_query_rephrase,
    custom_tool_argument_system_prompt,
    search_query_prompt,
    search_data_source_selector_prompt,
    task_prompt,
    document_set_ids,
    num_chunks,
    include_citations,
    is_public,
    uploaded_image_id,
    groups,
    microsoft_ad_groups,
    users,
    tool_ids,
    icon_color,
    icon_shape,
    remove_image,
    search_start_date,
    datetime_aware,
    is_default_persona: creationRequest.is_default_persona ?? false,
    recency_bias: "base_decay",
    prompt_ids: existing_prompt_id ? [existing_prompt_id] : [],
    llm_filter_extraction: false,
    llm_relevance_filter: creationRequest.llm_relevance_filter ?? null,
    llm_model_provider_override:
      creationRequest.llm_model_provider_override ?? null,
    llm_model_version_override:
      creationRequest.llm_model_version_override ?? null,
    starter_messages: creationRequest.starter_messages ?? null,
    display_priority: null,
    label_ids: creationRequest.label_ids ?? null,
  };
}

export async function uploadFile(file: File): Promise<string | null> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/admin/persona/upload-image", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    console.error("Failed to upload file");
    return null;
  }

  const responseJson = await response.json();
  return responseJson.file_id;
}

export async function createPersona(
  personaUpsertParams: PersonaUpsertParameters
): Promise<Response | null> {
  let fileId = null;
  if (personaUpsertParams.uploaded_image) {
    fileId = await uploadFile(personaUpsertParams.uploaded_image);
    if (!fileId) {
      return null;
    }
  }

  // Handle persona creation first
  const createPersonaResponse = await fetch("/api/persona", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(
      buildPersonaUpsertRequest(personaUpsertParams, fileId)
    ),
  });

  // If persona creation was successful, handle prompt shortcuts
  if (createPersonaResponse.ok) {
    try {
      // Clone the response before reading it
      const responseClone = createPersonaResponse.clone();
      const createdPersona = await responseClone.json();
      const assistantId = createdPersona.id;
      
      // For new personas, all shortcuts should be new (no existing IDs)
      const newShortcuts = personaUpsertParams.prompt_shortcuts.filter(shortcut => !shortcut.id);
      
      // Handle new prompt shortcuts with the new assistant ID
      if (newShortcuts.length > 0) {
        await createPromptShortcuts(newShortcuts, assistantId);
      }
    } catch (error) {
      console.error("Failed to handle prompt shortcuts after persona creation:", error);
    }
  }

  return createPersonaResponse;
}

export async function updatePersona(
  id: number,
  personaUpsertParams: PersonaUpsertParameters
): Promise<Response | null> {
  let fileId = null;
  if (personaUpsertParams.uploaded_image) {
    fileId = await uploadFile(personaUpsertParams.uploaded_image);
    if (!fileId) {
      return null;
    }
  }

  // Fetch existing shortcuts for this assistant
  let existingShortcuts: InputPrompt[] = [];
  try {
    const shortcutsResponse = await fetch("/api/input_prompt");
    if (shortcutsResponse.ok) {
      const allShortcuts = await shortcutsResponse.json();
      existingShortcuts = allShortcuts.filter((shortcut: InputPrompt) => 
        shortcut.assistant_id === id
      );
    }   
  } catch (error) {
    console.error("Failed to fetch existing shortcuts:", error);
  }
  

  // Handle persona update first
  const updatePersonaResponse = await fetch(`/api/persona/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(
      buildPersonaUpsertRequest(personaUpsertParams, fileId)
    ),
  });

  // If persona update was successful, handle prompt shortcuts
  if (updatePersonaResponse.ok) {
    try {
      // Handle shortcuts to delete first
      if (personaUpsertParams.shortcuts_to_delete && personaUpsertParams.shortcuts_to_delete.length > 0) {
        for (const shortcutId of personaUpsertParams.shortcuts_to_delete) {
          try {
            const response = await fetch(`/api/input_prompt/${shortcutId}`, {
              method: "DELETE",
              headers: { "Content-Type": "application/json" },
            });
            
            if (!response.ok) {
              console.error(`Failed to delete prompt shortcut ${shortcutId}:`, await response.text());
            }
          } catch (error) {
            console.error(`Failed to delete prompt shortcut ${shortcutId}:`, error);
          }
        }
      }
      
      // Handle new shortcuts (without id)
      const newShortcuts = personaUpsertParams.prompt_shortcuts.filter(shortcut => !shortcut.id);
      
      // Handle updated shortcuts from shortcuts_to_update field
      const updatedShortcuts = personaUpsertParams.shortcuts_to_update || [];
      
      // Handle new prompt shortcuts
      if (newShortcuts.length > 0) {
        await createPromptShortcuts(newShortcuts, id);
      }
      
      // Handle existing shortcuts updates
      if (updatedShortcuts.length > 0) {
        await updatePromptShortcuts(updatedShortcuts, id);
      }
    } catch (error) {
      console.error("Failed to handle prompt shortcuts after persona update:", error);
    }
  }

  return updatePersonaResponse;
}

export function deletePersona(personaId: number) {
  return fetch(`/api/persona/${personaId}`, {
    method: "DELETE",
  });
}

function smallerNumberFirstComparator(a: number, b: number) {
  return a > b ? 1 : -1;
}

function closerToZeroNegativesFirstComparator(a: number, b: number) {
  if (a < 0 && b > 0) {
    return -1;
  }
  if (a > 0 && b < 0) {
    return 1;
  }

  const absA = Math.abs(a);
  const absB = Math.abs(b);

  if (absA === absB) {
    return a > b ? 1 : -1;
  }

  return absA > absB ? 1 : -1;
}

export function personaComparator(a: Persona, b: Persona) {
  if (a.display_priority === null && b.display_priority === null) {
    return closerToZeroNegativesFirstComparator(a.id, b.id);
  }

  if (a.display_priority !== b.display_priority) {
    if (a.display_priority === null) {
      return 1;
    }
    if (b.display_priority === null) {
      return -1;
    }

    return smallerNumberFirstComparator(a.display_priority, b.display_priority);
  }

  return closerToZeroNegativesFirstComparator(a.id, b.id);
}

export const togglePersonaVisibility = async (
  personaId: number,
  isVisible: boolean
) => {
  const response = await fetch(`/api/admin/persona/${personaId}/visible`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      is_visible: !isVisible,
    }),
  });
  return response;
};

export const togglePersonaPublicStatus = async (
  personaId: number,
  isPublic: boolean
) => {
  const response = await fetch(`/api/persona/${personaId}/public`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      is_public: isPublic,
    }),
  });
  return response;
};

export const togglePersonaDefaultStatus = async (
  personaId: number,
  isDefault: boolean
) => {
  const response = await fetch(`/api/persona/${personaId}/default`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      is_default: isDefault,
    }),
  });
  return response;
};

export function checkPersonaRequiresImageGeneration(persona: Persona) {
  for (const tool of persona.tools) {
    if (tool.name === "ImageGenerationTool") {
      return true;
    }
  }
  return false;
}

export function providersContainImageGeneratingSupport(
  providers: FullLLMProvider[]
) {
  return providers.some((provider) => provider.provider === "openai");
}

// Default fallback persona for when we must display a persona
// but assistant has access to none
export const defaultPersona: Persona = {
  id: 0,
  name: "Default Assistant",
  description: "A default assistant",
  is_visible: true,
  is_public: true,
  builtin_persona: false,
  is_default_persona: true,
  users: [],
  groups: [],
  document_sets: [],
  prompts: [],
  tools: [],
  starter_messages: null,
  prompt_shortcuts: null,
  display_priority: null,
  search_start_date: null,
  owner: null,
  icon_shape: 50910,
  icon_color: "#FF6F6F",
};
