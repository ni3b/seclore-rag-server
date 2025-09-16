import { ToolSnapshot } from "@/lib/tools/interfaces";
import { DocumentSet, MinimalUserSnapshot } from "@/lib/types";
import { InputPrompt } from "@/app/chat/interfaces";

export interface StarterMessageBase {
  message: string;
}
export interface StarterMessage extends StarterMessageBase {
  name: string;
}

export interface Prompt {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  search_tool_description: string;
  history_query_rephrase: string;  //assistant_change
  custom_tool_argument_system_prompt: string;
  search_query_prompt: string;
  search_data_source_selector_prompt: string;
  task_prompt: string;
  include_citations: boolean;
  datetime_aware: boolean;
  default_prompt: boolean;
}

export interface Persona {
  id: number;
  name: string;
  search_start_date: Date | null;
  owner: MinimalUserSnapshot | null;
  is_visible: boolean;
  is_public: boolean;
  display_priority: number | null;
  description: string;
  document_sets: DocumentSet[];
  prompts: Prompt[];
  tools: ToolSnapshot[];
  num_chunks?: number;
  llm_relevance_filter?: boolean;
  llm_filter_extraction?: boolean;
  llm_model_provider_override?: string;
  llm_model_version_override?: string;
  starter_messages: StarterMessage[] | null;
  prompt_shortcuts: InputPrompt[] | null;
  builtin_persona: boolean;
  is_default_persona: boolean;
  users: MinimalUserSnapshot[];
  groups: number[];
  microsoft_ad_groups?: string[];
  icon_shape?: number;
  icon_color?: string;
  uploaded_image_id?: string;
  labels?: PersonaLabel[];
}

export interface PersonaLabel {
  id: number;
  name: string;
}

import { ToolSnapshot } from "@/lib/tools/interfaces";
import { DocumentSetSummary, MinimalUserSnapshot } from "@/lib/types";

export interface StarterMessageBase {
  message: string;
}
export interface StarterMessage extends StarterMessageBase {
  name: string;
}

export interface Prompt {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  task_prompt: string;
  include_citations: boolean;
  datetime_aware: boolean;
  default_prompt: boolean;
}

export interface MinimalPersonaSnapshot {
  id: number;
  name: string;
  description: string;
  tools: ToolSnapshot[];
  starter_messages: StarterMessage[] | null;
  document_sets: DocumentSetSummary[];
  llm_model_version_override?: string;
  llm_model_provider_override?: string;

  uploaded_image_id?: string;
  icon_shape?: number;
  icon_color?: string;

  is_public: boolean;
  is_visible: boolean;
  display_priority: number | null;
  is_default_persona: boolean;
  builtin_persona: boolean;

  labels?: PersonaLabel[];
  owner: MinimalUserSnapshot | null;
}

export interface Persona extends MinimalPersonaSnapshot {
  user_file_ids: number[];
  user_folder_ids: number[];
  users: MinimalUserSnapshot[];
  groups: number[];
  num_chunks?: number;
}

export interface FullPersona extends Persona {
  search_start_date: Date | null;
  prompts: Prompt[];
  llm_relevance_filter?: boolean;
  llm_filter_extraction?: boolean;
}

export interface PersonaLabel {
  id: number;
  name: string;
}
