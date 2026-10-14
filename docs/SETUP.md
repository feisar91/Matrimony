# Wedding App - Setup Guide

A generic, reusable Flask-based wedding website with admin control panel, RSVP tracking, photo challenges, and live streaming.

## Features

- ✅ **Admin Control Panel** - Configure all wedding details via web UI (no config file editing)
- ✅ **Dynamic Configuration** - Change names, dates, colors, venues anytime without redeploying
- ✅ **RSVP System** - Guest registration with email notifications
- ✅ **Photo Challenges** - Guests upload photos based on assigned challenges
- ✅ **Photo Gallery** - Display all submitted photos
- ✅ **Live Stream Integration** - Embed Twitch stream
- ✅ **Theme Customization** - Admin-controlled color scheme
- ✅ **Site Password Protection** - Optional password gate for guest-facing pages
- ✅ **Database-Backed** - All config stored in MySQL/MariaDB (not hardcoded)

## Quick Start

### Prerequisites

- Python 3.13+
- MySQL 8.0+ or MariaDB 10.5+
- pip (Python package manager)

### Step 1: Clone the Repository

```bash
cd /opt
git clone https://github.com/feisar91/Matrimony wedding_app
cd wedding_app
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Set Up Configuration

Copy the example configuration file and edit it with your database credentials:

```bash
cp config.example.yml config.yml
# Edit config.yml with your database host, user, password, etc.
nano config.yml
```

**Key config.yml sections:**
```yaml
database:
  host: localhost
  port: 3306
  name: wedding_db
  user: wedding_user
  password: your_secure_password

mail:
  # Gmail SMTP settings
  server: smtp.gmail.com
  port: 465
  username: your-email@gmail.com
  password: your-app-password  # Use Gmail app password if 2FA enabled

flask:
  secret_key: generate-a-random-key-here  # flask.Digester().generate()
```

### Step 4: Initialize Database

Run the setup script to create the database and tables:

```bash
python setup_database.py
# Prompts for MySQL root password
# Creates: database, user, all tables
```

### Step 5: Start the App

```bash
python app.py
# Listens on http://localhost:5000
```

### Step 6: Create Admin Account

1. Visit http://localhost:5000/admin/setup
2. Follow the 2-step setup wizard:
   - **Step 1:** Create admin account (email + password)
   - **Step 2:** Enter wedding details (names, dates, venues, colors)
3. Click "Complete Setup"

### Step 7: Admin Login

- Visit http://localhost:5000/admin/login
- Login with the email/password you created
- Access the admin dashboard

## Admin Panel Features

### Dashboard (`/admin`)
- Statistics (total RSVPs, confirmations, photos, challenges)
- Quick links to all admin sections

### Wedding Settings (`/admin/wedding`)
- **Couple info:** Bride name, groom name
- **Wedding dates:** Date, time, year
- **Venues:** Main venue, ceremony location, reception location, after-party location
- **Theme colors:** Primary, accent, gold colors (HTML5 color picker)
- **Site settings:** Site title, domain, Twitch channel
- **Site protection:** Optional password gate for guest pages

### Challenges (`/admin/challenges`)
- Create new photo challenges
- Delete existing challenges
- Challenges are assigned randomly to guests

### RSVP Management (`/admin/rsvp`)
- View all guest registrations
- See confirmation status
- Stats: total, confirmed, pending

### Photo Gallery (`/admin/gallery`)
- View all submitted challenge photos
- See which guest submitted each photo
- Which challenge was fulfilled

## Guest-Facing Website

### Public Pages
- **Home** (`/`) - Hero section with couple names and wedding date
- **Details** (`/details`) - Ceremony, reception, after-party details
- **Live Stream** (`/stream`) - Embedded Twitch stream
- **Photo Challenge** (`/photo-challenge`) - See assigned challenge, upload photo
- **Gallery** (`/gallery`) - View all submitted photos
- **Save the Date** (`/rsvp`) - Guest registration form

### Features
- Time-locked content (unlocks on wedding day)
- Auto-countdown timer
- Responsive mobile design
- Optional site-wide password protection

## Migration from Old Config

If you have an existing wedding site with hardcoded config, migrate to the database:

```bash
python migrate_from_yml.py
# Copies all settings from config.yml to database
# Prompts to confirm if data already exists
```

## Deployment

### Development
```bash
python app.py  # debug=True, auto-reload enabled
```

### Production (using Gunicorn)
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
# 4 worker processes
# Listens on port 8000
# Use reverse proxy (nginx) in front
```

### Environment Variables (Production)
Instead of config.yml, use environment variables:

