import { ChatSession } from "../interfaces";

export interface Folder {
  folder_id?: number;
  folder_name: string;
  display_priority: number;
  creator_assistant_id: number | null;
  chat_sessions: ChatSession[];
}
