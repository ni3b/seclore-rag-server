import { useState } from "react";
import { PopupSpec } from "@/components/admin/connectors/Popup";
import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { TableHeader } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { FiTrash2, FiPlusSquare } from "react-icons/fi";
import { ErrorCallout } from "@/components/ErrorCallout";
import { FetchError } from "@/lib/fetcher";

interface PlatformEmail {
  id: number;
  email: string;
}

interface Props {
  emails: PlatformEmail[];
  setPopup: (spec: PopupSpec) => void;
  mutate: () => void;
  error: FetchError | null;
  isLoading: boolean;
  q: string;
  onAddEmail?: () => void;
}

const PlatformEmailTable = ({
  emails,
  setPopup,
  mutate,
  error,
  isLoading,
  q,
  onAddEmail,
}: Props) => {
  const renderAddButton = () => {
    if (!onAddEmail) return null;
    return (
      <div className="flex">
        <Button
          onClick={onAddEmail}
          className="flex items-center gap-2"
        >
          <FiPlusSquare className="h-4 w-4" />
          Add Platform Email
        </Button>
      </div>
    );
  };

  const handleDelete = async (emailId: number) => {
    try {
      const response = await fetch(`/api/manage/platform-emails/${emailId}`, {
        method: "DELETE",
      });
      
      if (response.ok) {
        setPopup({
          message: "Platform email deleted successfully!",
          type: "success",
        });
        mutate();
      } else {
        const error = await response.json();
        setPopup({
          message: `Failed to delete platform email - ${error.detail}`,
          type: "error",
        });
      }
    } catch (error) {
      setPopup({
        message: "Failed to delete platform email",
        type: "error",
      });
    }
  };

  // Filter emails based on the search query
  const filteredEmails = q
    ? emails.filter((email) => email.email.includes(q))
    : emails;

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return (
      <ErrorCallout
        errorTitle="Error loading platform emails"
        errorMsg={error?.info?.detail}
      />
    );
  }

  if (!emails.length) {
    return (
      <div className="space-y-4">
        <p>Email for requesting access to the Assistant is not set. Please add an email to get started.</p>
        {renderAddButton()}
      </div>
    );
  }

  return (
    <>
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>
              <div className="flex justify-end">Actions</div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filteredEmails.length ? (
            filteredEmails.map((email) => (
              <TableRow key={email.id}>
                <TableCell>{email.email}</TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDelete(email.id)}
                    >
                      <FiTrash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={2} className="h-24 text-center">
                {`No platform emails found matching "${q}"`}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      
      {renderAddButton() && (
        <div className="mt-4">
          {renderAddButton()}
        </div>
      )}
    </>
  );
};

export default PlatformEmailTable; 