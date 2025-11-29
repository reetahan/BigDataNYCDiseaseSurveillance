# Reddit Scraper Setup Guide

This guide explains how to configure and run your Reddit scraper, including signing up for Reddit API credentials.

## 1. Prerequisites

* Python 3.8+
* `praw` or required Reddit API library installed
* Basic command-line knowledge

## 2. Install Dependencies

```bash
pip install praw
```

## 3. Register for Reddit API Credentials

> **Note:** Reddit recently restricted API access for newly created accounts. New users may experience delays or limited ability to register API apps until their account has built sufficient activity or age.
> To access Reddit programmatically, you must create an API application.

### Steps:

1. Go to **[https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)** (you must be logged in).
2. Scroll to the bottom and click **Create App** or **Create Another App**.
3. Fill out the form:

   * **Name:** Choose any project name.
   * **App Type:** Select **script**.
   * **Description:** (Optional) short description.
   * **Redirect URI:** Use `http://localhost:8080` (any valid URI works, not actually used for scripts).
4. Click **Create App**.

### After creation, you will see:

* **client_id** (string under the app name)
* **client_secret** (hidden unless you click **edit**)

Save these values—they are required for authentication.

## 4. Configure Environment Variables

Create a `.env` file in your project directory:

```
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=reddit_scraper/0.1 by your_username
```

Or export them directly:

```bash
export REDDIT_CLIENT_ID=your_client_id_here
export REDDIT_CLIENT_SECRET=your_client_secret_here
export REDDIT_USER_AGENT="reddit_scraper/0.1 by your_username"
```

## 5. Running the Scraper

Use your existing script, for example:

```bash
python redditscraper.py
```


## 7. Troubleshooting

* **401 Unauthorized:** Check your credentials and environment variables.
* **Invalid user agent:** Make sure your user agent is a short descriptive string.
* **Rate limits:** Reddit enforces API limits; add delays where necessary.

---

Your Reddit scraper is now ready to run!
