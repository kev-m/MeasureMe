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
   *(Note: Because this is an external app asking for restricted scopes, it might remain in "Testing" mode. Ensure you add your own Google email to the **Test Users** list on the next screen.)*
5. Add your Google Account email to the **Test users** section.

## Step 4: Generate OAuth Credentials (Client ID)
1. Navigate to **APIs & Services > Credentials**.
2. Click **+ Create Credentials** -> **OAuth client ID**.
3. Set the **Application Type** to **Web application**.
4. Name the client (e.g., `MeasureMe Web`).
5. **Authorized redirect URIs**: 
   Because MeasureMe uses Cloudflare Tunnels for webhook routing, you need to match your Cloudflare domain:
   - `https://your-tunnel-domain.com/callback`
   *(For initial local testing only, you may also add `http://localhost:5000/callback`)*
6. Click **Create**.
7. Download the `client_secret_XXXX.json` file. Save this to your MeasureMe setup under `MeasureMe\ghealthme\storage\client_secret.json`.

## Step 5: Webhook Subscriptions (Via Cloudflare Tunnels)
Using Cloudflare Tunnels (`cloudflared`), your local MeasureMe server is exposed. 
Ensure the tunnel points to `http://localhost:5000` locally.
- Google Health API allows you to register a push subscription. The blueprint logic in `ghealthme` will automatically attempt to subscribe to new data using your public tunnel domain when initialized.
