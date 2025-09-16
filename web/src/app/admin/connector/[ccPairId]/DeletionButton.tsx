"use client";

import { Button } from "@/components/ui/button";
import { CCPairFullInfo, ConnectorCredentialPairStatus } from "./types";
import { usePopup } from "@/components/admin/connectors/Popup";
import { FiTrash } from "react-icons/fi";
import { deleteCCPair } from "@/lib/documentDeletion";
import { mutate } from "swr";
import { buildCCPairInfoUrl } from "./lib";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useState } from "react";

export function DeletionButton({
  ccPair,
  refresh,
}: {
  ccPair: CCPairFullInfo;
  refresh: () => void;
}) {
  const { popup, setPopup } = usePopup();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const isDeleting =
    ccPair?.latest_deletion_attempt?.status === "PENDING" ||
    ccPair?.latest_deletion_attempt?.status === "STARTED";

  let tooltip: string;
  if (ccPair.status !== ConnectorCredentialPairStatus.ACTIVE) {
    if (isDeleting) {
      tooltip = "This connector is currently being deleted";
    } else {
      tooltip = "Click to delete";
    }
  } else {
    tooltip = "You must pause the connector before deleting it";
  }

  const handleDelete = async () => {
    try {
      // Await the delete operation to ensure it completes
      await deleteCCPair(
        ccPair.connector.id,
        ccPair.credential.id,
        setPopup,
        () => mutate(buildCCPairInfoUrl(ccPair.id))
      );

      // Call refresh to update the state after deletion
      refresh();
    } catch (error) {
      console.error("Error deleting connector:", error);
    }
  };

  return (
    <div>
      {popup}
      <Popover open={isDeleteModalOpen} onOpenChange={setIsDeleteModalOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="destructive"
            icon={FiTrash}
            disabled={
              ccPair.status === ConnectorCredentialPairStatus.ACTIVE || isDeleting
            }
            tooltip={tooltip}
          >
            Delete
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto min-w-[200px] max-w-[300px]">
          <div className="p-4">
            <p className="text-sm mb-4">
              Are you sure you want to delete this connector?
            </p>
            <div className="flex justify-start gap-2">
              <Button
                variant="outline"
                className="px-3 py-1 text-sm"
                onClick={() => setIsDeleteModalOpen(false)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                className="px-3 py-1 text-sm"
                onClick={() => {
                  handleDelete();
                  setIsDeleteModalOpen(false);
                }}
              >
                Delete
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
