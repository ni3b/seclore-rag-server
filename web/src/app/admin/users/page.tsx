"use client";
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import SignedUpUserTable from "@/components/admin/users/SignedUpUserTable";
import PlatformEmailTable from "@/components/admin/users/PlatformEmailTable";
import AddPlatformEmail from "@/components/admin/users/AddPlatformEmail";

import { FiPlusSquare } from "react-icons/fi";
import { Modal } from "@/components/Modal";
import { ThreeDotsLoader } from "@/components/Loading";
import { AdminPageTitle } from "@/components/admin/Title";
import { usePopup, PopupSpec } from "@/components/admin/connectors/Popup";
import { UsersIcon } from "@/components/icons/icons";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR, { mutate } from "swr";
import { ErrorCallout } from "@/components/ErrorCallout";
import BulkAdd from "@/components/admin/users/BulkAdd";
import Text from "@/components/ui/text";
import { InvitedUserSnapshot } from "@/lib/types";
import { SearchBar } from "@/components/search/SearchBar";

const UsersTables = ({
  q,
  setPopup,
  setShowAddPlatformEmail,
}: {
  q: string;
  setPopup: (spec: PopupSpec) => void;
  setShowAddPlatformEmail: (show: boolean) => void;
}) => {
  const [activeTab, setActiveTab] = useState("current");
  
  const {
    data: invitedUsers,
    error: invitedUsersError,
    isLoading: invitedUsersLoading,
    mutate: invitedUsersMutate,
  } = useSWR<InvitedUserSnapshot[]>(
    "/api/manage/users/invited",
    errorHandlingFetcher
  );

  const {
    data: platformEmails,
    error: platformEmailsError,
    isLoading: platformEmailsLoading,
    mutate: platformEmailsMutate,
  } = useSWR<{ id: number; email: string }[]>(
    activeTab === "platform-emails" ? "/api/manage/platform-emails" : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 60000, // 1 minute
    }
  );

  const { data: validDomains, error: domainsError } = useSWR<string[]>(
    "/api/manage/admin/valid-domains",
    errorHandlingFetcher
  );

  // Show loading animation only during the initial data fetch
  if (!validDomains) {
    return <ThreeDotsLoader />;
  }

  if (domainsError) {
    return (
      <ErrorCallout
        errorTitle="Error loading valid domains"
        errorMsg={domainsError?.info?.detail}
      />
    );
  }

  return (
    <Tabs defaultValue="current" value={activeTab} onValueChange={setActiveTab}>
      <TabsList>
        <TabsTrigger value="current">Current Users</TabsTrigger>
        <TabsTrigger value="platform-emails">Platform Email</TabsTrigger>
        {/* <TabsTrigger value="invited">Invited Users</TabsTrigger> */}
      </TabsList>

      <TabsContent value="current">
        <Card>
          <CardHeader>
            <CardTitle>Current Users</CardTitle>
          </CardHeader>
          <CardContent>
            <SignedUpUserTable
              invitedUsers={invitedUsers || []}
              setPopup={setPopup}
              q={q}
              invitedUsersMutate={invitedUsersMutate}
            />
          </CardContent>
        </Card>
      </TabsContent>

      <TabsContent value="platform-emails">
        <Card>
          <CardHeader>
            <CardTitle>Access Request Email</CardTitle>
          </CardHeader>
          <CardContent>
            <PlatformEmailTable
              emails={platformEmails || []}
              setPopup={setPopup}
              mutate={platformEmailsMutate}
              error={platformEmailsError}
              isLoading={platformEmailsLoading}
              q={q}
              onAddEmail={() => setShowAddPlatformEmail(true)}
            />
          </CardContent>
        </Card>
      </TabsContent>

      {/* <TabsContent value="invited">
        <Card>
          <CardHeader>
            <CardTitle>Invited Users</CardTitle>
          </CardHeader>
          <CardContent>
            <InvitedUserTable
              users={invitedUsers || []}
              setPopup={setPopup}
              mutate={invitedUsersMutate}
              error={invitedUsersError}
              isLoading={invitedUsersLoading}
              q={q}
            />
          </CardContent>
        </Card>
      </TabsContent> */}
    </Tabs>
  );
};

const SearchableTables = () => {
  const { popup, setPopup } = usePopup();
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  const [showAddPlatformEmail, setShowAddPlatformEmail] = useState(false);

  return (
    <div>
      {popup}
      <div className="flex flex-col gap-y-4">
        <div className="flex gap-x-4">
          <AddUserButton setPopup={setPopup} />
          <div className="flex-grow">
            <SearchBar
              query={query}
              setQuery={setQuery}
              onSearch={() => setQ(query)}
            />
          </div>
        </div>
        <UsersTables q={q} setPopup={setPopup} setShowAddPlatformEmail={setShowAddPlatformEmail} />
      </div>
      
      {showAddPlatformEmail && (
        <Modal title="Add Platform Email" onOutsideClick={() => setShowAddPlatformEmail(false)}>
          <div className="flex flex-col gap-y-4">
            <Text className="font-medium text-base">
              Add a new platform email address. This email will be used for requesting access to the Assistant.
            </Text>
            <AddPlatformEmail 
              onSuccess={() => {
                setShowAddPlatformEmail(false);
                setPopup({
                  message: "Platform email added successfully!",
                  type: "success",
                });
                // Refresh the platform emails data
                mutate(
                  (key) => typeof key === "string" && key.startsWith("/api/manage/platform-emails")
                );
              }}
              onFailure={(error) => {
                setPopup({
                  message: `Failed to add platform email - ${error}`,
                  type: "error",
                });
              }}
            />
          </div>
        </Modal>
      )}
    </div>
  );
};

const AddPlatformEmailButton = ({
  setPopup,
  setShowModal,
}: {
  setPopup: (spec: PopupSpec) => void;
  setShowModal: (show: boolean) => void;
}) => {
  return (
    <Button 
      className="my-auto w-fit" 
      onClick={() => setShowModal(true)}
    >
      <div className="flex">
        <FiPlusSquare className="my-auto mr-2" />
        Add Platform Email
      </div>
    </Button>
  );
};

const AddUserButton = ({
  setPopup,
}: {
  setPopup: (spec: PopupSpec) => void;
}) => {
  const [modal, setModal] = useState(false);
  const onSuccess = () => {
    mutate(
      (key) => typeof key === "string" && key.startsWith("/api/manage/users")
    );
    setModal(false);
    setPopup({
      message: "Users invited!",
      type: "success",
    });
  };
  const onFailure = async (res: Response) => {
    const error = (await res.json()).detail;
    setPopup({
      message: `Failed to invite users - ${error}`,
      type: "error",
    });
  };
  return (
    <>
      {/* <Button 
        className="my-auto w-fit" 
        onClick={() => {
          // Button is disabled, no action
        }}
      >
        <div className="flex">
          <FiPlusSquare className="my-auto mr-2" />
          Invite Users
        </div>
      </Button> */}

      {modal && (
        <Modal title="Bulk Add Users" onOutsideClick={() => setModal(false)}>
          <div className="flex flex-col gap-y-4">
            <Text className="font-medium text-base">
              Add the email addresses to import, separated by whitespaces.
              Invited users will be able to login to this domain with their
              email address.
            </Text>
            <BulkAdd onSuccess={onSuccess} onFailure={onFailure} />
          </div>
        </Modal>
      )}
    </>
  );
};

const Page = () => {
  return (
    <div className="mx-auto container">
      <AdminPageTitle title="Manage Users" icon={<UsersIcon size={32} />} />
      <SearchableTables />
    </div>
  );
};

export default Page;
