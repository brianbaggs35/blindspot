# The app shell

The shell is everything around a page: the top bar, the menu, the command palette, the themes and
the shared states. It lives in `frontend/src` and is built with Vue 3, Vuetify 4 and TypeScript 6.

## Look and feel

The direction is **Situation Room**: a dark-first interface with glass bars over a faint radar
grid, cyan to indigo for live things, and amber kept for blind spots and warnings. The light theme
(`daylight`) uses the same tokens with darker accents so text keeps its contrast. Both themes are
defined in `src/plugins/vuetify.ts`; changing the direction means changing those tokens and the
shell block at the end of `src/styles/main.css`.

- **Visual effects** (the grid, the glass bars) can be turned off from the top bar. They start off
  for anyone whose system asks for reduced motion, and a choice made here always wins.
- **Motion** is 150 to 250 ms and always has a reason. `prefers-reduced-motion` removes it.
- **Contrast** is checked with axe on every page, in both themes, at six widths.

## The menu

The menu is built from the router. A page appears in it when its route has `meta.nav`:

```ts
{
  path: "/findings",
  name: "findings",
  component: () => import("../views/FindingsView.vue"),
  meta: { title: "Findings", nav: { label: "Findings", group: "work", order: 30, icon: mdiBug } },
}
```

`group` is `work` or `system`, and `order` sorts within the group. Nothing else lists pages, so a
page added later shows up in the menu, in the command palette and in the tab title without
touching the shell. A route with `meta.title` and no `meta.nav` (the not-found page) is named in
the tab but not listed.

- On a laptop or desktop the menu stays beside the page and shrinks to icons (with tooltips).
  The choice is remembered in this browser.
- On a phone it is a drawer that opens over the page and closes when a link is used.

## The command palette

Press `Ctrl+K` (`⌘K` on a Mac) or use the search button. Type any words from a page or action;
every word has to match. Enter runs the first match, or pick one with the mouse, or Tab to it.
Commands are built in `src/commands.ts`: one for each menu page, plus the appearance actions.

## Shared pieces

| Piece                       | Use it for                                                                                                                                                       |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PageHeader`                | The page's `h1`, a subtitle and an actions slot. Every page has exactly one `h1`.                                                                                |
| `StateView`                 | The four states of a list or detail view: loading (a skeleton, not a spinner), empty (says what to do next), error (says what happened) and ready (the content). |
| `NavMenu`, `CommandPalette` | Used by the shell only.                                                                                                                                          |

## Remembered settings

Three things are kept in the browser's local storage, and only there: `blindspot.theme`,
`blindspot.nav` (collapsed or not) and `blindspot.effects`. Storage can be blocked, so every read
and write goes through `src/storage.ts` and the app works without it.

## Sign-in, setup and the account page

| Page      | Path         | Who                                                                                                    |
| --------- | ------------ | ------------------------------------------------------------------------------------------------------ |
| Setup     | `/setup`     | Anyone, only while no administrator exists (setup code from the log or `BLINDSPOT_SETUP_CODE`)         |
| Sign in   | `/sign-in`   | Anyone; a password or a passkey. `?next=` returns you to the page you asked for (same-site paths only) |
| Account   | `/account`   | Anyone signed in: change password, add or remove passkeys, end sessions                                |
| Forbidden | `/forbidden` | Shown when a viewer opens an admin-only page                                                           |

The router guard (`src/router/guard.ts`) sends signed-out visitors to setup or sign-in and
viewers away from admin pages; the API still enforces every rule. A `401` from any call ends
the session in the app and returns to sign-in. Sign-in failures use one message whether the
password was wrong or the account is locked. Passkeys need a host name (`localhost`), not an IP
address, and a certificate the browser accepts.

## AI providers

| Page         | Path            | What it does                                                                                                       |
| ------------ | --------------- | ------------------------------------------------------------------------------------------------------------------ |
| AI providers | `/ai-providers` | Providers, their models and prices, and the default model for each role. Administrators change it; viewers read it |

See [AI providers and spend](ai-providers.md#the-ai-providers-page) for the steps.

## Pentests

| Page      | Path                      | What it does                                                                                                                          |
| --------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Pentests  | `/pentests`               | Active, Archived and Trash tabs with search and a status filter; administrators make a pentest or import one                          |
| Pentest   | `/pentests/:id`           | Authorization, scope, rules, accounts and the signed letter. Administrators change them and every risky step asks first; viewers read |
| Checklist | `/pentests/:id/checklist` | Every test of the pentest's methodology with progress, filters and notes; administrators record results, viewers read                 |

See [Pentests](pentests.md#the-pentests-pages) for the steps.

## Methodologies

| Page          | Path             | What it does                                                                                                                                            |
| ------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Methodologies | `/methodologies` | The checklist by category and test, and the playbook each test's agent is given. Administrators edit playbooks, switch, reload and update; viewers read |

See [Methodologies](methodologies.md#the-methodologies-page) for the steps.

## Users and the audit log (administrators)

| Page      | Path     | What it does                                                                                                                               |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Users     | `/users` | List, add, edit (name, role, whether the account can sign in), reset a password, sign out everywhere, delete. Each risky step asks first   |
| Audit log | `/audit` | The audit trail, newest first. Filter by action, outcome, username and the day to start from; "Show older events" pages with `next_before` |

Both are `access: "admin"` routes: an administrator sees them in the menu and the command
palette, a viewer sees neither and gets the "No access" page if they open the address. The API
refuses the same requests whatever the page does. You cannot change the role or status of, or
delete, your own account (the API says so, and the page switches the controls off). The audit
log is read-only here. Action codes the page does not know are shown as they are; add a line to
`src/audit.ts` when a new action is added to the API.

## Checks

`npm test` (100% coverage target, 95% minimum) covers every component and store. The Playwright
specs run the menu, the palette, the themes and the not-found page, and the axe and layout specs
run on every page in `e2e/pages.ts`: add a page there when you add a route.
