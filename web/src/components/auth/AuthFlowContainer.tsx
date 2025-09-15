"use client";

import Link from "next/link";
import { Logo } from "../logo/Logo";
import { useContext, useEffect, useState } from "react";
import { SettingsContext } from "@/components/settings/SettingsProvider";

// Loading spinner component
function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center mt-4">
      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-gray-900"></div>
    </div>
  );
}

// Client-side version display component
function VersionDisplay() {
  const [version, setVersion] = useState<string | null>(null);
  const combinedSettings = useContext(SettingsContext);

  useEffect(() => {
    if (combinedSettings?.webVersion) {
      setVersion(combinedSettings.webVersion);
    }
  }, [combinedSettings?.webVersion]);

  if (!version) return null;

  return (
    <div className="text-xs mt-2 text-center w-full text-neutral-500">
      Seclore AI Version : {version}
    </div>
  );
}

export default function AuthFlowContainer({
  children,
  authState,
}: {
  children: React.ReactNode;
  authState?: "signup" | "login";
}) {
  const [isPageLoaded, setIsPageLoaded] = useState(false);
  const combinedSettings = useContext(SettingsContext);

  useEffect(() => {
    // Mark page as loaded when settings are available
    if (combinedSettings?.webVersion) {
      setIsPageLoaded(true);
    }
  }, [combinedSettings?.webVersion]);

  return (
    <div className="p-4 flex flex-col items-center justify-center min-h-screen bg-background">
      <div className={`w-full max-w-lg min-w-[450px] bg-black pt-10 pb-8 px-10 mx-4 gap-y-4 bg-white flex items-center flex-col rounded-xl shadow-lg border border-background-100 min-h-[300px] ${!isPageLoaded ? 'opacity-50 pointer-events-none' : ''}`}>
        <Logo width={70} height={70} />
        {children}
        {!isPageLoaded && <LoadingSpinner />}
      </div>
      {authState === "login" && (
        <div className="text-sm mt-4 text-center w-full text-neutral-900 font-medium mx-auto">
          Don&apos;t have an account?{" "}
          <Link
            href="/auth/signup"
            className=" underline transition-colors duration-200"
          >
            Create one
          </Link>
        </div>
      )}
      {authState === "signup" && (
        <div className="text-sm mt-4 text-center w-full text-neutral-800 font-medium mx-auto">
          Already have an account?{" "}
          <Link
            href="/auth/login"
            className=" underline transition-colors duration-200"
          >
            Log In
          </Link>
        </div>
      )}
      <VersionDisplay />
    </div>
  );
}
