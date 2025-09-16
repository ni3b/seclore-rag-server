import { getDomain } from "@/lib/redirectSS";
import { buildUrl } from "@/lib/utilsSS";
import { NextRequest, NextResponse } from "next/server";

export const GET = async (request: NextRequest) => {
  // Wrapper around the FastAPI endpoint /auth/oidc/callback,
  // which adds back a redirect to the main app.
  const url = new URL(buildUrl("/auth/oidc/callback"));
  url.search = request.nextUrl.search;
  
  // Set 'redirect' to 'manual' to prevent automatic redirection
  const response = await fetch(url.toString(), { redirect: "manual" });
  const setCookieHeader = response.headers.get("set-cookie");

  // Handle CSRF state mismatch error specifically
  if (response.status === 400) {
    try {
      const errorData = await response.json();
      if (errorData.detail && errorData.detail.includes("mismatching_state")) {
        // Redirect to login page with a specific error message
        const loginUrl = new URL("/auth/login", getDomain(request));
        loginUrl.searchParams.set("error", "csrf_state_mismatch");
        return NextResponse.redirect(loginUrl);
      }
    } catch (e) {
      // If we can't parse the error, continue with normal flow
    }
  }

  if (response.status === 401) {
    return NextResponse.redirect(
      new URL("/auth/create-account", getDomain(request))
    );
  }

  if (!setCookieHeader) {
    return NextResponse.redirect(new URL("/auth/error", getDomain(request)));
  }

  // Get the redirect URL from the backend's 'Location' header, or default to '/'
  const redirectUrl = response.headers.get("location") || "/";

  const redirectResponse = NextResponse.redirect(
    new URL(redirectUrl, getDomain(request))
  );

  redirectResponse.headers.set("set-cookie", setCookieHeader);
  return redirectResponse;
};
