import { api } from "./api/client";
import type { Ceremony, PasskeyInfo, User } from "./api/types";

// Passkeys through the browser's own WebAuthn JSON helpers (no library needed).

export function passkeysSupported(): boolean {
  return (
    typeof PublicKeyCredential !== "undefined" &&
    typeof PublicKeyCredential.parseCreationOptionsFromJSON === "function" &&
    typeof PublicKeyCredential.parseRequestOptionsFromJSON === "function"
  );
}

/** The person closed the browser's passkey prompt or it timed out. */
export class PasskeyCancelled extends Error {
  constructor() {
    super("The passkey prompt was closed before it finished.");
    this.name = "PasskeyCancelled";
  }
}

async function ask<T>(prompt: () => Promise<T | null>): Promise<T> {
  try {
    const answer = await prompt();
    if (answer === null) throw new PasskeyCancelled();
    return answer;
  } catch (error) {
    if (error instanceof DOMException && ["NotAllowedError", "AbortError"].includes(error.name)) {
      throw new PasskeyCancelled();
    }
    throw error;
  }
}

export async function signInWithPasskey(): Promise<User> {
  const { challenge_id, options } = await api<Ceremony>("POST", "/api/auth/passkeys/login/options");
  const credential = await ask(() =>
    navigator.credentials.get({
      publicKey: PublicKeyCredential.parseRequestOptionsFromJSON(
        options as unknown as PublicKeyCredentialRequestOptionsJSON,
      ),
    }),
  );
  return api<User>("POST", "/api/auth/passkeys/login", {
    challenge_id,
    credential: (credential as PublicKeyCredential).toJSON(),
  });
}

export async function addPasskey(name: string, password: string): Promise<PasskeyInfo> {
  const { challenge_id, options } = await api<Ceremony>(
    "POST",
    "/api/auth/passkeys/register/options",
    { password },
  );
  const credential = await ask(() =>
    navigator.credentials.create({
      publicKey: PublicKeyCredential.parseCreationOptionsFromJSON(
        options as unknown as PublicKeyCredentialCreationOptionsJSON,
      ),
    }),
  );
  return api<PasskeyInfo>("POST", "/api/auth/passkeys/register", {
    challenge_id,
    name,
    credential: (credential as PublicKeyCredential).toJSON(),
  });
}
