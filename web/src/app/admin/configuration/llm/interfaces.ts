import {
  AnthropicIcon,
  AmazonIcon,
  AWSIcon,
  AzureIcon,
  CPUIcon,
  MicrosoftIconSVG,
  MistralIcon,
  MetaIcon,
  OpenAIIcon,
  GeminiIcon,
  OpenSourceIcon,
  AnthropicSVG,
} from "@/components/icons/icons";
import { FaRobot } from "react-icons/fa";

export interface CustomConfigKey {
  name: string;
  description: string | null;
  is_required: boolean;
  is_secret: boolean;
}

export interface WellKnownLLMProviderDescriptor {
  name: string;
  display_name: string;

  deployment_name_required: boolean;
  api_key_required: boolean;
  api_base_required: boolean;
  api_version_required: boolean;

  single_model_supported: boolean;
  custom_config_keys: CustomConfigKey[] | null;
  llm_names: string[];
  default_model: string | null;
  default_fast_model: string | null;
  is_public: boolean;
  groups: number[];
}

export interface LLMProvider {
  name: string;
  provider: string;
  api_key: string | null;
  api_base: string | null;
  api_version: string | null;
  custom_config: { [key: string]: string } | null;
  default_model_name: string;
  fast_default_model_name: string | null;
  is_public: boolean;
  groups: number[];
  display_model_names: string[] | null;
  deployment_name: string | null;
}

export interface FullLLMProvider extends LLMProvider {
  id: number;
  is_default_provider: boolean | null;
  model_names: string[];
  icon?: React.FC<{ size?: number; className?: string }>;
}

export interface LLMProviderDescriptor {
  name: string;
  provider: string;
  model_names: string[];
  default_model_name: string;
  fast_default_model_name: string | null;
  is_default_provider: boolean | null;
  is_public: boolean;
  groups: number[];
  display_model_names: string[] | null;
}

export const getProviderIcon = (providerName: string, modelName?: string) => {
  switch (providerName) {
    case "openai":
      // Special cases for openai based on modelName
      if (modelName?.toLowerCase().includes("amazon")) {
        console.info("Amazon model detected, using AmazonIcon");
        return AmazonIcon;
      }
      if (modelName?.toLowerCase().includes("phi")) {
        console.info("microsoft model detected, using microsoft");
        return MicrosoftIconSVG;
      }
      if (modelName?.toLowerCase().includes("mistral")) {
        console.info("Mistral model detected, using MistralIcon");
        return MistralIcon;
      }
      if (modelName?.toLowerCase().includes("llama")) {
        console.info("Meta model detected, using MetaIcon");
        return MetaIcon;
      }
      if (modelName?.toLowerCase().includes("gemini")) {
        console.info("Gemini model detected, using GeminiIcon");
        return GeminiIcon;
      }
      if (modelName?.toLowerCase().includes("claude")) {
        console.info("Anthropic model detected, using AnthropicIcon");
        return AnthropicIcon;
      }

      return OpenAIIcon; // Default for openai
    case "anthropic":
      return AnthropicSVG;
    case "bedrock":
      return AWSIcon;
    case "azure":
      return AzureIcon;
    default:
      return CPUIcon;
  }
};

export const isAnthropic = (provider: string, modelName: string) =>
  provider === "anthropic" || modelName.toLowerCase().includes("claude");

export interface CustomConfigKey {
  name: string;
  display_name: string;
  description: string | null;
  is_required: boolean;
  is_secret: boolean;
  key_type: CustomConfigKeyType;
  default_value?: string;
}

export type CustomConfigKeyType = "text_input" | "file_input";

export interface ModelConfigurationUpsertRequest {
  name: string;
  is_visible: boolean;
  max_input_tokens: number | null;
}

export interface ModelConfiguration extends ModelConfigurationUpsertRequest {
  supports_image_input: boolean;
}

export interface WellKnownLLMProviderDescriptor {
  name: string;
  display_name: string;

  deployment_name_required: boolean;
  api_key_required: boolean;
  api_base_required: boolean;
  api_version_required: boolean;

  single_model_supported: boolean;
  custom_config_keys: CustomConfigKey[] | null;
  model_configurations: ModelConfiguration[];
  default_model: string | null;
  default_fast_model: string | null;
  is_public: boolean;
  groups: number[];
}

export interface LLMModelDescriptor {
  modelName: string;
  provider: string;
  maxTokens: number;
}

export interface LLMProvider {
  name: string;
  provider: string;
  api_key: string | null;
  api_base: string | null;
  api_version: string | null;
  custom_config: { [key: string]: string } | null;
  default_model_name: string;
  fast_default_model_name: string | null;
  is_public: boolean;
  groups: number[];
  deployment_name: string | null;
  default_vision_model: string | null;
  is_default_vision_provider: boolean | null;
  model_configurations: ModelConfiguration[];
}

export interface LLMProviderView extends LLMProvider {
  id: number;
  is_default_provider: boolean | null;
  icon?: React.FC<{ size?: number; className?: string }>;
}

export interface VisionProvider extends LLMProviderView {
  vision_models: string[];
}

export interface LLMProviderDescriptor {
  name: string;
  provider: string;
  default_model_name: string;
  fast_default_model_name: string | null;
  is_default_provider: boolean | null;
  is_public: boolean;
  groups: number[];
  model_configurations: ModelConfiguration[];
}