```bash
export FLASK_SECRET_KEY="your-secret-key"
export DATABASE_URL="mysql+pymysql://user:password@localhost/wedding_db"
export MAIL_SERVER="smtp.gmail.com"
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="your-app-password"
```

Then modify `app.py` to read from env vars (add this near top):
```python
import os
from dotenv import load_dotenv

load_dotenv()

app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'mysql+pymysql://wedding_user:password@localhost/wedding_db'
)
```

## File Structure

```
/opt/wedding_app/
├── app.py                      # Main Flask application
├── config.yml                  # Configuration file (gitignored)
├── config.example.yml          # Configuration template
├── requirements.txt            # Python dependencies
├── setup_database.py           # Initial database setup script
├── migrate_from_yml.py         # Migration: config.yml → database
├── static/
│   ├── css/style.css           # Styling + theme variables
│   ├── js/script.js            # Frontend interactions
│   └── uploads/photos/         # Guest-uploaded photos
└── templates/
    ├── base.html               # Master layout
    ├── home.html               # Homepage
    ├── details.html            # Wedding details
    ├── stream.html             # Live stream
    ├── photo_challenge.html    # Challenge assignment + upload
    ├── gallery.html            # Photo gallery
    ├── rsvp.html               # Guest registration
    ├── rsvp_confirm.html       # RSVP confirmation
    ├── site_login.html         # Site password protection
    └── admin/                  # Admin panel templates
        ├── base.html
        ├── setup.html
        ├── login.html
        ├── dashboard.html
        ├── wedding_settings.html
        ├── challenges.html
        ├── rsvp.html
        └── gallery.html
```

## Configuration Reference

### WeddingConfig Table Fields

| Field | Type | Example |
|-------|------|---------|
| bride | String | "Jane Smith" |
| groom | String | "John Smith" |
| wedding_date | String | "October 15, 2026" |
| venue | String | "The Grand Hotel" |
| city | String | "New York, NY" |
| ceremony_location | String | "Grand Ballroom, 2nd Floor" |
| ceremony_time | String | "4:00 PM" |
| reception_location | String | "Courtyard, Ground Floor" |
| reception_time | String | "5:00 PM" |
| after_party_location | String | "Bar & Lounge" |
| primary_color | String | "#2d5016" |
| accent_color | String | "#4a7c2c" |
| gold_accent | String | "#D4AF37" |
| site_title | String | "John & Jane 2026" |
| footer_domain | String | "johnandjane2026.com" |
| mail_contact_email | String | "contact@wedding.com" |
| twitch_enabled | Boolean | true |
| twitch_channel | String | "myweddingchannel" |
| site_password_protected | Boolean | false |
| site_password | String | "secret123" |

## Troubleshooting

### Database Connection Error
```
Error: (pymysql.err.OperationalError) (2003, "Can't connect to MySQL server")
```
**Solution:** Ensure MySQL/MariaDB is running:
```bash
sudo systemctl status mariadb  # Check if running
sudo systemctl start mariadb   # Start if stopped
```

### Email 535 Error
```
(smtplib.SMTPAuthenticationError) 535
```
**Solution:** Gmail requires app-specific passwords when 2FA is enabled:
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and "Windows Computer" (or other device)
3. Use the generated password in config.yml (not your regular password)

### Photos Not Uploading
**Solution:** Check file permissions on `static/uploads/photos/`:
```bash
chmod 755 static/uploads/photos/
# Ensure web server user can write to this directory
```

### Templates Not Using wedding_config
**Solution:** Verify `wedding_config` is being passed from Flask route:
```python
wed_cfg = get_wedding_config()
return render_template('page.html', wedding_config=wed_cfg)
```

## Development Notes

### Adding New Wedding Settings
1. Add column to `WeddingConfig` model in `app.py`
2. Add form field to `templates/admin/wedding_settings.html`
3. Add route handler logic in `/admin/wedding` POST handler
4. Use in templates via `{{ wedding_config.field_name }}`

### Time-Locked Features
The app automatically locks photo challenges and galleries until the wedding date. To test:
```python
# In app.py, temporarily change:
wedding_datetime = datetime(2020, 1, 1)  # Past date to unlock
# Or in admin: set wedding_date to today
```

### Email Templates
Email subject lines and body use variables from `WeddingConfig`:
```python
subject = f"From {config.groom} & {config.bride}"
```

## Support

For issues or questions:
1. Check this SETUP.md guide
2. Review app.py comments for code explanations
3. Check Flask/SQLAlchemy documentation
4. Review template files for UI logic

## License

MIT - See LICENSE file

---

**Ready to deploy?** You now have a fully configurable, database-driven wedding website! 🎉
