# 🌍 Deployment Strategy

> **Currently deployed:** https://autolyst.online — AWS EC2 `t3.micro`, Ubuntu 24.04,
> `ap-south-1`, instance `i-0de3279fe8e742bcc`, Elastic IP `3.7.191.122`.
> Option 0 below is the path that was actually taken.
>
> **To ship a change:**
> ```bash
> ssh -i your-key.pem ubuntu@3.7.191.122
> cd ~/Smart-Dashboard && git pull && sudo systemctl restart dashboard
> ```
> Then hard-refresh the browser (`Ctrl+Shift+R`) — CSS is cached.

This is a Python/Streamlit app, so it cannot run on standard Node.js or shared PHP
hosting (basic Hostinger plans included). It needs a Python runtime that can keep a
long-running process alive.

---

## Before You Deploy — checklist

- [ ] `.env` is **not** committed (it is in `.gitignore` — keep it that way).
- [ ] `GEMINI_API_KEY` is set as a platform secret, not in the code.
- [ ] `BREVO_API_KEY` and `BREVO_SENDER_EMAIL` are set, and the sender address is
      **verified in Brevo** — unverified senders are rejected and nobody can sign up.
- [ ] `data/` is **not** committed — it holds real user emails and password hashes.
- [ ] `assets/india_districts.geojson` (4 MB) is committed — the India maps need it.
- [ ] `requirements.txt` is current.
- [ ] Service account JSON, if used, goes in secrets — never in the repo.

---

## Where this app can and cannot run

It is Python, and Streamlit keeps a websocket open for the life of a session. So it
needs a host that gives you a Python runtime and lets a process stay alive.

| Host | Works? | Why |
|---|---|---|
| AWS EC2 / Lightsail | ✅ | Full control, background jobs possible |
| Streamlit Community Cloud | ✅ | Purpose-built, free |
| Render / Railway | ✅ | Python + long-running process supported |
| Hostinger **VPS** | ✅ | Root access, so Python can be installed |
| Hostinger **Web / Business / Cloud** | ❌ | Node.js only. Hostinger's own docs: *"Python is supported exclusively on VPS Hosting"* — Web and Cloud plans have no root access |
| Any shared/PHP hosting | ❌ | No persistent process |

---

## Option 0 — AWS EC2 on the instance's own hostname (no domain needed)

Every EC2 instance gets a free public DNS name the moment it boots:

```
http://ec2-13-234-56-78.ap-south-1.compute.amazonaws.com
```

That **is** your temporary domain. Nothing to buy, nothing to configure.

### Cost, honestly

AWS changed the free tier on **15 July 2025**, so which deal you get depends on when
your account was opened:

| Account created | What you get |
|---|---|
| Before 15 Jul 2025 | Classic free tier — 750 hrs/month of `t2.micro`/`t3.micro` free for 12 months |
| After 15 Jul 2025 | $100 credits (+$100 for onboarding tasks). EC2 draws **from the credits** — there is no separate free 750 hours |

Check your Billing console before assuming it is free. A `t3.small` running full time
is roughly $15–20/month in `ap-south-1`; `t3.micro` about half that.

### Already running something else on EC2?

Give the dashboard **its own instance**. Two reasons, and the second one is not
negotiable:

1. This setup claims port 80 and replaces Nginx's enabled sites. On an instance
   that already serves a project, that takes the other project offline. The setup
   script refuses to run if it finds other Nginx sites, but a separate instance
   removes the risk entirely.
2. A `t3.micro` has 1 GB of RAM. Streamlit with pandas, Plotly and the bundled
   India boundaries needs a few hundred MB on its own. Sharing that instance with
   another live app will push both into swap, and the existing project gets slower
   the moment someone opens a large spreadsheet.

Also **create a new Security Group** rather than reusing the existing project's —
editing a shared group later would change the firewall for both.

### Launch the instance

1. EC2 → **Launch instance**
2. **AMI:** Ubuntu Server 24.04 LTS
3. **Type:** `t3.small` (2 GB RAM) recommended. `t3.micro` (1 GB) works — the setup
   script adds swap so pandas can still install and run.
