"use client";

import { AuthType } from "@/lib/constants";
import { FaGoogle } from "react-icons/fa";
import { SiMicrosoft } from "react-icons/si";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import Image from "next/image";

export function SignInButton({
  authorizeUrl,
  authType,
}: {
  authorizeUrl: string;
  authType: AuthType;
}) {
  const [isLoading, setIsLoading] = useState(false);

  const handleClick = async () => {
    setIsLoading(true);
    // Navigate to the authorization URL
    window.location.href = authorizeUrl;
  };

  let buttonContent;
  let buttonText;
  
  if (authType === "google_oauth" || authType === "cloud") {
    buttonContent = (
      <div className="mx-auto flex items-center">
        <div className="my-auto mr-2">
          <FaGoogle />
        </div>
        <p className="text-sm font-medium select-none">Continue with Google</p>
      </div>
    );
    buttonText = "Continue with Google";
  } else if (authType === "oidc") {
    buttonContent = (
      <div className="mx-auto flex items-center">
        <div className="my-auto mr-2">
          <Image 
            src="/microsoft.png" 
            alt="Microsoft logo" 
            width={32} 
            height={32}
            className="object-contain w-8 h-8"
          />
        </div>
        <p className="text-base font-bold select-none">
          Continue with Microsoft
        </p>
      </div>
    );
    buttonText = "Continue with Microsoft";
  } else if (authType === "saml") {
    buttonContent = (
      <div className="mx-auto flex items-center">
        <p className="text-sm font-medium select-none">
          Continue with SAML SSO
        </p>
      </div>
    );
    buttonText = "Continue with SAML SSO";
  }

  if (!buttonContent) {
    throw new Error(`Unhandled authType: ${authType}`);
  }

  return (
    <Button
      onClick={handleClick}
      disabled={isLoading}
      className={`w-full mt-6 mb-4 py-4 h-12 disabled:opacity-50 disabled:cursor-not-allowed ${
        authType === "oidc" 
          ? "bg-black hover:bg-gray-800 text-white" 
          : "text-text-100 bg-accent hover:bg-indigo-800"
      }`}
      size="lg"
    >
      {isLoading ? (
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white mr-2"></div>
          <span className="text-sm font-medium">Signing in...</span>
        </div>
      ) : (
        buttonContent
      )}
    </Button>
  );
}
