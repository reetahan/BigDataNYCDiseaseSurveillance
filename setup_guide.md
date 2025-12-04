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

# Kafka Server Setup Guide (Using Docker)

This guide explains how to set up an Apache Kafka server using a provided Dockerfile for a GitHub project. It includes prerequisites, installation steps, environment configuration, and commands to run and test your Kafka environment.

---

## 🚧 Prerequisites

Before proceeding, ensure you have the following installed:

* **Docker** (latest version recommended)
* **Docker Compose** (if using a `docker-compose.yml` file)
* **Git** (to clone the repository)
* Basic understanding of containers and Kafka workflows

---

## 📂 Step 1: Clone the Repository

Clone the GitHub repository that contains your Kafka Dockerfile.

```sh
git clone <your-github-repo-url>
cd <your-repo-folder>
```

Ensure that the directory contains either:

* A **Dockerfile**, or
* A **docker-compose.yml** file

---

## ▶️ Step 2: Run Kafka Using Docker

### **Option A: Using Docker Compose (Recommended)**

If your repository contains a `docker-compose.yml` file:

```sh
docker compose up -d
```

To monitor logs:

```sh
docker compose logs -f
```

To stop services:

```sh
docker compose down
```

---

## 🛠 Step 3: Configure Kafka (If Needed)

Typical Kafka environment variables include:

* `KAFKA_BROKER_ID`
* `KAFKA_ZOOKEEPER_CONNECT`
* `KAFKA_ADVERTISED_LISTENERS`
* `KAFKA_LISTENERS`

You may modify these in:

* `.env` (if included)
* Dockerfile
* `docker-compose.yml`
* Kafka config files inside the container

You have an option to configure kafka using UI

Example snippet from Compose:

```yaml
  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    container_name: kafka-ui
    ports:
      - "8090:8080"
```
which can be reached at - http://localhost:{your_given_port}
---

## 📡 Step 4: Test Kafka

### Create a topic:

```sh
docker exec -it kafka kafka-topics.sh --create \
  --topic test-topic --bootstrap-server localhost:9092 \
  --partitions 1 --replication-factor 1
```

### List topics:

```sh
docker exec -it kafka kafka-topics.sh --list --bootstrap-server localhost:9092
```

### Start a producer:

```sh
docker exec -it kafka kafka-console-producer.sh --topic test-topic --bootstrap-server localhost:9092
```

### Start a consumer:

```sh
docker exec -it kafka kafka-console-consumer.sh --topic test-topic --from-beginning --bootstrap-server localhost:9092
```

---

## 🧹 Step 5: Stop and Cleanup

Stop the Kafka container:

```sh
docker stop kafka
```

Remove the container:

```sh
docker rm kafka
```

Remove the image:

```sh
docker rmi my-kafka-server
```

---

## ❗ Note on GitHub & Docker

If using GitHub Actions or automation:

* Ensure your Dockerfile is optimized
* Use `.dockerignore` to reduce build size
* Keep secrets out of the repository

---

## ✔️ You’re Done!

Your Kafka server should now be running successfully using Docker. You can now integrate it with your applications, producers, consumers, or streaming systems.

If you need help customizing the Dockerfile or docker-compose setup, feel free to ask!

