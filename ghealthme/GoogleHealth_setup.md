# Google Health API Setup Guide

This guide describes how to configure a Google Cloud Platform (GCP) project to authenticate with the explicit Google Health API and expose the resulting app to receive real-time updates seamlessly.

## Step 1: Create a Google Cloud Project
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. In the top toolbar, click the **Select a project** dropdown and click **New Project**.
3. Name your project (e.g. `MeasureMe-GHealth`) and click **Create**.

## Step 2: Enable the APIs
You need to enable the specific fitness APIs used by Google Health.
1. Once your project is created, navigate to **APIs & Services > Library**.
2. Search for **Fitness API**.
3. Click on **Fitness API** and click **Enable**.

## Step 3: Configure the OAuth Consent Screen
1. Navigate to **APIs & Services > OAuth consent screen**.
2. Choose **External** (unless you are a Google Workspace user and deploying this internally) and click **Create**.
3. **App Information**: 
   - App Name: `MeasureMe Health Sync`
   - User Support Email: *(Your Email)*
   - Developer Contact Information: *(Your Email)*
4. **Scopes**: Click *Add or Remove Scopes*. You will need at least the following to read physical metrics:
   - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
   - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
   - `https://www.googleapis.com/auth/googlehealth.location.readonly`
   - `https://www.googleapis.com/auth/googlehealth.nutrition.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
   - `https://www.googleapis.com/auth/googlehealth.ecg.readonly`
   *(Note: Because this is an external app asking for restricted scopes, it might remain in "Testing" mode. Ensure you add your own Google email to the **Test Users** list on the next screen.)*
5. Add your Google Account email to the **Test users** section.

## Step 4: Generate OAuth Credentials (Client ID)
1. Navigate to **APIs & Services > Credentials**.
2. Click **+ Create Credentials** -> **OAuth client ID**.
3. Set the **Application Type** to **Web application**.
4. Name the client (e.g., `MeasureMe Web`).
5. **Authorized redirect URIs**: 
   Because MeasureMe uses Cloudflare Tunnels for webhook routing, you need to match your Cloudflare domain:
   - `https://your-tunnel-domain.com/oauth/callback`
   *(For initial local testing only, you may also add `http://localhost:8124/oauth/callback`)*
6. Click **Create**.
7. Download the `client_secret_XXXX.json` file. Save this to your MeasureMe setup folder at `MeasureMe\ghealthme\storage\client_secret.json` (it's recommended to rename the long Google filename to just `client_secret.json` for easier configuration).

## Step 6: Initialize or Refresh Tokens
If your `ghealth_tokens.json` is missing or the refresh token has expired/been revoked, you must re-authenticate.

### Method A: Use the Local OAuth Service (Recommended)
This is the easiest way to get the tokens saved automatically to your `storage` folder.

1.  **Configure Environment**: 
    Ensure `MeasureMe\ghealthme\.env` exists with:
    ```env
    STORAGE_DIR=d:\Dev\HealthyMe_top\MeasureMe\ghealthme\storage
    GHEALTH_CREDENTIALS=client_secret.json
    ```
2.  **Authorized redirect URIs**: In the [Google Cloud Console](https://console.cloud.google.com/apis/credentials), add `http://127.0.0.1:8124/oauth/callback` to your client ID.
3.  **Run & Authorize**:
    ```powershell
    python src\web_services\main.py
    ```
    Open `http://127.0.0.1:8124/oauth/login` in your browser.

### Method B: Use the Google Parity Tool (Manual)
If you prefer using the [Google Health Parity Tool](https://developers.google.com/health/migration/parity-tool), you can manually paste the results into `storage/ghealth_tokens.json`.

1.  **Preparation**:
    *   In the Google Cloud Console, add `https://developers.google.com/oauthplayground` as an **Authorized redirect URI** for your client ID. (Note: The tool requires this specific URI).
2.  **Parity Tool Steps**:
    *   Input your **Client ID** and **Client Secret**.
    *   Set **Redirect URI** to `https://developers.google.com/oauthplayground`.
    *   Click **Get Code** and authorize.
    *   Click **Exchange** to get the JSON response.
3.  **Save Manually**:
    Copy the JSON block (containing `access_token`, `refresh_token`, etc.) and save it exactly as it is into:
    `MeasureMe\ghealthme\storage\ghealth_tokens.json`

## Step 7: Verify Connectivity (API Check)
Once you have valid tokens, you can check which Google Health endpoints are active for your account.

**Note**: If the API has changed recently, you may need to update the local Discovery document:
```powershell
python scripts\update_discovery.py
```

Then run the check:
```powershell
cd MeasureMe\ghealthme
$env:PYTHONPATH="src"
python scripts\api_check.py
```

## Step 8: Webhook Subscriptions (Via Cloudflare Tunnels)
Using Cloudflare Tunnels (`cloudflared`), your local MeasureMe server is exposed. 
Ensure the tunnel points to `http://localhost:8124` locally (the GHealth service port).
- Google Health API allows you to register a push subscription. The blueprint logic in `ghealthme` will automatically attempt to subscribe to new data using your public tunnel domain when initialized.

