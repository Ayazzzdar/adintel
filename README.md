# Ad Intel — The Day Archive

A Meta Ad Library dashboard (like Atria / Superscale / Parker) built for The Day Archive. It:

1. **Tracks brands.** It pulls every live ad from competitors and brands you like each day (Apify).
2. **Finds winners.** The Ad Library hides spend, so it infers what's working from how long an ad
   has run, how many variants of it are live, and how often the same copy is reused.
3. **Discovers new competitors.** It searches the whole Ad Library for niche phrases and ranks
   every advertiser by relevance. Claude can then sort them into competitor, adjacent or
   irrelevant, and suggest new search phrases.
4. **Explores new ideas.** You can search any angle outside the niche ("gift for dad",
   "retirement gift") for inspiration.
5. **Keeps a swipe file and AI breakdowns.** Save ads and get the hook, angle, format, offer and
   awareness level of each.
6. **Writes remix briefs.** Claude writes a Day Archive version of a saved ad: hooks, headlines,
   primary text, and image and video prompts. A hand-off message lets you generate the creative
   in Higgsfield. You then upload it to Meta yourself.

## Pages
| Page | What it's for |
|---|---|
| 📊 Overview | KPIs, a brand scoreboard, top winners and ads launched this week |
| 🔥 Ad Feed & Winners | Every ad, filterable by brand, status, format, angle and days running |
| 🏷️ Tracked Brands | Add, remove or refresh brands. Types: competitor, inspiration or own |
| 🔭 Discover | Find new competitors automatically, plus the idea explorer |
| ⭐ Swipe File | Saved ads, AI breakdowns and the "Create remix brief" button |
| 🎬 Remix Studio | Briefs, the Higgsfield hand-off, generated creative links and the upload pack |
| ⚙️ Settings | Connections and the brand profile Claude uses for everything |

## Setup (about 15 minutes)

### 1. Apify (scraping)
1. Sign up at apify.com.
2. Go to Settings → Integrations and copy your API token.
3. Cost is about $0.75 per 1,000 ads. Ten brands at 50 ads a day plus weekly discovery comes to
   roughly $5–10 a month.

### 2. Supabase (database, free tier)
1. Create a new project at supabase.com and save the database password.
2. Click **Connect** (top bar) and copy the **Session pooler** URI. Put your password in it.
3. You don't need to create any tables. The app creates them on first run.

### 3. Claude API (AI features)
Create a key at platform.claude.com → API keys. Each ad breakdown or remix brief costs a few cents.

### 4. Deploy on Streamlit Community Cloud
1. Go to share.streamlit.io → **Create app** and pick this repo, branch `main`, file `app.py`.
2. Under **Advanced settings → Secrets**, paste the contents of
   `.streamlit/secrets.toml.example` with your real values filled in.
3. Deploy. On first load, the app seeds your 4 competitors and The Day Archive's own page.
4. Go to **🏷️ Tracked Brands** and click **Refresh all active brands**.

### 5. Daily auto-refresh (GitHub Actions)
1. In the repo, go to Settings → Secrets and variables → Actions → **New repository secret**.
2. Add `APIFY_TOKEN` and `DATABASE_URL` (the same values as above).
3. The workflow in `.github/workflows/daily-refresh.yml` runs every morning (AU time). It also
   runs discovery on Mondays.
4. To run it by hand, go to Actions → Daily ad refresh → Run workflow.

## The creative loop
1. Start in 🔥 Feed and filter to **🏆 Proven winner**. Click ☆ **Save** on the ones you like.
2. In ⭐ Swipe File, optionally click **🧠 Break it down**. Add some direction (for example "60th
   birthday for dad, UGC style") and click **🎬 Create remix brief**.
3. In 🎬 Remix Studio, copy the **Higgsfield hand-off** into a Claude chat that has the
   Higgsfield connector. Claude generates the creative there.
4. Paste the creative links back into the brief and set its status to **ready**.
5. Download the **upload pack** and upload it in Ads Manager.

Rule of thumb: borrow the *angle and structure*, never another brand's footage, logo, reviews
or claims. The remix prompt enforces this.

## Local development
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # fill in
streamlit run app.py
python -m pytest -q
```
If `DATABASE_URL` isn't set, the app uses a local SQLite file (`ad_intel.db`).
