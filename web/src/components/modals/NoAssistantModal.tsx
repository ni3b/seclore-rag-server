import { Modal } from "@/components/Modal";
import { useEffect, useState } from "react";
import { errorHandlingFetcher } from "@/lib/fetcher";

interface PlatformEmail {
  id: number;
  email: string;
}

export const NoAssistantModal = ({ isAdmin }: { isAdmin: boolean }) => {
  const [platformEmails, setPlatformEmails] = useState<PlatformEmail[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPlatformEmails = async () => {
      try {
        const response = await fetch("/api/platform-emails");
        if (response.ok) {
          const emails = await response.json();
          setPlatformEmails(emails);
        } else {
          setError("Failed to load platform emails");
        }
      } catch (err) {
        setError("Failed to load platform emails");
      } finally {
        setIsLoading(false);
      }
    };

    fetchPlatformEmails();
  }, []);

  const renderContactInfo = () => {
    if (isLoading) {
      return (
        <p className="text-gray-600 mb-2 text-center">
          Loading contact information...
        </p>
      );
    }

    if (error || platformEmails.length === 0) {
      return (
        <p className="text-gray-600 mb-2 text-center">
          To request access, please contact Seclore AI administrator at{" "}
          <a 
            href="mailto:admin.ai@seclore.com" 
            className="font-bold underline text-blue-600 hover:text-blue-800"
          >
            admin.ai@seclore.com
          </a>
        </p>
      );
    }

    return (
      <div className="text-gray-600 mb-2 text-center">
        <p className="mb-2">
          To request access, please contact Seclore AI administrator at:
        </p>
        <div className="space-y-1">
          {platformEmails.map((email) => (
            <a 
              key={email.id}
              href={`mailto:${email.email}`}
              className="block font-bold underline text-blue-600 hover:text-blue-800"
            >
              {email.email}
            </a>
          ))}
        </div>
      </div>
    );
  };

  return (
    <Modal width="bg-white max-w-4xl rounded-lg shadow-xl">
      <>
        <h2 className="text-3xl font-bold text-gray-800 mb-4 text-center">
          Request Access
        </h2>
        <p className="text-gray-600 mb-4 text-center">
          You do not have access to any assistants.
        </p>
        {renderContactInfo()}
        {isAdmin ? (
          <>
            <p className="text-gray-600 mb-6">
              As an administrator, you can create a new assistant by visiting
              the admin panel.
            </p>
            <button
              onClick={() => {
                window.location.href = "/admin/assistants";
              }}
              className="inline-flex flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-background-800 text-center focus:outline-none focus:ring-2 focus:ring-offset-2 "
            >
              Go to Admin Panel
            </button>
          </>
        ) : (
          <p className="text-gray-600 mb-2">
            
          </p>
        )}
      </>
    </Modal>
  );
};
