"use client";
// /studio/signin — staff passphrase sign-in for the Curriculum Studio. Replaces the paste-a-token
// step: an operator provisions the account (one Studio role), the staff member signs in here.
import { useRouter } from "next/navigation";

import { StaffSignInForm } from "./StaffSignInForm";

export default function StudioSignInPage() {
  const router = useRouter();
  return <StaffSignInForm onSignedIn={() => router.replace("/studio")} />;
}
