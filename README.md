# BPTAP Server

Backend service for the [Benefits Package and Tariffs Advisory Panel (BPTAP)](https://bptap.health.go.ke) — digitizing Kenya's Health Technology Assessment (HTA) process, developed by [CEMA](https://cema-africa.uonbi.ac.ke) in collaboration with the Ministry of Health (MoH).

---

## Tech Stack

- **Framework:** Django + DRF
- **Realtime:** Django Channels + Redis
- **Auth:** JWT
- **Server:** Daphne + Gunicorn
- **Containerization:** Docker

---

## Local Setup

**Prerequisites:** Python 3.12+, Redis

```bash
# Clone and enter the repo
git clone https://github.com/Antoney20/hta-server.git
cd hta-server

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.local .env

# Run migrations
python manage.py migrate

# Start the development server
python manage.py runserver
```

Or with Docker:

```bash
docker compose up --build
```

---

## Project Structure

```
app/        # Core application logic
hta/        # HTA process modules 
members/    # Member management
users/      # Authentication and user accounts
templates/  # Email templates
```

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). For security issues, see [SECURITY.md](./SECURITY.md) — do not open public issues for vulnerabilities.

---

## License

Source-available. See [LICENSE.md](./LICENSE.md) for terms.  
© 2026 Center for Epidemiological Modelling and Analysis (CEMA), University of Nairobi.