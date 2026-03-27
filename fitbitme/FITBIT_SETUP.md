# Fitbit API Setup Guide

To pull your live data via the Fitbit API, you need to create a personal app in the Fitbit Developer Portal to obtain your `CLIENT_ID` and `CLIENT_SECRET`.

## Step 1: Register an Application
1. Go to [https://dev.fitbit.com](https://dev.fitbit.com) and log in with your Fitbit/Google account.
2. Go to **Manage** -> **Register An App** (or click "Register an App" on the dashboard).
3. Fill out the application details:
   - **Application Name**: `MeasureMe Sync` (or whatever you prefer)
   - **Description**: `Local NAS health data extraction`
   - **Application Website**: `http://localhost`
   - **Organization**: `Personal`
   - **Organization Website**: `http://localhost`
   - **Terms of Service URL**: `http://localhost`
   - **Privacy Policy URL**: `http://localhost`
   - **OAuth 2.0 Application Type**: `Personal` (CRITICAL: Select "Personal" so you can read your own intraday/detailed data)
   - **Callback URL**: `http://localhost:8080/callback` (We'll use this for the initial token exchange)
   - **Default Access Type**: `Read Only`
4. Accept the terms and click **Register**.

## Step 2: Get Your Credentials
After creating the app, you will see a page with your:
- **OAuth 2.0 Client ID**
- **Client Secret**

Save these credentials. You will need them for `fitbit_client.py`.

## Step 3: Perform Initial Authorization
Since this is a headless NAS application, you need to perform the initial OAuth 2.0 handshake once to get your original `access_token` and `refresh_token`.

1. Open your terminal in the `FitBitMe` directory.
2. Run the built-in CLI tool to authenticate:
   ```bash
   python fitbit_client.py auth
   ```
3. The script will prompt you for your `Client ID` and `Client Secret`.
4. It will generate a specific authorization URL. Click it or copy-paste it into your web browser.
5. Log into your Fitbit account and "Allow" access to all your health data.
6. The browser will redirect you to `http://localhost:8080/callback` and will likely fail to load. **That's fine!** 
7. Look at the URL in your browser's address bar. It will look like this:
   `http://localhost:8080/callback?code=YOUR_AUTHORIZATION_CODE_HERE#_=_`
8. Copy the entire URL and paste it back into the terminal prompt.
9. The script will exchange the code for a token, and save it locally to `tokens.json`.

From then on, the `FitBitMe` background worker will automatically renew the tokens whenever they expire, completely hands-off!

## Step 4: Configure the Webhook for Live Updates
To receive real-time push notifications from Fitbit whenever new data is available, you need to set up a Webhook. Fitbit strictly requires your webhook endpoint to use **HTTPS**.

1. **Expose the Webhook Server**: Ensure your local `app.py` (running on port 50123) is securely exposed to the internet. We highly recommend using a Cloudflare Tunnel (e.g., `https://fitbit.yourdomain.com`).
2. **Edit your App Settings**: Go back to your app in the [Fitbit Developer Portal](https://dev.fitbit.com) -> Manage -> Your App.
3. Scroll down to the **Subscriptions/Webhooks** section and click **Add a New Subscriber**.
4. You will see a 64-character **Verification Code**. Copy this string.
5. Open the `.env` file in your `FitBitMe` directory and add the code:
   ```env
   FITBIT_VERIFY_TOKEN=your_64_character_verification_code_here
   ```
6. **Start the Receiver**: Make sure `app.py` is running on your NAS so it can respond to Fitbit's verification ping:
   ```bash
   python app.py
   ```
7. **Register the URL**: In the Fitbit Developer Portal, paste your secure Tunnel URL including the path (e.g., `https://fitbit.yourdomain.com/webhook`) into the **Subscriber URL** field.
8. Click **Save**. Fitbit will immediately send a verification request to your server. 

If everything is routed correctly, `app.py` will reply with a `204 No Content`, and your webhook will be successfully activated!
