# Optional accounts and Private mode

CarePath does not require an account. The public reviewer experience remains directly usable with built-in synthetic personas, and users can choose whether persistence is useful for their own data.

## Runtime modes

| Mode | Sign-in required | Storage | Intended use |
| --- | --- | --- | --- |
| Anonymous standard demo | No | Persistent deployment database | Fast reviewer access and optional user-supplied demo data |
| Signed-in account | Yes | Persistent deployment database, scoped to the authenticated account | Resume saved data, plans and feedback across visits |
| Private mode | No; may also be used while signed in | Isolated in-memory SQLite workspace | Use CarePath without writing health data or interaction history to persistent storage |

Private mode and account sign-in are independent. If a signed-in user enables Private mode, activity in that workspace is not copied into the account's persistent history.

## Account boundary

Supabase Auth is an optional identity provider. CarePath accepts Supabase bearer access tokens and verifies them against the configured Supabase Auth user endpoint. A verified Supabase subject is mapped deterministically to a CarePath UUIDv5; email addresses are not used as database identifiers.

When a signed-in user imports real data, the imported user-scoped records are rebound to that account UUID and the profile is marked `account_managed`. Account-managed profiles require authentication and cannot be read by another signed-in account. Synthetic demo profiles remain public so reviewers can still use the built-in personas without an account.

The Web client supports email/password registration and sign-in plus Google OAuth. Expo Go keeps email/password sign-in available; native Google OAuth is intentionally deferred until platform-specific OAuth client IDs and redirect schemes are configured.

## Private mode storage boundary

`POST /privacy/session` creates an isolated in-process SQLite database with the same SQLAlchemy schema used by normal CarePath storage. Requests carry the random session identifier in `X-CarePath-Private-Session`. Profile, observation, trend, Patient Evidence, Coach, plan, feedback and audit operations use that private database while the header is present.

Private mode has these guarantees and limits:

- no Private-mode health records, journals, plans, feedback or coaching interactions are written to `CAREPATH_DATABASE_URL`;
- explicitly exiting Private mode disposes the in-memory database immediately;
- inactive workspaces expire after `CAREPATH_PRIVATE_SESSION_TTL_MINUTES` (60 minutes by default);
- application restart destroys all Private workspaces because they exist only in process memory;
- capacity is bounded by `CAREPATH_PRIVATE_SESSION_MAX_SESSIONS` (128 by default), with oldest-session eviction when full;
- Private mode is designed for the current single-service reviewer deployment. A future multi-instance deployment must add sticky routing or a non-persistent shared session layer before using this design unchanged.

The client keeps the private session identifier only in runtime state, not browser local storage. Closing a tab without explicitly exiting does not instantly erase server memory; the idle TTL is the fallback cleanup mechanism. Therefore UI copy says "temporary server memory" rather than claiming immediate deletion on tab close.

## Configuration

Leaving Supabase values unset keeps CarePath anonymous-only while Private mode remains available.

```dotenv
CAREPATH_SUPABASE_URL=
CAREPATH_SUPABASE_PUBLISHABLE_KEY=
CAREPATH_AUTH_REQUEST_TIMEOUT_SECONDS=5
CAREPATH_PRIVATE_SESSION_TTL_MINUTES=60
CAREPATH_PRIVATE_SESSION_MAX_SESSIONS=128
```

Only the Supabase project URL and **publishable** key belong here. Never configure a Supabase `service_role` key or another server-secret key for the client-facing authentication path.

The backend exposes only client-safe runtime values through `GET /config/public`. When both Supabase values are present, the Web account controls become active; otherwise the UI explicitly states that sign-in is not configured and continues anonymously.

## Google OAuth activation

External console ownership cannot be committed to this repository. To activate Google sign-in for the public Web demo:

1. Create or select a Supabase project and keep email/password authentication enabled if desired.
2. In Google Cloud, create a Web OAuth client for the CarePath deployment.
3. Use the Supabase Google callback URL shown by Supabase as the Google authorized redirect URI (normally `https://<project-ref>.supabase.co/auth/v1/callback`).
4. Put the Google Client ID and Client Secret into the Supabase Google provider configuration. These Google credentials stay in Supabase/Google consoles and are never committed to CarePath.
5. In Supabase Auth URL configuration, set the public CarePath origin as the Site URL and allow the exact public CarePath redirect URL.
6. Configure `CAREPATH_SUPABASE_URL` and `CAREPATH_SUPABASE_PUBLISHABLE_KEY` on Render and redeploy.
7. Verify email/password registration, Google sign-in, sign-out, saved-data restoration, cross-account isolation and anonymous use against the public deployment.

For the current Render reviewer deployment, the CarePath origin is `https://carepath-api-8edq.onrender.com`.

## Verification

The repository quality gate covers backend formatting, linting, type checking and tests plus frontend formatting, ESLint, TypeScript, Expo bundles and Jest coverage. The v0.8 real-backend Playwright journey additionally exercises entering Private mode, loading data through the isolated workspace and exiting back to standard mode. Account-provider acceptance that requires a real Google/Supabase tenant is performed after the external project credentials are configured; no provider secrets are embedded in CI or source control.
