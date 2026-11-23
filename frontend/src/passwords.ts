// The password rules the API enforces (backend/app/auth/passwords.py), shown as they are met so
// nobody has to submit to find out. The API is the authority; it also refuses very common
// passwords, which only it knows.
export const MIN_LENGTH = 12;
export const MAX_LENGTH = 256;

export interface Rule {
  id: string;
  text: string;
  met: boolean;
}

export function passwordRules(password: string, username: string): Rule[] {
  const name = username.trim().toLowerCase();
  return [
    {
      id: "length",
      text: `At least ${String(MIN_LENGTH)} characters`,
      met: password.length >= MIN_LENGTH,
    },
    {
      id: "short",
      text: `At most ${String(MAX_LENGTH)} characters`,
      met: password.length <= MAX_LENGTH,
    },
    { id: "variety", text: "At least 4 different characters", met: new Set(password).size >= 4 },
    {
      id: "username",
      text: "Does not contain the username",
      met: name.length < 3 || !password.toLowerCase().includes(name),
    },
  ];
}

export function allMet(rules: readonly Rule[]): boolean {
  return rules.every((rule) => rule.met);
}
