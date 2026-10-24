# Gmail agent: one-off setup (about 10 minutes)

You do this once. You never give anyone your Gmail password: Google signs you in and
hands back a "refresh token" that only allows **reading** (for now).

## 1. Google Cloud project
1. Go to https://console.cloud.google.com and sign in with the Gmail account to manage.
2. Top bar project picker > **New project** > name it `gmail-agent` > Create, then select it.
3. Search **Gmail API** > open it > **Enable**.

## 2. Consent screen ("Google Auth Platform")
1. Search **Google Auth Platform** (older name: OAuth consent screen) > **Get started**.
2. App name `Gmail agent`, support email = your Gmail. Audience: **External**. Contact email: your Gmail. Finish > Create.
3. **Audience** > Test users > **Add users** > your own Gmail address > Save.
4. **Data Access** > Add or remove scopes > tick `.../auth/gmail.readonly` > Update > Save.

## 3. Login file
1. **Clients** > **Create client** > Application type **Desktop app** > name `gmail-agent-pc` > Create.
2. **Download JSON**. Rename it `client_secret.json` and put it in a new folder, e.g. `C:\Users\User\gmail-setup`.
   Never put it in the repo or share it.

## 4. Get the refresh token (on your PC)
1. From GitHub, download `gmail_agent/authorize.py` (open the file > Download raw file) into the same folder.
2. Open a terminal in that folder (Explorer address bar > type `cmd` > Enter) and run:
   ```
   pip install google-auth-oauthlib
   python authorize.py client_secret.json
   ```
3. A browser opens. Pick your account. You'll see **"Google hasn't verified this app"**: that's normal for
   your own app. Click **Continue**, allow **read** access.
4. The terminal prints three values.

## 5. GitHub secrets
Repo > **Settings > Secrets and variables > Actions > New repository secret**, add:
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET` (the `client_secret` value inside client_secret.json)
- `GMAIL_REFRESH_TOKEN`

Secrets are encrypted and never shown in logs, even though the repo is public.

## 6. Test it
Repo > **Actions > gmail > Run workflow**. The log shows counts only (nothing private).

## Good to know
- **Testing mode logins expire after 7 days.** Fine for now. Before the agent runs on a schedule we'll
  switch the app to "In production" (Audience > Publish app) so the token lasts.
- **Switch the agent off:** Settings > Secrets and variables > Actions > **Variables** > `GMAIL_AGENT_ENABLED` = `0`.
- **Revoke access any time:** https://myaccount.google.com/permissions > Gmail agent > Remove access.
