"use client";

import React from "react";
import { Option } from "@/components/Dropdown";
import { generateRandomIconShape } from "@/lib/assistantIconUtils";
import { CCPairBasicInfo, DocumentSet, User, UserGroup } from "@/lib/types";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { ArrayHelpers, FieldArray, Form, Formik, FormikProps } from "formik";

import {
  BooleanFormField,
  Label,
  TextFormField,
} from "@/components/admin/connectors/Field";

import { usePopup } from "@/components/admin/connectors/Popup";
import { getDisplayNameForModel, useLabels, useMicrosoftADGroups, useAuthType, useMicrosoftADGroupUsers } from "@/lib/hooks";
import { DocumentSetSelectable } from "@/components/documentSet/DocumentSetSelectable";
import { addAssistantToList } from "@/lib/assistants/updateAssistantPreferences";
import {
  checkLLMSupportsImageInput,
  destructureValue,
  structureValue,
} from "@/lib/llm/utils";
import { ToolSnapshot } from "@/lib/tools/interfaces";
import { checkUserIsNoAuthUser } from "@/lib/user";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FiInfo } from "react-icons/fi";
import * as Yup from "yup";
import CollapsibleSection from "./CollapsibleSection";
import { SuccessfulPersonaUpdateRedirectType } from "./enums";
import { Persona, PersonaLabel, StarterMessage } from "./interfaces";
import { PersonaUpsertParameters, createPersona, updatePersona } from "./lib";
import {
  CameraIcon,
  GroupsIconSkeleton,
  NewChatIcon,
  SwapIcon,
  TrashIcon,
} from "@/components/icons/icons";
import { buildImgUrl } from "@/app/chat/files/images/utils";
import { useAssistants } from "@/components/context/AssistantsContext";
import { debounce } from "lodash";
import { FullLLMProvider } from "../configuration/llm/interfaces";
import StarterMessagesList from "./StarterMessageList";

import { Switch, SwitchField } from "@/components/ui/switch";
import { generateIdenticon } from "@/components/assistants/AssistantIcon";
import { BackButton } from "@/components/BackButton";
import { Checkbox, CheckboxField } from "@/components/ui/checkbox";
import { AdvancedOptionsToggle } from "@/components/AdvancedOptionsToggle";
import { MinimalUserSnapshot } from "@/lib/types";
import { useUserGroups } from "@/lib/hooks";
import {
  SearchMultiSelectDropdown,
  Option as DropdownOption,
} from "@/components/Dropdown";
import { MicrosoftADGroupsDropdown } from "@/components/MicrosoftADGroupsDropdown";

// Extended option type for Microsoft AD groups that includes membership status
interface MicrosoftADGroupOption extends DropdownOption<string | number> {
  is_member?: boolean;
  type?: string;
  mail?: string;
}
import { SourceChip } from "@/app/chat/input/ChatInputBar";
import { TagIcon, UserIcon, XIcon } from "lucide-react";
import { LLMSelector } from "@/components/llm/LLMSelector";
import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { DeleteEntityModal } from "@/components/modals/DeleteEntityModal";
import { DeletePersonaButtonInAssistantEditor } from "./[id]/DeletePersonaButtonInAssistantEditor";
import Title from "@/components/ui/title";
import { SEARCH_TOOL_ID } from "@/app/chat/tools/constants";
import PromptShortcutsList from "@/components/admin/PromptShortcutsList";

function findSearchTool(tools: ToolSnapshot[]) {
  return tools.find((tool) => tool.in_code_tool_id === SEARCH_TOOL_ID);
}

function findImageGenerationTool(tools: ToolSnapshot[]) {
  return tools.find((tool) => tool.in_code_tool_id === "ImageGenerationTool");
}

function findInternetSearchTool(tools: ToolSnapshot[]) {
  return tools.find((tool) => tool.in_code_tool_id === "InternetSearchTool");
}

function SubLabel({ children }: { children: string | JSX.Element }) {
  return (
    <div
      className="text-sm text-description font-description mb-2"
      style={{ color: "rgb(113, 114, 121)" }}
    >
      {children}
    </div>
  );
}

