# Getting a Web Link for Friends to Test (No Coding Needed)

This walks you through putting the dashboard online with a real
https:// link, using free hosting. Total time: ~15 minutes.

## Step 1 — Put the code on GitHub (free)

1. Go to https://github.com and create a free account if you don't
   have one.
2. Click the **+** icon top-right → **New repository**.
3. Name it `memebot` (or anything), leave it **Public**, click
   **Create repository**.
4. On the new repo page, click **uploading an existing file**.
5. Drag in every file from the `memebot` folder I gave you
   (`app.py`, `bot.py`, `config.py`, `portfolio.py`, `signal_engine.py`,
   `wallet_watcher.py`, `x_scanner.py`, `jupiter_client.py`,
   `requirements.txt`, `Procfile`, `README.md`, and the whole
   `templates` folder with `dashboard.html` inside it).
6. Scroll down, click **Commit changes**.

## Step 2 — Deploy on Render (free tier)

1. Go to https://render.com and sign up (you can sign up with your
   GitHub account — makes step 3 easier).
2. Click **New +** → **Web Service**.
3. Connect your GitHub account if prompted, then select the
   `memebot` repo you just created.
4. Fill in:
   - **Name**: anything, e.g. `signal-terminal`
   - **Region**: closest to you
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --workers 1 --threads 4 --timeout 120`
   - **Instance Type**: Free
5. (Optional) Click **Advanced** → **Add Environment Variable**:
   - `SOLANA_RPC_URL` = `https://api.mainnet-beta.solana.com` (fine
     for testing; a dedicated RPC like Helius is better for real use)
   - You do **not** need `X_BEARER_TOKEN` — the bot defaults to a free
     on-chain activity signal (DexScreener buy/sell data), no API key
     required. Trades should start showing up on the dashboard once
     it's live.
6. Click **Create Web Service**.

Render will build and deploy automatically. After a few minutes
you'll get a URL like:

```
https://signal-terminal.onrender.com
```

That's the link you send your friends. Anyone who opens it sees the
live dashboard — no login, no wallet, no coding on their end.

## Switching to X mention data later (optional)

The bot runs out of the box on a free on-chain activity signal — no
setup needed. If later you want to switch to X mention velocity
instead:

1. Go to https://developer.x.com/en/portal/products, sign up for API
   access (the Basic tier is paid — X removed the free search tier a
   while back), and copy your **Bearer Token**.
2. In Render, add two environment variables: `SIGNAL_SOURCE = x` and
   `X_BEARER_TOKEN = <your token>`.
3. Redeploy.

## A few things worth knowing about the free tier

- Render's free web services "spin down" after 15 minutes of no
  traffic and take ~30 seconds to wake back up on the next visit —
  fine for casual testing, just don't be surprised by a slow first
  load.
- The bot's scan loop runs in the background as long as the app is
  awake — if it spins down, scanning pauses until someone opens the
  link again.
- All portfolio/trade data is saved to a file on Render's disk, which
  free-tier services can reset on redeploys — treat this as a testing
  environment, not permanent storage. If your friends' feedback goes
  well and you want it to persist properly, that's a good next step
  to build.

## If you'd rather I do the GitHub/Render clicking for you

I can't click through external websites on your behalf — but if you
create the GitHub repo and paste me the URL, I can double check
everything's uploaded correctly, and I'm happy to troubleshoot any
error message Render shows you during deploy.