4. **Key pair:** create one and download the `.pem`
5. **Network settings → Edit**, allow inbound:
   - **SSH (22)** from *My IP*
   - **HTTP (80)** from *Anywhere (0.0.0.0/0)*
6. **Storage:** 16–20 GB
7. Launch, then copy the **Public IPv4 DNS** from the instance page

> Assign an **Elastic IP** if you plan to stop/start the instance — otherwise the
> public DNS name changes every time it restarts. It is free while attached to a
> running instance.

### Set it up (one command)

SSH in:

```bash
ssh -i your-key.pem ubuntu@ec2-XX-XX-XX-XX.ap-south-1.compute.amazonaws.com
```

Then run:

```bash
curl -fsSL https://raw.githubusercontent.com/Mking697/Smart-Dashboard/main/deploy/aws-setup.sh | bash
```

The script installs Python and Nginx, adds 2 GB of swap, clones the repo, builds the
virtualenv, registers a systemd service that survives reboots and crashes, and puts
Nginx in front on port 80 with the websocket headers Streamlit needs.

### Add your API key

```bash
nano ~/Smart-Dashboard/.env          # GEMINI_API_KEY=your_real_key
sudo systemctl restart dashboard
```

### PDF export needs a browser on the server

Kaleido renders charts by driving Chrome rather than shipping one. A desktop
already has Chrome; a fresh Ubuntu server does not, and Chrome needs shared
libraries a minimal image leaves out. Run this once:

```bash
~/Smart-Dashboard/deploy/install-pdf.sh
sudo systemctl restart dashboard
```

It installs the libraries, downloads Chrome, and proves it works by rendering a
test PNG. Until it has run, exporting shows a message saying exactly this rather
than a browser stack trace.

> Chrome wants a few hundred MB of RAM. On the 1 GB `t3.micro`, export **one
> report** first and watch `sudo journalctl -u dashboard -f`. If the service is
> OOM-killed during an all-reports export, either export one at a time or move
> the instance up to `t3.small`.

### Back up the user accounts

Accounts live in one SQLite file. Losing it means every user has to sign up again,
so copy it somewhere off the instance on a schedule:

```bash
# on the server
sqlite3 ~/Smart-Dashboard/data/users.db ".backup /tmp/users-backup.db"

# from your own machine
scp -i your-key.pem ubuntu@<your-ip>:/tmp/users-backup.db .
```

`git pull` never touches it — `data/` is gitignored.

### Day-to-day

```bash
sudo systemctl status dashboard      # is it running?
sudo journalctl -u dashboard -f      # live logs
cd ~/Smart-Dashboard && git pull && sudo systemctl restart dashboard   # deploy an update
```

### When a deploy looks like it did nothing

Almost always the browser cache. Hard-refresh with `Ctrl+Shift+R`. If it still
looks stale, confirm what the server is actually running:

```bash
cd ~/Smart-Dashboard && git log --oneline -1
```

Compare that against the latest commit on GitHub. A `git pull` that reports
"Already up to date" while the page looks old means the cache, not the code.

### The one real limitation

The URL will be **`http://`, not `https://`**. Let's Encrypt will not issue a
certificate for an `amazonaws.com` hostname you do not own, so browsers show
"Not secure". That is fine for testing and internal demos.

For HTTPS you need either your own domain (point it at the Elastic IP, then
`sudo certbot --nginx`), or **AWS App Runner**, which serves an
`xxx.awsapprunner.com` URL over HTTPS out of the box — but has no meaningful free
tier, so expect roughly $5–25/month.

---

## Option 1 — Streamlit Community Cloud (free, best for MVP)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo.
3. Main file: `app.py`.
4. In **Settings → Secrets**, add:

```toml
GEMINI_API_KEY = "your_key_here"
BREVO_API_KEY = "your_brevo_key"
BREVO_SENDER_EMAIL = "noreply@yourdomain.com"
BREVO_SENDER_NAME = "AI Smart Dashboard"

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
