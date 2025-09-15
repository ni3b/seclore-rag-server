"use client";

import { Button } from "@/components/ui/button";
import { deletePersona } from "../lib";
import { useRouter } from "next/navigation";
import { SuccessfulPersonaUpdateRedirectType } from "../enums";
import { PopupSpec } from "@/components/admin/connectors/Popup";
import { useState } from "react";
import { DeleteEntityModal } from "@/components/modals/DeleteEntityModal";

export function DeletePersonaButtonInAssistantEditor({
  isDeleting,
  setIsDeleting,
  setPopup,
  personaName = "this assistant",
  personaId,
  redirectType,
}: {
  isDeleting: boolean;
  setIsDeleting: (state: boolean) => void;
  setPopup: (popupSpec: PopupSpec | null) => void;
  personaName: string;
  personaId: number;
  redirectType: SuccessfulPersonaUpdateRedirectType;
}) {
  const router = useRouter();
  const [openConfirm, setOpenConfirm] = useState(false);

  return (
    <>
      {openConfirm && (
        <DeleteEntityModal
          entityType="assistant"
          entityName={personaName}
          onClose={() => {
            setOpenConfirm(false);
            setIsDeleting(false);
          }}
          onSubmit={async () => {
            const response = await deletePersona(personaId);
            if (response.ok) {
              setOpenConfirm(false);
              setIsDeleting(true);
              setPopup({
                type: "success",
                message: `"${personaName}" deleted successfully`,
              });
              await new Promise((resolve) => setTimeout(resolve, 1000));
              window.location.href =
                redirectType === SuccessfulPersonaUpdateRedirectType.ADMIN
                  ? `/admin/assistants?u=${Date.now()}`
                  : `/chat`;
            } else {
              setOpenConfirm(false);
              setPopup({
                type: "error",
                message: `Failed to delete persona. Try Again.`,
              });
            }
          }}
        />
      )}
      <Button
        type="button"
        variant="destructive"
        onClick={() => {
          setOpenConfirm(true);
          setIsDeleting(false);
        }}
        disabled={isDeleting}
      >
        Delete
      </Button>
    </>
  );
}