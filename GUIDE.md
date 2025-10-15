# HTA Server Setup Guide

This guide will walk you through setting up the HTA Server.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

### 1. Python 3.12+
- **Download:** [https://www.python.org/downloads/](https://www.python.org/downloads/)
- **Verify installation:**
  ```bash
  python3 --version
  ```

### 2. Redis
Redis is required for Celery task queue management.

**Installation on Ubuntu:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**Verify Redis is running:**
```bash
redis-cli ping
 
```
 should return: PONG

### 3. PostgreSQL
PostgreSQL is the database system used by HTA Server.

**Installation on Ubuntu:**
```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Verify PostgreSQL is running:**
```bash
sudo systemctl status postgresql
```

---

## Database Setup

### 1. Create PostgreSQL Database and User

Access the PostgreSQL shell:
```bash
sudo -u postgres psql
```

Create the database and user:
```sql
CREATE DATABASE bptap;
** - done
\q
```

### 2. Configure Database Connection

Create a `.env` file in the project root directory with your database credentials:

```properties
# Database Configuration
DB_NAME=hta_db
DB_USER=postgres
DB_PASSWORD=""
DB_HOST=127.0.0.0.1
DB_PORT=5432

# Django Secret Key (generate a new one for production)
SECRET_KEY=  

# Debug Mode (set to False in production)
DEBUG=True

# Allowed Hosts (comma-separated,) # we will add the domain here
ALLOWED_HOSTS=127.0.0.0.1,127.0.0.1
```


**Note:**  I'll share env separately

---

## Setup Process

### 1. Clone the Repository
```bash
git clone https://github.com/Antoney20/hta-server.git
cd hta-server
ls


or find the zip file
unzip  >>> navigate to hta-server
ls


```

### 2. Make Setup Script Executable
```bash
chmod +x setup.sh
```

### 3. Run the Setup Script
```bash
./setup.sh
```

The setup script will automatically:
- ✓ Check Python installation and version
- ✓ Check pip installation
- ✓ Check Redis installation and status
- ✓ Create a virtual environment
- ✓ Install all required Python packages
- ✓ Create necessary directories for media files
- ✓ Run database migrations (users app first, then all apps)
- ✓ Collect static files
- ✓ Prompt you to create a superuser account

### 4. Create Superuser (Admin Account)

When prompted by the setup script, create your admin account: (Required)
```bash
Username: admin
Email address: admin@bptap.com
Password: ********
Password (again): ********
```
then share the password.

---

## Running the Application

### Start the Development Server

1. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Ensure Redis is running:**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

3. **Start the Django development server:**
   ```bash
   python manage.py runserver
   ```

4. **Start Celery worker (in a new terminal):**
   ```bash
   source venv/bin/activate
   celery -A hta worker -l info
   ```

### Access the Application

- **Main Application:** [http://127.0.0.0.1:8000](http://127.0.0.0.1:8000)
- **Admin Panel:** [http://127.0.0.0.1:8000/admin](http://127.0.0.0.1:8000/admin)

---

## Troubleshooting

### Redis Connection Error
If you encounter Redis connection errors:
```bash
# Check if Redis is running
redis-cli ping

# Start Redis if not running
sudo systemctl start redis-server

# Check Redis status
sudo systemctl status redis-server
```

### Database Connection Error
If you encounter database connection errors:
- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Check your `.env` file credentials match your database setup
- Ensure the database exists: `psql -U postgres -l`





## Next Steps

After successful setup:

1. **Access the admin panel** at [http://127.0.0.0.1:8000/admin](http://127.0.0.0.1:8000/admin)
2. **Configure your application settings** through the admin interface
3. **Create additional user accounts** as needed
4. **Review the API documentation** (if available)

---

## Production Deployment

For production deployment, remember to:

- Set `DEBUG=False` in your `.env` file
- Use a strong, unique `SECRET_KEY`
- Configure `ALLOWED_HOSTS` with your domain
- Use a production-grade web server (e.g., Gunicorn, uWSGI)
- Set up a reverse proxy (e.g., Nginx)
- Configure SSL/TLS certificates
- Use environment variables for sensitive data
- Set up automated backups for your database

---