export function AssistantEditor({
  existingPersona,
  ccPairs,
  documentSets,
  user,
  defaultPublic,
  redirectType,
  llmProviders,
  tools,
  shouldAddAssistantToUserPreferences,
  admin,
}: {
  existingPersona?: Persona | null;
  ccPairs: CCPairBasicInfo[];
  documentSets: DocumentSet[];
  user: User | null;
  defaultPublic: boolean;
  redirectType: SuccessfulPersonaUpdateRedirectType;
  llmProviders: FullLLMProvider[];
  tools: ToolSnapshot[];
  shouldAddAssistantToUserPreferences?: boolean;
  admin?: boolean;
}) {
  const { refreshAssistants, isImageGenerationAvailable } = useAssistants();
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);

  const { popup, setPopup } = usePopup();
  const { labels, refreshLabels, createLabel, updateLabel, deleteLabel } =
    useLabels();
  const authType = useAuthType();
  const isOIDC = authType === "oidc";
  
  // Add state for Microsoft AD groups search (client-side only)
  const [microsoftGroupsSearchQuery, setMicrosoftGroupsSearchQuery] = useState<string>("");
  const { data: microsoftADGroups } = useMicrosoftADGroups();
  
  // Add state for selected group and its users
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const { data: groupUsers, isLoading: loadingGroupUsers } = useMicrosoftADGroupUsers(selectedGroupId);

  // Add state for selected database group
  const [selectedDBGroupId, setSelectedDBGroupId] = useState<number | null>(null);

  // Add state for Microsoft users
  const { data: microsoftUsers } = useSWR<{ users: Array<{ id: string; display_name: string; user_principal_name: string; mail: string }> }>(
    isOIDC ? "/api/auth/oidc/microsoft-users" : null,
    errorHandlingFetcher
  );

  const colorOptions = [
    "#FF6FBF",
    "#6FB1FF",
    "#B76FFF",
    "#FFB56F",
    "#6FFF8D",
    "#FF6F6F",
    "#6FFFFF",
  ];

  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);

  // state to persist across formik reformatting
  const [defautIconColor, _setDeafultIconColor] = useState(
    colorOptions[Math.floor(Math.random() * colorOptions.length)]
  );
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [defaultIconShape, setDefaultIconShape] = useState<any>(null);

  useEffect(() => {
    if (defaultIconShape === null) {
      setDefaultIconShape(generateRandomIconShape().encodedGrid);
    }
  }, [defaultIconShape]);

  const [isIconDropdownOpen, setIsIconDropdownOpen] = useState(false);

  const [removePersonaImage, setRemovePersonaImage] = useState(false);

  const autoStarterMessageEnabled = useMemo(
    () => llmProviders.length > 0,
    [llmProviders.length]
  );
  const isUpdate = existingPersona !== undefined && existingPersona !== null;
  const existingPrompt = existingPersona?.prompts[0] ?? null;
  const defaultProvider = llmProviders.find(
    (llmProvider) => llmProvider.is_default_provider
  );
  const defaultModelName = defaultProvider?.default_model_name;
  const providerDisplayNameToProviderName = new Map<string, string>();
  llmProviders.forEach((llmProvider) => {
    providerDisplayNameToProviderName.set(
      llmProvider.name,
      llmProvider.provider
    );
  });

  const modelOptionsByProvider = new Map<string, Option<string>[]>();
  llmProviders.forEach((llmProvider) => {
    const providerOptions = llmProvider.model_names.map((modelName) => {
      return {
        name: getDisplayNameForModel(modelName),
        value: modelName,
      };
    });
    modelOptionsByProvider.set(llmProvider.name, providerOptions);
  });

  const personaCurrentToolIds =
    existingPersona?.tools.map((tool) => tool.id) || [];

  const searchTool = findSearchTool(tools);
  const imageGenerationTool = findImageGenerationTool(tools);
  const internetSearchTool = findInternetSearchTool(tools);

  const customTools = tools.filter(
    (tool) =>
      tool.in_code_tool_id !== searchTool?.in_code_tool_id &&
      tool.in_code_tool_id !== imageGenerationTool?.in_code_tool_id &&
      tool.in_code_tool_id !== internetSearchTool?.in_code_tool_id
  );

  const availableTools = [
    ...customTools,
    ...(searchTool ? [searchTool] : []),
    ...(imageGenerationTool ? [imageGenerationTool] : []),
    ...(internetSearchTool ? [internetSearchTool] : []),
  ];
  const enabledToolsMap: { [key: number]: boolean } = {};
  availableTools.forEach((tool) => {
    enabledToolsMap[tool.id] = personaCurrentToolIds.includes(tool.id);
  });

  const initialValues = {
    name: existingPersona?.name ?? "",
    description: existingPersona?.description ?? "",
    datetime_aware: existingPrompt?.datetime_aware ?? false,
    system_prompt: existingPrompt?.system_prompt ?? "",
    search_tool_description: existingPrompt?.search_tool_description ?? "",
    history_query_rephrase: existingPrompt?.history_query_rephrase ?? "",
    custom_tool_argument_system_prompt: existingPrompt?.custom_tool_argument_system_prompt ?? "",
    search_query_prompt: existingPrompt?.search_query_prompt ?? "",
    search_data_source_selector_prompt: existingPrompt?.search_data_source_selector_prompt ?? "",
    task_prompt: existingPrompt?.task_prompt ?? "",
    is_public: existingPersona?.is_public ?? defaultPublic,
    document_set_ids:
      existingPersona?.document_sets?.map((documentSet) => documentSet.id) ??
      ([] as number[]),
    num_chunks: existingPersona?.num_chunks ?? null,
    search_start_date: existingPersona?.search_start_date
      ? existingPersona?.search_start_date.toString().split("T")[0]
      : null,
    include_citations: existingPersona?.prompts[0]?.include_citations ?? true,
    llm_relevance_filter: existingPersona?.llm_relevance_filter ?? false,
    llm_model_provider_override:
      existingPersona?.llm_model_provider_override ?? null,
    llm_model_version_override:
      existingPersona?.llm_model_version_override ?? null,
    starter_messages: existingPersona?.starter_messages ?? [
      {
        message: "",
      },
    ],
    enabled_tools_map: enabledToolsMap,
    icon_color: existingPersona?.icon_color ?? defautIconColor,
    icon_shape: existingPersona?.icon_shape ?? defaultIconShape,
    uploaded_image: null,
    labels: existingPersona?.labels ?? null,
    prompt_shortcuts: existingPersona?.prompt_shortcuts ?? [],
    shortcuts_to_delete: [],

    // EE Only
    label_ids: existingPersona?.labels?.map((label) => label.id) ?? [],
    selectedUsers:
      existingPersona?.users?.filter(
        (u) => u.id !== existingPersona.owner?.id
      ) ?? [],
    selectedGroups: existingPersona?.groups ?? [],
    selectedMicrosoftADGroups: existingPersona?.microsoft_ad_groups ?? [],
  };

  interface AssistantPrompt {
    message: string;
    name: string;
  }

  const debouncedRefreshPrompts = debounce(
    async (formValues: any, setFieldValue: any) => {
      if (!autoStarterMessageEnabled) {
        return;
      }
      setIsRefreshing(true);
      try {
        const response = await fetch("/api/persona/assistant-prompt-refresh", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: formValues.name || "",
            description: formValues.description || "",
            document_set_ids: formValues.document_set_ids || [],
            instructions:
              formValues.system_prompt || formValues.task_prompt || "",
            search_tool_description: formValues.search_tool_description || "",
            history_query_rephrase: formValues.history_query_rephrase || "",
            custom_tool_argument_system_prompt: formValues.custom_tool_argument_system_prompt || "",
            search_query_prompt: formValues.search_query_prompt || "",
            search_data_source_selector_prompt: formValues.search_data_source_selector_prompt || "",
            generation_count:
              4 -
              formValues.starter_messages.filter(
                (message: StarterMessage) => message.message.trim() !== ""
              ).length,
          }),
        });

        const data: AssistantPrompt[] = await response.json();
        if (response.ok) {
          const filteredStarterMessages = formValues.starter_messages.filter(
            (message: StarterMessage) => message.message.trim() !== ""
          );
          setFieldValue("starter_messages", [
            ...filteredStarterMessages,
            ...data,
          ]);
        }
      } catch (error) {
        console.error("Failed to refresh prompts:", error);
      } finally {
        setIsRefreshing(false);
      }
    },
    1000
  );

  const [labelToDelete, setLabelToDelete] = useState<PersonaLabel | null>(null);
  const [isRequestSuccessful, setIsRequestSuccessful] = useState(false);

  const { data: userGroups } = useUserGroups();
  // const { data: allUsers } = useUsers() as {
  //   data: MinimalUserSnapshot[] | undefined;
  // };

  const { data: users } = useSWR<MinimalUserSnapshot[]>(
    "/api/users",
    errorHandlingFetcher
  );

  const mapUsersToMinimalSnapshot = (users: any): MinimalUserSnapshot[] => {
    if (!users || !Array.isArray(users.users)) return [];
    return users.users.map((user: any) => ({
      id: user.id,
      name: user.name,
      email: user.email,
    }));
  };

  if (!labels) {
    return <></>;
  }

  // hiding some prompts not required for now
  const showAllPrompts = false;

  return (
    <div className="mx-auto max-w-4xl">
      <style>
        {`
          .assistant-editor input::placeholder,
          .assistant-editor textarea::placeholder {
            opacity: 0.5;
          }
        `}
      </style>
      {!admin && (
        <div className="absolute top-4 left-4">
          <BackButton />
        </div>
      )}
      {labelToDelete && (
        <DeleteEntityModal
          entityType="label"
          entityName={labelToDelete.name}
          onClose={() => setLabelToDelete(null)}
          onSubmit={async () => {
            const response = await deleteLabel(labelToDelete.id);
            if (response?.ok) {
              setPopup({
                message: `Label deleted successfully`,
                type: "success",
              });
              await refreshLabels();
            } else {
              setPopup({
                message: `Failed to delete label - ${await response.text()}`,
                type: "error",
              });
            }
            setLabelToDelete(null);
          }}
        />
      )}
      {popup}
      <Formik
        enableReinitialize={true}
        initialValues={initialValues}
        validationSchema={Yup.object()
          .shape({
            name: Yup.string().required(
              "Must provide a name for the Assistant"
            ),
            description: Yup.string().required(
              "Must provide a description for the Assistant"
            ),
            system_prompt: Yup.string(),
            search_tool_description: Yup.string(),
            history_query_rephrase: Yup.string(),
            custom_tool_argument_system_prompt: Yup.string(),
            search_query_prompt: Yup.string(),
            search_data_source_selector_prompt: Yup.string(),
            task_prompt: Yup.string(),
            is_public: Yup.boolean().required(),
            document_set_ids: Yup.array().of(Yup.number()),
            num_chunks: Yup.number().nullable(),
            include_citations: Yup.boolean().required(),
            llm_relevance_filter: Yup.boolean().required(),
            llm_model_version_override: Yup.string().nullable(),
            llm_model_provider_override: Yup.string().nullable(),
            starter_messages: Yup.array().of(
              Yup.object().shape({
                message: Yup.string(),
              })
            ),
            search_start_date: Yup.date().nullable(),
            icon_color: Yup.string(),
            icon_shape: Yup.number(),
            uploaded_image: Yup.mixed().nullable(),
            prompt_shortcuts: Yup.array().of(
              Yup.object().shape({
                prompt: Yup.string(),
                content: Yup.string(),
                active: Yup.boolean(),
                is_public: Yup.boolean(),
                assistant_id: Yup.number().nullable(),
              })
            ),
            // EE Only
            label_ids: Yup.array().of(Yup.number()),
            selectedUsers: Yup.array().of(Yup.object()),
            selectedGroups: Yup.array().of(Yup.number()),
            selectedMicrosoftADGroups: Yup.array().of(Yup.string()),
          })
          .test(
            "system-prompt-or-task-prompt",
            "Must provide either Instructions or Reminders (Advanced)",
            function (values) {
              const systemPromptSpecified =
                values.system_prompt && values.system_prompt.trim().length > 0;
              const taskPromptSpecified =
                values.task_prompt && values.task_prompt.trim().length > 0;
             
              if (systemPromptSpecified || taskPromptSpecified) {
                return true;
              }

              return this.createError({
                path: "system_prompt",
                message:
                  "Must provide either Instructions or Reminders (Advanced)",
              });
            }
          )}
        onSubmit={async (values, formikHelpers) => {
          if (
            values.llm_model_provider_override &&
            !values.llm_model_version_override
          ) {
            setPopup({
              type: "error",
              message:
                "Must select a model if a non-default LLM provider is chosen.",
            });
            return;
          }

          formikHelpers.setSubmitting(true);
          let enabledTools = Object.keys(values.enabled_tools_map)
            .map((toolId) => Number(toolId))
            .filter((toolId) => values.enabled_tools_map[toolId]);

          const searchToolEnabled = searchTool
            ? enabledTools.includes(searchTool.id)
            : false;

          // if disable_retrieval is set, set num_chunks to 0
          // to tell the backend to not fetch any documents
          const numChunks = searchToolEnabled ? values.num_chunks || 10 : 0;
          const starterMessages = values.starter_messages
            .filter(
              (message: { message: string }) => message.message.trim() !== ""
            )
            .map((message: { message: string; name?: string }) => ({
              message: message.message,
              name: message.name || message.message,
            }));

          // Filter out empty prompt shortcuts and include all valid shortcuts
          const promptShortcuts = values.prompt_shortcuts
            .filter(
              (shortcut: { prompt: string; content: string; active: boolean; is_public: boolean; assistant_id: number | null }) => 
                shortcut.prompt.trim() !== "" && shortcut.content.trim() !== ""
            );

          // don't set groups if marked as public
          const groups = values.is_public ? [] : values.selectedGroups;
          const microsoftADGroups = values.is_public ? [] : (values.selectedMicrosoftADGroups || []);
          const submissionData: PersonaUpsertParameters = {
            ...values,
            existing_prompt_id: existingPrompt?.id ?? null,
            is_default_persona: admin!,
            starter_messages: starterMessages,
            prompt_shortcuts: promptShortcuts,
            shortcuts_to_delete: values.shortcuts_to_delete || [],
            groups: groups,
            microsoft_ad_groups: microsoftADGroups,
            users: values.is_public
              ? undefined
              : [
                  ...values.selectedUsers
                    .map((u: MinimalUserSnapshot) => u.id)
                    .filter((id: string) => !(user && id === user.id)),
                  ...(user && !checkUserIsNoAuthUser(user.id) ? [user.id] : []),
                ],
            tool_ids: enabledTools,
            remove_image: removePersonaImage,
            search_start_date: values.search_start_date
              ? new Date(values.search_start_date)
              : null,
            num_chunks: numChunks,
          };

          let personaResponse;
          if (isUpdate) {
            personaResponse = await updatePersona(
              existingPersona.id,
              submissionData
            );
          } else {
            personaResponse = await createPersona(submissionData);
          }

          let error = null;

          if (!personaResponse) {
            error = "Failed to create Assistant - no response received";
          } else if (!personaResponse.ok) {
            error = await personaResponse.text();
          }

          if (error || !personaResponse) {
            setPopup({
              type: "error",
              message: `Failed to create Assistant - ${error}`,
            });
            formikHelpers.setSubmitting(false);
          } else {
            const assistant = await personaResponse.json();
            const assistantId = assistant.id;
            if (
              shouldAddAssistantToUserPreferences &&
              user?.preferences?.chosen_assistants
            ) {
              const success = await addAssistantToList(assistantId);
              if (success) {
                setPopup({
                  message: `"${assistant.name}" has been added to your list.`,
                  type: "success",
                });
                await refreshAssistants();
              } else {
                setPopup({
                  message: `"${assistant.name}" could not be added to your list.`,
                  type: "error",
                });
              }
            }

            await refreshAssistants();
            router.push(
              redirectType === SuccessfulPersonaUpdateRedirectType.ADMIN
                ? `/admin/assistants?u=${Date.now()}`
                : `/chat?assistantId=${assistantId}`
            );
            setIsRequestSuccessful(true);
          }
        }}
      >
        {({
          isSubmitting,
          values,
          setFieldValue,
          errors,
          ...formikProps
        }: FormikProps<any>) => {
          function toggleToolInValues(toolId: number) {
            const updatedEnabledToolsMap = {
              ...values.enabled_tools_map,
              [toolId]: !values.enabled_tools_map[toolId],
            };
            setFieldValue("enabled_tools_map", updatedEnabledToolsMap);
          }

          // model must support image input for image generation
          // to work
          const currentLLMSupportsImageOutput = checkLLMSupportsImageInput(
            values.llm_model_version_override || defaultModelName || ""
          );

          return (
            <Form className="w-full text-text-950 assistant-editor"
            onKeyDown={(e: React.KeyboardEvent<HTMLFormElement>) => {
              if (e.key === "Enter" && e.target instanceof HTMLInputElement) {
                e.preventDefault();
              }
            }}
            >
              {/* Refresh starter messages when name or description changes */}
              <p className="text-base font-normal text-2xl">
                {existingPersona ? (
                  <>
                    Edit assistant <b>{existingPersona.name}</b>
                  </>
                ) : (
                  "Create an Assistant"
                )}
              </p>
              <div className="max-w-4xl w-full">
                <Separator />
                <div className="flex gap-x-2 items-center">
                  <div className="block font-medium text-sm">
                    Assistant Icon
                  </div>
                </div>
                <SubLabel>
                  The icon that will visually represent your Assistant
                </SubLabel>
                <div className="flex gap-x-2 items-center">
                  <div
                    className="p-4 cursor-pointer  rounded-full flex  "
                    style={{
                      borderStyle: "dashed",
                      borderWidth: "1.5px",
                      borderSpacing: "4px",
                    }}
                  >
                    {values.uploaded_image ? (
                      <img
                        src={URL.createObjectURL(values.uploaded_image)}
                        alt="Uploaded assistant icon"
                        className="w-12 h-12 rounded-full object-cover"
                      />
                    ) : existingPersona?.uploaded_image_id &&
                      !removePersonaImage ? (
                      <img
                        src={buildImgUrl(existingPersona?.uploaded_image_id)}
                        alt="Uploaded assistant icon"
                        className="w-12 h-12 rounded-full object-cover"
                      />
                    ) : (
                      generateIdenticon((values.icon_shape || 0).toString(), 36)
                    )}
                  </div>

                  <div className="flex flex-col gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="text-xs flex justify-start gap-x-2"
                      onClick={() => {
                        const fileInput = document.createElement("input");
                        fileInput.type = "file";
                        fileInput.accept = "image/*";
                        fileInput.onchange = (e) => {
                          const file = (e.target as HTMLInputElement)
                            .files?.[0];
                          if (file) {
                            setFieldValue("uploaded_image", file);
                          }
                        };
                        fileInput.click();
                      }}
                    >
                      <CameraIcon size={14} />
                      Upload {values.uploaded_image && "New "}Image
                    </Button>

                    {values.uploaded_image && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="flex justify-start gap-x-2 text-xs"
                        onClick={() => {
                          setFieldValue("uploaded_image", null);
                          setRemovePersonaImage(false);
                        }}
                      >
                        <TrashIcon className="h-3 w-3" />
                        {removePersonaImage ? "Revert to Previous " : "Remove "}
                        Image
                      </Button>
                    )}

                    {!values.uploaded_image &&
                      (!existingPersona?.uploaded_image_id ||
                        removePersonaImage) && (
                        <Button
                          type="button"
                          className="text-xs"
                          variant="outline"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            const newShape = generateRandomIconShape();
                            const randomColor =
                              colorOptions[
                                Math.floor(Math.random() * colorOptions.length)
                              ];
                            setFieldValue("icon_shape", newShape.encodedGrid);
                            setFieldValue("icon_color", randomColor);
                          }}
                        >
                          <NewChatIcon size={14} />
                          Generate Icon
                        </Button>
                      )}

                    {existingPersona?.uploaded_image_id &&
                      removePersonaImage &&
                      !values.uploaded_image && (
                        <Button
                          type="button"
                          variant="outline"
                          className="text-xs"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRemovePersonaImage(false);
                            setFieldValue("uploaded_image", null);
                          }}
                        >
                          <SwapIcon className="h-3 w-3" />
                          Revert to Previous Image
                        </Button>
                      )}

                    {existingPersona?.uploaded_image_id &&
                      !removePersonaImage &&
                      !values.uploaded_image && (
                        <Button
                          type="button"
                          variant="outline"
                          className="text-xs"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRemovePersonaImage(true);
                          }}
                        >
                          <TrashIcon className="h-3 w-3" />
                          Remove Image
                        </Button>
                      )}
                  </div>
                </div>
              </div>

              <TextFormField
                maxWidth="max-w-lg"
                name="name"
                label="Name"
                placeholder="Email Assistant"
                aria-label="assistant-name-input"
                className="[&_input]:placeholder:text-text-muted/50"
                subtext="The name of the assistant"
              />

              <TextFormField
                maxWidth="max-w-lg"
                name="description"
                label="Description"
                placeholder="Provide a summary of what this assistant does.Mention when or why someone would use it."
                data-testid="assistant-description-input"
                className="[&_input]:placeholder:text-text-muted/50"
                subtext="Provide a summary of what this assistant does.Mention when or why someone would use it."
                />

              <Separator />

              <TextFormField
                maxWidth="max-w-4xl"
                name="system_prompt"
                label="Global Context Prompt"
                isTextArea={true}
                placeholder="Explain the Assistant's role and define how it handles queries, selects appropriate data sources, and formats responses while applying component naming rules for accurate technical support."                
                data-testid="assistant-instructions-input"
                className="[&_textarea]:placeholder:text-text-muted/50"
                subtext="Explain the Assistant's role and define how it handles queries, selects appropriate data sources, and formats responses while applying component naming rules for accurate technical support."
              />
              
              {showAllPrompts && (
                <TextFormField
                maxWidth="max-w-4xl"
                name="search_tool_description"
                label="Search Tool Selection Prompt"
                isTextArea={true}
                placeholder="Specifies when to use the search tool for fetching data from stored documents. Also guides how to handle queries containing quoted text ensuring the quoted content is preserved exactly for accurate searching, with quotes removed from the query string."
                data-testid="assistant-search_tool_description-input"
                className="[&_textarea]:placeholder:text-text-muted/50"
                subtext="DSpecifies when to use the search tool for fetching data from stored documents. Also guides how to handle queries containing quoted text ensuring the quoted content is preserved exactly for accurate searching, with quotes removed from the query string."
              />
              )}              

              <TextFormField
                maxWidth="max-w-4xl"
                name="history_query_rephrase"
                label="Chat History Rephrasing Prompt"
                isTextArea={true}
                placeholder="Explain how the assistant should rephrase follow-up questions using context from previous messages. If there is any change in the terminology or the any components details, then use the history to rephrase the question."
                data-testid="assistant-history_query_rephrase-input"
                className="[&_textarea]:placeholder:text-text-muted/50"
                subtext="Explain how the assistant should rephrase follow-up questions using context from previous messages. If there is any change in the terminology or the any components details, then use the history to rephrase the question."
              />

              <TextFormField
                maxWidth="max-w-4xl"
                name="custom_tool_argument_system_prompt"
                label="Custom Tool System Prompt"
                isTextArea={true}
                placeholder="Explain how to extract relevant arguments from user input. Include any mappings or transformation rules needed."
                data-testid="assistant-custom_tool_argument_system_prompt-input"
                className="[&_textarea]:placeholder:text-text-muted/50"
                subtext="Explain how to extract relevant arguments from user input. Include any mappings or transformation rules needed."
              />

              <TextFormField
                maxWidth="max-w-4xl"
                name="search_query_prompt"
                label="Search Tool Query Prompt"
                isTextArea={true}
                placeholder="This field defines how user queries should be processed, including preserving specific input formats and mapping alternate names for Seclore components. It also sets rules for determining the correct data source when resolving version-related queries."
                data-testid="assistant-search_query_prompt-input"
                className="[&_textarea]:placeholder:text-text-muted/50"
                subtext="This field defines how user queries should be processed, including preserving specific input formats and mapping alternate names for Seclore components. It also sets rules for determining the correct data source when resolving version-related queries."
              />

              <TextFormField
                maxWidth="max-w-4xl"
                name="search_data_source_selector_prompt"
                label="Knowledge Base Filter Prompt"
                isTextArea={true}
                placeholder="Defines the logic for selecting the appropriate knowledge base (KB) to answer user queries. Based on the query type such as version info, infra-specific details, informational content, or troubleshooting this prompt ensures responses are sourced from the correct KB like docs.seclore.com or Freshdesk."
                data-testid="assistant-search_data_source_selector_prompt-input"
                className="[&_textarea]:placeholder:text-text-muted/50"
                subtext="Defines the logic for selecting the appropriate knowledge base (KB) to answer user queries. Based on the query type such as version info, infra-specific details, informational content, or troubleshooting this prompt ensures responses are sourced from the correct KB like docs.seclore.com or Freshdesk."
              />

              <div className="w-full max-w-4xl">
                <div className="flex flex-col">
                  {searchTool && (
                    <>
                      <Separator />
                      <div className="flex gap-x-2 py-2 flex justify-start">
                        <div>
                          <div
                            className="flex items-start gap-x-2
                          "
                          >
                            <p className="block font-medium text-sm">
                              Knowledge
                            </p>
                            <div className="flex items-center">
                              <TooltipProvider delayDuration={0}>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div
                                      className={`${
                                        ccPairs.length === 0
                                          ? "opacity-70 cursor-not-allowed"
                                          : ""
                                      }`}
                                    >
                                      <SwitchField
                                        size="sm"
                                        onCheckedChange={(checked) => {
                                          setFieldValue("num_chunks", null);
                                          toggleToolInValues(searchTool.id);
                                        }}
                                        name={`enabled_tools_map.${searchTool.id}`}
                                        disabled={ccPairs.length === 0}
                                      />
                                    </div>
                                  </TooltipTrigger>

                                  {ccPairs.length === 0 && (
                                    <TooltipContent side="top" align="center">
                                      <p className="bg-background-900 max-w-[200px] text-sm rounded-lg p-1.5 text-white">
                                        To use the Knowledge Action, you need to
                                        have at least one Connector configured.
                                      </p>
                                    </TooltipContent>
                                  )}
                                </Tooltip>
                              </TooltipProvider>
                            </div>
                          </div>
                          <p
                            className="text-sm text-subtle"
                            style={{ color: "rgb(113, 114, 121)" }}
                          >
                            Attach additional unique knowledge to this assistant
                          </p>
                        </div>
                      </div>
                    </>
                  )}
                  {ccPairs.length > 0 &&
                    searchTool &&
                    values.enabled_tools_map[searchTool.id] &&
                    !(user?.role != "admin" && documentSets.length === 0) && (
                      <CollapsibleSection>
                        <div className="mt-2">
                          {ccPairs.length > 0 && (
                            <>
                              <Label small>Document Sets</Label>
                              <div>
                                <SubLabel>
                                  <>
                                    Select which{" "}
                                    {!user || user.role === "admin" ? (
                                      <Link
                                        href="/admin/documents/sets"
                                        className="font-semibold underline hover:underline text-text"
                                        target="_blank"
                                      >
                                        Document Sets
                                      </Link>
                                    ) : (
                                      "Document Sets"
                                    )}{" "}
                                    this Assistant should use to inform its
                                    responses. If none are specified, the
                                    Assistant will reference all available
                                    documents.
                                  </>
                                </SubLabel>
                              </div>

                              {documentSets.length > 0 ? (
                                <FieldArray
                                  name="document_set_ids"
                                  render={(arrayHelpers: ArrayHelpers) => (
                                    <div>
                                      <div className="mb-3 mt-2 flex gap-2 flex-wrap text-sm">
                                        {documentSets.map((documentSet) => (
                                          <DocumentSetSelectable
                                            key={documentSet.id}
                                            documentSet={documentSet}
                                            isSelected={values.document_set_ids.includes(
                                              documentSet.id
                                            )}
                                            onSelect={() => {
                                              const index =
                                                values.document_set_ids.indexOf(
                                                  documentSet.id
                                                );
                                              if (index !== -1) {
                                                arrayHelpers.remove(index);
                                              } else {
                                                arrayHelpers.push(
                                                  documentSet.id
                                                );
                                              }
                                            }}
                                          />
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                />
                              ) : (
                                <p className="text-sm">
                                  <Link
                                    href="/admin/documents/sets/new"
                                    className="text-primary hover:underline"
                                  >
                                    + Create Document Set
                                  </Link>
                                </p>
                              )}
                            </>
                          )}
                        </div>
                      </CollapsibleSection>
                    )}

                  <Separator />
                  <div className="py-2">
                    <p className="block font-medium text-sm mb-2">Actions</p>

                    {imageGenerationTool && (
                      <>
                        <div className="flex items-center content-start mb-2">
                          <BooleanFormField
                            name={`enabled_tools_map.${imageGenerationTool.id}`}
                            label={imageGenerationTool.display_name}
                            subtext="Generate and manipulate images using AI-powered tools"
                            disabled={
                              !currentLLMSupportsImageOutput ||
                              !isImageGenerationAvailable
                            }
                            disabledTooltip={
                              !currentLLMSupportsImageOutput
                                ? "To use Image Generation, select GPT-4 or another image compatible model as the default model for this Assistant."
                                : "Image Generation requires an OpenAI or Azure Dall-E configuration."
                            }
                          />
                        </div>
                      </>
                    )}

                    {internetSearchTool && (
                      <>
                        <BooleanFormField
                          name={`enabled_tools_map.${internetSearchTool.id}`}
                          label={internetSearchTool.display_name}
                          subtext="Access real-time information and search the web for up-to-date results"
                        />
                      </>
                    )}

                    {customTools.length > 0 &&
                      customTools.map((tool) => (
                        <BooleanFormField
                          key={tool.id}
                          name={`enabled_tools_map.${tool.id}`}
                          label={tool.display_name}
                          subtext={tool.description}
                        />
                      ))}
                  </div>
                </div>
              </div>
              <Separator className="max-w-4xl mt-0" />

              <div className="-mt-2">
                <div className="flex gap-x-2 mb-2 items-center">
                  <div className="block font-medium text-sm">Default Model</div>
                </div>
                <LLMSelector
                  llmProviders={llmProviders}
                  currentLlm={
                    values.llm_model_version_override
                      ? structureValue(
                          values.llm_model_provider_override,
                          "",
                          values.llm_model_version_override
                        )
                      : null
                  }
                  requiresImageGeneration={
                    imageGenerationTool
                      ? values.enabled_tools_map[imageGenerationTool.id]
                      : false
                  }
                  onSelect={(selected) => {
                    if (selected === null) {
                      setFieldValue("llm_model_version_override", null);
                      setFieldValue("llm_model_provider_override", null);
                    } else {
                      const { modelName, provider, name } =
                        destructureValue(selected);
                      if (modelName && name) {
                        setFieldValue("llm_model_version_override", modelName);
                        setFieldValue("llm_model_provider_override", name);
                      }
                    }
                  }}
                />
              </div>

              <Separator />
              <AdvancedOptionsToggle
                showAdvancedOptions={showAdvancedOptions}
                setShowAdvancedOptions={setShowAdvancedOptions}
              />
              {showAdvancedOptions && (
                <>
                  <div className="max-w-4xl w-full">
                    <div className="flex gap-x-2 items-center ">
                      <div className="block font-medium text-sm">Access</div>
                    </div>
                    <SubLabel>
                      Control who can access and use this assistant
                    </SubLabel>

                    <div className="min-h-[100px]">
                      <div className="flex items-center mb-2">
                        <SwitchField
                          name="is_public"
                          size="md"
                          onCheckedChange={(checked) => {
                            setFieldValue("is_public", checked);
                            if (checked) {
                              setFieldValue("selectedUsers", []);
                              setFieldValue("selectedGroups", []);
                              setFieldValue("selectedMicrosoftADGroups", []);
                            }
                          }}
                        />
                        <span className="text-sm ml-2">
                          {values.is_public ? "Public" : "Private"}
                        </span>
                      </div>

                      {values.is_public ? (
                        <p className="text-sm text-text-dark">
                          Anyone from your organization can view and use this
                          assistant
                        </p>
                      ) : (
                        <>
                          <div className="mt-2">
                            <Label className="mb-2" small>
                              Share with Users and Groups
                            </Label>

                            {/* Users Section */}
                            <div className="mb-4">
                              <h4 className="text-sm font-medium text-gray-700 mb-2">Users</h4>
                            <SearchMultiSelectDropdown
                              options={[
                                ...(Array.isArray(users) ? users : [])
                                  .filter(
                                    (u: MinimalUserSnapshot) =>
                                      !values.selectedUsers.some(
                                        (su: MinimalUserSnapshot) =>
                                          su.id === u.id
                                      ) && u.id !== user?.id
                                  )
                                  .map((u: MinimalUserSnapshot) => ({
                                    name: u.email,
                                    value: u.id,
                                    type: "user",
                                  })),
                                // Add Microsoft AD users when OIDC is enabled
                                ...(isOIDC && microsoftUsers?.users ? 
                                  microsoftUsers.users
                                    .filter(
                                      (mu: { id: string; user_principal_name: string }) =>
                                        !values.selectedUsers.some(
                                          (su: MinimalUserSnapshot) =>
                                            su.id === mu.user_principal_name
                                        ) && mu.user_principal_name !== user?.email
                                    )
                                    .map((mu: { id: string; display_name: string; user_principal_name: string; mail: string }) => ({
                                      name: mu.user_principal_name,
                                      value: mu.user_principal_name,
                                      type: "microsoft_user" as const,
                                      display_name: mu.display_name,
                                      mail: mu.mail,
                                    })) : []
                                ),
                              ]}
                                onSelect={async (
                                  selected: DropdownOption<string | number>
                                ) => {
                                  const option = selected as {
                                    name: string;
                                    value: string | number;
                                    type: "user" | "microsoft_user";
                                  };
                                  if (option.type === "user") {
                                    setFieldValue("selectedUsers", [
                                      ...values.selectedUsers,
                                      { id: option.value, email: option.name },
                                    ]);
                                  } else if (option.type === "microsoft_user") {
                                    try {
                                      // First, add the Microsoft user to the database
                                      const response = await fetch("/api/auth/oidc/add-microsoft-user", {
                                        method: "POST",
                                        headers: {
                                          "Content-Type": "application/json",
                                        },
                                        body: JSON.stringify({
                                          email: option.name,
                                        }),
                                      });
                                      
                                      if (response.ok) {
                                        const result = await response.json();
                                        // Use the new UUID from the database
                                        setFieldValue("selectedUsers", [
                                          ...values.selectedUsers,
                                          { id: result.user_id, email: option.name },
                                        ]);
                                      } else {
                                        console.error("Failed to add Microsoft user to database");
                                      }
                                    } catch (error) {
                                      console.error("Error adding Microsoft user:", error);
                                    }
                                  }
                                }}
                              />
                            </div>

                            {/* Groups Section */}
                            <div className="mb-4">
                              <h4 className="text-sm font-medium text-gray-700 mb-2">Groups</h4>
                              

                              
                              {isOIDC ? (
                                <>
                                  <MicrosoftADGroupsDropdown
                                  options={[
                                    ...(userGroups || [])
                                      .filter(
                                        (g: UserGroup) =>
                                          !values.selectedGroups.includes(g.id)
                                      )
                                      .map((g: UserGroup) => ({
                                        name: g.name,
                                        value: g.id,
                                        type: "group",
                                      })),
                                    // Add Microsoft AD groups when OIDC is enabled (let component handle filtering)
                                    ...(microsoftADGroups?.groups ? 
                                      microsoftADGroups.groups
                                        .filter(
                                          (g: { id: string; display_name: string }) =>
                                            !values.selectedMicrosoftADGroups?.includes(g.id)
                                        )
                                        .map((g: { id: string; display_name: string; mail?: string; is_member: boolean }) => ({
                                          name: g.display_name,
                                          value: g.id,
                                          type: "microsoft_ad_group" as const,
                                          mail: g.mail,
                                          is_member: g.is_member,
                                        } as MicrosoftADGroupOption)) : []
                                    ),
                                  ]}
                                  onSelect={(
                                    selected: DropdownOption<string | number>
                                  ) => {
                                    const option = selected as {
                                      name: string;
                                      value: string | number;
                                        type: "user" | "group" | "microsoft_ad_group";
                                    };
                                      if (option.type === "group") {
                                      setFieldValue("selectedGroups", [
                                        ...values.selectedGroups,
                                        option.value,
                                      ]);
                                      } else if (option.type === "microsoft_ad_group") {
                                        setFieldValue("selectedMicrosoftADGroups", [
                                          ...(values.selectedMicrosoftADGroups || []),
                                          option.value as string,
                                        ]);
                                    }
                                  }}
                                  onSearchChange={(searchTerm) => {
                                    setMicrosoftGroupsSearchQuery(searchTerm);
                                  }}
                                  searchQuery={microsoftGroupsSearchQuery}
                                  isLoading={false}
                                  placeholder="Search and select groups..."
                                />
                                </>
                              ) : (
                                <SearchMultiSelectDropdown
                                  options={[
                                    ...(userGroups || [])
                                      .filter(
                                        (g: UserGroup) =>
                                          !values.selectedGroups.includes(g.id)
                                      )
                                      .map((g: UserGroup) => ({
                                        name: g.name,
                                        value: g.id,
                                        type: "group",
                                      })),
                                  ]}
                                  onSelect={(
                                    selected: DropdownOption<string | number>
                                  ) => {
                                    const option = selected as {
                                      name: string;
                                      value: string | number;
                                        type: "user" | "group" | "microsoft_ad_group";
                                    };
                                      if (option.type === "group") {
                                      setFieldValue("selectedGroups", [
                                        ...values.selectedGroups,
                                        option.value,
                                      ]);
                                    }
                                  }}
                                />
                              )}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2 mt-2">
                            {/* Selected Users */}
                            {values.selectedUsers.length > 0 && (
                              <div className="w-full mb-4">
                                <h5 className="text-sm font-medium text-gray-600 mb-2">Selected Users:</h5>
                                <div className="flex flex-wrap gap-2">
                            {values.selectedUsers.map(
                              (user: MinimalUserSnapshot) => (
                                <SourceChip
                                  key={user.id}
                                  onRemove={() => {
                                    setFieldValue(
                                      "selectedUsers",
                                      values.selectedUsers.filter(
                                        (u: MinimalUserSnapshot) =>
                                          u.id !== user.id
                                      )
                                    );
                                  }}
                                  title={user.email}
                                  icon={<UserIcon size={12} />}
                                />
                              )
                            )}
                                </div>
                              </div>
                            )}

                            {/* Selected Groups */}
                            {(values.selectedGroups.length > 0 || values.selectedMicrosoftADGroups?.length > 0) && (
                              <div className="w-full mb-4">
                                <h5 className="text-sm font-medium text-gray-600 mb-2">Selected Groups:</h5>
                                <div className="flex flex-wrap gap-2">
                            {values.selectedGroups.map((groupId: number) => {
                              const group = (userGroups || []).find(
                                (g: UserGroup) => g.id === groupId
                              );
                              return group ? (
                                      <div
                                        key={group.id}
                                        className={`inline-block ${
                                          selectedDBGroupId === group.id ? 'ring-2 ring-blue-500' : ''
                                        }`}
                                      >
                                <SourceChip
                                  key={group.id}
                                  title={group.name}
                                  onRemove={() => {
                                    setFieldValue(
                                      "selectedGroups",
                                      values.selectedGroups.filter(
                                        (id: number) => id !== group.id
                                      )
                                    );
                                            // Clear selected group if it was this one
                                            if (selectedDBGroupId === group.id) {
                                              setSelectedDBGroupId(null);
                                            }
                                  }}
                                          onClick={() => setSelectedDBGroupId(group.id)}
                                  icon={<GroupsIconSkeleton size={12} />}
                                />
                                      </div>
                              ) : null;
                            })}
                                  {/* Display selected Microsoft AD groups */}
                                  {values.selectedMicrosoftADGroups?.map((groupId: string) => {
                                    const group = microsoftADGroups?.groups?.find(
                                      (g: { id: string; display_name: string }) => g.id === groupId
                                    );
                                    return group ? (
                                      <div
                                        key={group.id}
                                        className={`inline-block ${
                                          selectedGroupId === group.id ? 'ring-2 ring-blue-500' : ''
                                        }`}
                                      >
                                        <SourceChip
                                          title={group.display_name}
                                          onRemove={() => {
                                            setFieldValue(
                                              "selectedMicrosoftADGroups",
                                              values.selectedMicrosoftADGroups?.filter(
                                                (id: string) => id !== group.id
                                              ) || []
                                            );
                                            // Clear selected group if it was this one
                                            if (selectedGroupId === group.id) {
                                              setSelectedGroupId(null);
                                            }
                                          }}
                                          onClick={() => setSelectedGroupId(group.id)}
                                        />
                                      </div>
                                    ) : null;
                                  })}
                                </div>
                              </div>
                            )}

                            {/* Display users for selected group */}
                            {selectedGroupId && (
                              <div className="w-full mt-4 p-4 border rounded-lg bg-gray-50">
                                <div className="flex justify-between items-center mb-2">
                                  <h4 className="font-medium text-sm text-gray-700">
                                    Users in selected Microsoft AD group:
                                  </h4>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setSelectedGroupId(null)}
                                    className="text-xs text-gray-500 hover:text-gray-700"
                                  >
                                    <XIcon size={14} />
                                  </Button>
                                </div>
                                {loadingGroupUsers ? (
                                  <div className="text-sm text-gray-500">Loading users...</div>
                                ) : groupUsers && groupUsers.length > 0 ? (
                                  <div className="space-y-1">
                                    {groupUsers.map((user) => (
                                      <div key={user.id} className="flex justify-between items-center text-sm text-gray-600">
                                        <span>{user.display_name} ({user.user_principal_name})</span>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="text-sm text-gray-500">No users are present in this Microsoft AD group</div>
                                )}
                              </div>
                            )}

                            {/* Display users for selected database group */}
                            {selectedDBGroupId && userGroups && (
                              <div className="w-full mt-4 p-4 border rounded-lg bg-gray-50">
                                <div className="flex justify-between items-center mb-2">
                                  <h4 className="font-medium text-sm text-gray-700">
                                    Users in selected database group:
                                  </h4>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setSelectedDBGroupId(null)}
                                    className="text-xs text-gray-500 hover:text-gray-700"
                                  >
                                    <XIcon size={14} />
                                  </Button>
                              </div>
                                <div className="space-y-1">
                                  {(() => {
                                    const selectedGroup = userGroups.find(g => g.id === selectedDBGroupId);
                                    return selectedGroup?.users?.map((user) => (
                                      <div key={user.id} className="flex justify-between items-center text-sm text-gray-600">
                                        <span>{user.email}</span>
                                        
                                      </div>
                                    )) || [];
                                  })()}
                                </div>
                              </div>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  
                  <Separator />
                  <div className="w-full flex flex-col">
                    <div className="flex gap-x-2 items-center">
                      <div className="block font-medium text-sm">
                        [Optional] Starter Messages
                      </div>
                    </div>

                    <SubLabel>
                      Sample messages that help users understand what this
                      assistant can do and how to interact with it effectively.
                    </SubLabel>

                    <div className="w-full">
                      <FieldArray
                        name="starter_messages"
                        render={(arrayHelpers: ArrayHelpers) => (
                          <StarterMessagesList
                            debouncedRefreshPrompts={() =>
                              debouncedRefreshPrompts(values, setFieldValue)
                            }
                            autoStarterMessageEnabled={
                              autoStarterMessageEnabled
                            }
                            isRefreshing={isRefreshing}
                            values={values.starter_messages}
                            arrayHelpers={arrayHelpers}
                            setFieldValue={setFieldValue}
                          />
                        )}
                      />
                    </div>
                  </div>

                  {/* start changes for the quick prompts */}
                  <Separator />
                  <div className="w-full flex flex-col">
                    <div className="flex gap-x-2 items-center">
                      <div className="block font-medium text-sm">
                        Prompt Shortcuts
                      </div>
                    </div>

                    <SubLabel>
                      Manage and customize prompt shortcuts for your assistants. 
                    </SubLabel>

                    <div className="w-full">
                      <FieldArray
                        name="prompt_shortcuts"
                        render={(arrayHelpers: ArrayHelpers) => (
                          <PromptShortcutsList
                            values={values.prompt_shortcuts || []}
                            arrayHelpers={arrayHelpers}
                            setFieldValue={setFieldValue}
                            assistantId={existingPersona?.id ?? null}
                          />
                        )}
                      />
                    </div>
                  </div>
                  {/* end of changes for the quick prompts */}

                  <div className=" w-full max-w-4xl">
                    <Separator />
                    <div className="flex gap-x-2 items-center mt-4 ">
                      <div className="block font-medium text-sm">Labels</div>
                    </div>
                    <p
                      className="text-sm text-subtle"
                      style={{ color: "rgb(113, 114, 121)" }}
                    >
                      Select labels to categorize this assistant
                    </p>
                    <div className="mt-3">
                      <SearchMultiSelectDropdown
                        onCreate={async (name: string) => {
                          await createLabel(name);
                          const currentLabels = await refreshLabels();

                          setTimeout(() => {
                            const newLabelId = currentLabels.find(
                              (l: { name: string }) => l.name === name
                            )?.id;
                            const updatedLabelIds = [
                              ...values.label_ids,
                              newLabelId as number,
                            ];
                            setFieldValue("label_ids", updatedLabelIds);
                          }, 300);
                        }}
                        options={Array.from(
                          new Set(labels.map((label) => label.name))
                        ).map((name) => ({
                          name,
                          value: name,
                        }))}
                        onSelect={(selected) => {
                          const newLabelIds = [
                            ...values.label_ids,
                            labels.find((l) => l.name === selected.value)
                              ?.id as number,
                          ];
                          setFieldValue("label_ids", newLabelIds);
                        }}
                        itemComponent={({ option }) => (
                          <div className="flex items-center justify-between px-4 py-3 text-sm hover:bg-hover cursor-pointer border-b border-border last:border-b-0">
                            <div
                              className="flex-grow"
                              onClick={() => {
                                const label = labels.find(
                                  (l) => l.name === option.value
                                );
                                if (label) {
                                  const isSelected = values.label_ids.includes(
                                    label.id
                                  );
                                  const newLabelIds = isSelected
                                    ? values.label_ids.filter(
                                        (id: number) => id !== label.id
                                      )
                                    : [...values.label_ids, label.id];
                                  setFieldValue("label_ids", newLabelIds);
                                }
                              }}
                            >
                              <span className="font-normal leading-none">
                                {option.name}
                              </span>
                            </div>
                            {admin && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const label = labels.find(
                                    (l) => l.name === option.value
                                  );
                                  if (label) {
                                    deleteLabel(label.id);
                                  }
                                }}
                                className="ml-2 p-1 hover:bg-background-hover rounded"
                              >
                                <TrashIcon size={16} />
                              </button>
                            )}
                          </div>
                        )}
                      />
                      <div className="mt-2 flex flex-wrap gap-2">
                        {values.label_ids.map((labelId: number) => {
                          const label = labels.find((l) => l.id === labelId);
                          return label ? (
                            <SourceChip
                              key={label.id}
                              onRemove={() => {
                                setFieldValue(
                                  "label_ids",
                                  values.label_ids.filter(
                                    (id: number) => id !== label.id
                                  )
                                );
                              }}
                              title={label.name}
                              icon={<TagIcon size={12} />}
                            />
                          ) : null;
                        })}
                      </div>
                    </div>
                  </div>
                  <Separator />

                  <div className="flex flex-col gap-y-4">
                    <div className="flex flex-col gap-y-4">
                      <h3 className="font-medium text-sm">Knowledge Options</h3>
                      <div className="flex flex-col gap-y-4 ml-4">
                        <TextFormField
                          small={true}
                          name="num_chunks"
                          label="[Optional] Number of Context Documents"
                          placeholder="Default 10"
                          onChange={(e) => {
                            const value = e.target.value;
                            if (value === "" || /^[0-9]+$/.test(value)) {
                              setFieldValue("num_chunks", value);
                            }
                          }}
                        />

                        <TextFormField
                          width="max-w-xl"
                          type="date"
                          small
                          subtext="Documents prior to this date will be ignored."
                          label="[Optional] Knowledge Cutoff Date"
                          name="search_start_date"
                        />

                        <BooleanFormField
                          small
                          removeIndent
                          name="llm_relevance_filter"
                          label="AI Relevance Filter"
                          subtext="If enabled, the LLM will filter out documents that are not useful for answering the user query prior to generating a response. This typically improves the quality of the response but incurs slightly higher cost."
                        />

                        <BooleanFormField
                          small
                          removeIndent
                          name="include_citations"
                          label="Citations"
                          subtext="Response will include citations ([1], [2], etc.) for documents referenced by the LLM. In general, we recommend to leave this enabled in order to increase trust in the LLM answer."
                        />
                      </div>
                    </div>
                  </div>
                  <Separator />

                  <BooleanFormField
                    small
                    removeIndent
                    name="datetime_aware"
                    label="Date and Time Aware"
                    subtext='Toggle this option to let the assistant know the current date and time (formatted like: "Thursday Jan 1, 1970 00:01"). To inject it in a specific place in the prompt, use the pattern [[CURRENT_DATETIME]]'
                  />

                  <Separator />

                  <TextFormField
                    maxWidth="max-w-4xl"
                    name="task_prompt"
                    label="[Optional] Reminders"
                    isTextArea={true}
                    placeholder="Remember to reference all of the points mentioned in my message to you and focus on identifying action items that can move things forward"
                    onChange={(e) => {
                      setFieldValue("task_prompt", e.target.value);
                    }}
                    className="[&_textarea]:placeholder:text-text-muted/50"
                    subtext="Reminders are optional messages that are added to the assistant's response to help the user remember to take action. They are displayed in a separate section of the response."
                  />
                  <div className="flex justify-end">
                    {existingPersona && (
                      <DeletePersonaButtonInAssistantEditor
                        isDeleting={isDeleting}
                        setIsDeleting={setIsDeleting}
                        setPopup={setPopup}
                        personaName={existingPersona.name}
                        personaId={existingPersona!.id}
                        redirectType={SuccessfulPersonaUpdateRedirectType.ADMIN}
                      />
                    )}
                  </div>
                </>
              )}

              <div className="mt-12 gap-x-2 w-full  justify-end flex">
                <Button
                  type="submit"
                  disabled={isSubmitting || isRequestSuccessful || isDeleting}
                >
                  {isUpdate ? "Update" : "Create"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={isDeleting}
                  onClick={() => router.back()}
                >
                  Cancel
                </Button>
              </div>
            </Form>
          );
        }}
      </Formik>
    </div>
  );
}
