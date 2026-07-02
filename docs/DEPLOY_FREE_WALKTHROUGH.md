# Free Deployment Walkthrough — $0, no purchase

End state: your platform live at `https://<you>.duckdns.org` with auto-HTTPS, the
full stack (TimescaleDB + Redis + API + worker + web + Caddy) on a free,
always-free cloud VM. **Total cost: $0** (a card is required only for Oracle's
identity check — Always-Free resources never bill).

Legend: 🧑 = only you can do it (account/identity)  ·  🤖 = I can do it once you bridge access.

---

## Part 1 — 🧑 Oracle Cloud account + free VM (~15 min)

### 1.1 Sign up
1. Go to **https://signup.oracle.com**.
2. Enter email + country, verify the email, set a password.
3. Add a **credit/debit card** — this is identity verification only. Always-Free
   never charges; you may see a temporary ~$1 authorization that drops off.
4. **Home Region** — pick one close to you. ⚠️ This is **permanent**. ARM free
   capacity is scarce in busy regions; if you're in India, try **Hyderabad**
   (often more available than Mumbai). (See Troubleshooting if ARM is "out of capacity".)

### 1.2 Create an SSH key on your PC (so you can log into the VM)
In PowerShell or Git Bash on your machine:
```bash
ssh-keygen -t ed25519 -f $HOME/.ssh/oracle -N ""
cat $HOME/.ssh/oracle.pub      # copy this whole line
```

### 1.3 Launch the VM
1. Console menu (☰) → **Compute → Instances → Create instance**.
2. **Name:** `trading`.
3. **Image & shape → Edit:**
   - Image: **Canonical Ubuntu 22.04** (or 24.04).
   - Shape: **Ampere → VM.Standard.A1.Flex**, set **2 OCPU / 12 GB** (well within
     the free 4 OCPU / 24 GB). *(If ARM is unavailable, pick
     **VM.Standard.E2.1.Micro** — AMD, Always-Free, 1 GB — and see Troubleshooting → swap.)*
4. **Networking:** leave defaults (it creates a VCN + assigns a public IPv4).
5. **Add SSH keys → Paste public keys** → paste the `oracle.pub` line from 1.2.
6. **Create.** When it's "Running", copy the **Public IP address**.

### 1.4 Open ports 80 + 443 (two firewalls — both matter)
**Cloud firewall (VCN Security List):**
1. Instance page → **Virtual cloud network** link → **Security Lists** → the default list.
2. **Add Ingress Rules** (twice): Source `0.0.0.0/0`, IP Protocol **TCP**, Destination Port `80`; then again for `443`.

