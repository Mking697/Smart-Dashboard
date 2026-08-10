# 🌍 Deployment Strategy

This is a Python/Streamlit app, so it cannot run on standard Node.js or shared PHP
hosting (basic Hostinger plans included). It needs a Python runtime that can keep a
long-running process alive.

---

## Before You Deploy — checklist

- [ ] `.env` is **not** committed (it is in `.gitignore` — keep it that way).
- [ ] `GEMINI_API_KEY` is set as a platform secret, not in the code.
- [ ] `assets/india_districts.geojson` (4 MB) is committed — the India maps need it.
- [ ] `requirements.txt` is current.
- [ ] Service account JSON, if used, goes in secrets — never in the repo.

---

## Option 1 — Streamlit Community Cloud (free, best for MVP)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo.
3. Main file: `app.py`.
4. In **Settings → Secrets**, add:

```toml
GEMINI_API_KEY = "your_key_here"

# Only if you use private Google Sheets:
[gcp_service_account]
type = "service_account"
project_id = "your-project"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "dashboard@your-project.iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
```

The app reads `st.secrets["gcp_service_account"]` automatically, so no upload is
needed once this is set.

> Note: the free tier sleeps when idle and has ~1 GB RAM. Fine for this app; watch
> memory if users upload very large workbooks.

---

## Option 2 — Render.com (free tier)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
- Add `GEMINI_API_KEY` under **Environment**.

The free instance spins down when idle; the first request after that is slow.

---

## Option 3 — VPS (Hostinger VPS, AWS EC2, DigitalOcean)

Best option once scheduled email reports land, because a VPS can run the background
scheduler alongside the web app.

```bash
git clone https://github.com/Mking697/Smart-Dashboard.git
cd Smart-Dashboard
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
printf 'GEMINI_API_KEY=your_key_here\n' > .env
```

Keep it alive with systemd (`/etc/systemd/system/dashboard.service`):

```ini
[Unit]
Description=AI Smart Dashboard
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Smart-Dashboard
ExecStart=/home/ubuntu/Smart-Dashboard/venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now dashboard
```

Then put Nginx in front for a custom domain and HTTPS:

```nginx
server {
    listen 80;
    server_name dashboard.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # required for Streamlit websockets
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

Finish with `sudo certbot --nginx -d dashboard.yourdomain.com`.

The websocket headers are not optional — without them the app loads but never
finishes connecting.

---

## Option 4 — Docker (any host)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

```bash
docker build -t smart-dashboard .
docker run -p 8501:8501 -e GEMINI_API_KEY=your_key_here smart-dashboard
```

---

## Coming Soon — scheduled email reports

Streamlit only runs code while a browser session is open, so a scheduler cannot live
inside `app.py`. Plan: a separate `scheduler.py` process (APScheduler) that re-fetches
the Google Sheet, regenerates the PDF and sends it over SMTP.

- **VPS:** a second systemd service running `python scheduler.py`.
- **Docker:** a second container, or supervisord running both processes.
- **Streamlit Cloud / Render free tier:** not supported — they only host the web
  process. Use a VPS or an external cron trigger for this feature.
