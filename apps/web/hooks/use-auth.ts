"use client";
import { useState, useEffect } from "react";

export function useIsSignedIn() {
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  useEffect(() => {
    setIsSignedIn(!!localStorage.getItem("oh_token"));
    setIsLoaded(true);
  }, []);
  return { isSignedIn, isLoaded };
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("oh_token");
}

export function handleSignOut(redirectUrl: string = "/sign-in") {
  localStorage.removeItem("oh_token");
  window.location.href = redirectUrl;
}