**Host firewall** (Oracle's Ubuntu images block everything but SSH) — do this after you SSH in (Part 1.5):
```bash
sudo iptables -I INPUT 6 -p tcp -m state --state NEW --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -p tcp -m state --state NEW --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

### 1.5 Log in
```bash
ssh -i $HOME/.ssh/oracle ubuntu@<PUBLIC_IP>
```

---

## Part 2 — 🧑 Free domain (DuckDNS, ~2 min)

1. Go to **https://www.duckdns.org**, sign in (GitHub/Google).
2. Type a subdomain (e.g. `mubintrade`) → **add domain**. You now own
   `mubintrade.duckdns.org`.
3. In the "current ip" box for that domain, paste your VM's **Public IP** → **update ip**.
4. Verify it resolves (from your PC): `nslookup mubintrade.duckdns.org` → should show the VM IP.

> Do this **before** deploying — Caddy needs the domain pointing at the VM to get
> the HTTPS certificate.

(Alternative: **Cloudflare Tunnel** if you can't open ports / are behind NAT — more
setup; DuckDNS is simpler and recommended here.)

---

## Part 3 — 🤖 Install Docker (on the VM)
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit            # log out so the docker group applies
```
…then SSH back in (`ssh -i ~/.ssh/oracle ubuntu@<IP>`). Compose v2 ships with Docker.

---

## Part 4 — 🤖 Get the code (private repo → deploy key)
On the VM, make a read-only deploy key and add it to GitHub:
```bash
ssh-keygen -t ed25519 -f $HOME/.ssh/gh_deploy -N ""
cat $HOME/.ssh/gh_deploy.pub      # copy this
```
🧑 In the browser: GitHub repo → **Settings → Deploy keys → Add deploy key** →
paste it, title `oracle-vm`, leave "Allow write access" **unchecked** → Add.

Back on the VM:
```bash
echo "Host github.com
  IdentityFile ~/.ssh/gh_deploy
  StrictHostKeyChecking accept-new" >> ~/.ssh/config

git clone git@github.com:mubin-attar-007/tradepulse.git
cd tradepulse
```

---

## Part 5 — 🤖 Configure secrets (`infra/.env.prod`)
```bash
cp infra/.env.prod.example infra/.env.prod
APP_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
CRED_KEY=$(python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
PG_PW=$(python3 -c "import secrets;print(secrets.token_hex(24))")
sed -i "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$APP_SECRET|" infra/.env.prod
sed -i "s|^BROKER_CRED_KEY=.*|BROKER_CRED_KEY=$CRED_KEY|" infra/.env.prod
sed -i "s|CHANGE_ME|$PG_PW|g" infra/.env.prod
nano infra/.env.prod
```
In `nano`, set these three (then Ctrl+O, Enter, Ctrl+X):
```
DOMAIN=mubintrade.duckdns.org
CORS_ALLOW_ORIGINS=https://mubintrade.duckdns.org
GEMINI_API_KEY=<your FRESH Gemini key>     # rotate the one shared in chat
```
Leave `LIVE_TRADING_ENABLED=false`.

---

## Part 6 — 🤖 Deploy
```bash
bash infra/deploy.sh
```
This builds the images, runs DB migrations, and starts everything behind Caddy
(which fetches the HTTPS cert automatically). First build takes a few minutes.

Then seed the universe + pull real bars:
```bash
C="docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod"
$C run --rm api python -m app.cli.seed
$C run --rm api python -m app.cli.backfill BTC/USD --days 2
$C run --rm api python -m app.cli.backfill ETH/USD --days 2
```

---

## Part 7 — 🤖 Verify
```bash
curl -s https://mubintrade.duckdns.org/api/health    # -> {"status":"ok"}
curl -s https://mubintrade.duckdns.org/api/ready      # -> db + redis healthy
```
Open **https://mubintrade.duckdns.org** in your browser → register an account → dashboard.

---

## Part 8 — Updates, rollback, logs
```bash
cd ~/tradepulse
git pull && bash infra/deploy.sh         # deploy the latest main
docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod logs -f --tail=100
git checkout <old-sha> && bash infra/deploy.sh   # roll back
```

---

## Troubleshooting
- **ARM "Out of host capacity":** common. Retry the Create over a day or two (it
  frees up), or use the **E2.1.Micro** (AMD) shape now and switch to ARM later.
- **1 GB RAM box (E2.1.Micro):** add swap before building, or the Next.js build OOMs:
  ```bash
  sudo fallocate -l 3G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile \
    && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```
- **Site won't load / no cert:** confirm DuckDNS points at the VM IP, and BOTH
  firewalls (VCN Security List **and** host iptables) allow 80 + 443. Check
  `docker compose ... logs caddy`.
- **`git clone` Permission denied:** the deploy key wasn't added, or the `~/.ssh/config`
  block is missing. Re-check Part 4.

---

## GCP alternative (always-free, but only 1 GB RAM)
1. 🧑 **https://console.cloud.google.com** → new project → **Compute Engine → Create instance**.
2. Machine type **e2-micro**, region **us-west1 / us-central1 / us-east1** (the
   always-free regions), boot disk **Ubuntu 22.04**, and tick **Allow HTTP** +
   **Allow HTTPS traffic** (this creates the firewall rules — no iptables needed).
3. SSH in from the console (or add your key), then follow **Parts 3–7** unchanged.
   Add **swap** (Troubleshooting) first — e2-micro is 1 GB.

---

## Make it hands-off for me
Add this to your PC's `~/.ssh/config`:
```
Host trading
  HostName <VM_PUBLIC_IP>
  User ubuntu
  IdentityFile ~/.ssh/oracle
```
Then `ssh trading` works, and you can ask me to run the Part 3–7 commands via
`ssh trading "..."` from this session — I'll drive the whole deploy and report back.
(You still create the VM + domain in Parts 1–2; those are the only steps that are
fundamentally yours.)
