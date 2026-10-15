# Granola Settings: what the screens show (observed 2026-10-15, Granola 7.663, dark and light)

Only what was seen on screen. Nothing here is inferred from Granola's code.

## Shell
- Settings is a page inside the app with a Back button top-left and the title "Settings" centred.
- Left rail: avatar, name, email. Block 1 (personal): Preferences, Profile, Referrals, Calendar, Notifications, Connectors, Get help.
  Block 2, headed "Workspace": General, Members, Spaces, Analytics, Billing. "Sign out" pinned at the bottom in red.
- Every rail item has a small outline icon. The active item has a filled rounded background.
- Content is one centred column (~570px), page title in a serif face ("Preferences"), sections below it.

## Section pattern
- Small grey section label above a rounded card ("General", "Features", "Appearance", "Data & sharing", "Language", "Transparency", "More").
- A card holds rows separated by dashed hairlines. No per-row borders or shadows.
- Row = [rounded-square icon tile] + title + one-line grey description + control on the right.
- Controls seen: switch (toggle), select with chevron and its current value ("System", "Multi-language", "Anyone with the link"), value + chevron that opens a sub-page ("Speaker tags  Enabled ›", "Automated chat message  Off ›"), button ("Import", "Generate CSV", "Edit"), text field, tags input (Personal jargon), status text ("✓ Enabled").
- Rows with a chevron are navigation, never inline controls.
- Section header can carry a quiet action on the right ("Reset to default", "Reset") in the accent colour.
- A row can expand inline under itself (Notifications > "Auto-detected meetings" opens "Don't notify me when a call is detected in these apps" with a select).

## Where icons appear
- Preferences, Calendar (some rows), Connectors (brand logos), General: icon tiles on rows.
- Notifications and Profile: plain rows with no icon tiles; fields are label left, input right.
- So icons are used where rows are different features; plain rows where it is a form or a list of the same kind of thing.

## Pages
- Preferences (top to bottom): General (Live meeting indicator, Open at login, Reposition for meetings, Pause music when joining, Find in Mission Control: all switches), Features (Speaker tags ›, Take snapshots: switch), Appearance (Theme select; App icon picker), Data & sharing (Default link sharing select, Use my data switch, Auto deletion select), Language (Transcription language, Summary language, Personal jargon tags), Transparency (Automated chat message ›, Watermark ›), More (Labs ›).
- Notifications: Meeting notifications (2 switches + inline app select), Sharing notifications (selects Email/Off, "Reset to default"), Marketing emails (switch), Admin notifications (select).
- Calendar: Display (2 switches), Permissions (Create events: "✓ Enabled"), Visible calendars (one switch per calendar with a colour dot, "Reset").
- Connectors: a list card, one row per tool with its brand logo, a one-line description, "Connected ›" or just ›. Then an "API" section (Personal API keys ›).
- Connector page (HubSpot): logo + title + one-line subtitle; a banner when the plan lacks it; ONE setting row (entity type select: Note); a short "How it works" paragraph; "Last delivery".
- Profile: Account (email, name, job title, LinkedIn), Your company (name, description), Account management (Import, Export CSV), Danger zone.
- Workspace General: Workspace setup (name, logo, plan + Edit), invites & members (switches, Invite links ›, SSO and Directory sync greyed "Upgrade to Enterprise"), Data security (switches, Data export permissions ›).

## Toggle
- Off state in light mode: grey track with the thumb, clearly visible; on: olive/dark green track, white thumb. In dark mode off is a dark grey track with a lighter thumb.
